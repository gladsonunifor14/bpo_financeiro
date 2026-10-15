"""Contrato de adesão, termos LGPD/confidencialidade e procurações."""
from __future__ import annotations

import hashlib
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import registrar_evento
from ..config import get_settings
from ..database import get_db
from ..middleware import ip_cliente
from ..models import AceiteTermo, Contrato, Escritorio, ModeloContrato, Procuracao, TermoVersao, Usuario, agora
from ..schemas import (
    AceiteContratoEntrada,
    AceiteTermoEntrada,
    ContratoDetalhe,
    ContratoEntrada,
    ContratoSaida,
    Mensagem,
    ModeloContratoEntrada,
    ModeloContratoSaida,
    ProcuracaoSaida,
    RescisaoEntrada,
    TermoEntrada,
    TermoSaida,
)
from ..security import equipe_escritorio, obter_cliente_autorizado, somente_admin, usuario_atual
from ..services import contratos as contratos_svc

router = APIRouter(prefix="/api/v1", tags=["Contratos, LGPD e Procurações"])


# ------------------------------------------------------------------ modelos de contrato
def _modelo_ativo(db: Session, escritorio_id: int) -> ModeloContrato:
    modelo = db.scalar(
        select(ModeloContrato)
        .where(ModeloContrato.escritorio_id == escritorio_id, ModeloContrato.ativo)
        .order_by(ModeloContrato.versao.desc())
    )
    if not modelo:
        modelo = ModeloContrato(
            escritorio_id=escritorio_id, titulo=contratos_svc.MODELO_PADRAO_TITULO, conteudo=contratos_svc.MODELO_PADRAO
        )
        db.add(modelo)
        db.flush()
    return modelo


@router.get("/modelos-contrato", response_model=list[ModeloContratoSaida], summary="Modelos de contrato de adesão")
def listar_modelos(usuario: Usuario = Depends(equipe_escritorio), db: Session = Depends(get_db)):
    _modelo_ativo(db, usuario.escritorio_id)
    db.commit()
    return db.scalars(select(ModeloContrato).where(ModeloContrato.escritorio_id == usuario.escritorio_id).order_by(ModeloContrato.versao.desc())).all()


@router.post("/modelos-contrato", response_model=ModeloContratoSaida, status_code=201, summary="Publicar nova versão do modelo")
def criar_modelo(dados: ModeloContratoEntrada, usuario: Usuario = Depends(somente_admin), db: Session = Depends(get_db)):
    """Variáveis disponíveis: {{escritorio_razao_social}}, {{escritorio_cnpj}}, {{escritorio_crc}},
    {{escritorio_endereco}}, {{escritorio_municipio}}, {{escritorio_uf}}, {{cliente_razao_social}},
    {{cliente_cnpj}}, {{cliente_endereco}}, {{valor_mensal}}, {{dia_vencimento}}, {{inicio_vigencia}}, {{prazo}}.
    Contratos já emitidos não mudam (o texto e o hash ficam congelados no contrato)."""
    versao = (db.scalar(select(func.max(ModeloContrato.versao)).where(ModeloContrato.escritorio_id == usuario.escritorio_id)) or 0) + 1
    for m in db.scalars(select(ModeloContrato).where(ModeloContrato.escritorio_id == usuario.escritorio_id, ModeloContrato.ativo)):
        m.ativo = False
    modelo = ModeloContrato(escritorio_id=usuario.escritorio_id, titulo=dados.titulo, conteudo=dados.conteudo, versao=versao)
    db.add(modelo)
    db.commit()
    return modelo


# ------------------------------------------------------------------ contratos
def _contrato(db: Session, usuario: Usuario, contrato_id: int) -> Contrato:
    c = db.get(Contrato, contrato_id)
    if not c or c.escritorio_id != usuario.escritorio_id or (usuario.papel == "cliente" and c.cliente_id != usuario.cliente_id):
        raise HTTPException(404, "Contrato não encontrado")
    return c


@router.get("/contratos", response_model=list[ContratoSaida], summary="Listar contratos")
def listar_contratos(cliente_id: int | None = None, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    q = select(Contrato).where(Contrato.escritorio_id == usuario.escritorio_id)
    if usuario.papel == "cliente":
        q = q.where(Contrato.cliente_id == usuario.cliente_id)
    elif cliente_id:
        q = q.where(Contrato.cliente_id == cliente_id)
    return db.scalars(q.order_by(Contrato.criado_em.desc())).all()


@router.post("/contratos", response_model=ContratoDetalhe, status_code=201, summary="Emitir contrato de adesão para um cliente")
def emitir_contrato(dados: ContratoEntrada, usuario: Usuario = Depends(equipe_escritorio), db: Session = Depends(get_db)):
    cliente = obter_cliente_autorizado(db, usuario, dados.cliente_id)
    if dados.fim_vigencia and dados.fim_vigencia <= dados.inicio_vigencia:
        raise HTTPException(422, [{"loc": ["body", "fim_vigencia"], "msg": "O fim da vigência deve ser posterior ao início", "type": "data"}])
    vigente = db.scalar(select(Contrato.id).where(Contrato.cliente_id == cliente.id, Contrato.status.in_(("aguardando_aceite", "vigente"))))
    if vigente:
        raise HTTPException(409, "Este cliente já possui contrato vigente ou aguardando aceite")
    if dados.modelo_id:
        modelo = db.get(ModeloContrato, dados.modelo_id)
        if not modelo or modelo.escritorio_id != usuario.escritorio_id:
            raise HTTPException(404, "Modelo não encontrado")
    else:
        modelo = _modelo_ativo(db, usuario.escritorio_id)
    esc = db.get(Escritorio, usuario.escritorio_id)
    texto = contratos_svc.renderizar(modelo.conteudo, esc, cliente, dados.valor_mensal, dados.dia_vencimento, dados.inicio_vigencia, dados.fim_vigencia)
    seq = (db.scalar(select(func.count(Contrato.id)).where(Contrato.escritorio_id == usuario.escritorio_id)) or 0) + 1
    contrato = Contrato(
        escritorio_id=usuario.escritorio_id,
        cliente_id=cliente.id,
        modelo_id=modelo.id,
        numero=f"{date.today().year}/{seq:05d}",
        conteudo=texto,
        hash_sha256=contratos_svc.sha256(texto),
        valor_mensal=dados.valor_mensal,
        dia_vencimento=dados.dia_vencimento,
        inicio_vigencia=dados.inicio_vigencia,
        fim_vigencia=dados.fim_vigencia,
    )
    db.add(contrato)
    db.commit()
    return contrato


@router.get("/contratos/{contrato_id}", response_model=ContratoDetalhe, summary="Detalhar contrato (texto integral)")
def obter_contrato(contrato_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return _contrato(db, usuario, contrato_id)


@router.post("/contratos/{contrato_id}/aceite", response_model=ContratoSaida, summary="Aceite eletrônico do contrato (cliente)")
def aceitar_contrato(contrato_id: int, dados: AceiteContratoEntrada, request: Request, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Somente o usuário do cliente (representante) pode aceitar. Registra data/hora, IP,
    user-agent e confere o hash do texto exibido com o hash do contrato."""
    contrato = _contrato(db, usuario, contrato_id)
    if usuario.papel != "cliente":
        raise HTTPException(403, "O aceite deve ser feito pelo representante do cliente")
    if contrato.status != "aguardando_aceite":
        raise HTTPException(409, "Contrato não está aguardando aceite")
    if not dados.li_e_concordo:
        raise HTTPException(422, [{"loc": ["body", "li_e_concordo"], "msg": "Confirme que leu e concorda com o contrato", "type": "aceite"}])
    if dados.hash_sha256 != contrato.hash_sha256:
        raise HTTPException(409, "O texto do contrato mudou desde que foi exibido. Recarregue e leia novamente.")
    contrato.status = "vigente"
    contrato.aceito_em = agora()
    contrato.aceito_por_id = usuario.id
    contrato.aceite_ip = ip_cliente(request)
    contrato.aceite_user_agent = (request.headers.get("user-agent") or "")[:300]
    registrar_evento(db, "ACEITE_CONTRATO", tabela="contrato", registro_id=contrato.id, detalhes={"hash": contrato.hash_sha256})
    db.commit()
    return contrato


@router.post("/contratos/{contrato_id}/rescisao", response_model=ContratoSaida, summary="Rescindir contrato")
def rescindir_contrato(contrato_id: int, dados: RescisaoEntrada, usuario: Usuario = Depends(equipe_escritorio), db: Session = Depends(get_db)):
    contrato = _contrato(db, usuario, contrato_id)
    if contrato.status == "rescindido":
        raise HTTPException(409, "Contrato já rescindido")
    contrato.status = "rescindido"
    contrato.rescindido_em = agora()
    contrato.motivo_rescisao = dados.motivo
    db.commit()
    return contrato


# ------------------------------------------------------------------ termos LGPD
@router.get("/termos", response_model=list[TermoSaida], summary="Termos vigentes e situação de aceite do usuário")
def listar_termos(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    termos = db.scalars(select(TermoVersao).where(TermoVersao.escritorio_id == usuario.escritorio_id, TermoVersao.ativo).order_by(TermoVersao.tipo)).all()
    aceites = {a.termo_id: a.aceito_em for a in db.scalars(select(AceiteTermo).where(AceiteTermo.usuario_id == usuario.id))}
    return [TermoSaida(**TermoSaida.model_validate(t).model_dump(exclude={"aceito_em"}), aceito_em=aceites.get(t.id)) for t in termos]


@router.get("/termos/pendentes", response_model=list[TermoSaida], summary="Termos obrigatórios ainda não aceitos")
def termos_pendentes(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return [t for t in listar_termos(usuario, db) if t.obrigatorio and not t.aceito_em]


@router.post("/termos", response_model=TermoSaida, status_code=201, summary="Publicar nova versão de termo")
def publicar_termo(dados: TermoEntrada, usuario: Usuario = Depends(somente_admin), db: Session = Depends(get_db)):
    """A nova versão substitui a anterior e exige novo aceite de todos os usuários."""
    versao = (db.scalar(select(func.max(TermoVersao.versao)).where(TermoVersao.escritorio_id == usuario.escritorio_id, TermoVersao.tipo == dados.tipo)) or 0) + 1
    for t in db.scalars(select(TermoVersao).where(TermoVersao.escritorio_id == usuario.escritorio_id, TermoVersao.tipo == dados.tipo, TermoVersao.ativo)):
        t.ativo = False
    termo = TermoVersao(escritorio_id=usuario.escritorio_id, versao=versao, hash_sha256=contratos_svc.sha256(dados.conteudo), **dados.model_dump())
    db.add(termo)
    db.commit()
    return termo


@router.post("/termos/{termo_id}/aceite", response_model=Mensagem, summary="Aceitar termo")
def aceitar_termo(termo_id: int, dados: AceiteTermoEntrada, request: Request, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    termo = db.get(TermoVersao, termo_id)
    if not termo or termo.escritorio_id != usuario.escritorio_id or not termo.ativo:
        raise HTTPException(404, "Termo não encontrado")
    if dados.hash_sha256 != termo.hash_sha256:
        raise HTTPException(409, "O texto do termo mudou. Recarregue e leia novamente.")
    if db.scalar(select(AceiteTermo.id).where(AceiteTermo.termo_id == termo.id, AceiteTermo.usuario_id == usuario.id)):
        return Mensagem(mensagem="Termo já aceito")
    db.add(AceiteTermo(termo_id=termo.id, usuario_id=usuario.id, hash_sha256=termo.hash_sha256,
                       ip=ip_cliente(request), user_agent=(request.headers.get("user-agent") or "")[:300]))
    db.commit()
    return Mensagem(mensagem="Aceite registrado")


@router.get("/termos/{termo_id}/aceites", summary="Relatório de aceites de um termo (comprovação LGPD)")
def aceites_do_termo(termo_id: int, usuario: Usuario = Depends(equipe_escritorio), db: Session = Depends(get_db)):
    termo = db.get(TermoVersao, termo_id)
    if not termo or termo.escritorio_id != usuario.escritorio_id:
        raise HTTPException(404, "Termo não encontrado")
    linhas = db.execute(
        select(AceiteTermo, Usuario.nome, Usuario.email).join(Usuario, AceiteTermo.usuario_id == Usuario.id).where(AceiteTermo.termo_id == termo.id)
    ).all()
    return [
        {"usuario": nome, "email": email, "aceito_em": a.aceito_em.isoformat(), "ip": a.ip, "hash_sha256": a.hash_sha256}
        for a, nome, email in linhas
    ]


# ------------------------------------------------------------------ procurações
def _situacao(p: Procuracao) -> str:
    hoje = date.today()
    if p.revogada_em:
        return "revogada"
    if p.data_inicio > hoje:
        return "futura"
    if p.data_fim and p.data_fim < hoje:
        return "vencida"
    if p.data_fim and (p.data_fim - hoje).days <= 30:
        return "vence_em_30_dias"
    return "vigente"


def _proc_saida(p: Procuracao) -> ProcuracaoSaida:
    s = ProcuracaoSaida.model_validate(p)
    s.situacao = _situacao(p)
    return s


@router.get("/procuracoes", response_model=list[ProcuracaoSaida], summary="Listar procurações")
def listar_procuracoes(cliente_id: int | None = None, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    q = select(Procuracao).where(Procuracao.escritorio_id == usuario.escritorio_id)
    if usuario.papel == "cliente":
        q = q.where(Procuracao.cliente_id == usuario.cliente_id)
    elif cliente_id:
        q = q.where(Procuracao.cliente_id == cliente_id)
    return [_proc_saida(p) for p in db.scalars(q.order_by(Procuracao.data_fim))]


@router.post("/procuracoes", response_model=ProcuracaoSaida, status_code=201, summary="Registrar procuração (PDF opcional)")
async def criar_procuracao(
    cliente_id: int = Form(...),
    tipo: str = Form(..., pattern="^(ecac|particular|publica|sefaz|prefeitura|outra)$"),
    outorgado_nome: str = Form(..., min_length=2, max_length=200),
    outorgado_documento: str = Form(..., pattern=r"^[0-9A-Za-z./-]{11,18}$"),
    poderes: str = Form(..., min_length=5, max_length=5000),
    data_inicio: date = Form(...),
    data_fim: date | None = Form(None),
    arquivo: UploadFile | None = File(None),
    usuario: Usuario = Depends(equipe_escritorio),
    db: Session = Depends(get_db),
):
    obter_cliente_autorizado(db, usuario, cliente_id)
    if data_fim and data_fim < data_inicio:
        raise HTTPException(422, [{"loc": ["body", "data_fim"], "msg": "Data final anterior à inicial", "type": "data"}])
    conteudo = nome = sha = None
    if arquivo and arquivo.filename:
        conteudo = await arquivo.read(get_settings().upload_max_bytes + 1)
        if len(conteudo) > get_settings().upload_max_bytes:
            raise HTTPException(413, "Arquivo excede o tamanho máximo")
        if not conteudo.startswith(b"%PDF-"):
            raise HTTPException(415, "Envie a procuração em PDF")
        nome, sha = arquivo.filename[:200], hashlib.sha256(conteudo).hexdigest()
    p = Procuracao(
        escritorio_id=usuario.escritorio_id,
        cliente_id=cliente_id,
        tipo=tipo,
        outorgado_nome=outorgado_nome,
        outorgado_documento="".join(ch for ch in outorgado_documento.upper() if ch.isalnum()),
        poderes=poderes,
        data_inicio=data_inicio,
        data_fim=data_fim,
        arquivo=conteudo,
        arquivo_nome=nome,
        arquivo_sha256=sha,
    )
    db.add(p)
    db.commit()
    return _proc_saida(p)


@router.get("/procuracoes/{procuracao_id}/arquivo", summary="Baixar PDF da procuração")
def baixar_procuracao(procuracao_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    p = db.get(Procuracao, procuracao_id)
    if not p or p.escritorio_id != usuario.escritorio_id or (usuario.papel == "cliente" and p.cliente_id != usuario.cliente_id) or not p.arquivo:
        raise HTTPException(404, "Arquivo não encontrado")
    return Response(p.arquivo, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="procuracao-{p.id}.pdf"'})


@router.post("/procuracoes/{procuracao_id}/revogar", response_model=ProcuracaoSaida, summary="Revogar procuração")
def revogar_procuracao(procuracao_id: int, usuario: Usuario = Depends(equipe_escritorio), db: Session = Depends(get_db)):
    p = db.get(Procuracao, procuracao_id)
    if not p or p.escritorio_id != usuario.escritorio_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Procuração não encontrada")
    p.revogada_em = p.revogada_em or agora()
    db.commit()
    return _proc_saida(p)
