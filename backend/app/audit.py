"""Trilha de auditoria automática.

Um listener `after_flush` do SQLAlchemy registra INSERT/UPDATE/DELETE de todas as
entidades de negócio (exceto as listadas em TABELAS_IGNORADAS), com valores antes/depois.
O contexto (usuário, IP, request id) vem de contextvars preenchidas a cada requisição.
A gravação usa um INSERT direto na conexão para fazer parte da mesma transação:
se a operação de negócio falhar (rollback), a auditoria também é desfeita.
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, inspect, insert
from sqlalchemy.orm import Session

from .models import Auditoria, agora


@dataclass
class ContextoAuditoria:
    usuario_id: int | None = None
    usuario_email: str | None = None
    escritorio_id: int | None = None
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None


CONTEXTO_PADRAO = ContextoAuditoria()
contexto_atual: contextvars.ContextVar[ContextoAuditoria] = contextvars.ContextVar(
    "contexto_auditoria", default=CONTEXTO_PADRAO
)

TABELAS_IGNORADAS = {"auditoria", "desafio_otp", "sessao_refresh"}
CAMPOS_SENSIVEIS = {"senha_hash", "codigo_hash", "token_hash", "hash"}
CAMPOS_VOLUMOSOS = {"xml", "arquivo", "conteudo", "dados_receita"}


def _serializar(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, bytes):
        return f"<{len(valor)} bytes>"
    return valor


def _valor_seguro(campo: str, valor: Any) -> Any:
    if campo in CAMPOS_SENSIVEIS:
        return "***"
    if campo in CAMPOS_VOLUMOSOS and valor is not None:
        return "<omitido>"
    return _serializar(valor)


def _snapshot(obj) -> dict:
    ins = inspect(obj)
    dados = {}
    for attr in ins.mapper.column_attrs:
        if attr.key in ins.unloaded:
            continue
        dados[attr.key] = _valor_seguro(attr.key, getattr(obj, attr.key))
    return dados


def _pk(obj) -> str | None:
    ident = inspect(obj).mapper.primary_key_from_instance(obj)
    return ",".join(str(i) for i in ident) if ident and None not in ident else None


def _linha(acao: str, obj, antes, depois, campos) -> dict:
    ctx = contexto_atual.get()
    escritorio_id = getattr(obj, "escritorio_id", None) or ctx.escritorio_id
    return {
        "escritorio_id": escritorio_id,
        "usuario_id": ctx.usuario_id,
        "usuario_email": ctx.usuario_email,
        "acao": acao,
        "tabela": obj.__tablename__,
        "registro_id": _pk(obj),
        "dados_antes": antes,
        "dados_depois": depois,
        "campos_alterados": campos,
        "ip": ctx.ip,
        "user_agent": ctx.user_agent,
        "request_id": ctx.request_id,
        "criado_em": agora(),
    }


@event.listens_for(Session, "after_flush")
def _auditar(session: Session, _flush_context) -> None:
    linhas: list[dict] = []
    for obj in session.new:
        if getattr(obj, "__tablename__", None) in TABELAS_IGNORADAS:
            continue
        linhas.append(_linha("INSERT", obj, None, _snapshot(obj), None))
    for obj in session.dirty:
        if getattr(obj, "__tablename__", None) in TABELAS_IGNORADAS:
            continue
        ins = inspect(obj)
        antes, depois, campos = {}, {}, []
        for attr in ins.mapper.column_attrs:
            hist = ins.attrs[attr.key].history
            if not hist.has_changes():
                continue
            velho = hist.deleted[0] if hist.deleted else None
            novo = hist.added[0] if hist.added else None
            if velho == novo or attr.key in ("atualizado_em",):
                continue
            campos.append(attr.key)
            antes[attr.key] = _valor_seguro(attr.key, velho)
            depois[attr.key] = _valor_seguro(attr.key, novo)
        if campos:
            linhas.append(_linha("UPDATE", obj, antes, depois, campos))
    for obj in session.deleted:
        if getattr(obj, "__tablename__", None) in TABELAS_IGNORADAS:
            continue
        linhas.append(_linha("DELETE", obj, _snapshot(obj), None, None))
    if linhas:
        session.connection().execute(insert(Auditoria.__table__), linhas)


def registrar_evento(
    db: Session,
    acao: str,
    *,
    tabela: str | None = None,
    registro_id: Any = None,
    detalhes: dict | None = None,
    usuario_id: int | None = None,
    usuario_email: str | None = None,
    escritorio_id: int | None = None,
) -> None:
    """Eventos de negócio/segurança que não são simples alterações de linha (LOGIN, EXPORTACAO...)."""
    ctx = contexto_atual.get()
    db.add(
        Auditoria(
            escritorio_id=escritorio_id or ctx.escritorio_id,
            usuario_id=usuario_id or ctx.usuario_id,
            usuario_email=usuario_email or ctx.usuario_email,
            acao=acao,
            tabela=tabela,
            registro_id=str(registro_id) if registro_id is not None else None,
            dados_depois=detalhes,
            ip=ctx.ip,
            user_agent=ctx.user_agent,
            request_id=ctx.request_id,
        )
    )
