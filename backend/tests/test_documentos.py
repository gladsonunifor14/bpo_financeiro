import io
import zipfile
from datetime import date

from .conftest import CNPJ_CLIENTE, CNPJ_COMPRADOR, CNPJ_FORNECEDOR, SENHA, login
from .util import OFX, OFX_ABRIL, xml_nfe


def _importar(client, h, cliente_id, *arquivos):
    files = [("arquivos", (nome, conteudo, "application/xml")) for nome, conteudo in arquivos]
    r = client.post(f"/api/v1/clientes/{cliente_id}/notas/importar", files=files, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _contas(client, h):
    return {c["codigo"]: c["id"] for c in client.get("/api/v1/plano-contas", headers=h).json()}


def test_importa_nfe_emitida_e_recebida_com_classificacao(client, admin, cliente_id):
    venda = xml_nfe(CNPJ_CLIENTE, CNPJ_COMPRADOR, [("Notebook", "5102", 5000.0), ("Garantia", "5933", 300.0)], numero=1, icms=900, pis=82.5, cofins=380,
                    duplicatas=[("001", date(2026, 4, 10), 5300.0)])
    compra = xml_nfe(CNPJ_FORNECEDOR, CNPJ_CLIENTE, [("Notebook p/ revenda", "6102", 3000.0), ("Papel A4", "6102", 100.0)], numero=7,
                     duplicatas=[("1/1", date(2026, 4, 5), 3100.0)])
    res = _importar(client, admin, cliente_id, ("venda.xml", venda), ("compra.xml", compra))
    assert [r["status"] for r in res] == ["importada", "importada"]
    assert "emitida" in res[0]["mensagem"] and "recebida" in res[1]["mensagem"]

    contas = _contas(client, admin)
    nota = client.get(f"/api/v1/notas/{res[0]['nota_id']}", headers=admin).json()
    assert [i["conta_id"] for i in nota["itens"]] == [contas["3.1.01"], contas["3.1.03"]]
    assert nota["duplicatas"][0]["valor"] in ("5300.00", "5300")
    nota2 = client.get(f"/api/v1/notas/{res[1]['nota_id']}", headers=admin).json()
    assert nota2["tipo"] == "recebida" and nota2["itens"][0]["conta_id"] == contas["4.1.01"]

    # reclassificação manual do papel A4 como material de consumo
    item = nota2["itens"][1]["id"]
    r = client.put(f"/api/v1/notas/itens/{item}/classificacao", json={"conta_id": contas["4.2.05"]}, headers=admin)
    assert r.json()["classificacao_origem"] == "manual"

    # duplicidade
    assert _importar(client, admin, cliente_id, ("venda.xml", venda))[0]["status"] == "duplicada"
    lista = client.get(f"/api/v1/clientes/{cliente_id}/notas?tipo=emitida", headers=admin).json()
    assert lista["total"] == 1


def test_rejeita_nota_de_terceiros_nao_autorizada_e_xxe(client, admin, cliente_id):
    terceiros = xml_nfe(CNPJ_FORNECEDOR, CNPJ_COMPRADOR, [("x", "5102", 10.0)])
    cancelada = xml_nfe(CNPJ_CLIENTE, CNPJ_COMPRADOR, [("x", "5102", 10.0)], numero=2, cstat="101")
    xxe = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>'
    res = _importar(client, admin, cliente_id, ("t.xml", terceiros), ("c.xml", cancelada), ("xxe.xml", xxe), ("lixo.xml", b"nao e xml"))
    assert [r["status"] for r in res] == ["erro", "ignorada", "erro", "erro"]
    assert "inseguras" in res[2]["mensagem"]


def test_importacao_em_lote_zip(client, admin, cliente_id):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in range(3):
            z.writestr(f"nfe{n}.xml", xml_nfe(CNPJ_CLIENTE, CNPJ_COMPRADOR, [("x", "5102", 100.0)], numero=10 + n))
    res = _importar(client, admin, cliente_id, ("lote.zip", buf.getvalue()))
    assert [r["status"] for r in res] == ["importada"] * 3


def _conta_bancaria(client, h, cliente_id, tipo="corrente"):
    r = client.post("/api/v1/contas-bancarias", json={"cliente_id": cliente_id, "banco_codigo": "001", "banco_nome": "Banco do Brasil",
                                                       "agencia": "1234", "numero_conta": "99999-9", "tipo": tipo}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_extrato_ofx_classificacao_manual_e_replicacao_por_ia(client, caixa, admin, cliente_id):
    client.post("/api/v1/usuarios", json={"nome": "Carla", "email": "carla@modelo.com", "papel": "cliente", "cliente_id": cliente_id, "senha_inicial": SENHA}, headers=admin)
    h = login(client, caixa, "carla@modelo.com")  # o próprio cliente classifica
    conta = _conta_bancaria(client, h, cliente_id)
    r = client.post(f"/api/v1/contas-bancarias/{conta}/extratos", files={"arquivo": ("marco.ofx", OFX)}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["quantidade"] == 4
    # reimportar não duplica
    r = client.post(f"/api/v1/contas-bancarias/{conta}/extratos", files={"arquivo": ("marco.ofx", OFX)}, headers=h)
    assert r.json()["quantidade"] == 0 and r.json()["duplicados"] == 4

    contas = _contas(client, h)
    lancs = {l["historico"][:12]: l for l in client.get(f"/api/v1/clientes/{cliente_id}/lancamentos", headers=h).json()["itens"]}
    for prefixo, codigo in [("PIX ENVIADO ", "4.2.03"), ("PAGTO ENERGI", "4.2.04"), ("PIX RECEBIDO", "9.1.01"), ("TARIFA PACOT", "4.3.01")]:
        r = client.put(f"/api/v1/lancamentos/{lancs[prefixo]['id']}/classificacao", json={"conta_id": contas[codigo]}, headers=h)
        assert r.status_code == 200, r.text

    # mês seguinte: a IA replica as classificações do cliente
    r = client.post(f"/api/v1/contas-bancarias/{conta}/extratos", files={"arquivo": ("abril.ofx", OFX_ABRIL)}, headers=h)
    assert r.json()["classificados_ia"] == 2
    abril = {l["historico"][:12]: l for l in client.get(f"/api/v1/clientes/{cliente_id}/lancamentos?inicio=2026-04-01", headers=h).json()["itens"]}
    assert abril["PIX ENVIADO "]["conta_id"] == contas["4.2.03"]
    assert abril["PIX ENVIADO "]["status_classificacao"] == "ia_sugerida"
    assert abril["PAGTO ENERGI"]["conta_id"] == contas["4.2.04"]
    assert abril["COMPRA CARTA"]["status_classificacao"] == "pendente"

    # confirmação em lote das sugestões
    ids = [l["id"] for l in abril.values() if l["status_classificacao"] == "ia_sugerida"]
    r = client.post("/api/v1/lancamentos/classificacao-lote", json={"lancamento_ids": ids}, headers=h)
    assert r.json()["atualizados"] == 2


def test_extrato_invalido(client, admin, cliente_id):
    conta = _conta_bancaria(client, admin, cliente_id)
    r = client.post(f"/api/v1/contas-bancarias/{conta}/extratos", files={"arquivo": ("x.pdf", b"%PDF-1.4")}, headers=admin)
    assert r.status_code == 422


def test_aplicacoes_financeiras(client, admin, cliente_id):
    conta = _conta_bancaria(client, admin, cliente_id, "aplicacao")
    dados = {"conta_bancaria_id": conta, "produto": "CDB DI 102%", "tipo_produto": "cdb", "competencia": "2026-03-15",
             "saldo_inicial": "100000.00", "aplicacoes": "10000.00", "resgates": "5000.00", "saldo_final_bruto": "106000.00",
             "irrf": "150.00", "taxa_administracao": "50.00", "cdi_mes_percentual": "0.95"}
    r = client.post("/api/v1/aplicacoes", json=dados, headers=admin)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["competencia"] == "2026-03-01"
    assert p["rendimento_bruto"] == "1200.00" and p["rendimento_liquido"] == "1000.00"
    assert client.post("/api/v1/aplicacoes", json=dados, headers=admin).status_code == 409
    r = client.post("/api/v1/aplicacoes/simular-tributos", json={"rendimento": "1000.00", "dias": 400}, headers=admin)
    assert r.json()["irrf"] == "175.00"


def test_open_finance_desabilitado_por_padrao(client, admin, cliente_id):
    assert client.get("/api/v1/open-finance/status", headers=admin).json()["disponivel"] is False
    assert client.post("/api/v1/open-finance/consentimentos", json={"cliente_id": cliente_id}, headers=admin).status_code == 501


def test_open_finance_simulado(client, admin, cliente_id, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "open_finance_provedor", "simulado")
    conta = _conta_bancaria(client, admin, cliente_id)
    c = client.post("/api/v1/open-finance/consentimentos", json={"cliente_id": cliente_id}, headers=admin).json()
    assert c["url_autorizacao"]
    r = client.post(f"/api/v1/open-finance/consentimentos/{c['id']}/sincronizar",
                    json={"conta_bancaria_id": conta, "inicio": "2026-03-01", "fim": "2026-03-31"}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["formato"] == "open_finance" and r.json()["quantidade"] == 10


def test_robo_importa_pasta_do_cliente(client, admin, cliente_id, tmp_path):
    from app.jobs import importar_pasta

    conta = _conta_bancaria(client, admin, cliente_id)
    pasta = tmp_path / CNPJ_CLIENTE
    pasta.mkdir()
    (pasta / "venda.xml").write_bytes(xml_nfe(CNPJ_CLIENTE, CNPJ_COMPRADOR, [("x", "5102", 100.0)], numero=99))
    (pasta / f"{conta}_marco.ofx").write_bytes(OFX)
    (pasta / "999_invalido.ofx").write_bytes(OFX)
    assert importar_pasta(tmp_path) == {"notas": 1, "lancamentos": 4, "erros": 1}
    assert (tmp_path / "processados" / CNPJ_CLIENTE / "venda.xml").exists()
    assert (pasta / "999_invalido.ofx").exists()  # arquivo com erro permanece para análise
