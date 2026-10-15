import os

os.environ.update(
    BPO_DATABASE_URL="sqlite:///:memory:",
    BPO_AMBIENTE="teste",
    BPO_COOKIE_SEGURO="false",
    BPO_RATE_LIMIT_AUTH_POR_MINUTO="10000",
    BPO_CNPJ_PROVEDOR="brasilapi",
)

import re  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import email as email_svc  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import cnpj as cnpj_svc  # noqa: E402

from .util import gerar_cnpj  # noqa: E402

CNPJ_ESCRITORIO = gerar_cnpj("112223330001")
CNPJ_CLIENTE = gerar_cnpj("445556660001")
CNPJ_FORNECEDOR = gerar_cnpj("778889990001")
CNPJ_COMPRADOR = gerar_cnpj("121212120001")
SENHA = "Senha@Forte123"

BASE_RECEITA = {
    CNPJ_ESCRITORIO: {"razao_social": "CONTABIL EXEMPLO LTDA", "nome_fantasia": "Contábil Exemplo", "municipio": "FORTALEZA", "uf": "CE"},
    CNPJ_CLIENTE: {"razao_social": "COMERCIO MODELO LTDA", "nome_fantasia": "Modelo", "municipio": "FORTALEZA", "uf": "CE"},
}


def _receita_falsa(request: httpx.Request) -> httpx.Response:
    cnpj = request.url.path.rstrip("/").rsplit("/", 1)[-1]
    if cnpj not in BASE_RECEITA:
        return httpx.Response(404, json={"message": "não encontrado"})
    return httpx.Response(
        200,
        json={
            "cnpj": cnpj,
            "descricao_situacao_cadastral": "ATIVA",
            "cnae_fiscal": 6920601,
            "cnae_fiscal_descricao": "Atividades de contabilidade",
            "logradouro": "SANTOS DUMONT",
            "descricao_tipo_de_logradouro": "AVENIDA",
            "numero": "100",
            "bairro": "ALDEOTA",
            "cep": "60150-160",
            "email": "contato@exemplo.com.br",
            **BASE_RECEITA[cnpj],
        },
    )


@pytest.fixture(autouse=True)
def ambiente():
    Base.metadata.create_all(engine)
    caixa: list[dict] = []
    email_svc.caixa_saida_testes = caixa
    cnpj_svc.transporte_http = httpx.MockTransport(_receita_falsa)
    yield caixa
    email_svc.caixa_saida_testes = None
    cnpj_svc.transporte_http = None
    Base.metadata.drop_all(engine)


@pytest.fixture
def caixa(ambiente):
    return ambiente


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def ultimo_codigo(caixa) -> str:
    return re.search(r"\b(\d{6})\b", caixa[-1]["corpo"]).group(1)


def login(client, caixa, email, senha=SENHA) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/auth/otp/verificar", json={"desafio_id": r.json()["desafio_id"], "codigo": ultimo_codigo(caixa)})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def cadastrar_escritorio(client, caixa, email="admin@contabil.com", cnpj=CNPJ_ESCRITORIO) -> dict:
    r = client.post(
        "/api/v1/auth/cadastro",
        json={"cnpj": cnpj, "nome": "Ana Contadora", "email": email, "senha": SENHA, "crc": "CE-012345/O", "aceite_termos": True},
    )
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/otp/verificar", json={"desafio_id": r.json()["desafio_id"], "codigo": ultimo_codigo(caixa)})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin(client, caixa):
    return cadastrar_escritorio(client, caixa)


@pytest.fixture
def cliente_id(client, admin):
    r = client.post("/api/v1/clientes", json={"cnpj": CNPJ_CLIENTE, "regime_tributario": "presumido"}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()["id"]
