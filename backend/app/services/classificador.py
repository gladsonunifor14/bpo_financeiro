"""Classificação inteligente de lançamentos bancários.

O cliente classifica manualmente os primeiros lançamentos (histórico + débito/crédito).
O motor aprende com essas decisões e replica nos demais, em três camadas:

1. Correspondência exata do histórico normalizado + natureza (D/C) já classificado
   pelo próprio cliente → alta confiança.
2. Naive Bayes multinomial sobre os tokens do histórico (com a natureza como atributo),
   treinado com o histórico do cliente (peso 1) e do escritório (peso 0,3, para
   aproveitar padrões comuns como tarifas e impostos).
3. Regras de partida a frio (palavras-chave) com confiança moderada — viram apenas
   sugestões, nunca aplicação automática.

Sugestões acima de `ia_confianca_minima` são aplicadas com status `ia_sugerida`
(o usuário revisa e confirma); abaixo disso ficam como sugestão.
Todo o processamento é local: nenhum dado financeiro sai do servidor.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LancamentoBancario, PlanoConta

STATUS_ROTULADOS = ("manual", "ia_confirmada")

REGRAS_PARTIDA: list[tuple[tuple[str, ...], str | None, str]] = [
    # (palavras, natureza exigida, código da conta)
    (("TARIFA",), "D", "4.3.01"),
    (("TAR",), "D", "4.3.01"),
    (("CESTA",), "D", "4.3.01"),
    (("IOF",), "D", "4.3.03"),
    (("RENDIMENTO",), "C", "3.3.01"),
    (("REND",), "C", "3.3.01"),
    (("APLICACAO",), None, "9.1.04"),
    (("RESGATE",), None, "9.1.04"),
    (("JUROS",), "D", "4.3.02"),
    (("JUROS",), "C", "3.3.02"),
    (("FOLHA",), "D", "4.2.01"),
    (("SALARIO",), "D", "4.2.01"),
    (("FGTS",), "D", "4.2.01"),
    (("INSS",), "D", "4.2.01"),
    (("PRO", "LABORE"), "D", "4.2.02"),
    (("ALUGUEL",), "D", "4.2.03"),
    (("CONDOMINIO",), "D", "4.2.03"),
    (("ENERGIA",), "D", "4.2.04"),
    (("TELEFONIA",), "D", "4.2.04"),
    (("INTERNET",), "D", "4.2.04"),
    (("SIMPLES", "NACIONAL"), "D", "3.2.05"),
    (("DAS",), "D", "3.2.05"),
    (("COMBUSTIVEL",), "D", "4.2.08"),
    (("POSTO",), "D", "4.2.08"),
]
CONFIANCA_REGRA = 0.6


@dataclass
class Sugestao:
    lancamento_id: int
    conta_id: int
    confianca: float
    metodo: str  # exato | modelo | regra


class Classificador:
    def __init__(self) -> None:
        self.exatos: dict[tuple[str, str], Counter] = defaultdict(Counter)
        self.contagem_classe: Counter = Counter()
        self.tokens_classe: dict[int, Counter] = defaultdict(Counter)
        self.vocab: set[str] = set()

    @staticmethod
    def _atributos(hist_norm: str, natureza: str) -> list[str]:
        return hist_norm.split() + [f"__NAT_{natureza}"] * 2

    def treinar(self, amostras: list[tuple[str, str, int, float]]) -> None:
        """amostras: (historico_normalizado, natureza, conta_id, peso)"""
        for hist, nat, conta, peso in amostras:
            if peso >= 1:
                self.exatos[(hist, nat)][conta] += 1
            self.contagem_classe[conta] += peso
            for t in self._atributos(hist, nat):
                self.tokens_classe[conta][t] += peso
                self.vocab.add(t)

    @property
    def treinado(self) -> bool:
        return bool(self.contagem_classe)

    def prever(self, hist: str, nat: str) -> tuple[int, float, str] | None:
        exato = self.exatos.get((hist, nat))
        if exato:
            conta, n = exato.most_common(1)[0]
            total = sum(exato.values())
            share = n / total
            confianca = share * (0.97 if n >= 2 else 0.9)
            return conta, round(confianca, 4), "exato"
        if not self.treinado:
            return None
        attrs = [t for t in self._atributos(hist, nat) if t in self.vocab]
        if len(attrs) <= 2:  # só a natureza: sem evidência textual
            return None
        total_docs = sum(self.contagem_classe.values())
        v = len(self.vocab)
        log_probs = {}
        for conta, cnt in self.contagem_classe.items():
            tokens = self.tokens_classe[conta]
            total_tokens = sum(tokens.values())
            lp = math.log(cnt / total_docs)
            for t in attrs:
                lp += math.log((tokens[t] + 0.5) / (total_tokens + 0.5 * v))
            log_probs[conta] = lp
        m = max(log_probs.values())
        soma = sum(math.exp(lp - m) for lp in log_probs.values())
        conta = max(log_probs, key=log_probs.get)
        prob = 1 / soma
        # Penaliza quando poucas palavras conhecidas sustentam a decisão
        cobertura = (len(attrs) - 2) / max(1, len(hist.split()))
        return conta, round(prob * (0.6 + 0.4 * cobertura) * 0.95, 4), "modelo"


def _regra(hist: str, nat: str, contas: dict[str, int]) -> int | None:
    tokens = set(hist.split())
    for palavras, natureza, codigo in REGRAS_PARTIDA:
        if (natureza is None or natureza == nat) and all(p in tokens for p in palavras) and codigo in contas:
            return contas[codigo]
    return None


def treinar_para_cliente(db: Session, escritorio_id: int, cliente_id: int) -> Classificador:
    linhas = db.execute(
        select(
            LancamentoBancario.historico_normalizado,
            LancamentoBancario.natureza,
            LancamentoBancario.conta_id,
            LancamentoBancario.cliente_id,
        ).where(
            LancamentoBancario.escritorio_id == escritorio_id,
            LancamentoBancario.status_classificacao.in_(STATUS_ROTULADOS),
            LancamentoBancario.conta_id.is_not(None),
        )
    ).all()
    clf = Classificador()
    clf.treinar([(h, n, c, 1.0 if cli == cliente_id else 0.3) for h, n, c, cli in linhas])
    return clf


def sugerir(db: Session, escritorio_id: int, cliente_id: int, lancamentos: list[LancamentoBancario]) -> list[Sugestao]:
    clf = treinar_para_cliente(db, escritorio_id, cliente_id)
    contas = {
        c.codigo: c.id
        for c in db.scalars(select(PlanoConta).where(PlanoConta.escritorio_id == escritorio_id, PlanoConta.ativo))
    }
    saida = []
    for lanc in lancamentos:
        pred = clf.prever(lanc.historico_normalizado, lanc.natureza)
        if pred:
            saida.append(Sugestao(lanc.id, pred[0], pred[1], pred[2]))
            continue
        conta = _regra(lanc.historico_normalizado, lanc.natureza, contas)
        if conta:
            saida.append(Sugestao(lanc.id, conta, CONFIANCA_REGRA, "regra"))
    return saida
