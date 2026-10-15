"""Middlewares de segurança: cabeçalhos HTTP, contexto de auditoria e limitação de taxa."""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .audit import ContextoAuditoria, contexto_atual
from .config import get_settings

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)
# O Swagger UI carrega assets do CDN jsDelivr; política específica só para /api/docs
CSP_DOCS = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; frame-ancestors 'none'; object-src 'none'"
)


def ip_cliente(request: Request) -> str:
    # Atrás de proxy reverso, configure o uvicorn com --proxy-headers e --forwarded-allow-ips
    return request.client.host if request.client else "desconhecido"


class SegurancaMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        try:
            uuid.UUID(rid)
        except ValueError:
            rid = str(uuid.uuid4())
        token = contexto_atual.set(
            ContextoAuditoria(
                ip=ip_cliente(request),
                user_agent=(request.headers.get("user-agent") or "")[:300],
                request_id=rid,
            )
        )
        try:
            resposta = await call_next(request)
        finally:
            contexto_atual.reset(token)
        h = resposta.headers
        h["X-Request-ID"] = rid
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Content-Security-Policy"] = CSP_DOCS if request.url.path.startswith("/api/docs") else CSP
        if get_settings().producao:
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        if request.url.path.startswith("/api/"):
            h["Cache-Control"] = "no-store"
        return resposta


class LimiteTaxaMiddleware(BaseHTTPMiddleware):
    """Janela deslizante em memória por IP para rotas sensíveis (login, OTP, recuperação).
    Em produção com várias réplicas, substitua por um limitador em Redis ou no gateway/WAF."""

    PREFIXOS = ("/api/v1/auth/",)

    def __init__(self, app):
        super().__init__(app)
        self.janelas: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and request.url.path.startswith(self.PREFIXOS):
            limite = get_settings().rate_limit_auth_por_minuto
            chave = f"{ip_cliente(request)}:{request.url.path}"
            agora = time.monotonic()
            janela = self.janelas[chave]
            while janela and agora - janela[0] > 60:
                janela.popleft()
            if len(janela) >= limite:
                return JSONResponse(
                    {"detail": "Muitas tentativas. Aguarde um minuto e tente novamente."},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            janela.append(agora)
        return await call_next(request)
