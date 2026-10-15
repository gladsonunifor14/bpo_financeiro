"""Hash de senhas (Argon2id), tokens JWT, chaves de API e dependências de autorização."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import CONTEXTO_PADRAO, ContextoAuditoria, contexto_atual
from .config import get_settings
from .database import get_db
from .models import ChaveApi, Cliente, Usuario, agora

_ph = PasswordHasher()  # Argon2id com parâmetros recomendados pela RFC 9106


def hash_senha(senha: str) -> str:
    return _ph.hash(senha)


def verificar_senha(senha: str, hash_: str) -> bool:
    try:
        return _ph.verify(hash_, senha)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# Hash fixo para igualar o tempo de resposta quando o e-mail não existe (anti-enumeração)
HASH_FICTICIO = _ph.hash(secrets.token_urlsafe(16))

_REGRAS_SENHA = [
    (r".{10,}", "ter ao menos 10 caracteres"),
    (r"[a-z]", "conter letra minúscula"),
    (r"[A-Z]", "conter letra maiúscula"),
    (r"\d", "conter número"),
    (r"[^A-Za-z0-9]", "conter caractere especial"),
]


def problemas_senha(senha: str) -> list[str]:
    return [msg for padrao, msg in _REGRAS_SENHA if not re.search(padrao, senha)]


def gerar_codigo_otp() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_token(token: str) -> str:
    """SHA-256 para tokens de alta entropia (refresh/API key) — busca por igualdade."""
    return hashlib.sha256(token.encode()).hexdigest()


def comparar_constante(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def criar_access_token(usuario: Usuario) -> str:
    s = get_settings()
    agora_ = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario.id),
        "esc": usuario.escritorio_id,
        "papel": usuario.papel,
        "ver": usuario.versao_token or 0,
        "iat": agora_,
        "exp": agora_ + timedelta(minutes=s.access_token_minutos),
        "jti": str(uuid.uuid4()),
        "typ": "access",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algoritmo)


def decodificar_access_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(
        token, s.jwt_secret, algorithms=[s.jwt_algoritmo], options={"require": ["exp", "sub", "iat"]}
    )


_bearer = HTTPBearer(auto_error=False, description="Token JWT obtido em /api/v1/auth/otp/verificar")
_api_key = APIKeyHeader(name="X-API-Key", auto_error=False, description="Chave de integração")

_NAO_AUTENTICADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Não autenticado ou sessão expirada",
    headers={"WWW-Authenticate": "Bearer"},
)


def _usuario_por_api_key(db: Session, chave: str) -> Usuario | None:
    registro = db.scalar(select(ChaveApi).where(ChaveApi.hash == hash_token(chave)))
    if not registro or registro.revogada_em:
        return None
    registro.ultimo_uso_em = agora()
    return db.get(Usuario, registro.usuario_id)


def usuario_atual(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    chave: str | None = Depends(_api_key),
    db: Session = Depends(get_db),
) -> Usuario:
    usuario: Usuario | None = None
    if cred and cred.scheme.lower() == "bearer":
        try:
            payload = decodificar_access_token(cred.credentials)
        except jwt.PyJWTError:
            raise _NAO_AUTENTICADO
        if payload.get("typ") != "access":
            raise _NAO_AUTENTICADO
        usuario = db.get(Usuario, int(payload["sub"]))
        if usuario and payload.get("ver") != (usuario.versao_token or 0):
            raise _NAO_AUTENTICADO
    elif chave:
        usuario = _usuario_por_api_key(db, chave)
    if not usuario or not usuario.ativo:
        raise _NAO_AUTENTICADO
    # O objeto de contexto é criado por requisição no middleware e mutado aqui: dependências
    # síncronas rodam em threads com cópias do contexto, então um .set() não seria visto
    # pelo endpoint — já a mutação do mesmo objeto é.
    ctx = contexto_atual.get()
    if ctx is CONTEXTO_PADRAO:
        ctx = ContextoAuditoria()
        contexto_atual.set(ctx)
    ctx.usuario_id = usuario.id
    ctx.usuario_email = usuario.email
    ctx.escritorio_id = usuario.escritorio_id
    return usuario


def exigir_papel(*papeis: str):
    def _dep(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
        if usuario.papel not in papeis:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Seu perfil não tem permissão para esta operação")
        return usuario

    return _dep


equipe_escritorio = exigir_papel("admin", "analista")
somente_admin = exigir_papel("admin")


def obter_cliente_autorizado(db: Session, usuario: Usuario, cliente_id: int) -> Cliente:
    """Garante isolamento: mesmo escritório e, para perfil cliente, apenas a própria empresa.
    Responde 404 (e não 403) para não revelar a existência de registros de outros tenants."""
    cliente = db.get(Cliente, cliente_id)
    if (
        not cliente
        or cliente.escritorio_id != usuario.escritorio_id
        or (usuario.papel == "cliente" and usuario.cliente_id != cliente.id)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado")
    return cliente


def gerar_chave_api() -> tuple[str, str]:
    """Retorna (chave_completa, prefixo). A chave só é exibida uma vez."""
    corpo = secrets.token_urlsafe(32)
    chave = f"bpo_{corpo}"
    return chave, chave[:12]
