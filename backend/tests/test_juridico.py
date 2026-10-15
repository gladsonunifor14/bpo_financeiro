from .conftest import SENHA, login


def _usuario_cliente(client, caixa, admin, cliente_id):
    client.post("/api/v1/usuarios", json={"nome": "Carla", "email": "carla@modelo.com", "papel": "cliente", "cliente_id": cliente_id, "senha_inicial": SENHA}, headers=admin)
    return login(client, caixa, "carla@modelo.com")


def test_contrato_de_adesao_com_aceite_eletronico(client, caixa, admin, cliente_id):
    r = client.post("/api/v1/contratos", json={"cliente_id": cliente_id, "valor_mensal": "1500.00", "dia_vencimento": 10, "inicio_vigencia": "2026-11-01"}, headers=admin)
    assert r.status_code == 201, r.text
    c = r.json()
    assert "COMERCIO MODELO LTDA" in c["conteudo"] and "CONTABIL EXEMPLO LTDA" in c["conteudo"]
    assert "R$ 1.500,00" in c["conteudo"] and "{{" not in c["conteudo"]
    assert c["status"] == "aguardando_aceite"
    # segundo contrato para o mesmo cliente é bloqueado
    assert client.post("/api/v1/contratos", json={"cliente_id": cliente_id, "valor_mensal": "1", "dia_vencimento": 1, "inicio_vigencia": "2026-11-01"}, headers=admin).status_code == 409
    # escritório não pode aceitar pelo cliente
    assert client.post(f"/api/v1/contratos/{c['id']}/aceite", json={"hash_sha256": c["hash_sha256"], "li_e_concordo": True}, headers=admin).status_code == 403
    h = _usuario_cliente(client, caixa, admin, cliente_id)
    assert client.post(f"/api/v1/contratos/{c['id']}/aceite", json={"hash_sha256": "x" * 64, "li_e_concordo": True}, headers=h).status_code == 409
    r = client.post(f"/api/v1/contratos/{c['id']}/aceite", json={"hash_sha256": c["hash_sha256"], "li_e_concordo": True}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "vigente" and r.json()["aceite_ip"]


def test_termos_lgpd_versionados_exigem_novo_aceite(client, caixa, admin, cliente_id):
    assert client.get("/api/v1/termos/pendentes", headers=admin).json() == []  # aceitos no cadastro
    h = _usuario_cliente(client, caixa, admin, cliente_id)
    pend = client.get("/api/v1/termos/pendentes", headers=h).json()
    assert {t["tipo"] for t in pend} == {"termos_uso", "politica_privacidade", "confidencialidade"}
    for t in pend:
        assert client.post(f"/api/v1/termos/{t['id']}/aceite", json={"hash_sha256": t["hash_sha256"]}, headers=h).status_code == 200
    assert client.get("/api/v1/termos/pendentes", headers=h).json() == []
    novo = client.post("/api/v1/termos", json={"tipo": "politica_privacidade", "titulo": "Política v2", "conteudo": "Nova política de privacidade com DPO."}, headers=admin).json()
    assert novo["versao"] == 2
    assert [t["id"] for t in client.get("/api/v1/termos/pendentes", headers=h).json()] == [novo["id"]]
    aceites = client.get(f"/api/v1/termos/{pend[0]['id']}/aceites", headers=admin).json()
    assert "carla@modelo.com" in {a["email"] for a in aceites}


def test_procuracoes(client, admin, cliente_id):
    dados = {"cliente_id": str(cliente_id), "tipo": "ecac", "outorgado_nome": "Contabil Exemplo", "outorgado_documento": "11.222.333/0001-81",
             "poderes": "Consulta e transmissão de declarações no e-CAC", "data_inicio": "2026-01-01", "data_fim": "2026-10-20"}
    r = client.post("/api/v1/procuracoes", data=dados, files={"arquivo": ("p.pdf", b"%PDF-1.4 conteudo", "application/pdf")}, headers=admin)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["arquivo_sha256"] and p["situacao"] in ("vence_em_30_dias", "vencida", "vigente")
    assert client.get(f"/api/v1/procuracoes/{p['id']}/arquivo", headers=admin).content.startswith(b"%PDF")
    r = client.post("/api/v1/procuracoes", data=dados, files={"arquivo": ("p.pdf", b"MZ executavel", "application/pdf")}, headers=admin)
    assert r.status_code == 415
    assert client.post(f"/api/v1/procuracoes/{p['id']}/revogar", headers=admin).json()["situacao"] == "revogada"
    assert client.get("/api/v1/painel", headers=admin).status_code == 200
