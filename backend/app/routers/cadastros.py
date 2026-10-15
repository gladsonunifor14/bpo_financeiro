"""Cadastros: consulta CNPJ, escritório, clientes, usuários e chaves de API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..audit import registrar_evento
from ..database import get_db
from ..models import ChaveApi, Cliente, Escritorio, Usuario, agora
from ..schemas import (
    ChaveApiCriada,
    ChaveApiEntrada,
    ChaveApiSaida,
    ClienteAtualizacao,
    ClienteEntrada,
    ClienteSaida,
    ConsultaCNPJSaida,
    EscritorioAtualizacao,
    EscritorioSaida,
    Pagina,
    UsuarioAtualizacao,
    UsuarioEntrada,
    UsuarioSaida,
)
from ..security import (
    equipe_escritorio,
    gerar_chave_api,
    hash_senha,
    hash_token,
    obter_cliente_autorizado,
    problemas_senha,
    somente_admin,
    usuario_atual,
)
from ..services import cnpj as cnpj_svc

router = APIRouter(prefix="/api/v1", tags=["Cadastros"])

CAMPOS_RECEITA = (
    "razao_social", "nome_fantasia", "situacao_cadastral", "cnae_principal", "email", "telefone",
    "logradouro", "numero", "complemento", "bairro", "municipio", "uf", "cep",
)


def _consultar(cnpj: str) -> cnpj_svc.DadosCNPJ:
    try:
        return cnpj_svc.consultar(cnpj)
    except cnpj_svc.ErroConsultaCNPJ as e:
        raise HTTPException(e.status, e.mensagem)


@router.get("/cnpj/{cnpj}", response_model=ConsultaCNPJSaida, summary="Consultar CNPJ na base da Receita Federal")
def consultar_cnpj(cnpj: str, _: Usuario = Depends(equipe_escritorio)):
    """Aceita CNPJ numérico ou alfanumérico, com ou sem máscara."""
    return _consultar(cnpj).para_dict()


# ------------------------------------------------------------------ escritório
@router.get("/escritorio", response_model=EscritorioSaida, summary="Dados do escritório")
def obter_escritorio(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return db.get(Escritorio, usuario.escritorio_id)


@router.put("/escritorio", response_model=EscritorioSaida, summary="Atualizar dados do escritório")
def atualizar_escritorio(dados: EscritorioAtualizacao, usuario: Usuario = Depends(somente_admin), db: Session = Depends(get_db)):
    esc = db.get(Escritorio, usuario.escritorio_id)
    for k, v in dados.model_dump(exclude_unset=True).items():
        setattr(esc, k, v)
    db.commit()
    return esc


@router.post("/escritorio/reimportar-receita", response_model=EscritorioSaida, summary="Atualizar escritório com dados da Receita")
def reimportar_escritorio(usuario: Usuario = Depends(somente_admin), db: Session = Depends(get_db)):
    esc = db.get(Escritorio, usuario.escritorio_id)
    dados = _consultar(esc.cnpj)
    for k in CAMPOS_RECEITA:
        v = getattr(dados, k)
        if v:
            setattr(esc, k, v)
    esc.dados_receita = dados.bruto
    db.commit()
    return esc


# ------------------------------------------------------------------ clientes
@router.get("/clientes", response_model=Pagina, summary="Listar clientes")
def listar_clientes(
    busca: str | None = Query(default=None, max_length=100),
    ativos: bool | None = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    q = select(Cliente).where(Cliente.escritorio_id == usuario.escritorio_id)
    if usuario.papel == "cliente":
        q = q.where(Cliente.id == usuario.cliente_id)
    if busca:
        termo = f"%{busca.strip()}%"
        q = q.where(or_(Cliente.razao_social.ilike(termo), Cliente.nome_fantasia.ilike(termo), Cliente.cnpj.ilike(f"%{cnpj_svc.normalizar(busca)}%")))
    if ativos is not None:
        q = q.where(Cliente.ativo.is_(ativos))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    itens = db.scalars(q.order_by(Cliente.razao_social).offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
    return Pagina(total=total, itens=[ClienteSaida.model_validate(c).model_dump(mode="json") for c in itens])


@router.post("/clientes", response_model=ClienteSaida, status_code=201, summary="Cadastrar cliente (importa dados da Receita)")
def criar_cliente(dados: ClienteEntrada, usuario: Usuario = Depends(equipe_escritorio), db: Session = Depends(get_db)):
    if db.scalar(select(Cliente.id).where(Cliente.escritorio_id == usuario.escritorio_id, Cliente.cnpj == dados.cnpj)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cliente com este CNPJ já cadastrado")
    valores = dados.model_dump(exclude={"importar_receita", "cnpj"}, exclude_none=True)
    bruto = None
    if dados.importar_receita:
        receita = _consultar(dados.cnpj)
        bruto = receita.bruto
        for k in CAMPOS_RECEITA:
            v = getattr(receita, k)
            if v and k not in valores:  # o que o usuário digitou prevalece
                valores[k] = v
    if not valores.get("razao_social"):
        raise HTTPException(422, [{"loc": ["body", "razao_social"], "msg": "Informe a razão social", "type": "obrigatorio"}])
    cliente = Cliente(escritorio_id=usuario.escritorio_id, cnpj=dados.cnpj, dados_receita=bruto, **valores)
    db.add(cliente)
    db.commit()
    return cliente


@router.get("/clientes/{cliente_id}", response_model=ClienteSaida, summary="Detalhar cliente")
def obter_cliente(cliente_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return obter_cliente_autorizado(db, usuario, cliente_id)


@router.put("/clientes/{cliente_id}", response_model=ClienteSaida, summary="Atualizar cliente")
def atualizar_cliente(cliente_id: int, dados: ClienteAtualizacao, usuario: Usuario = Depends(equipe_escritorio), db: Session = Depends(get_db)):
    cliente = obter_cliente_autorizado(db, usuario, cliente_id)
    for k, v in dados.model_dump(exclude_unset=True).items():
        setattr(cliente, k, v)
    db.commit()
    return cliente


@router.post("/clientes/{cliente_id}/reimportar-receita", response_model=ClienteSaida, summary="Atualizar cliente com dados da Receita")
def reimportar_cliente(cliente_id: int, usuario: Usuario = Depends(equipe_escritorio), db: Session = Depends(get_db)):
    cliente = obter_cliente_autorizado(db, usuario, cliente_id)
    dados = _consultar(cliente.cnpj)
    for k in CAMPOS_RECEITA:
        v = getattr(dados, k)
        if v:
            setattr(cliente, k, v)
    cliente.dados_receita = dados.bruto
    db.commit()
    return cliente


@router.delete("/clientes/{cliente_id}", status_code=204, summary="Inativar cliente")
def inativar_cliente(cliente_id: int, usuario: Usuario = Depends(somente_admin), db: Session = Depends(get_db)):
    """Exclusão lógica: dados fiscais são mantidos pelo prazo legal de guarda."""
    cliente = obter_cliente_autorizado(db, usuario, cliente_id)
    cliente.ativo = False
    db.commit()
    return Response(status_code=204)


@router.get("/clientes/{cliente_id}/exportar-dados", summary="Portabilidade LGPD (art. 18, V)")
def exportar_dados_cliente(cliente_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Exporta os dados cadastrais do cliente e de seus usuários em formato estruturado."""
    cliente = obter_cliente_autorizado(db, usuario, cliente_id)
    usuarios = db.scalars(select(Usuario).where(Usuario.cliente_id == cliente.id)).all()
    registrar_evento(db, "EXPORTACAO_LGPD", tabela="cliente", registro_id=cliente.id)
    db.commit()
    return {
        "cliente": ClienteSaida.model_validate(cliente).model_dump(mode="json"),
        "usuarios": [UsuarioSaida.model_validate(u).model_dump(mode="json") for u in usuarios],
        "gerado_em": agora().isoformat(),
    }


# ------------------------------------------------------------------ usuários
@router.get("/usuarios", response_model=list[UsuarioSaida], summary="Listar usuários do escritório")
def listar_usuarios(usuario: Usuario = Depends(somente_admin), db: Session = Depends(get_db)):
    return db.scalars(select(Usuario).where(Usuario.escritorio_id == usuario.escritorio_id).order_by(Usuario.nome)).all()


@router.post("/usuarios", response_model=UsuarioSaida, status_code=201, summary="Convidar usuário")
def criar_usuario(dados: UsuarioEntrada, usuario: Usuario = Depends(somente_admin), db: Session = Depends(get_db)):
    if dados.papel == "cliente":
        if not dados.cliente_id:
            raise HTTPException(422, [{"loc": ["body", "cliente_id"], "msg": "Selecione o cliente deste usuário", "type": "obrigatorio"}])
        obter_cliente_autorizado(db, usuario, dados.cliente_id)
    problemas = problemas_senha(dados.senha_inicial)
    if problemas:
        raise HTTPException(422, [{"loc": ["body", "senha_inicial"], "msg": "A senha deve " + ", ".join(problemas), "type": "senha_fraca"}])
    if db.scalar(select(Usuario.id).where(Usuario.email == dados.email.lower())):
        raise HTTPException(409, "E-mail já utilizado")
    novo = Usuario(
        escritorio_id=usuario.escritorio_id,
        cliente_id=dados.cliente_id if dados.papel == "cliente" else None,
        nome=dados.nome,
        email=dados.email.lower(),
        senha_hash=hash_senha(dados.senha_inicial),
        papel=dados.papel,
    )
    db.add(novo)
    db.commit()
    return novo


@router.patch("/usuarios/{usuario_id}", response_model=UsuarioSaida, summary="Alterar perfil/ativar/desativar usuário")
def atualizar_usuario(usuario_id: int, dados: UsuarioAtualizacao, usuario: Usuario = Depends(somente_admin), db: Session = Depends(get_db)):
    alvo = db.get(Usuario, usuario_id)
    if not alvo or alvo.escritorio_id != usuario.escritorio_id:
        raise HTTPException(404, "Usuário não encontrado")
    if alvo.id == usuario.id and (dados.ativo is False or (dados.papel and dados.papel != "admin")):
        raise HTTPException(422, "Você não pode desativar nem rebaixar o próprio acesso")
    for k, v in dados.model_dump(exclude_unset=True).items():
        setattr(alvo, k, v)
    db.commit()
    return alvo


# ------------------------------------------------------------------ chaves de API
@router.get("/chaves-api", response_model=list[ChaveApiSaida], tags=["Integração"], summary="Listar chaves de API")
def listar_chaves(usuario: Usuario = Depends(somente_admin), db: Session = Depends(get_db)):
    return db.scalars(select(ChaveApi).where(ChaveApi.escritorio_id == usuario.escritorio_id).order_by(ChaveApi.criado_em.desc())).all()


@router.post("/chaves-api", response_model=ChaveApiCriada, status_code=201, tags=["Integração"], summary="Criar chave de API")
def criar_chave(dados: ChaveApiEntrada, usuario: Usuario = Depends(somente_admin), db: Session = Depends(get_db)):
    """A chave autentica como o usuário que a criou, via cabeçalho `X-API-Key`.
    Apenas o hash é armazenado; o valor é exibido uma única vez."""
    chave, prefixo = gerar_chave_api()
    registro = ChaveApi(escritorio_id=usuario.escritorio_id, usuario_id=usuario.id, nome=dados.nome, prefixo=prefixo, hash=hash_token(chave))
    db.add(registro)
    db.commit()
    return ChaveApiCriada(**ChaveApiSaida.model_validate(registro).model_dump(), chave=chave)


@router.delete("/chaves-api/{chave_id}", status_code=204, tags=["Integração"], summary="Revogar chave de API")
def revogar_chave(chave_id: int, usuario: Usuario = Depends(somente_admin), db: Session = Depends(get_db)):
    registro = db.get(ChaveApi, chave_id)
    if not registro or registro.escritorio_id != usuario.escritorio_id:
        raise HTTPException(404, "Chave não encontrada")
    registro.revogada_em = registro.revogada_em or agora()
    db.commit()
    return Response(status_code=204)
