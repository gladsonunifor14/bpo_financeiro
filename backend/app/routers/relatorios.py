"""Relatórios (Fluxo de Caixa, DRE, Gerencial), painel do escritório e trilha de auditoria."""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import registrar_evento
from ..database import get_db
from ..models import (
    Auditoria,
    Cliente,
    ContaBancaria,
    Contrato,
    ItemNota,
    LancamentoBancario,
    NotaFiscal,
    Procuracao,
    Usuario,
)
from ..schemas import AuditoriaSaida, Pagina
from ..security import equipe_escritorio, obter_cliente_autorizado, somente_admin, usuario_atual
from ..services import relatorios as rel

router = APIRouter(prefix="/api/v1")


def _periodo(inicio: date | None, fim: date | None) -> tuple[date, date]:
    hoje = date.today()
    fim = fim or hoje
    inicio = inicio or date(fim.year, 1, 1)
    if inicio > fim:
        raise HTTPException(422, [{"loc": ["query", "inicio"], "msg": "Início posterior ao fim", "type": "periodo"}])
    if (fim - inicio).days > 366 * 3:
        raise HTTPException(422, [{"loc": ["query", "fim"], "msg": "Período máximo de 3 anos", "type": "periodo"}])
    return inicio, fim


def _br(v) -> str:
    return f"{v:.2f}".replace(".", ",")


def _csv(nome: str, linhas: list[list]) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    for linha in linhas:
        # Neutraliza injeção de fórmulas em planilhas (CSV injection)
        w.writerow([("'" + c) if isinstance(c, str) and c[:1] in ("=", "+", "-", "@") else c for c in linha])
    return StreamingResponse(
        iter(["﻿" + buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}.csv"'},
    )


def _rodape(r: dict) -> list[list]:
    e = r["elaborado_por"]
    return [[], [f"Elaborado por: {e['razao_social']} - CNPJ {e['cnpj']}" + (f" - CRC {e['crc']}" if e.get("crc") else "")]]


@router.get("/clientes/{cliente_id}/relatorios/fluxo-caixa", tags=["Relatórios"], summary="Fluxo de Caixa realizado e projetado")
def fluxo_caixa(
    cliente_id: int,
    inicio: date | None = None,
    fim: date | None = None,
    saldo_inicial: Decimal = Query(Decimal(0), max_digits=16, decimal_places=2),
    formato: str = Query("json", pattern="^(json|csv)$"),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    cliente = obter_cliente_autorizado(db, usuario, cliente_id)
    inicio, fim = _periodo(inicio, fim)
    r = rel.fluxo_caixa(db, cliente, inicio, fim, saldo_inicial)
    if formato == "csv":
        linhas = [[r["titulo"], cliente.razao_social], ["Mês", "Saldo inicial", "Entradas", "Saídas", "Variação", "Saldo final"]]
        linhas += [[m["mes"], _br(m["saldo_inicial"]), _br(m["entradas"]), _br(m["saidas"]), _br(m["variacao"]), _br(m["saldo_final"])] for m in r["realizado"]]
        return _csv("fluxo-de-caixa", linhas + _rodape(r))
    return r


@router.get("/clientes/{cliente_id}/relatorios/dre", tags=["Relatórios"], summary="DRE gerencial mensal")
def dre(
    cliente_id: int,
    inicio: date | None = None,
    fim: date | None = None,
    formato: str = Query("json", pattern="^(json|csv)$"),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    cliente = obter_cliente_autorizado(db, usuario, cliente_id)
    inicio, fim = _periodo(inicio, fim)
    r = rel.dre(db, cliente, inicio, fim)
    if formato == "csv":
        linhas = [[r["titulo"], cliente.razao_social], ["Linha", *r["meses"], "Total"]]
        for linha in r["linhas"]:
            linhas.append([linha["rotulo"], *[_br(linha["valores"][m]) for m in r["meses"]], _br(linha["total"])])
            for c in linha["contas"]:
                linhas.append([f"   {c['codigo']} {c['nome']}", *[_br(c["valores"][m]) for m in r["meses"]], _br(c["total"])])
        return _csv("dre", linhas + _rodape(r))
    return r


@router.get("/clientes/{cliente_id}/relatorios/gerencial", tags=["Relatórios"], summary="Indicadores gerenciais (painel BI)")
def gerencial(cliente_id: int, inicio: date | None = None, fim: date | None = None, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    cliente = obter_cliente_autorizado(db, usuario, cliente_id)
    inicio, fim = _periodo(inicio, fim)
    return rel.gerencial(db, cliente, inicio, fim)


@router.get("/clientes/{cliente_id}/pre-requisitos", tags=["Relatórios"], summary="O que falta para gerar os relatórios")
def pre_requisitos(cliente_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Usado pela interface para desabilitar operações impossíveis e exibir chamadas para ação."""
    cliente = obter_cliente_autorizado(db, usuario, cliente_id)
    contas = db.scalar(select(func.count(ContaBancaria.id)).where(ContaBancaria.cliente_id == cliente.id)) or 0
    notas = db.scalar(select(func.count(NotaFiscal.id)).where(NotaFiscal.cliente_id == cliente.id)) or 0
    lancs = db.scalar(select(func.count(LancamentoBancario.id)).where(LancamentoBancario.cliente_id == cliente.id)) or 0
    pend = db.scalar(select(func.count(LancamentoBancario.id)).where(LancamentoBancario.cliente_id == cliente.id, LancamentoBancario.status_classificacao.in_(("pendente", "ia_sugerida")))) or 0
    itens_pend = db.scalar(select(func.count(ItemNota.id)).join(NotaFiscal).where(NotaFiscal.cliente_id == cliente.id, ItemNota.conta_id.is_(None))) or 0
    contrato = db.scalar(select(Contrato.status).where(Contrato.cliente_id == cliente.id).order_by(Contrato.criado_em.desc()))
    return {
        "contas_bancarias": contas,
        "notas_fiscais": notas,
        "lancamentos": lancs,
        "lancamentos_a_revisar": pend,
        "itens_nota_sem_classificacao": itens_pend,
        "contrato_status": contrato,
        "pode_gerar_fluxo_caixa": lancs > 0,
        "pode_gerar_dre": (notas + lancs) > 0,
    }


# ------------------------------------------------------------------ painel do escritório
@router.get("/painel", tags=["Relatórios"], summary="Resumo do escritório (pendências e alertas)")
def painel(usuario: Usuario = Depends(equipe_escritorio), db: Session = Depends(get_db)):
    esc = usuario.escritorio_id
    hoje = date.today()
    clientes = db.scalar(select(func.count(Cliente.id)).where(Cliente.escritorio_id == esc, Cliente.ativo)) or 0
    procs = db.execute(
        select(Procuracao.id, Procuracao.data_fim, Cliente.razao_social)
        .join(Cliente, Procuracao.cliente_id == Cliente.id)
        .where(Procuracao.escritorio_id == esc, Procuracao.revogada_em.is_(None), Procuracao.data_fim.is_not(None),
               Procuracao.data_fim <= hoje + timedelta(days=30))
        .order_by(Procuracao.data_fim)
    ).all()
    pend_por_cliente = db.execute(
        select(Cliente.id, Cliente.razao_social, func.count(LancamentoBancario.id))
        .join(LancamentoBancario, LancamentoBancario.cliente_id == Cliente.id)
        .where(Cliente.escritorio_id == esc, LancamentoBancario.status_classificacao.in_(("pendente", "ia_sugerida")))
        .group_by(Cliente.id, Cliente.razao_social)
        .order_by(func.count(LancamentoBancario.id).desc())
        .limit(10)
    ).all()
    aguardando = db.scalar(select(func.count(Contrato.id)).where(Contrato.escritorio_id == esc, Contrato.status == "aguardando_aceite")) or 0
    return {
        "clientes_ativos": clientes,
        "contratos_aguardando_aceite": aguardando,
        "procuracoes_vencendo": [
            {"id": i, "cliente": nome, "data_fim": f.isoformat(), "vencida": f < hoje} for i, f, nome in procs
        ],
        "lancamentos_a_revisar": [{"cliente_id": i, "cliente": nome, "quantidade": q} for i, nome, q in pend_por_cliente],
    }


# ------------------------------------------------------------------ auditoria
@router.get("/auditoria", response_model=Pagina, tags=["Auditoria"], summary="Consultar trilha de auditoria")
def consultar_auditoria(
    tabela: str | None = Query(default=None, max_length=60),
    registro_id: str | None = Query(default=None, max_length=60),
    usuario_id: int | None = None,
    acao: str | None = Query(default=None, max_length=30),
    inicio: date | None = None,
    fim: date | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    usuario: Usuario = Depends(somente_admin),
    db: Session = Depends(get_db),
):
    """Somente leitura (append-only): quem, quando e o que foi alterado, com valores antes/depois."""
    q = select(Auditoria).where(Auditoria.escritorio_id == usuario.escritorio_id)
    if tabela:
        q = q.where(Auditoria.tabela == tabela)
    if registro_id:
        q = q.where(Auditoria.registro_id == registro_id)
    if usuario_id:
        q = q.where(Auditoria.usuario_id == usuario_id)
    if acao:
        q = q.where(Auditoria.acao == acao.upper())
    if inicio:
        q = q.where(Auditoria.criado_em >= inicio)
    if fim:
        q = q.where(Auditoria.criado_em < fim + timedelta(days=1))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    itens = db.scalars(q.order_by(Auditoria.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
    registrar_evento(db, "CONSULTA_AUDITORIA", detalhes={"tabela": tabela, "registro_id": registro_id})
    db.commit()
    return Pagina(total=total, itens=[AuditoriaSaida.model_validate(a).model_dump(mode="json") for a in itens])
