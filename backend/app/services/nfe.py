"""Leitura segura de XML de NF-e/NFC-e (modelos 55 e 65) e importação com classificação por CFOP.

Segurança: o XML é lido com defusedxml (bloqueia DTD, entidades externas/XXE e
"billion laughs"). Uploads ZIP são verificados quanto a quantidade e tamanho
descompactado (proteção contra zip bomb).
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Cliente, Duplicata, ItemNota, NotaFiscal
from . import cfop as cfop_svc
from .plano_contas import mapa_por_codigo

NS = {"n": "http://www.portalfiscal.inf.br/nfe"}


class ErroNFe(Exception):
    pass


@dataclass
class ItemLido:
    numero_item: int
    codigo: str | None
    descricao: str
    ncm: str | None
    cfop: str
    quantidade: Decimal
    valor_unitario: Decimal
    valor_total: Decimal


@dataclass
class NotaLida:
    chave: str
    modelo: str
    serie: str | None
    numero: str
    data_emissao: date
    tipo_operacao: str
    natureza_operacao: str | None
    emitente_documento: str
    emitente_nome: str
    destinatario_documento: str | None
    destinatario_nome: str | None
    totais: dict[str, Decimal]
    itens: list[ItemLido] = field(default_factory=list)
    duplicatas: list[tuple[str | None, date, Decimal]] = field(default_factory=list)
    status_autorizacao: str | None = None


def _txt(el, caminho: str) -> str | None:
    if el is None:
        return None
    achado = el.find(caminho, NS)
    if achado is None or achado.text is None:
        return None
    return achado.text.strip()


def _dec(v: str | None) -> Decimal:
    if not v:
        return Decimal("0")
    try:
        return Decimal(v)
    except InvalidOperation:
        raise ErroNFe(f"Valor numérico inválido no XML: {v!r}")


def _data(v: str | None) -> date:
    if not v:
        raise ErroNFe("Data de emissão ausente")
    try:
        return datetime.fromisoformat(v).date() if "T" in v else date.fromisoformat(v[:10])
    except ValueError:
        raise ErroNFe(f"Data de emissão inválida: {v}")


def ler_xml(conteudo: bytes) -> NotaLida:
    try:
        raiz = SafeET.fromstring(conteudo, forbid_dtd=True)
    except DefusedXmlException:
        raise ErroNFe("XML rejeitado por conter construções inseguras (DTD/entidades)")
    except SafeET.ParseError:
        raise ErroNFe("Arquivo não é um XML válido")

    inf = raiz.find(".//n:infNFe", NS)
    if inf is None:
        raise ErroNFe("XML não é uma NF-e (infNFe não encontrado)")
    chave = (inf.get("Id") or "").removeprefix("NFe")
    if len(chave) != 44 or not chave.isdigit():
        raise ErroNFe("Chave de acesso inválida")

    ide = inf.find("n:ide", NS)
    emit = inf.find("n:emit", NS)
    dest = inf.find("n:dest", NS)
    tot = inf.find("n:total/n:ICMSTot", NS)
    if ide is None or emit is None:
        raise ErroNFe("XML incompleto: grupos ide/emit ausentes")

    totais = {
        "valor_produtos": _dec(_txt(tot, "n:vProd")),
        "valor_desconto": _dec(_txt(tot, "n:vDesc")),
        "valor_frete": _dec(_txt(tot, "n:vFrete")),
        "valor_icms": _dec(_txt(tot, "n:vICMS")),
        "valor_icms_st": _dec(_txt(tot, "n:vST")),
        "valor_ipi": _dec(_txt(tot, "n:vIPI")),
        "valor_pis": _dec(_txt(tot, "n:vPIS")),
        "valor_cofins": _dec(_txt(tot, "n:vCOFINS")),
        "valor_total": _dec(_txt(tot, "n:vNF")),
    }

    nota = NotaLida(
        chave=chave,
        modelo=_txt(ide, "n:mod") or "55",
        serie=_txt(ide, "n:serie"),
        numero=_txt(ide, "n:nNF") or "",
        data_emissao=_data(_txt(ide, "n:dhEmi") or _txt(ide, "n:dEmi")),
        tipo_operacao="saida" if _txt(ide, "n:tpNF") == "1" else "entrada",
        natureza_operacao=_txt(ide, "n:natOp"),
        emitente_documento=_txt(emit, "n:CNPJ") or _txt(emit, "n:CPF") or "",
        emitente_nome=_txt(emit, "n:xNome") or "",
        destinatario_documento=(_txt(dest, "n:CNPJ") or _txt(dest, "n:CPF")) if dest is not None else None,
        destinatario_nome=_txt(dest, "n:xNome") if dest is not None else None,
        totais=totais,
        status_autorizacao=_txt(raiz, ".//n:protNFe/n:infProt/n:cStat"),
    )
    for det in inf.findall("n:det", NS):
        prod = det.find("n:prod", NS)
        cfop = _txt(prod, "n:CFOP")
        if not cfop or len(cfop) != 4:
            raise ErroNFe(f"Item {det.get('nItem')} sem CFOP válido")
        nota.itens.append(
            ItemLido(
                numero_item=int(det.get("nItem") or len(nota.itens) + 1),
                codigo=_txt(prod, "n:cProd"),
                descricao=(_txt(prod, "n:xProd") or "")[:300],
                ncm=_txt(prod, "n:NCM"),
                cfop=cfop,
                quantidade=_dec(_txt(prod, "n:qCom")),
                valor_unitario=_dec(_txt(prod, "n:vUnCom")),
                valor_total=_dec(_txt(prod, "n:vProd")),
            )
        )
    if not nota.itens:
        raise ErroNFe("NF-e sem itens")
    for dup in inf.findall("n:cobr/n:dup", NS):
        venc = _txt(dup, "n:dVenc")
        if venc:
            nota.duplicatas.append((_txt(dup, "n:nDup"), date.fromisoformat(venc), _dec(_txt(dup, "n:vDup"))))
    return nota


@dataclass
class ResultadoImportacao:
    arquivo: str
    status: str  # importada | duplicada | erro | ignorada
    mensagem: str
    nota_id: int | None = None
    chave: str | None = None


def importar(db: Session, cliente: Cliente, conteudo: bytes, nome: str, usuario_id: int | None) -> ResultadoImportacao:
    try:
        lida = ler_xml(conteudo)
    except ErroNFe as e:
        return ResultadoImportacao(nome, "erro", str(e))

    if lida.status_autorizacao and lida.status_autorizacao not in ("100", "150"):
        return ResultadoImportacao(nome, "ignorada", f"NF-e não autorizada (cStat {lida.status_autorizacao})", chave=lida.chave)

    cnpj_cli = cliente.cnpj
    if lida.emitente_documento == cnpj_cli:
        tipo, cliente_emitente = "emitida", True
    elif lida.destinatario_documento == cnpj_cli:
        tipo, cliente_emitente = "recebida", False
    else:
        return ResultadoImportacao(
            nome, "erro", "O CNPJ do cliente não é emitente nem destinatário desta nota", chave=lida.chave
        )

    existente = db.scalar(
        select(NotaFiscal.id).where(NotaFiscal.cliente_id == cliente.id, NotaFiscal.chave == lida.chave)
    )
    if existente:
        return ResultadoImportacao(nome, "duplicada", "Nota já importada", existente, lida.chave)

    contas = mapa_por_codigo(db, cliente.escritorio_id)
    nota = NotaFiscal(
        escritorio_id=cliente.escritorio_id,
        cliente_id=cliente.id,
        chave=lida.chave,
        modelo=lida.modelo,
        serie=lida.serie,
        numero=lida.numero,
        data_emissao=lida.data_emissao,
        tipo=tipo,
        tipo_operacao=lida.tipo_operacao,
        natureza_operacao=lida.natureza_operacao,
        emitente_documento=lida.emitente_documento,
        emitente_nome=lida.emitente_nome[:200],
        destinatario_documento=lida.destinatario_documento,
        destinatario_nome=(lida.destinatario_nome or "")[:200] or None,
        xml_sha256=hashlib.sha256(conteudo).hexdigest(),
        xml=conteudo.decode("utf-8", errors="replace"),
        importado_por_id=usuario_id,
        **lida.totais,
    )
    for it in lida.itens:
        res = cfop_svc.classificar(it.cfop, cliente_emitente)
        conta = contas.get(res.conta_codigo) if res.conta_codigo else None
        nota.itens.append(
            ItemNota(
                numero_item=it.numero_item,
                codigo=it.codigo,
                descricao=it.descricao,
                ncm=it.ncm,
                cfop=it.cfop,
                quantidade=it.quantidade,
                valor_unitario=it.valor_unitario,
                valor_total=it.valor_total,
                conta_id=conta.id if conta else None,
                classificacao_origem="cfop" if conta else "pendente",
            )
        )
    for numero, venc, valor in lida.duplicatas:
        nota.duplicatas.append(Duplicata(numero=numero, vencimento=venc, valor=valor))
    db.add(nota)
    db.flush()
    return ResultadoImportacao(nome, "importada", f"NF-e {tipo} nº {lida.numero}", nota.id, lida.chave)


def extrair_xmls(nome: str, conteudo: bytes) -> list[tuple[str, bytes]]:
    """Aceita um .xml ou um .zip com vários XMLs (importação em lote)."""
    s = get_settings()
    if not nome.lower().endswith(".zip"):
        return [(nome, conteudo)]
    try:
        zf = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile:
        raise ErroNFe("Arquivo ZIP inválido")
    infos = [i for i in zf.infolist() if not i.is_dir() and i.filename.lower().endswith(".xml")]
    if len(infos) > s.zip_max_arquivos:
        raise ErroNFe(f"ZIP com mais de {s.zip_max_arquivos} XMLs")
    if sum(i.file_size for i in infos) > s.zip_max_bytes_descompactados:
        raise ErroNFe("ZIP excede o tamanho máximo descompactado")
    saida = []
    for i in infos:
        with zf.open(i) as f:
            dados = f.read(s.upload_max_bytes + 1)
        if len(dados) > s.upload_max_bytes:
            raise ErroNFe(f"{i.filename} excede o tamanho máximo")
        saida.append((i.filename.rsplit("/", 1)[-1], dados))
    return saida
