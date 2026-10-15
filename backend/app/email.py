"""Envio de e-mails transacionais (OTP, recuperação de senha, avisos)."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from .config import get_settings

log = logging.getLogger("bpo.email")

# Nos testes, substituímos por uma lista que captura as mensagens
caixa_saida_testes: list[dict] | None = None


def enviar(destinatario: str, assunto: str, corpo: str) -> None:
    s = get_settings()
    if caixa_saida_testes is not None:
        caixa_saida_testes.append({"para": destinatario, "assunto": assunto, "corpo": corpo})
        return
    if not s.smtp_host:
        # Desenvolvimento: sem SMTP, registra no log (nunca em produção)
        if s.producao:
            log.error("SMTP não configurado em produção; e-mail para %s não enviado", destinatario)
            return
        log.warning("[E-MAIL DEV] Para: %s | %s\n%s", destinatario, assunto, corpo)
        return
    msg = EmailMessage()
    msg["From"] = s.smtp_remetente
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.set_content(corpo)
    with smtplib.SMTP(s.smtp_host, s.smtp_porta, timeout=15) as smtp:
        if s.smtp_tls:
            smtp.starttls()
        if s.smtp_usuario:
            smtp.login(s.smtp_usuario, s.smtp_senha or "")
        smtp.send_message(msg)


def enviar_otp(destinatario: str, nome: str, codigo: str, finalidade: str, minutos: int) -> None:
    acao = "acessar o sistema" if finalidade == "login" else "redefinir sua senha"
    enviar(
        destinatario,
        f"Seu código de verificação: {codigo}",
        f"Olá, {nome}.\n\nUse o código {codigo} para {acao}. Ele expira em {minutos} minutos.\n"
        "Se você não fez esta solicitação, ignore este e-mail e considere alterar sua senha.\n\n"
        "Nunca compartilhe este código. Nossa equipe jamais o solicitará.",
    )
