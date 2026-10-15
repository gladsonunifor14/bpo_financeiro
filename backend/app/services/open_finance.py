"""Integração com Open Finance Brasil (importação automática de extratos).

Viabilidade (ver docs/open-finance.md): para receber dados via Open Finance é preciso ser
instituição autorizada pelo BACEN e participante do diretório, ou usar um agregador/ITP
autorizado (ex.: Pluggy, Belvo, Celcoin, Klavi) que intermedeia o consentimento do cliente.
O desenho abaixo isola o provedor atrás de uma interface; o provedor 'simulado' permite
testar o fluxo ponta a ponta sem credenciais.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import date, timedelta
from decimal import Decimal

from ..config import get_settings
from .extratos import LancamentoLido

PERMISSOES_PADRAO = [
    "ACCOUNTS_READ",
    "ACCOUNTS_BALANCES_READ",
    "ACCOUNTS_TRANSACTIONS_READ",
    "RESOURCES_READ",
    "BANK_FIXED_INCOMES_READ",
    "FUNDS_READ",
]


class OpenFinanceIndisponivel(Exception):
    pass


class ProvedorOpenFinance(ABC):
    nome: str

    @abstractmethod
    def criar_consentimento(self, cnpj: str, permissoes: list[str]) -> tuple[str, str]:
        """Retorna (id_externo, url_de_redirecionamento_para_autorizacao_no_banco)."""

    @abstractmethod
    def status_consentimento(self, id_externo: str) -> str:
        """aguardando_autorizacao | autorizado | rejeitado | revogado | expirado"""

    @abstractmethod
    def transacoes(self, id_externo: str, inicio: date, fim: date) -> list[LancamentoLido]:
        ...


class ProvedorSimulado(ProvedorOpenFinance):
    nome = "simulado"

    def criar_consentimento(self, cnpj, permissoes):
        ide = f"sim-{uuid.uuid4()}"
        return ide, f"/#/open-finance/simulado?consentimento={ide}"

    def status_consentimento(self, id_externo):
        return "autorizado"

    def transacoes(self, id_externo, inicio, fim):
        saida, d = [], inicio
        while d <= fim:
            saida.append(LancamentoLido(d, "TARIFA PACOTE SERVICOS", Decimal("49.90"), "D", fitid=f"{id_externo}-{d}-t"))
            saida.append(LancamentoLido(d, "PIX RECEBIDO CLIENTE EXEMPLO", Decimal("1500.00"), "C", fitid=f"{id_externo}-{d}-p"))
            d += timedelta(days=7)
        return saida


def provedor() -> ProvedorOpenFinance:
    s = get_settings()
    if s.open_finance_provedor == "simulado":
        return ProvedorSimulado()
    if not s.open_finance_provedor:
        raise OpenFinanceIndisponivel(
            "Open Finance não configurado. Contrate um agregador/ITP autorizado pelo BACEN e defina "
            "BPO_OPEN_FINANCE_PROVEDOR, BPO_OPEN_FINANCE_CLIENT_ID e BPO_OPEN_FINANCE_CLIENT_SECRET."
        )
    raise OpenFinanceIndisponivel(f"Adaptador para o provedor '{s.open_finance_provedor}' ainda não implementado")
