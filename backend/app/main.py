"""Aplicação FastAPI do BPO Financeiro.

O frontend é "burro" (apenas exibe dados e envia formulários): toda regra de negócio,
cálculo, autorização e validação ocorre aqui no backend.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import audit  # noqa: F401  (registra o listener de auditoria)
from .config import get_settings
from .database import Base, engine
from .middleware import LimiteTaxaMiddleware, SegurancaMiddleware
from .routers import auth, cadastros, documentos, juridico, relatorios

log = logging.getLogger("bpo")

DESCRICAO = """
API do **BPO Financeiro** para escritórios de contabilidade.

### Autenticação
1. `POST /api/v1/auth/login` com e-mail e senha → recebe `desafio_id` e um código OTP por e-mail;
2. `POST /api/v1/auth/otp/verificar` com `desafio_id` e `codigo` → recebe o `access_token` (JWT, 15 min);
3. Envie `Authorization: Bearer <token>` nas demais chamadas.

Para integrações sistema-a-sistema, um administrador cria uma chave em `POST /api/v1/chaves-api`
e o sistema integrador envia o cabeçalho `X-API-Key`.

### Convenções
* Valores monetários em reais, com ponto decimal (`1234.56`); datas em ISO-8601 (`2026-01-31`).
* CNPJ aceito com ou sem máscara, inclusive no formato alfanumérico (a partir de jul/2026).
* Erros de validação seguem o formato `{"detail": [{"loc": [...], "msg": "..."}]}`.
* Toda alteração é registrada na trilha de auditoria (`GET /api/v1/auditoria`).
"""

TAGS = [
    {"name": "Autenticação", "description": "Login com senha + OTP por e-mail, refresh, troca e recuperação de senha"},
    {"name": "Cadastros", "description": "Escritório, clientes (importação pela Receita Federal) e usuários"},
    {"name": "Integração", "description": "Chaves de API para sistemas externos"},
    {"name": "Contratos, LGPD e Procurações", "description": "Contrato de adesão, termos e procurações"},
    {"name": "Plano de contas", "description": "Contas gerenciais usadas na classificação"},
    {"name": "Notas fiscais", "description": "Importação de XML de NF-e com classificação por CFOP"},
    {"name": "Extratos bancários", "description": "OFX/CSV, classificação manual e por IA"},
    {"name": "Aplicações financeiras", "description": "Rendimentos, taxas, IRRF e IOF"},
    {"name": "Open Finance", "description": "Importação automática de extratos via consentimento"},
    {"name": "Relatórios", "description": "Fluxo de Caixa, DRE e indicadores gerenciais"},
    {"name": "Auditoria", "description": "Trilha de auditoria (somente leitura)"},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Em produção, prefira migrações versionadas (Alembic); create_all é idempotente.
    Base.metadata.create_all(engine)
    yield


def criar_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="BPO Financeiro — API",
        version="1.0.0",
        description=DESCRICAO,
        openapi_tags=TAGS,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": False, "tryItOutEnabled": True},
    )

    app.add_middleware(LimiteTaxaMiddleware)
    app.add_middleware(SegurancaMiddleware)
    if s.cors_origens:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_origens,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Requested-With"],
        )

    @app.middleware("http")
    async def limitar_corpo(request: Request, call_next):
        tamanho = request.headers.get("content-length")
        if tamanho and tamanho.isdigit() and int(tamanho) > s.upload_max_bytes * 12:
            return JSONResponse({"detail": "Requisição muito grande"}, status_code=413)
        return await call_next(request)

    @app.exception_handler(Exception)
    async def erro_inesperado(request: Request, exc: Exception):
        # Nunca expõe stack trace ao cliente; o request id permite localizar o log
        log.exception("Erro não tratado em %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Erro interno. Informe o código da requisição ao suporte."}, status_code=500)

    @app.get("/api/saude", tags=["Infra"], summary="Healthcheck")
    def saude():
        return {"status": "ok"}

    for r in (auth.router, cadastros.router, juridico.router, documentos.router, relatorios.router):
        app.include_router(r)

    frontend = Path(__file__).resolve().parents[2] / "frontend"
    if s.servir_frontend and frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = criar_app()
