from datetime import date

from .conftest import CNPJ_CLIENTE, CNPJ_COMPRADOR, CNPJ_FORNECEDOR
from .util import OFX, xml_nfe


def _preparar(client, h, cliente_id):
    venda = xml_nfe(CNPJ_CLIENTE, CNPJ_COMPRADOR, [("Notebook", "5102", 10000.0)], numero=1, icms=1800, pis=165, cofins=760,
                    duplicatas=[("001", date(2026, 4, 10), 10000.0)])
    compra = xml_nfe(CNPJ_FORNECEDOR, CNPJ_CLIENTE, [("Notebook", "6102", 6000.0)], numero=2, duplicatas=[("1", date(2026, 4, 5), 6000.0)])
    client.post(f"/api/v1/clientes/{cliente_id}/notas/importar", files=[("arquivos", ("v.xml", venda)), ("arquivos", ("c.xml", compra))], headers=h)
    conta = client.post("/api/v1/contas-bancarias", json={"cliente_id": cliente_id, "banco_nome": "Banco X"}, headers=h).json()["id"]
    client.post(f"/api/v1/contas-bancarias/{conta}/extratos", files={"arquivo": ("m.ofx", OFX)}, headers=h)
    contas = {c["codigo"]: c["id"] for c in client.get("/api/v1/plano-contas", headers=h).json()}
    for l in client.get(f"/api/v1/clientes/{cliente_id}/lancamentos", headers=h).json()["itens"]:
        codigo = {"TARIFA": "4.3.01", "PIX ENV": "4.2.03", "PIX REC": "9.1.01", "PAGTO E": "4.2.04"}
        for k, v in codigo.items():
            if l["historico"].startswith(k):
                client.put(f"/api/v1/lancamentos/{l['id']}/classificacao", json={"conta_id": contas[v]}, headers=h)
    aplic = client.post("/api/v1/contas-bancarias", json={"cliente_id": cliente_id, "banco_nome": "Banco X", "tipo": "aplicacao"}, headers=h).json()["id"]
    client.post("/api/v1/aplicacoes", json={"conta_bancaria_id": aplic, "produto": "CDB", "tipo_produto": "cdb", "competencia": "2026-03-01",
                                            "saldo_inicial": "50000", "saldo_final_bruto": "50500", "irrf": "0"}, headers=h)


def test_dre(client, admin, cliente_id):
    _preparar(client, admin, cliente_id)
    r = client.get(f"/api/v1/clientes/{cliente_id}/relatorios/dre?inicio=2026-03-01&fim=2026-03-31", headers=admin)
    assert r.status_code == 200, r.text
    d = r.json()
    t = {l["chave"]: l["total"] for l in d["linhas"]}
    assert t["receita_bruta"] == 10000.0
    assert t["deducoes"] == 1800 + 165 + 760
    assert t["receita_liquida"] == 10000 - 2725
    assert t["custos"] == 6000.0
    assert t["despesas_operacionais"] == 3500 + 890.45
    assert t["receitas_financeiras"] == 500.0
    assert t["despesas_financeiras"] == 49.90
    assert t["lucro_liquido"] == round(7275 - 6000 - 4390.45 + 500 - 49.90, 2)
    assert d["elaborado_por"]["razao_social"] == "CONTABIL EXEMPLO LTDA"
    assert d["elaborado_por"]["crc"] == "CE-012345/O"
    assert d["meses"] == ["2026-03"]


def test_fluxo_caixa_realizado_e_projetado(client, admin, cliente_id):
    _preparar(client, admin, cliente_id)
    r = client.get(f"/api/v1/clientes/{cliente_id}/relatorios/fluxo-caixa?inicio=2026-03-01&fim=2026-04-30&saldo_inicial=1000", headers=admin).json()
    marco = r["realizado"][0]
    assert marco["entradas"] == 12000.0 and marco["saidas"] == round(49.90 + 3500 + 890.45, 2)
    assert marco["saldo_final"] == round(1000 + 12000 - 4440.35, 2)
    abril = r["projetado"][1]
    assert abril == {"mes": "2026-04", "a_receber": 10000.0, "a_pagar": 6000.0, "saldo_projetado": 4000.0}


def test_exportacao_csv_com_rodape_do_escritorio(client, admin, cliente_id):
    _preparar(client, admin, cliente_id)
    r = client.get(f"/api/v1/clientes/{cliente_id}/relatorios/dre?inicio=2026-03-01&fim=2026-03-31&formato=csv", headers=admin)
    assert r.headers["content-type"].startswith("text/csv")
    assert "Elaborado por: CONTABIL EXEMPLO LTDA" in r.text
    assert "(=) Lucro líquido do período" in r.text


def test_gerencial_e_pre_requisitos(client, admin, cliente_id):
    vazio = client.get(f"/api/v1/clientes/{cliente_id}/pre-requisitos", headers=admin).json()
    assert vazio["pode_gerar_dre"] is False and vazio["pode_gerar_fluxo_caixa"] is False
    _preparar(client, admin, cliente_id)
    g = client.get(f"/api/v1/clientes/{cliente_id}/relatorios/gerencial?inicio=2026-01-01&fim=2026-03-31", headers=admin).json()
    i = g["indicadores"]
    assert i["receita_bruta"] == 10000.0 and i["notas_emitidas"] == 1 and i["ticket_medio"] == 10000.0
    assert g["top_clientes"][0]["documento"] == CNPJ_COMPRADOR
    assert g["top_fornecedores"][0]["documento"] == CNPJ_FORNECEDOR
    assert any("negativo" in a["mensagem"] for a in g["alertas"])
    assert client.get(f"/api/v1/clientes/{cliente_id}/pre-requisitos", headers=admin).json()["pode_gerar_dre"] is True


def test_periodo_invalido(client, admin, cliente_id):
    r = client.get(f"/api/v1/clientes/{cliente_id}/relatorios/dre?inicio=2026-05-01&fim=2026-03-31", headers=admin)
    assert r.status_code == 422
