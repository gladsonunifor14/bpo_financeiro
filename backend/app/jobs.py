"""Robôs (RPA) executados por agendador (cron/Kubernetes CronJob/systemd timer).

Uso:
    python -m app.jobs classificar-ia          # IA em todos os lançamentos pendentes
    python -m app.jobs alertas                 # e-mails de procurações/contratos pendentes
    python -m app.jobs limpeza                 # remove OTPs e sessões expiradas
    python -m app.jobs importar-pasta DIR      # importa DIR/<cnpj_cliente>/*.xml|*.zip|*.ofx|*.csv
    python -m app.jobs diario                  # classificar-ia + alertas + limpeza

`importar-pasta` permite que um robô de download (portal da SEFAZ, e-mail, SFTP do banco)
apenas deposite os arquivos na pasta do cliente; arquivos processados vão para `processados/`.
"""
from __future__ import annotations

import argparse
import logging
import shutil
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import delete, select

from . import audit  # noqa: F401
from . import email as email_svc
from .config import get_settings
from .database import Base, SessionLocal, engine
from .models import (
    Cliente,
    ContaBancaria,
    Contrato,
    DesafioOTP,
    ImportacaoExtrato,
    LancamentoBancario,
    Procuracao,
    SessaoRefresh,
    Usuario,
    agora,
)
from .routers.documentos import _aplicar_ia, _gravar_lancamentos
from .services import extratos, nfe

log = logging.getLogger("bpo.jobs")


def classificar_ia() -> int:
    total = 0
    with SessionLocal() as db:
        pares = db.execute(
            select(LancamentoBancario.escritorio_id, LancamentoBancario.cliente_id)
            .where(LancamentoBancario.status_classificacao == "pendente")
            .distinct()
        ).all()
        for esc, cli in pares:
            pend = db.scalars(select(LancamentoBancario).where(LancamentoBancario.cliente_id == cli, LancamentoBancario.status_classificacao == "pendente")).all()
            total += sum(1 for s in _aplicar_ia(db, esc, cli, list(pend)) if s.aplicada)
        db.commit()
    log.info("IA classificou %s lançamentos", total)
    return total


def alertas() -> int:
    hoje = date.today()
    mensagens: dict[int, list[str]] = defaultdict(list)
    with SessionLocal() as db:
        for p, nome in db.execute(
            select(Procuracao, Cliente.razao_social).join(Cliente, Procuracao.cliente_id == Cliente.id).where(
                Procuracao.revogada_em.is_(None), Procuracao.data_fim.is_not(None), Procuracao.data_fim <= hoje + timedelta(days=30)
            )
        ):
            situacao = "VENCIDA" if p.data_fim < hoje else "vence"
            mensagens[p.escritorio_id].append(f"Procuração ({p.tipo}) de {nome} {situacao} em {p.data_fim:%d/%m/%Y}")
        for c, nome in db.execute(
            select(Contrato, Cliente.razao_social).join(Cliente, Contrato.cliente_id == Cliente.id).where(Contrato.status == "aguardando_aceite")
        ):
            mensagens[c.escritorio_id].append(f"Contrato {c.numero} de {nome} aguardando aceite")
        enviados = 0
        for esc, linhas in mensagens.items():
            for admin in db.scalars(select(Usuario).where(Usuario.escritorio_id == esc, Usuario.papel == "admin", Usuario.ativo)):
                email_svc.enviar(admin.email, "BPO Financeiro: pendências do dia", "\n".join(f"• {m}" for m in linhas))
                enviados += 1
    return enviados


def limpeza() -> None:
    with SessionLocal() as db:
        db.execute(delete(DesafioOTP).where(DesafioOTP.expira_em < agora() - timedelta(days=1)))
        db.execute(delete(SessaoRefresh).where(SessaoRefresh.expira_em < agora()))
        db.commit()


def importar_pasta(raiz: Path) -> dict:
    """Estrutura esperada: raiz/<CNPJ do cliente>/arquivo. Para extratos, o nome do arquivo deve
    começar com o id da conta bancária: `12_extrato_marco.ofx`."""
    resumo = {"notas": 0, "lancamentos": 0, "erros": 0}
    with SessionLocal() as db:
        for pasta in sorted(p for p in raiz.iterdir() if p.is_dir() and p.name != "processados"):
            for cliente in db.scalars(select(Cliente).where(Cliente.cnpj == pasta.name.upper(), Cliente.ativo)):
                for arq in sorted(pasta.iterdir()):
                    if not arq.is_file():
                        continue
                    try:
                        dados = arq.read_bytes()
                        nome = arq.name.lower()
                        if nome.endswith((".xml", ".zip")):
                            for n, x in nfe.extrair_xmls(arq.name, dados):
                                with db.begin_nested():
                                    r = nfe.importar(db, cliente, x, n, None)
                                resumo["notas"] += r.status == "importada"
                        elif nome.endswith((".ofx", ".csv")):
                            conta = db.get(ContaBancaria, int(arq.name.split("_", 1)[0]))
                            if not conta or conta.cliente_id != cliente.id:
                                raise ValueError("conta bancária não identificada no nome do arquivo")
                            formato, lidos = extratos.ler(arq.name, dados)
                            imp = ImportacaoExtrato(escritorio_id=cliente.escritorio_id, cliente_id=cliente.id, conta_bancaria_id=conta.id, arquivo_nome=arq.name[:200], formato=formato)
                            db.add(imp)
                            db.flush()
                            novos = _gravar_lancamentos(db, conta, lidos, imp)
                            _aplicar_ia(db, cliente.escritorio_id, cliente.id, novos)
                            resumo["lancamentos"] += len(novos)
                        else:
                            continue
                        db.commit()
                        destino = raiz / "processados" / pasta.name
                        destino.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(arq), destino / arq.name)
                    except Exception as e:  # um arquivo ruim não interrompe o lote
                        db.rollback()
                        resumo["erros"] += 1
                        log.error("Falha ao importar %s: %s", arq, e)
    return resumo


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    Base.metadata.create_all(engine)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tarefa", choices=["classificar-ia", "alertas", "limpeza", "importar-pasta", "diario"])
    ap.add_argument("pasta", nargs="?")
    a = ap.parse_args(argv)
    get_settings()
    if a.tarefa == "importar-pasta":
        if not a.pasta:
            ap.error("informe a pasta")
        print(importar_pasta(Path(a.pasta)))
    elif a.tarefa == "classificar-ia":
        classificar_ia()
    elif a.tarefa == "alertas":
        alertas()
    elif a.tarefa == "limpeza":
        limpeza()
    else:
        classificar_ia()
        alertas()
        limpeza()


if __name__ == "__main__":
    main()
