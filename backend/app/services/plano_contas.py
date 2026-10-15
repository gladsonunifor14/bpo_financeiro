"""Plano de contas gerencial padrão e a estrutura da DRE."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PlanoConta

# Ordem e rótulos da DRE. 'sinal' indica como o grupo compõe o resultado.
GRUPOS_DRE = [
    ("receita_bruta", "Receita operacional bruta", +1),
    ("deducoes", "(-) Deduções da receita", -1),
    ("custos", "(-) Custos (CMV/CPV/CSP)", -1),
    ("despesas_operacionais", "(-) Despesas operacionais", -1),
    ("receitas_financeiras", "(+) Receitas financeiras", +1),
    ("despesas_financeiras", "(-) Despesas financeiras", -1),
    ("outras_receitas", "(+) Outras receitas", +1),
    ("outras_despesas", "(-) Outras despesas", -1),
    ("impostos_lucro", "(-) IRPJ e CSLL", -1),
]
GRUPOS_VALIDOS = {g for g, _, _ in GRUPOS_DRE} | {"nao_dre"}

PLANO_PADRAO = [
    # Receitas
    ("3.1.01", "Venda de mercadorias", "receita_bruta"),
    ("3.1.02", "Venda de produtos de fabricação própria", "receita_bruta"),
    ("3.1.03", "Prestação de serviços", "receita_bruta"),
    ("3.1.09", "Outras receitas operacionais", "receita_bruta"),
    # Deduções
    ("3.2.01", "Devoluções de vendas", "deducoes"),
    ("3.2.02", "ICMS sobre vendas", "deducoes"),
    ("3.2.03", "PIS e COFINS sobre vendas", "deducoes"),
    ("3.2.04", "IPI faturado", "deducoes"),
    ("3.2.05", "Simples Nacional / ISS", "deducoes"),
    # Custos
    ("4.1.01", "Compras de mercadorias para revenda", "custos"),
    ("4.1.02", "Compras de matéria-prima e insumos", "custos"),
    ("4.1.03", "Serviços tomados vinculados à produção", "custos"),
    ("4.1.04", "Fretes sobre compras", "custos"),
    ("4.1.05", "Devoluções de compras", "custos"),
    # Despesas operacionais
    ("4.2.01", "Salários e encargos", "despesas_operacionais"),
    ("4.2.02", "Pró-labore", "despesas_operacionais"),
    ("4.2.03", "Aluguel e condomínio", "despesas_operacionais"),
    ("4.2.04", "Energia, água e telecomunicações", "despesas_operacionais"),
    ("4.2.05", "Material de uso e consumo", "despesas_operacionais"),
    ("4.2.06", "Serviços de terceiros (contabilidade, TI, jurídico)", "despesas_operacionais"),
    ("4.2.07", "Marketing e publicidade", "despesas_operacionais"),
    ("4.2.08", "Combustíveis e viagens", "despesas_operacionais"),
    ("4.2.09", "Impostos e taxas diversos", "despesas_operacionais"),
    ("4.2.10", "Fretes sobre vendas", "despesas_operacionais"),
    ("4.2.99", "Outras despesas operacionais", "despesas_operacionais"),
    # Financeiro
    ("3.3.01", "Rendimentos de aplicações financeiras", "receitas_financeiras"),
    ("3.3.02", "Juros e descontos obtidos", "receitas_financeiras"),
    ("4.3.01", "Tarifas bancárias", "despesas_financeiras"),
    ("4.3.02", "Juros e multas pagos", "despesas_financeiras"),
    ("4.3.03", "IRRF e IOF sobre aplicações", "despesas_financeiras"),
    ("4.3.04", "Taxa de administração de fundos", "despesas_financeiras"),
    # Outras
    ("3.4.01", "Outras receitas não operacionais", "outras_receitas"),
    ("4.4.01", "Outras despesas não operacionais", "outras_despesas"),
    ("4.5.01", "IRPJ e CSLL", "impostos_lucro"),
    # Fora da DRE (movimentos patrimoniais/financeiros)
    ("9.1.01", "Recebimento de clientes", "nao_dre"),
    ("9.1.02", "Pagamento a fornecedores", "nao_dre"),
    ("9.1.03", "Transferência entre contas", "nao_dre"),
    ("9.1.04", "Aplicação / resgate financeiro", "nao_dre"),
    ("9.1.05", "Empréstimos e financiamentos (principal)", "nao_dre"),
    ("9.1.06", "Aporte / distribuição de lucros", "nao_dre"),
    ("9.1.07", "Aquisição de ativo imobilizado", "nao_dre"),
    ("9.1.08", "Remessas e retornos sem efeito no resultado", "nao_dre"),
    ("9.1.09", "Tributos sobre o faturamento (pagamento)", "nao_dre"),
]


def criar_plano_padrao(db: Session, escritorio_id: int) -> None:
    existentes = set(db.scalars(select(PlanoConta.codigo).where(PlanoConta.escritorio_id == escritorio_id)))
    for codigo, nome, grupo in PLANO_PADRAO:
        if codigo not in existentes:
            db.add(PlanoConta(escritorio_id=escritorio_id, codigo=codigo, nome=nome, grupo=grupo))


def mapa_por_codigo(db: Session, escritorio_id: int) -> dict[str, PlanoConta]:
    contas = db.scalars(select(PlanoConta).where(PlanoConta.escritorio_id == escritorio_id))
    return {c.codigo: c for c in contas}
