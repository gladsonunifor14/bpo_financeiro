"""Relatórios: Fluxo de Caixa (realizado e projetado), DRE e indicadores gerenciais.

Fontes de dados da DRE (regime de competência gerencial):
  * Itens de NF-e classificados por CFOP/manual (receitas, devoluções, compras, despesas);
  * ICMS/PIS/COFINS destacados nas NF-e emitidas, proporcionais aos itens de receita;
  * Lançamentos bancários classificados em contas de resultado (despesas sem nota,
    tarifas, folha, etc.). Recebimentos/pagamentos de notas devem ser classificados em
    contas 'nao_dre' (9.1.01/9.1.02) para não duplicar valores — a DRE expõe a origem;
  * Extratos de aplicações (rendimentos, IRRF/IOF, taxa de administração).
O Fluxo de Caixa usa somente lançamentos bancários (realizado) e duplicatas das NF-e (projetado).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Cliente,
    Duplicata,
    Escritorio,
    ItemNota,
    LancamentoBancario,
    NotaFiscal,
    PlanoConta,
    PosicaoAplicacao,
)
from . import investimentos
from .plano_contas import GRUPOS_DRE

ZERO = Decimal("0")


def meses_entre(inicio: date, fim: date) -> list[str]:
    saida, a, m = [], inicio.year, inicio.month
    while (a, m) <= (fim.year, fim.month):
        saida.append(f"{a:04d}-{m:02d}")
        m += 1
        if m > 12:
            a, m = a + 1, 1
    return saida


def _mes(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _f(v: Decimal | None) -> float:
    return float((v or ZERO).quantize(Decimal("0.01")))


def cabecalho(db: Session, cliente: Cliente, titulo: str, inicio: date, fim: date) -> dict:
    esc = db.get(Escritorio, cliente.escritorio_id)
    return {
        "titulo": titulo,
        "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
        "cliente": {"id": cliente.id, "razao_social": cliente.razao_social, "cnpj": cliente.cnpj},
        "elaborado_por": {
            "razao_social": esc.razao_social,
            "nome_fantasia": esc.nome_fantasia,
            "cnpj": esc.cnpj,
            "crc": esc.crc,
            "responsavel_tecnico": esc.responsavel_tecnico,
            "municipio": esc.municipio,
            "uf": esc.uf,
        },
    }


# ------------------------------------------------------------------ fluxo de caixa
def fluxo_caixa(db: Session, cliente: Cliente, inicio: date, fim: date, saldo_inicial: Decimal = ZERO) -> dict:
    meses = meses_entre(inicio, fim)
    lancs = db.execute(
        select(LancamentoBancario, PlanoConta)
        .outerjoin(PlanoConta, LancamentoBancario.conta_id == PlanoConta.id)
        .where(
            LancamentoBancario.cliente_id == cliente.id,
            LancamentoBancario.data.between(inicio, fim),
        )
    ).all()
    entradas = defaultdict(lambda: ZERO)
    saidas = defaultdict(lambda: ZERO)
    por_conta: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    pendentes = 0
    for lanc, conta in lancs:
        m = _mes(lanc.data)
        if lanc.natureza == "C":
            entradas[m] += lanc.valor
        else:
            saidas[m] += lanc.valor
        chave = (conta.codigo, conta.nome) if conta else ("—", "Não classificado")
        if not conta:
            pendentes += 1
        por_conta[(lanc.natureza, *chave)][m] += lanc.valor

    saldo = saldo_inicial
    linhas_mes = []
    for m in meses:
        abertura = saldo
        saldo = saldo + entradas[m] - saidas[m]
        linhas_mes.append(
            {
                "mes": m,
                "saldo_inicial": _f(abertura),
                "entradas": _f(entradas[m]),
                "saidas": _f(saidas[m]),
                "variacao": _f(entradas[m] - saidas[m]),
                "saldo_final": _f(saldo),
            }
        )

    detalhamento = [
        {
            "natureza": "entrada" if nat == "C" else "saida",
            "conta_codigo": cod,
            "conta_nome": nome,
            "valores": {m: _f(vals[m]) for m in meses},
            "total": _f(sum(vals.values(), ZERO)),
        }
        for (nat, cod, nome), vals in sorted(por_conta.items())
    ]

    # Projetado: duplicatas das NF-e (a receber = emitidas de saída; a pagar = recebidas)
    dups = db.execute(
        select(Duplicata, NotaFiscal.tipo, NotaFiscal.tipo_operacao, NotaFiscal.emitente_nome, NotaFiscal.destinatario_nome, NotaFiscal.numero)
        .join(NotaFiscal, Duplicata.nota_id == NotaFiscal.id)
        .where(NotaFiscal.cliente_id == cliente.id, Duplicata.vencimento.between(inicio, fim))
        .order_by(Duplicata.vencimento)
    ).all()
    receber = defaultdict(lambda: ZERO)
    pagar = defaultdict(lambda: ZERO)
    for dup, tipo, op, emit, dest, num in dups:
        alvo = receber if (tipo == "emitida" and op == "saida") else pagar
        alvo[_mes(dup.vencimento)] += dup.valor

    return {
        **cabecalho(db, cliente, "Fluxo de Caixa", inicio, fim),
        "meses": meses,
        "realizado": linhas_mes,
        "detalhamento": detalhamento,
        "projetado": [
            {"mes": m, "a_receber": _f(receber[m]), "a_pagar": _f(pagar[m]), "saldo_projetado": _f(receber[m] - pagar[m])}
            for m in meses
        ],
        "totais": {
            "entradas": _f(sum(entradas.values(), ZERO)),
            "saidas": _f(sum(saidas.values(), ZERO)),
            "saldo_final": _f(saldo),
        },
        "lancamentos_nao_classificados": pendentes,
    }


# ------------------------------------------------------------------ DRE
def _acumular_dre(db: Session, cliente: Cliente, inicio: date, fim: date):
    """Retorna valores[grupo][(codigo, nome)][mes] (sempre positivos no sentido do grupo) e origens."""
    valores: dict[str, dict[tuple[str, str], dict[str, Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: ZERO))
    )
    origem = defaultdict(lambda: ZERO)
    contas = {c.codigo: c for c in db.scalars(select(PlanoConta).where(PlanoConta.escritorio_id == cliente.escritorio_id))}

    # 1) Itens de NF-e
    itens = db.execute(
        select(ItemNota, PlanoConta, NotaFiscal)
        .join(NotaFiscal, ItemNota.nota_id == NotaFiscal.id)
        .join(PlanoConta, ItemNota.conta_id == PlanoConta.id)
        .where(NotaFiscal.cliente_id == cliente.id, NotaFiscal.data_emissao.between(inicio, fim))
    ).all()
    receita_por_nota: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for item, conta, nota in itens:
        if conta.grupo == "nao_dre":
            continue
        valor = item.valor_total
        # Devolução de compra reduz o custo: entra como valor negativo no grupo de custos
        if conta.codigo == "4.1.05":
            valor = -valor
        valores[conta.grupo][(conta.codigo, conta.nome)][_mes(nota.data_emissao)] += valor
        origem["notas_fiscais"] += abs(valor)
        if conta.grupo == "receita_bruta" and nota.tipo == "emitida":
            receita_por_nota[nota.id] += item.valor_total

    # 2) Tributos destacados nas notas de venda (proporcionais aos itens de receita)
    if receita_por_nota:
        notas = db.scalars(select(NotaFiscal).where(NotaFiscal.id.in_(receita_por_nota.keys())))
        for nota in notas:
            base = nota.valor_produtos or ZERO
            fator = (receita_por_nota[nota.id] / base) if base else Decimal(1)
            m = _mes(nota.data_emissao)
            for codigo, valor in (("3.2.02", nota.valor_icms), ("3.2.03", (nota.valor_pis or ZERO) + (nota.valor_cofins or ZERO))):
                if valor and codigo in contas:
                    c = contas[codigo]
                    valores[c.grupo][(c.codigo, c.nome)][m] += (valor * fator).quantize(Decimal("0.01"))

    # 3) Lançamentos bancários em contas de resultado
    lancs = db.execute(
        select(LancamentoBancario, PlanoConta)
        .join(PlanoConta, LancamentoBancario.conta_id == PlanoConta.id)
        .where(
            LancamentoBancario.cliente_id == cliente.id,
            LancamentoBancario.data.between(inicio, fim),
            PlanoConta.grupo != "nao_dre",
        )
    ).all()
    sinais = {g: s for g, _, s in GRUPOS_DRE}
    for lanc, conta in lancs:
        # Crédito em conta de receita soma; débito em conta de receita (estorno) subtrai — e vice-versa
        positivo = (lanc.natureza == "C") == (sinais[conta.grupo] > 0)
        valor = lanc.valor if positivo else -lanc.valor
        valores[conta.grupo][(conta.codigo, conta.nome)][_mes(lanc.data)] += valor
        origem["extratos_bancarios"] += lanc.valor

    # 4) Aplicações financeiras
    posicoes = db.scalars(
        select(PosicaoAplicacao).where(
            PosicaoAplicacao.cliente_id == cliente.id, PosicaoAplicacao.competencia.between(inicio, fim)
        )
    )
    for p in posicoes:
        r = investimentos.calcular(p.saldo_inicial, p.aplicacoes, p.resgates, p.saldo_final_bruto, p.irrf, p.iof, p.taxa_administracao)
        m = _mes(p.competencia)
        for codigo, valor in (("3.3.01", r.rendimento_bruto), ("4.3.03", p.irrf + p.iof), ("4.3.04", p.taxa_administracao)):
            if valor and codigo in contas:
                c = contas[codigo]
                valores[c.grupo][(c.codigo, c.nome)][m] += valor
                origem["aplicacoes_financeiras"] += abs(valor)
    return valores, origem


def dre(db: Session, cliente: Cliente, inicio: date, fim: date) -> dict:
    meses = meses_entre(inicio, fim)
    valores, origem = _acumular_dre(db, cliente, inicio, fim)

    def total_grupo(g: str) -> dict[str, Decimal]:
        t = {m: ZERO for m in meses}
        for vals in valores.get(g, {}).values():
            for m, v in vals.items():
                if m in t:
                    t[m] += v
        return t

    tg = {g: total_grupo(g) for g, _, _ in GRUPOS_DRE}

    def combina(*partes: tuple[int, str]) -> dict[str, Decimal]:
        return {m: sum((s * tg[g][m] for s, g in partes), ZERO) for m in meses}

    receita_liquida = combina((1, "receita_bruta"), (-1, "deducoes"))
    lucro_bruto = {m: receita_liquida[m] - tg["custos"][m] for m in meses}
    resultado_operacional = {m: lucro_bruto[m] - tg["despesas_operacionais"][m] for m in meses}
    resultado_financeiro = combina((1, "receitas_financeiras"), (-1, "despesas_financeiras"))
    outras = combina((1, "outras_receitas"), (-1, "outras_despesas"))
    lair = {m: resultado_operacional[m] + resultado_financeiro[m] + outras[m] for m in meses}
    lucro_liquido = {m: lair[m] - tg["impostos_lucro"][m] for m in meses}

    def linha(chave, rotulo, serie, tipo="grupo", contas=None):
        return {
            "chave": chave,
            "rotulo": rotulo,
            "tipo": tipo,
            "valores": {m: _f(serie[m]) for m in meses},
            "total": _f(sum(serie.values(), ZERO)),
            "contas": contas or [],
        }

    def contas_do(g):
        return [
            {
                "codigo": cod,
                "nome": nome,
                "valores": {m: _f(vals.get(m, ZERO)) for m in meses},
                "total": _f(sum((vals.get(m, ZERO) for m in meses), ZERO)),
            }
            for (cod, nome), vals in sorted(valores.get(g, {}).items())
        ]

    rot = {g: r for g, r, _ in GRUPOS_DRE}
    linhas = [
        linha("receita_bruta", rot["receita_bruta"], tg["receita_bruta"], contas=contas_do("receita_bruta")),
        linha("deducoes", rot["deducoes"], tg["deducoes"], contas=contas_do("deducoes")),
        linha("receita_liquida", "(=) Receita líquida", receita_liquida, "subtotal"),
        linha("custos", rot["custos"], tg["custos"], contas=contas_do("custos")),
        linha("lucro_bruto", "(=) Lucro bruto", lucro_bruto, "subtotal"),
        linha("despesas_operacionais", rot["despesas_operacionais"], tg["despesas_operacionais"], contas=contas_do("despesas_operacionais")),
        linha("resultado_operacional", "(=) Resultado operacional", resultado_operacional, "subtotal"),
        linha("receitas_financeiras", rot["receitas_financeiras"], tg["receitas_financeiras"], contas=contas_do("receitas_financeiras")),
        linha("despesas_financeiras", rot["despesas_financeiras"], tg["despesas_financeiras"], contas=contas_do("despesas_financeiras")),
        linha("outras_receitas", rot["outras_receitas"], tg["outras_receitas"], contas=contas_do("outras_receitas")),
        linha("outras_despesas", rot["outras_despesas"], tg["outras_despesas"], contas=contas_do("outras_despesas")),
        linha("resultado_antes_ir", "(=) Resultado antes do IR/CSLL", lair, "subtotal"),
        linha("impostos_lucro", rot["impostos_lucro"], tg["impostos_lucro"], contas=contas_do("impostos_lucro")),
        linha("lucro_liquido", "(=) Lucro líquido do período", lucro_liquido, "resultado"),
    ]
    return {
        **cabecalho(db, cliente, "Demonstração do Resultado do Exercício (gerencial)", inicio, fim),
        "meses": meses,
        "linhas": linhas,
        "origem_valores": {k: _f(v) for k, v in origem.items()},
    }


# ------------------------------------------------------------------ gerencial
def _pct(a: Decimal, b: Decimal) -> float | None:
    return round(float(a / b * 100), 2) if b else None


def gerencial(db: Session, cliente: Cliente, inicio: date, fim: date, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    d = dre(db, cliente, inicio, fim)
    tot = {linha["chave"]: Decimal(str(linha["total"])) for linha in d["linhas"]}
    rec_liq = tot["receita_liquida"]

    notas_emitidas = db.execute(
        select(func.count(NotaFiscal.id), func.coalesce(func.sum(NotaFiscal.valor_total), 0)).where(
            NotaFiscal.cliente_id == cliente.id,
            NotaFiscal.tipo == "emitida",
            NotaFiscal.tipo_operacao == "saida",
            NotaFiscal.data_emissao.between(inicio, fim),
        )
    ).one()
    qtd_nf, total_nf = notas_emitidas[0], Decimal(str(notas_emitidas[1]))

    def top(campo_doc, campo_nome, tipo, operacao):
        rows = db.execute(
            select(campo_doc, func.max(campo_nome), func.sum(NotaFiscal.valor_total).label("total"))
            .where(
                NotaFiscal.cliente_id == cliente.id,
                NotaFiscal.tipo == tipo,
                NotaFiscal.tipo_operacao == operacao,
                NotaFiscal.data_emissao.between(inicio, fim),
            )
            .group_by(campo_doc)
            .order_by(func.sum(NotaFiscal.valor_total).desc())
            .limit(5)
        ).all()
        return [{"documento": r[0], "nome": r[1], "total": _f(Decimal(str(r[2])))} for r in rows]

    despesas = []
    for linha in d["linhas"]:
        if linha["chave"] in ("custos", "despesas_operacionais", "despesas_financeiras", "outras_despesas"):
            despesas.extend({"codigo": c["codigo"], "nome": c["nome"], "total": c["total"]} for c in linha["contas"])
    despesas.sort(key=lambda x: x["total"], reverse=True)

    status = dict(
        db.execute(
            select(LancamentoBancario.status_classificacao, func.count())
            .where(LancamentoBancario.cliente_id == cliente.id, LancamentoBancario.data.between(inicio, fim))
            .group_by(LancamentoBancario.status_classificacao)
        ).all()
    )
    total_lanc = sum(status.values())
    classificados = status.get("manual", 0) + status.get("ia_confirmada", 0)

    def aberto(tipo, operacao) -> Decimal:
        v = db.scalar(
            select(func.coalesce(func.sum(Duplicata.valor), 0))
            .join(NotaFiscal, Duplicata.nota_id == NotaFiscal.id)
            .where(NotaFiscal.cliente_id == cliente.id, NotaFiscal.tipo == tipo, NotaFiscal.tipo_operacao == operacao, Duplicata.vencimento >= hoje)
        )
        return Decimal(str(v))

    a_receber = aberto("emitida", "saida")
    a_pagar = aberto("recebida", "saida")

    creditos = db.scalar(select(func.coalesce(func.sum(LancamentoBancario.valor), 0)).where(LancamentoBancario.cliente_id == cliente.id, LancamentoBancario.natureza == "C", LancamentoBancario.data <= fim))
    debitos = db.scalar(select(func.coalesce(func.sum(LancamentoBancario.valor), 0)).where(LancamentoBancario.cliente_id == cliente.id, LancamentoBancario.natureza == "D", LancamentoBancario.data <= fim))
    saldo_caixa = Decimal(str(creditos)) - Decimal(str(debitos))

    alertas = []
    if rec_liq and tot["lucro_liquido"] < 0:
        alertas.append({"nivel": "alto", "mensagem": "Resultado líquido negativo no período"})
    if total_lanc and classificados / total_lanc < 0.8:
        alertas.append(
            {"nivel": "medio", "mensagem": f"{total_lanc - classificados} lançamentos bancários ainda sem classificação confirmada"}
        )
    lb = next(item for item in d["linhas"] if item["chave"] == "lucro_bruto")
    if rec_liq and lb["total"] < 0:
        alertas.append({"nivel": "alto", "mensagem": "Margem bruta negativa: revise preços e custos"})
    if a_pagar > a_receber + max(saldo_caixa, ZERO):
        alertas.append({"nivel": "alto", "mensagem": "Contas a pagar superam a receber + saldo em caixa"})

    return {
        **cabecalho(db, cliente, "Relatório Gerencial", inicio, fim),
        "indicadores": {
            "receita_bruta": _f(tot["receita_bruta"]),
            "receita_liquida": _f(rec_liq),
            "lucro_bruto": _f(tot["lucro_bruto"]),
            "resultado_operacional": _f(tot["resultado_operacional"]),
            "lucro_liquido": _f(tot["lucro_liquido"]),
            "margem_bruta_pct": _pct(tot["lucro_bruto"], rec_liq),
            "margem_operacional_pct": _pct(tot["resultado_operacional"], rec_liq),
            "margem_liquida_pct": _pct(tot["lucro_liquido"], rec_liq),
            "notas_emitidas": qtd_nf,
            "ticket_medio": _f(total_nf / qtd_nf) if qtd_nf else 0.0,
            "saldo_caixa": _f(saldo_caixa),
            "contas_a_receber": _f(a_receber),
            "contas_a_pagar": _f(a_pagar),
            "lancamentos_total": total_lanc,
            "lancamentos_classificados_pct": round(classificados / total_lanc * 100, 1) if total_lanc else None,
        },
        "serie_mensal": {
            "meses": d["meses"],
            "receita_liquida": next(item for item in d["linhas"] if item["chave"] == "receita_liquida")["valores"],
            "lucro_liquido": next(item for item in d["linhas"] if item["chave"] == "lucro_liquido")["valores"],
        },
        "top_clientes": top(NotaFiscal.destinatario_documento, NotaFiscal.destinatario_nome, "emitida", "saida"),
        "top_fornecedores": top(NotaFiscal.emitente_documento, NotaFiscal.emitente_nome, "recebida", "saida"),
        "maiores_despesas": despesas[:10],
        "alertas": alertas,
    }
