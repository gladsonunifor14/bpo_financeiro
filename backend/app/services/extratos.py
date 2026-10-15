"""Leitura de extratos bancários (OFX 1.x/2.x e CSV) e normalização de históricos."""
from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class ErroExtrato(Exception):
    pass


@dataclass
class LancamentoLido:
    data: date
    historico: str
    valor: Decimal  # positivo
    natureza: str  # C | D
    documento: str | None = None
    fitid: str | None = None

    def hash_dedup(self) -> str:
        base = self.fitid or f"{self.data}|{self.historico}|{self.valor}|{self.natureza}|{self.documento or ''}"
        return hashlib.sha256(base.encode()).hexdigest()


def decodificar(conteudo: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return conteudo.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ErroExtrato("Codificação de arquivo não suportada")


_STOP = {"DE", "DA", "DO", "EM", "PARA", "COM", "E", "A", "O", "S", "LTDA", "ME", "EPP", "SA"}


def normalizar_historico(texto: str) -> str:
    """Remove acentos, números variáveis (datas, documentos, valores) e ruído.
    Ex.: 'PIX ENVIADO 12/03 JOÃO DA SILVA 123456' → 'PIX ENVIADO JOAO SILVA'."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()
    t = re.sub(r"[^A-Z0-9 ]+", " ", t)
    t = re.sub(r"\b\w*\d\w*\b", " ", t)  # tokens com dígitos
    tokens = [p for p in t.split() if p not in _STOP and len(p) > 1]
    return " ".join(tokens)[:300]


# ------------------------------------------------------------------ OFX
_RE_TRN = re.compile(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))", re.S | re.I)


def _tag(bloco: str, nome: str) -> str | None:
    m = re.search(rf"<{nome}>([^<\r\n]*)", bloco, re.I)
    return m.group(1).strip() if m else None


def _data_ofx(v: str) -> date:
    return datetime.strptime(v[:8], "%Y%m%d").date()


def ler_ofx(conteudo: bytes) -> list[LancamentoLido]:
    texto = decodificar(conteudo)
    if "<OFX>" not in texto.upper():
        raise ErroExtrato("Arquivo não parece ser OFX")
    saida = []
    for bloco in _RE_TRN.findall(texto):
        dt, valor = _tag(bloco, "DTPOSTED"), _tag(bloco, "TRNAMT")
        if not dt or not valor:
            continue
        try:
            v = Decimal(valor.replace(",", "."))
        except InvalidOperation:
            raise ErroExtrato(f"Valor inválido no OFX: {valor}")
        hist = " ".join(filter(None, [_tag(bloco, "NAME"), _tag(bloco, "MEMO")])) or (_tag(bloco, "TRNTYPE") or "")
        saida.append(
            LancamentoLido(
                data=_data_ofx(dt),
                historico=hist[:300],
                valor=abs(v),
                natureza="C" if v > 0 else "D",
                documento=_tag(bloco, "CHECKNUM") or _tag(bloco, "REFNUM"),
                fitid=_tag(bloco, "FITID"),
            )
        )
    if not saida:
        raise ErroExtrato("Nenhuma transação encontrada no OFX")
    return saida


# ------------------------------------------------------------------ CSV
def _valor_br(v: str) -> Decimal:
    v = (v or "").strip().replace("R$", "").replace(" ", "")
    if not v:
        return Decimal("0")
    neg = v.startswith("-") or v.endswith("-") or (v.startswith("(") and v.endswith(")"))
    v = v.strip("-()")
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    try:
        d = Decimal(v)
    except InvalidOperation:
        raise ErroExtrato(f"Valor inválido: {v}")
    return -d if neg else d


def _data_br(v: str) -> date:
    v = v.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    raise ErroExtrato(f"Data inválida: {v}")


def _chave(nome: str) -> str:
    return unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().strip().lower()


def ler_csv(conteudo: bytes) -> list[LancamentoLido]:
    """Colunas aceitas (cabeçalho obrigatório, separador ; ou ,):
    data, historico|descricao, valor (com sinal) — ou — debito e credito; documento (opcional)."""
    texto = decodificar(conteudo)
    amostra = texto[:2048]
    sep = ";" if amostra.count(";") >= amostra.count(",") else ","
    leitor = csv.DictReader(io.StringIO(texto), delimiter=sep)
    if not leitor.fieldnames:
        raise ErroExtrato("CSV sem cabeçalho")
    campos = {_chave(c): c for c in leitor.fieldnames}
    col_data = campos.get("data")
    col_hist = campos.get("historico") or campos.get("descricao")
    if not col_data or not col_hist:
        raise ErroExtrato("CSV precisa das colunas 'data' e 'historico'")
    saida = []
    for n, linha in enumerate(leitor, start=2):
        if not (linha.get(col_data) or "").strip():
            continue
        if "valor" in campos:
            v = _valor_br(linha[campos["valor"]])
        elif "debito" in campos and "credito" in campos:
            v = _valor_br(linha[campos["credito"]]) - abs(_valor_br(linha[campos["debito"]]))
        else:
            raise ErroExtrato("CSV precisa da coluna 'valor' ou das colunas 'debito' e 'credito'")
        if v == 0:
            continue
        try:
            dt = _data_br(linha[col_data])
        except ErroExtrato as e:
            raise ErroExtrato(f"Linha {n}: {e}")
        doc_col = campos.get("documento")
        saida.append(
            LancamentoLido(
                data=dt,
                historico=(linha[col_hist] or "").strip()[:300],
                valor=abs(v),
                natureza="C" if v > 0 else "D",
                documento=(linha.get(doc_col) or None) if doc_col else None,
            )
        )
    if not saida:
        raise ErroExtrato("Nenhum lançamento encontrado no CSV")
    return saida


def ler(nome: str, conteudo: bytes) -> tuple[str, list[LancamentoLido]]:
    n = nome.lower()
    if n.endswith(".ofx") or b"<OFX>" in conteudo[:4096].upper():
        return "ofx", ler_ofx(conteudo)
    if n.endswith(".csv") or n.endswith(".txt"):
        return "csv", ler_csv(conteudo)
    raise ErroExtrato("Formato não suportado. Envie OFX ou CSV")
