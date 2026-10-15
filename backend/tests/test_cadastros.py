import httpx

from app.services import cnpj as cnpj_svc

from .conftest import CNPJ_CLIENTE, CNPJ_FORNECEDOR, SENHA, login, ultimo_codigo
from .util import gerar_cnpj


def test_cliente_importado_da_receita(client, admin, cliente_id):
    c = client.get(f"/api/v1/clientes/{cliente_id}", headers=admin).json()
    assert c["razao_social"] == "COMERCIO MODELO LTDA"
    assert c["situacao_cadastral"] == "ATIVA"
    lista = client.get("/api/v1/clientes?busca=modelo", headers=admin).json()
    assert lista["total"] == 1


def test_cliente_duplicado_e_cnpj_inexistente(client, admin, cliente_id):
    assert client.post("/api/v1/clientes", json={"cnpj": CNPJ_CLIENTE}, headers=admin).status_code == 409
    r = client.post("/api/v1/clientes", json={"cnpj": CNPJ_FORNECEDOR}, headers=admin)
    assert r.status_code == 404
    r = client.post("/api/v1/clientes", json={"cnpj": CNPJ_FORNECEDOR, "importar_receita": False, "razao_social": "Manual SA"}, headers=admin)
    assert r.status_code == 201


def test_consulta_cnpj_alfanumerico_valida_dv(client, admin):
    cnpj = gerar_cnpj("12ABC34501DE")
    r = client.get(f"/api/v1/cnpj/{cnpj}", headers=admin)
    assert r.status_code == 404  # válido, mas não existe na base simulada
    assert client.get("/api/v1/cnpj/12ABC34501DE00", headers=admin).status_code in (422, 404)


def test_cadastro_manual_quando_receita_indisponivel_e_isolamento(client, caixa, admin, cliente_id):
    dados = {"cnpj": gerar_cnpj("999888770001"), "nome": "Beto", "email": "beto@x.com", "senha": SENHA,
             "aceite_termos": True, "razao_social": "Outro Escritorio"}
    # CNPJ inexistente na Receita: não permite cadastro manual
    assert client.post("/api/v1/auth/cadastro", json=dados).status_code == 404
    # Receita fora do ar: aceita a razão social informada
    cnpj_svc.transporte_http = httpx.MockTransport(lambda req: httpx.Response(503))
    r = client.post("/api/v1/auth/cadastro", json=dados)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/otp/verificar", json={"desafio_id": r.json()["desafio_id"], "codigo": ultimo_codigo(caixa)})
    outro = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"/api/v1/clientes/{cliente_id}", headers=outro).status_code == 404
    assert client.get("/api/v1/clientes", headers=outro).json()["total"] == 0


def test_usuario_cliente_ve_somente_sua_empresa(client, caixa, admin, cliente_id):
    r = client.post("/api/v1/clientes", json={"cnpj": CNPJ_FORNECEDOR, "importar_receita": False, "razao_social": "Outra"}, headers=admin)
    outro_id = r.json()["id"]
    r = client.post("/api/v1/usuarios", json={"nome": "Carla", "email": "carla@modelo.com", "papel": "cliente", "cliente_id": cliente_id, "senha_inicial": SENHA}, headers=admin)
    assert r.status_code == 201, r.text
    h = login(client, caixa, "carla@modelo.com")
    assert client.get("/api/v1/clientes", headers=h).json()["total"] == 1
    assert client.get(f"/api/v1/clientes/{outro_id}", headers=h).status_code == 404
    assert client.post("/api/v1/clientes", json={"cnpj": gerar_cnpj("333444550001"), "importar_receita": False, "razao_social": "X"}, headers=h).status_code == 403
    assert client.get("/api/v1/auditoria", headers=h).status_code == 403


def test_chave_api_autentica_e_pode_ser_revogada(client, admin, cliente_id):
    r = client.post("/api/v1/chaves-api", json={"nome": "ERP"}, headers=admin)
    chave, cid = r.json()["chave"], r.json()["id"]
    assert client.get("/api/v1/clientes", headers={"X-API-Key": chave}).status_code == 200
    client.delete(f"/api/v1/chaves-api/{cid}", headers=admin)
    assert client.get("/api/v1/clientes", headers={"X-API-Key": chave}).status_code == 401


def test_auditoria_registra_quem_quando_o_que(client, admin, cliente_id):
    client.put(f"/api/v1/clientes/{cliente_id}", json={"telefone": "8533334444"}, headers=admin)
    r = client.get(f"/api/v1/auditoria?tabela=cliente&registro_id={cliente_id}", headers=admin).json()
    acoes = {i["acao"]: i for i in r["itens"]}
    assert {"INSERT", "UPDATE"} <= set(acoes)
    upd = acoes["UPDATE"]
    assert upd["usuario_email"] == "admin@contabil.com"
    assert upd["campos_alterados"] == ["telefone"]
    assert upd["dados_depois"]["telefone"] == "8533334444"
    assert upd["ip"]
    # senha nunca aparece na auditoria
    usuarios = client.get("/api/v1/auditoria?tabela=usuario", headers=admin).json()["itens"]
    assert all(i["dados_depois"] is None or i["dados_depois"].get("senha_hash") in (None, "***") for i in usuarios)
