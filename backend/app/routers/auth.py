"""Autenticação: senha + OTP por e-mail (MFA), refresh token rotativo, troca e recuperação de senha."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import email as email_svc
from ..audit import registrar_evento
from ..config import get_settings
from ..database import get_db
from ..middleware import ip_cliente
from ..models import AceiteTermo, DesafioOTP, Escritorio, SessaoRefresh, TermoVersao, Usuario, agora
from ..schemas import (
    AlterarSenhaEntrada,
    CadastroEscritorioEntrada,
    DesafioSaida,
    LoginEntrada,
    Mensagem,
    RecuperarSenhaEntrada,
    RedefinirSenhaEntrada,
    TokenSaida,
    UsuarioSaida,
    VerificarOTPEntrada,
)
from ..security import (
    HASH_FICTICIO,
    criar_access_token,
    gerar_codigo_otp,
    hash_senha,
    hash_token,
    problemas_senha,
    usuario_atual,
    verificar_senha,
)
from ..services import cnpj as cnpj_svc
from ..services.plano_contas import criar_plano_padrao
from ..services.termos import publicar_padrao

router = APIRouter(prefix="/api/v1/auth", tags=["Autenticação"])

COOKIE_REFRESH = "bpo_refresh"
MSG_OTP = "Se os dados estiverem corretos, enviamos um código de 6 dígitos para o seu e-mail."


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _validar_politica(senha: str) -> None:
    problemas = problemas_senha(senha)
    if problemas:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [{"loc": ["body", "senha"], "msg": "A senha deve " + ", ".join(problemas), "type": "senha_fraca"}],
        )


def _criar_desafio(db: Session, usuario: Usuario, finalidade: str) -> DesafioSaida:
    s = get_settings()
    # invalida desafios anteriores pendentes da mesma finalidade
    db.execute(
        update(DesafioOTP)
        .where(DesafioOTP.usuario_id == usuario.id, DesafioOTP.finalidade == finalidade, DesafioOTP.usado_em.is_(None))
        .values(usado_em=agora())
    )
    codigo = gerar_codigo_otp()
    desafio = DesafioOTP(
        id=str(uuid.uuid4()),
        usuario_id=usuario.id,
        finalidade=finalidade,
        codigo_hash=hash_senha(codigo),
        expira_em=agora() + timedelta(minutes=s.otp_minutos_validade),
    )
    db.add(desafio)
    db.commit()
    email_svc.enviar_otp(usuario.email, usuario.nome, codigo, finalidade, s.otp_minutos_validade)
    return DesafioSaida(desafio_id=desafio.id, mensagem=MSG_OTP, expira_em_segundos=s.otp_minutos_validade * 60)


def _desafio_ficticio() -> DesafioSaida:
    s = get_settings()
    return DesafioSaida(desafio_id=str(uuid.uuid4()), mensagem=MSG_OTP, expira_em_segundos=s.otp_minutos_validade * 60)


def _consumir_desafio(db: Session, desafio_id: str, codigo: str, finalidade: str) -> Usuario:
    s = get_settings()
    invalido = HTTPException(status.HTTP_400_BAD_REQUEST, "Código inválido ou expirado")
    desafio = db.get(DesafioOTP, desafio_id)
    if not desafio or desafio.finalidade != finalidade or desafio.usado_em:
        raise invalido
    if _utc(desafio.expira_em) < agora() or desafio.tentativas >= s.otp_max_tentativas:
        raise invalido
    if not verificar_senha(codigo, desafio.codigo_hash):
        desafio.tentativas += 1
        if desafio.tentativas >= s.otp_max_tentativas:
            desafio.usado_em = agora()
        db.commit()
        raise invalido
    desafio.usado_em = agora()
    usuario = db.get(Usuario, desafio.usuario_id)
    if not usuario or not usuario.ativo:
        raise invalido
    return usuario


def _emitir_sessao(db: Session, usuario: Usuario, request: Request, response: Response) -> TokenSaida:
    s = get_settings()
    refresh = uuid.uuid4().hex + uuid.uuid4().hex
    db.add(
        SessaoRefresh(
            usuario_id=usuario.id,
            token_hash=hash_token(refresh),
            expira_em=agora() + timedelta(days=s.refresh_token_dias),
            ip=ip_cliente(request),
            user_agent=(request.headers.get("user-agent") or "")[:300],
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE_REFRESH,
        refresh,
        max_age=s.refresh_token_dias * 86400,
        httponly=True,
        secure=s.cookie_seguro,
        samesite="strict",
        path="/api/v1/auth",
    )
    return TokenSaida(
        access_token=criar_access_token(usuario),
        expira_em_segundos=s.access_token_minutos * 60,
        usuario=UsuarioSaida.model_validate(usuario),
    )


@router.post("/cadastro", response_model=DesafioSaida, status_code=201, summary="Cadastrar escritório e administrador")
def cadastrar(dados: CadastroEscritorioEntrada, db: Session = Depends(get_db)):
    """Consulta o CNPJ na base da Receita Federal, cria o escritório com os dados oficiais,
    o plano de contas padrão, os termos LGPD e o usuário administrador. Em seguida envia o
    OTP de primeiro acesso (que também confirma o e-mail)."""
    if not dados.aceite_termos:
        raise HTTPException(422, [{"loc": ["body", "aceite_termos"], "msg": "É necessário aceitar os termos", "type": "aceite"}])
    _validar_politica(dados.senha)
    conflito = HTTPException(status.HTTP_409_CONFLICT, "Não foi possível concluir o cadastro com estes dados")
    if db.scalar(select(Escritorio.id).where(Escritorio.cnpj == dados.cnpj)):
        raise conflito
    if db.scalar(select(Usuario.id).where(Usuario.email == dados.email.lower())):
        raise conflito
    try:
        receita = cnpj_svc.consultar(dados.cnpj).para_dict()
    except cnpj_svc.ErroConsultaCNPJ as e:
        if e.status == 404 or not dados.razao_social:
            raise HTTPException(e.status if e.status in (404, 429) else 422, e.mensagem + (
                "" if e.status == 404 else ". Informe a razão social para cadastrar manualmente."
            ))
        receita = {"razao_social": dados.razao_social, "fonte": "manual", "bruto": None}
    bruto = receita.pop("bruto", None)
    receita.pop("fonte", None)
    receita.pop("cnpj", None)
    esc = Escritorio(cnpj=dados.cnpj, crc=dados.crc, dados_receita=bruto, responsavel_tecnico=dados.nome, **receita)
    db.add(esc)
    db.flush()
    criar_plano_padrao(db, esc.id)
    publicar_padrao(db, esc.id)
    usuario = Usuario(
        escritorio_id=esc.id,
        nome=dados.nome,
        email=dados.email.lower(),
        senha_hash=hash_senha(dados.senha),
        papel="admin",
    )
    db.add(usuario)
    db.flush()
    for termo in db.scalars(select(TermoVersao).where(TermoVersao.escritorio_id == esc.id)):
        db.add(AceiteTermo(termo_id=termo.id, usuario_id=usuario.id, hash_sha256=termo.hash_sha256))
    registrar_evento(db, "CADASTRO", tabela="escritorio", registro_id=esc.id, usuario_id=usuario.id,
                     usuario_email=usuario.email, escritorio_id=esc.id)
    db.commit()
    return _criar_desafio(db, usuario, "login")


@router.post("/login", response_model=DesafioSaida, summary="Etapa 1: e-mail e senha")
def login(dados: LoginEntrada, db: Session = Depends(get_db)):
    """Valida e-mail e senha e envia um código OTP por e-mail. A resposta é a mesma para
    e-mails inexistentes (proteção contra enumeração de usuários)."""
    s = get_settings()
    usuario = db.scalar(select(Usuario).where(Usuario.email == dados.email.lower()))
    if not usuario:
        verificar_senha(dados.senha, HASH_FICTICIO)  # tempo constante
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos")
    if usuario.bloqueado_ate and _utc(usuario.bloqueado_ate) > agora():
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Acesso temporariamente bloqueado por excesso de tentativas. Tente mais tarde ou redefina a senha.")
    if not verificar_senha(dados.senha, usuario.senha_hash) or not usuario.ativo:
        usuario.tentativas_falhas += 1
        if usuario.tentativas_falhas >= s.login_max_falhas:
            usuario.bloqueado_ate = agora() + timedelta(minutes=s.login_bloqueio_minutos)
            usuario.tentativas_falhas = 0
        registrar_evento(db, "LOGIN_FALHA", tabela="usuario", registro_id=usuario.id, usuario_id=usuario.id,
                         usuario_email=usuario.email, escritorio_id=usuario.escritorio_id)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos")
    usuario.tentativas_falhas = 0
    db.commit()
    return _criar_desafio(db, usuario, "login")


@router.post("/otp/verificar", response_model=TokenSaida, summary="Etapa 2: código OTP")
def verificar_otp(dados: VerificarOTPEntrada, request: Request, response: Response, db: Session = Depends(get_db)):
    """Valida o código recebido por e-mail. Retorna o access token (JWT, 15 min) e grava o
    refresh token em cookie HttpOnly/SameSite=Strict (usado pelo frontend)."""
    usuario = _consumir_desafio(db, dados.desafio_id, dados.codigo, "login")
    usuario.email_verificado = True
    usuario.ultimo_login_em = agora()
    registrar_evento(db, "LOGIN", tabela="usuario", registro_id=usuario.id, usuario_id=usuario.id,
                     usuario_email=usuario.email, escritorio_id=usuario.escritorio_id)
    return _emitir_sessao(db, usuario, request, response)


@router.post("/refresh", response_model=TokenSaida, summary="Renovar sessão (cookie)")
def refresh(
    request: Request,
    response: Response,
    bpo_refresh: str | None = Cookie(default=None),
    x_requested_with: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Troca o refresh token (cookie) por um novo par de tokens (rotação). Exige o cabeçalho
    `X-Requested-With: fetch` como defesa adicional contra CSRF."""
    if x_requested_with != "fetch" or not bpo_refresh:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada")
    sessao = db.scalar(select(SessaoRefresh).where(SessaoRefresh.token_hash == hash_token(bpo_refresh)))
    if not sessao or _utc(sessao.expira_em) < agora():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada")
    if sessao.revogado_em:
        # Reuso de token já rotacionado = possível roubo: revoga todas as sessões do usuário
        db.execute(update(SessaoRefresh).where(SessaoRefresh.usuario_id == sessao.usuario_id, SessaoRefresh.revogado_em.is_(None)).values(revogado_em=agora()))
        registrar_evento(db, "REFRESH_REUTILIZADO", tabela="usuario", registro_id=sessao.usuario_id, usuario_id=sessao.usuario_id)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada")
    usuario = db.get(Usuario, sessao.usuario_id)
    if not usuario or not usuario.ativo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada")
    sessao.revogado_em = agora()
    return _emitir_sessao(db, usuario, request, response)


@router.post("/logout", response_model=Mensagem, summary="Encerrar sessão")
def logout(response: Response, bpo_refresh: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if bpo_refresh:
        sessao = db.scalar(select(SessaoRefresh).where(SessaoRefresh.token_hash == hash_token(bpo_refresh)))
        if sessao and not sessao.revogado_em:
            sessao.revogado_em = agora()
            db.commit()
    response.delete_cookie(COOKIE_REFRESH, path="/api/v1/auth")
    return Mensagem(mensagem="Sessão encerrada")


@router.get("/me", response_model=UsuarioSaida, summary="Usuário autenticado")
def me(usuario: Usuario = Depends(usuario_atual)):
    return usuario


@router.post("/senha/alterar", response_model=Mensagem, summary="Alterar senha (autenticado)")
def alterar_senha(dados: AlterarSenhaEntrada, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    if not verificar_senha(dados.senha_atual, usuario.senha_hash):
        raise HTTPException(422, [{"loc": ["body", "senha_atual"], "msg": "Senha atual incorreta", "type": "senha"}])
    if verificar_senha(dados.nova_senha, usuario.senha_hash):
        raise HTTPException(422, [{"loc": ["body", "nova_senha"], "msg": "A nova senha deve ser diferente da atual", "type": "senha"}])
    _validar_politica(dados.nova_senha)
    _trocar_senha(db, usuario, dados.nova_senha)
    registrar_evento(db, "SENHA_ALTERADA", tabela="usuario", registro_id=usuario.id)
    db.commit()
    return Mensagem(mensagem="Senha alterada. Entre novamente em todos os dispositivos.")


def _trocar_senha(db: Session, usuario: Usuario, nova: str) -> None:
    usuario.senha_hash = hash_senha(nova)
    usuario.senha_alterada_em = agora()
    usuario.versao_token = (usuario.versao_token or 0) + 1
    usuario.bloqueado_ate = None
    usuario.tentativas_falhas = 0
    db.execute(
        update(SessaoRefresh)
        .where(SessaoRefresh.usuario_id == usuario.id, SessaoRefresh.revogado_em.is_(None))
        .values(revogado_em=agora())
    )


@router.post("/senha/recuperar", response_model=DesafioSaida, summary="Recuperar senha: enviar código")
def recuperar_senha(dados: RecuperarSenhaEntrada, db: Session = Depends(get_db)):
    """Envia um código de redefinição se o e-mail existir. A resposta é sempre igual."""
    usuario = db.scalar(select(Usuario).where(Usuario.email == dados.email.lower(), Usuario.ativo.is_(True)))
    if not usuario:
        return _desafio_ficticio()
    return _criar_desafio(db, usuario, "recuperacao")


@router.post("/senha/redefinir", response_model=Mensagem, summary="Recuperar senha: definir nova senha")
def redefinir_senha(dados: RedefinirSenhaEntrada, db: Session = Depends(get_db)):
    _validar_politica(dados.nova_senha)
    usuario = _consumir_desafio(db, dados.desafio_id, dados.codigo, "recuperacao")
    _trocar_senha(db, usuario, dados.nova_senha)
    usuario.email_verificado = True
    registrar_evento(db, "SENHA_REDEFINIDA", tabela="usuario", registro_id=usuario.id, usuario_id=usuario.id,
                     usuario_email=usuario.email, escritorio_id=usuario.escritorio_id)
    db.commit()
    return Mensagem(mensagem="Senha redefinida com sucesso. Faça login com a nova senha.")
