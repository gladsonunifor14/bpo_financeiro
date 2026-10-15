from decimal import Decimal

import pytest

from app.services import cfop, cnpj, extratos, investimentos
from app.services.classificador import Classificador

from .util import gerar_cnpj


@pytest.mark.parametrize("valor,ok", [
    ("11.222.333/0001-81", True),
    ("11222333000181", True),
    ("11222333000180", False),
    ("00000000000000", False),
    ("12.ABC.345/01DE-35", True),  # exemplo oficial do CNPJ alfanumérico (RFB)
    ("12ABC34501DE34", False),
    ("123", False),
])
def test_validacao_cnpj(valor, ok):
    assert cnpj.validar(valor) is ok


def test_formatar_cnpj():
    assert cnpj.formatar(gerar_cnpj("112223330001")) == "11.222.333/0001-81"


@pytest.mark.parametrize("cfop_xml,emitente,conta,sentido", [
    ("5102", True, "3.1.01", "saida"),      # venda de mercadoria
    ("6101", True, "3.1.02", "saida"),      # venda de produção própria interestadual
    ("5933", True, "3.1.03", "saida"),      # serviço (ISS)
    ("1202", True, "3.2.01", "entrada"),    # devolução de venda emitida pelo próprio cliente
    ("5102", False, "4.1.01", "entrada"),   # recebida: fornecedor vendeu → compra p/ revenda
    ("6556", False, "4.2.05", "entrada"),   # recebida: material de uso e consumo
    ("5551", False, "9.1.07", "entrada"),   # recebida: ativo imobilizado
    ("5915", True, "9.1.08", "saida"),      # remessa para conserto
    ("5202", True, "4.1.05", "saida"),      # devolução de compra
    ("5949", True, "9.1.08", "saida"),      # outras saídas
])
def test_classificacao_cfop(cfop_xml, emitente, conta, sentido):
    r = cfop.classificar(cfop_xml, emitente)
    assert (r.conta_codigo, r.sentido) == (conta, sentido)


def test_normalizacao_historico():
    assert extratos.normalizar_historico("PIX ENVIADO 12/03 João da Silva 123456") == "PIX ENVIADO JOAO SILVA"


def test_csv_extrato_formato_brasileiro():
    csv = "Data;Histórico;Débito;Crédito\n05/03/2026;Tarifa;49,90;\n06/03/2026;Recebimento;;1.200,50\n".encode("cp1252")
    lidos = extratos.ler_csv(csv)
    assert [(l.natureza, l.valor) for l in lidos] == [("D", Decimal("49.90")), ("C", Decimal("1200.50"))]


def test_classificador_aprende_e_generaliza():
    clf = Classificador()
    clf.treinar([
        ("PIX ENVIADO IMOBILIARIA CENTRO", "D", 1, 1.0),
        ("PAGTO ENERGIA ENEL", "D", 2, 1.0),
        ("PAGTO ENERGIA ENEL", "D", 2, 1.0),
        ("PIX RECEBIDO CLIENTE ALFA", "C", 3, 1.0),
    ])
    conta, conf, metodo = clf.prever("PAGTO ENERGIA ENEL", "D")
    assert (conta, metodo) == (2, "exato") and conf > 0.9
    conta, conf, metodo = clf.prever("PIX RECEBIDO CLIENTE BETA", "C")
    assert conta == 3 and metodo == "modelo"
    assert clf.prever("XYZ ABC", "D") is None


def test_rendimentos_aplicacao():
    r = investimentos.calcular(
        saldo_inicial=Decimal("100000"), aplicacoes=Decimal("10000"), resgates=Decimal("5000"),
        saldo_final_bruto=Decimal("106000"), irrf=Decimal("150"), iof=Decimal("0"),
        taxa_administracao=Decimal("50"), cdi_mes_percentual=Decimal("0.95"),
    )
    # líquido = 106000 − 100000 − 10000 + 5000 = 1000; bruto = 1000 + 150 + 50 = 1200
    assert r.rendimento_liquido == Decimal("1000.00")
    assert r.rendimento_bruto == Decimal("1200.00")
    assert r.capital_medio == Decimal("102500.00")
    assert r.taxa_bruta_mes == Decimal("0.011707")
    assert r.percentual_cdi == Decimal("123.23")
    assert r.taxa_bruta_ano > Decimal("0.14")


@pytest.mark.parametrize("dias,ir", [(30, "0.225"), (181, "0.20"), (361, "0.175"), (721, "0.15")])
def test_tabela_regressiva_ir(dias, ir):
    assert investimentos.aliquota_ir(dias) == Decimal(ir)


def test_iof_regressivo():
    r = investimentos.estimar_tributos_resgate(Decimal("100.00"), 10)
    assert r["iof"] == Decimal("66.00")
    assert r["irrf"] == Decimal("7.65")  # 22,5% sobre (100 − 66)
