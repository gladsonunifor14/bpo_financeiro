"""Cálculos de aplicações financeiras a partir do extrato mensal.

Convenções do extrato informado (uma linha por produto e mês):
  saldo_inicial, saldo_final_bruto — posição de abertura/fechamento (antes de resgates futuros);
  aplicacoes — aportes no mês; resgates — valores LÍQUIDOS creditados em conta;
  irrf / iof — tributos retidos no mês (resgates ou come-cotas);
  taxa_administracao — taxa cobrada pelo fundo no mês (já refletida no valor da cota).

  rendimento líquido = saldo_final − saldo_inicial − aplicações + resgates
  rendimento bruto   = rendimento líquido + IRRF + IOF + taxa de administração
  capital médio      = saldo_inicial + (aplicações − resgates)/2   (Dietz simplificado)
  taxa mensal        = rendimento / capital médio;  taxa anual equivalente = (1+i)^12 − 1
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

DUAS = Decimal("0.01")

# Tabela regressiva de IRRF para renda fixa e fundos de longo prazo (Lei 11.033/2004).
# Para PJ o IRRF é antecipação do IRPJ devido; LCI/LCA só são isentas para pessoa física.
TABELA_IR_REGRESSIVA = [(180, Decimal("0.225")), (360, Decimal("0.20")), (720, Decimal("0.175"))]
ALIQUOTA_IR_LONGO = Decimal("0.15")

# IOF regressivo sobre rendimento em resgates com menos de 30 dias (Decreto 6.306/2007, anexo)
TABELA_IOF = [96, 93, 90, 86, 83, 80, 76, 73, 70, 66, 63, 60, 56, 53, 50, 46, 43, 40, 36, 33, 30, 26, 23, 20, 16, 13, 10, 6, 3, 0]


def aliquota_ir(dias: int) -> Decimal:
    for limite, aliquota in TABELA_IR_REGRESSIVA:
        if dias <= limite:
            return aliquota
    return ALIQUOTA_IR_LONGO


def aliquota_iof(dias: int) -> Decimal:
    if dias >= 30:
        return Decimal("0")
    return Decimal(TABELA_IOF[max(dias, 1) - 1]) / 100


def estimar_tributos_resgate(rendimento: Decimal, dias: int) -> dict:
    """IOF incide primeiro sobre o rendimento; o IR incide sobre o rendimento líquido do IOF."""
    iof = (rendimento * aliquota_iof(dias)).quantize(DUAS, ROUND_HALF_UP)
    ir = ((rendimento - iof) * aliquota_ir(dias)).quantize(DUAS, ROUND_HALF_UP)
    return {
        "rendimento": rendimento,
        "aliquota_iof": aliquota_iof(dias),
        "iof": iof,
        "aliquota_ir": aliquota_ir(dias),
        "irrf": ir,
        "rendimento_liquido": rendimento - iof - ir,
    }


@dataclass
class ResultadoMensal:
    rendimento_bruto: Decimal
    rendimento_liquido: Decimal
    capital_medio: Decimal
    taxa_bruta_mes: Decimal | None
    taxa_liquida_mes: Decimal | None
    taxa_bruta_ano: Decimal | None
    taxa_liquida_ano: Decimal | None
    aliquota_efetiva_ir: Decimal | None
    percentual_cdi: Decimal | None


def _anual(i: Decimal | None) -> Decimal | None:
    if i is None:
        return None
    return Decimal(str((1 + float(i)) ** 12 - 1)).quantize(Decimal("0.000001"))


def calcular(
    saldo_inicial: Decimal,
    aplicacoes: Decimal,
    resgates: Decimal,
    saldo_final_bruto: Decimal,
    irrf: Decimal = Decimal(0),
    iof: Decimal = Decimal(0),
    taxa_administracao: Decimal = Decimal(0),
    cdi_mes_percentual: Decimal | None = None,
) -> ResultadoMensal:
    liquido = saldo_final_bruto - saldo_inicial - aplicacoes + resgates
    bruto = liquido + irrf + iof + taxa_administracao
    capital = saldo_inicial + (aplicacoes - resgates) / 2
    q = Decimal("0.000001")
    tb = (bruto / capital).quantize(q) if capital > 0 else None
    tl = (liquido / capital).quantize(q) if capital > 0 else None
    tributavel = bruto - taxa_administracao
    ef = (irrf / tributavel).quantize(q) if tributavel > 0 and irrf > 0 else None
    pcdi = None
    if tb is not None and cdi_mes_percentual:
        pcdi = (tb * 100 / cdi_mes_percentual * 100).quantize(Decimal("0.01"))
    return ResultadoMensal(
        rendimento_bruto=bruto.quantize(DUAS),
        rendimento_liquido=liquido.quantize(DUAS),
        capital_medio=capital.quantize(DUAS),
        taxa_bruta_mes=tb,
        taxa_liquida_mes=tl,
        taxa_bruta_ano=_anual(tb),
        taxa_liquida_ano=_anual(tl),
        aliquota_efetiva_ir=ef,
        percentual_cdi=pcdi,
    )
