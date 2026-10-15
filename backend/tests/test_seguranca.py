def test_cabecalhos_de_seguranca(client):
    r = client.get("/api/saude")
    h = r.headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "unsafe-inline" not in h["content-security-policy"]
    assert h["cache-control"] == "no-store"
    assert h["x-request-id"]


def test_swagger_documentado(client):
    spec = client.get("/api/openapi.json").json()
    assert spec["info"]["title"].startswith("BPO Financeiro")
    assert "/api/v1/auth/otp/verificar" in spec["paths"]
    assert "/api/v1/clientes/{cliente_id}/relatorios/dre" in spec["paths"]
    esquemas = spec["components"]["securitySchemes"]
    assert {"HTTPBearer", "APIKeyHeader"} <= set(esquemas)
    assert client.get("/api/docs").status_code == 200


def test_rotas_protegidas_exigem_autenticacao(client):
    spec = client.get("/api/openapi.json").json()
    publicas = {"/api/saude", "/api/v1/auth/cadastro", "/api/v1/auth/login", "/api/v1/auth/otp/verificar", "/api/v1/auth/refresh",
                "/api/v1/auth/logout", "/api/v1/auth/senha/recuperar", "/api/v1/auth/senha/redefinir"}
    for caminho, metodos in spec["paths"].items():
        if caminho in publicas:
            continue
        url = caminho.replace("{", "").replace("}", "")
        url = "/".join("1" if p.endswith("_id") else p for p in url.split("/"))
        for metodo in metodos:
            r = client.request(metodo.upper(), url)
            assert r.status_code in (401, 422), f"{metodo} {caminho} -> {r.status_code}"


def test_token_adulterado_rejeitado(client, admin):
    token = admin["Authorization"].split()[1]
    cab, corpo, ass = token.split(".")
    adulterado = f"{cab}.{corpo}.{ass[::-1]}"
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {adulterado}"}).status_code == 401
    import jwt

    falso = jwt.encode({"sub": "1", "typ": "access", "ver": 0, "iat": 1, "exp": 9999999999}, "segredo-errado", algorithm="HS256")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {falso}"}).status_code == 401


def test_rate_limit_login(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_limit_auth_por_minuto", 3)
    codigos = [client.post("/api/v1/auth/login", json={"email": "x@y.com", "senha": "a"}).status_code for _ in range(5)]
    assert codigos[-1] == 429


def test_frontend_servido_com_csp(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_url_postgres_do_render_recebe_driver_psycopg():
    from app.config import Settings

    assert Settings(database_url="postgres://u:s@h:5432/bpo").database_url == "postgresql+psycopg://u:s@h:5432/bpo"
    assert Settings(database_url="postgresql://u:s@h/bpo").database_url == "postgresql+psycopg://u:s@h/bpo"
    assert Settings(database_url="sqlite:///x.db").database_url == "sqlite:///x.db"
