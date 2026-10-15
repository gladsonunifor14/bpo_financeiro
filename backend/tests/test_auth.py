from .conftest import CNPJ_ESCRITORIO, SENHA, cadastrar_escritorio, login, ultimo_codigo


def test_cadastro_importa_dados_da_receita_e_exige_otp(client, caixa):
    h = cadastrar_escritorio(client, caixa)
    esc = client.get("/api/v1/escritorio", headers=h).json()
    assert esc["cnpj"] == CNPJ_ESCRITORIO
    assert esc["razao_social"] == "CONTABIL EXEMPLO LTDA"
    assert esc["logradouro"] == "AVENIDA SANTOS DUMONT"
    assert esc["cep"] == "60150160"
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["papel"] == "admin"


def test_cadastro_rejeita_senha_fraca_e_cnpj_invalido(client):
    base = {"nome": "Xavier", "email": "a@b.com", "aceite_termos": True}
    r = client.post("/api/v1/auth/cadastro", json={**base, "cnpj": "11.111.111/1111-11", "senha": SENHA})
    assert r.status_code == 422
    r = client.post("/api/v1/auth/cadastro", json={**base, "cnpj": CNPJ_ESCRITORIO, "senha": "fraca12345"})
    assert r.status_code == 422
    assert "maiúscula" in r.json()["detail"][0]["msg"]


def test_login_sem_otp_nao_da_acesso_e_otp_errado_falha(client, caixa, admin):
    r = client.post("/api/v1/auth/login", json={"email": "admin@contabil.com", "senha": SENHA})
    desafio = r.json()["desafio_id"]
    assert client.get("/api/v1/clientes").status_code == 401
    r = client.post("/api/v1/auth/otp/verificar", json={"desafio_id": desafio, "codigo": "000000" if ultimo_codigo(caixa) != "000000" else "111111"})
    assert r.status_code == 400


def test_otp_bloqueia_apos_tentativas_e_nao_pode_ser_reutilizado(client, caixa, admin):
    r = client.post("/api/v1/auth/login", json={"email": "admin@contabil.com", "senha": SENHA})
    desafio, codigo = r.json()["desafio_id"], ultimo_codigo(caixa)
    errado = "000000" if codigo != "000000" else "111111"
    for _ in range(5):
        client.post("/api/v1/auth/otp/verificar", json={"desafio_id": desafio, "codigo": errado})
    r = client.post("/api/v1/auth/otp/verificar", json={"desafio_id": desafio, "codigo": codigo})
    assert r.status_code == 400  # esgotou as tentativas


def test_login_nao_revela_se_email_existe(client, admin):
    r1 = client.post("/api/v1/auth/login", json={"email": "naoexiste@x.com", "senha": "Qualquer@123"})
    r2 = client.post("/api/v1/auth/login", json={"email": "admin@contabil.com", "senha": "Errada@12345"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_bloqueio_apos_falhas(client, admin):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "admin@contabil.com", "senha": "Errada@12345"})
    r = client.post("/api/v1/auth/login", json={"email": "admin@contabil.com", "senha": SENHA})
    assert r.status_code == 429


def test_refresh_rotativo_e_deteccao_de_reuso(client, caixa, admin):
    antigo = client.cookies.get("bpo_refresh")
    assert antigo
    r = client.post("/api/v1/auth/refresh", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and r.json()["access_token"]
    # sem o cabeçalho anti-CSRF
    assert client.post("/api/v1/auth/refresh").status_code == 401
    # reuso do token antigo revoga todas as sessões
    client.cookies.set("bpo_refresh", antigo, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh", headers={"X-Requested-With": "fetch"}).status_code == 401


def test_alterar_senha_invalida_tokens_antigos(client, caixa, admin):
    nova = "NovaSenha#2026x"
    r = client.post("/api/v1/auth/senha/alterar", json={"senha_atual": SENHA, "nova_senha": nova}, headers=admin)
    assert r.status_code == 200, r.text

    assert client.get("/api/v1/auth/me", headers=admin).status_code == 401
    h = login(client, caixa, "admin@contabil.com", nova)
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200


def test_alterar_senha_exige_senha_atual(client, admin):
    r = client.post("/api/v1/auth/senha/alterar", json={"senha_atual": "Errada@12345", "nova_senha": "NovaSenha#2026x"}, headers=admin)
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"][-1] == "senha_atual"


def test_recuperar_senha(client, caixa, admin):
    r = client.post("/api/v1/auth/senha/recuperar", json={"email": "admin@contabil.com"})
    assert r.status_code == 200
    desafio = r.json()["desafio_id"]
    codigo = ultimo_codigo(caixa)
    assert "redefinir" in caixa[-1]["corpo"]
    r = client.post("/api/v1/auth/senha/redefinir", json={"desafio_id": desafio, "codigo": codigo, "nova_senha": "Recuperada@2026"})
    assert r.status_code == 200, r.text
    login(client, caixa, "admin@contabil.com", "Recuperada@2026")
    # e-mail inexistente: mesma resposta, nenhum e-mail enviado
    n = len(caixa)
    r = client.post("/api/v1/auth/senha/recuperar", json={"email": "ninguem@x.com"})
    assert r.status_code == 200 and len(caixa) == n


def test_logout_revoga_refresh(client, admin):
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.post("/api/v1/auth/refresh", headers={"X-Requested-With": "fetch"}).status_code == 401
