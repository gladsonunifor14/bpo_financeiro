"""Contrato de adesão de BPO Financeiro: modelo padrão, renderização e hash de integridade."""
from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import Decimal

from ..models import Cliente, Escritorio
from .cnpj import formatar

MODELO_PADRAO_TITULO = "Contrato de Prestação de Serviços de BPO Financeiro (Adesão)"

MODELO_PADRAO = """CONTRATO DE PRESTAÇÃO DE SERVIÇOS DE BPO FINANCEIRO — CONTRATO DE ADESÃO

CONTRATADA: {{escritorio_razao_social}}, inscrita no CNPJ sob nº {{escritorio_cnpj}}, CRC {{escritorio_crc}}, com sede em {{escritorio_endereco}}.
CONTRATANTE: {{cliente_razao_social}}, inscrita no CNPJ sob nº {{cliente_cnpj}}, com sede em {{cliente_endereco}}.

CLÁUSULA 1ª — DO OBJETO. Prestação de serviços de terceirização de rotinas financeiras (BPO Financeiro), compreendendo: (a) recepção e organização de documentos fiscais (XML de NF-e emitidas e recebidas); (b) importação e classificação de extratos bancários e de aplicações financeiras; (c) conciliação e elaboração de Fluxo de Caixa, DRE gerencial e relatórios gerenciais; (d) consultoria contábil e tributária baseada nos painéis de BI.

CLÁUSULA 2ª — DA ADESÃO. Este é um contrato de adesão (art. 54 do CDC, no que couber, e arts. 423 e 424 do Código Civil). O aceite eletrônico pelo representante da CONTRATANTE, registrado com data, hora, endereço IP e hash do conteúdo, tem validade jurídica nos termos do art. 10, §2º, da MP 2.200-2/2001.

CLÁUSULA 3ª — DAS OBRIGAÇÕES DA CONTRATANTE. Enviar tempestivamente os documentos e extratos; realizar a classificação inicial dos lançamentos bancários quando solicitada; manter atualizados os dados cadastrais e as procurações necessárias.

CLÁUSULA 4ª — DAS OBRIGAÇÕES DA CONTRATADA. Executar os serviços com zelo técnico, observando as Normas Brasileiras de Contabilidade e o Código de Ética Profissional do Contador; manter sigilo sobre as informações recebidas.

CLÁUSULA 5ª — DO PREÇO. Honorários mensais de R$ {{valor_mensal}}, com vencimento todo dia {{dia_vencimento}}, reajustados anualmente pelo IPCA.

CLÁUSULA 6ª — DA VIGÊNCIA. Início em {{inicio_vigencia}}, por prazo {{prazo}}, podendo ser rescindido por qualquer parte mediante aviso prévio de 30 (trinta) dias.

CLÁUSULA 7ª — DA PROTEÇÃO DE DADOS (LGPD). As partes observarão a Lei nº 13.709/2018. A CONTRATANTE atua como CONTROLADORA e a CONTRATADA como OPERADORA dos dados pessoais tratados exclusivamente para a execução deste contrato (art. 7º, V), adotando medidas de segurança técnicas e administrativas (art. 46), comunicando incidentes de segurança em até 3 (três) dias úteis (Res. CD/ANPD nº 15/2024) e eliminando os dados ao término do tratamento, ressalvada a guarda legal (art. 16).

CLÁUSULA 8ª — DA CONFIDENCIALIDADE. As partes manterão sigilo sobre informações financeiras, fiscais e estratégicas trocadas, durante a vigência e por 5 (cinco) anos após seu término.

CLÁUSULA 9ª — DO FORO. Fica eleito o foro da comarca de {{escritorio_municipio}}/{{escritorio_uf}}.
"""

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def _endereco(e) -> str:
    partes = [e.logradouro, e.numero, e.complemento, e.bairro, e.municipio and f"{e.municipio}/{e.uf or ''}", e.cep]
    return ", ".join(p for p in partes if p) or "endereço não informado"


def _moeda(v: Decimal) -> str:
    s = f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def renderizar(
    modelo: str,
    escritorio: Escritorio,
    cliente: Cliente,
    valor_mensal: Decimal,
    dia_vencimento: int,
    inicio: date,
    fim: date | None,
) -> str:
    variaveis = {
        "escritorio_razao_social": escritorio.razao_social,
        "escritorio_cnpj": formatar(escritorio.cnpj),
        "escritorio_crc": escritorio.crc or "—",
        "escritorio_endereco": _endereco(escritorio),
        "escritorio_municipio": escritorio.municipio or "—",
        "escritorio_uf": escritorio.uf or "—",
        "cliente_razao_social": cliente.razao_social,
        "cliente_cnpj": formatar(cliente.cnpj),
        "cliente_endereco": _endereco(cliente),
        "valor_mensal": _moeda(valor_mensal),
        "dia_vencimento": str(dia_vencimento),
        "inicio_vigencia": inicio.strftime("%d/%m/%Y"),
        "prazo": f"determinado até {fim.strftime('%d/%m/%Y')}" if fim else "indeterminado",
    }
    return _PLACEHOLDER.sub(lambda m: variaveis.get(m.group(1), m.group(0)), modelo)


def sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
