"""Classificação contábil (gerencial) de itens de NF-e a partir do CFOP.

O CFOP do XML está na ótica do EMITENTE. Para notas recebidas pelo cliente, o CFOP é
convertido para a ótica do cliente (5→1, 6→2, 7→3 e vice-versa) antes da classificação.
Ex.: o fornecedor emite 5102 (venda de mercadoria) → para o cliente é 1102 (compra p/ revenda).

Primeiro dígito: 1/2/3 = entradas (estadual/interestadual/exterior); 5/6/7 = saídas.
"""
from __future__ import annotations

from dataclasses import dataclass

# sufixo (3 dígitos) → (conta quando SAÍDA, conta quando ENTRADA). None = sem regra específica.
REGRAS: dict[str, tuple[str | None, str | None]] = {
    # Vendas / compras
    "101": ("3.1.02", "4.1.02"),
    "102": ("3.1.01", "4.1.01"),
    "103": ("3.1.02", None),
    "104": ("3.1.01", None),
    "105": ("3.1.02", None),
    "106": ("3.1.01", None),
    "109": ("3.1.02", None),
    "110": ("3.1.01", None),
    "111": ("3.1.02", "4.1.02"),
    "113": ("3.1.01", "4.1.01"),
    "116": ("3.1.02", "4.1.02"),
    "117": ("3.1.01", "4.1.01"),
    "118": ("3.1.01", "4.1.01"),
    "120": ("3.1.01", "4.1.01"),
    "121": (None, "4.1.01"),
    "122": ("3.1.02", "4.1.02"),
    "123": ("3.1.01", None),
    "124": ("3.1.03", "4.1.03"),
    "125": ("3.1.03", "4.1.03"),
    "126": (None, "4.1.02"),
    "128": (None, "4.1.02"),
    "401": ("3.1.02", "4.1.02"),
    "402": ("3.1.02", None),
    "403": ("3.1.01", "4.1.01"),
    "405": ("3.1.01", None),
    "651": ("3.1.02", "4.1.02"),
    "652": ("3.1.01", "4.1.01"),
    "653": ("3.1.01", "4.2.08"),
    "655": ("3.1.01", None),
    "656": ("3.1.01", None),
    "929": ("3.1.01", None),
    # Serviços (ICMS/ISS), energia, comunicação e transporte
    "933": ("3.1.03", "4.2.06"),
    "251": ("3.1.01", None),
    "252": (None, "4.2.04"),
    "253": (None, "4.2.04"),
    "301": ("3.1.03", "4.2.04"),
    "302": ("3.1.03", "4.2.04"),
    "303": ("3.1.03", "4.2.04"),
    "351": ("3.1.03", "4.1.04"),
    "352": ("3.1.03", "4.1.04"),
    "353": ("3.1.03", "4.1.04"),
    "357": ("3.1.03", "4.1.04"),
    "360": ("3.1.03", None),
    # Devoluções
    "201": ("4.1.05", "3.2.01"),
    "202": ("4.1.05", "3.2.01"),
    "203": (None, "3.2.01"),
    "204": (None, "3.2.01"),
    "208": ("9.1.08", "9.1.08"),
    "209": ("9.1.08", "9.1.08"),
    "410": ("4.1.05", "3.2.01"),
    "411": ("4.1.05", "3.2.01"),
    "412": ("9.1.07", None),
    "413": ("4.2.05", None),
    "553": ("9.1.07", "9.1.07"),
    "556": ("4.2.05", "4.2.05"),
    "660": ("4.1.05", "3.2.01"),
    "661": ("4.1.05", "3.2.01"),
    "662": ("4.1.05", "3.2.01"),
    # Ativo imobilizado e uso/consumo
    "551": ("3.4.01", "9.1.07"),
    "406": (None, "9.1.07"),
    "407": (None, "4.2.05"),
    # Bonificações, perdas
    "910": ("4.2.07", "3.4.01"),
    "927": ("4.4.01", None),
    # Remessas/retornos/transferências sem efeito no resultado
    **{s: ("9.1.08", "9.1.08") for s in (
        "151", "152", "155", "156", "408", "409", "552", "554", "555", "557",
        "901", "902", "903", "904", "905", "906", "907", "908", "909", "911", "912",
        "913", "914", "915", "916", "917", "918", "919", "920", "921", "922", "923",
        "924", "925", "926", "934", "949",
    )},
}


@dataclass
class ResultadoCFOP:
    cfop_cliente: str
    sentido: str  # entrada | saida
    conta_codigo: str | None


def converter_para_destinatario(cfop: str) -> str:
    """CFOP do emitente → CFOP equivalente na ótica do destinatário."""
    mapa = {"5": "1", "6": "2", "7": "3", "1": "5", "2": "6", "3": "7"}
    return mapa.get(cfop[0], cfop[0]) + cfop[1:]


def sentido(cfop: str) -> str:
    return "entrada" if cfop[0] in "123" else "saida"


def classificar(cfop_xml: str, cliente_e_emitente: bool) -> ResultadoCFOP:
    cfop = cfop_xml if cliente_e_emitente else converter_para_destinatario(cfop_xml)
    sent = sentido(cfop)
    sufixo = cfop[1:]
    regra = REGRAS.get(sufixo)
    conta = None
    if regra:
        conta = regra[0] if sent == "saida" else regra[1]
    if conta is None:
        # Regras de família: grupo x1xx/x4xx = operações de compra e venda
        if sufixo[0] in "14":
            conta = "3.1.01" if sent == "saida" else "4.1.01"
        elif sufixo[0] == "9":
            conta = "9.1.08"
    return ResultadoCFOP(cfop_cliente=cfop, sentido=sent, conta_codigo=conta)
