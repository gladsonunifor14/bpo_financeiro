"""Repositório de documentos: plano de contas, NF-e (XML), extratos bancários, aplicações e Open Finance."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..database import get_db
from ..models import (
    ConsentimentoOpenFinance,
    ContaBancaria,
    ImportacaoExtrato,
    ItemNota,
    LancamentoBancario,
    NotaFiscal,
    PlanoConta,
    PosicaoAplicacao,
    Usuario,
)
from ..schemas import (
    ClassificacaoLoteEntrada,
    ClassificarItemEntrada,
    ClassificarLancamentoEntrada,
    ConsentimentoEntrada,
    ConsentimentoSaida,
    ContaBancariaEntrada,
    ContaBancariaSaida,
    ImportacaoSaida,
    ItemNotaSaida,
    LancamentoSaida,
    NotaDetalhe,
    NotaSaida,
    Pagina,
    PlanoContaEntrada,
    PlanoContaSaida,
    PosicaoEntrada,
    PosicaoSaida,
    ResultadoClassificacao,
    ResultadoImportacaoSaida,
    SimulacaoTributosEntrada,
    SincronizarOpenFinanceEntrada,
    SugestaoSaida,
)
from ..security import equipe_escritorio, obter_cliente_autorizado, usuario_atual
from ..services import classificador, extratos, investimentos, nfe, open_finance
from ..services.plano_contas import GRUPOS_VALIDOS

router = APIRouter(prefix="/api/v1")


async def _ler_upload(arquivo: UploadFile, limite: int | None = None) -> bytes:
    limite = limite or get_settings().upload_max_bytes
    dados = await arquivo.read(limite + 1)
    if len(dados) > limite:
        raise HTTPException(413, f"Arquivo excede o tamanho máximo de {limite // (1024 * 1024)} MB")
    if not dados:
        raise HTTPException(422, "Arquivo vazio")
    return dados


def _conta_plano(db: Session, usuario: Usuario, conta_id: int) -> PlanoConta:
    conta = db.get(PlanoConta, conta_id)
    if not conta or conta.escritorio_id != usuario.escritorio_id or not conta.ativo:
        raise HTTPException(422, [{"loc": ["body", "conta_id"], "msg": "Conta do plano inválida", "type": "conta"}])
    return conta


# ================================================================== plano de contas
@router.get("/plano-contas", response_model=list[PlanoContaSaida], tags=["Plano de contas"], summary="Listar plano de contas")
def listar_plano(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return db.scalars(select(PlanoConta).where(PlanoConta.escritorio_id == usuario.escritorio_id).order_by(PlanoConta.codigo)).all()


@router.post("/plano-contas", response_model=PlanoContaSaida, status_code=201, tags=["Plano de contas"], summary="Criar conta gerencial")
def criar_conta_plano(dados: PlanoContaEntrada, usuario: Usuario = Depends(equipe_escritorio), db: Session = Depends(get_db)):
    if dados.grupo not in GRUPOS_VALIDOS:
        raise HTTPException(422, [{"loc": ["body", "grupo"], "msg": "Grupo inválido", "type": "grupo"}])
    if db.scalar(select(PlanoConta.id).where(PlanoConta.escritorio_id == usuario.escritorio_id, PlanoConta.codigo == dados.codigo)):
        raise HTTPException(409, "Código já existe")
    conta = PlanoConta(escritorio_id=usuario.escritorio_id, **dados.model_dump())
    db.add(conta)
    db.commit()
    return conta


# ================================================================== notas fiscais
@router.post("/clientes/{cliente_id}/notas/importar", response_model=list[ResultadoImportacaoSaida], tags=["Notas fiscais"],
             summary="Importar XML de NF-e (ou ZIP com vários XMLs)")
async def importar_notas(cliente_id: int, arquivos: list[UploadFile] = File(...), usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Identifica automaticamente se a nota foi **emitida** ou **recebida** pelo cliente
    (comparando o CNPJ com emitente/destinatário), evita duplicidade pela chave de acesso e
    classifica cada item em receita/custo/despesa a partir do CFOP."""
    cliente = obter_cliente_autorizado(db, usuario, cliente_id)
    if len(arquivos) > 50:
        raise HTTPException(422, "Envie no máximo 50 arquivos por vez (use ZIP para lotes maiores)")
    resultados = []
    for arq in arquivos:
        nome = (arq.filename or "arquivo")[:200]
        limite = get_settings().upload_max_bytes * (10 if nome.lower().endswith(".zip") else 1)
        conteudo = await _ler_upload(arq, limite)
        try:
            xmls = nfe.extrair_xmls(nome, conteudo)
        except nfe.ErroNFe as e:
            resultados.append(ResultadoImportacaoSaida(arquivo=nome, status="erro", mensagem=str(e)))
            continue
        for nome_xml, dados in xmls:
            with db.begin_nested():
                r = nfe.importar(db, cliente, dados, nome_xml, usuario.id)
            resultados.append(ResultadoImportacaoSaida(**r.__dict__))
    db.commit()
    return resultados


@router.get("/clientes/{cliente_id}/notas", response_model=Pagina, tags=["Notas fiscais"], summary="Listar notas fiscais")
def listar_notas(
    cliente_id: int,
    tipo: str | None = Query(default=None, pattern="^(emitida|recebida)$"),
    inicio: date | None = None,
    fim: date | None = None,
    busca: str | None = Query(default=None, max_length=100),
    pendentes: bool = Query(False, description="Somente notas com itens sem classificação"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    obter_cliente_autorizado(db, usuario, cliente_id)
    q = select(NotaFiscal).where(NotaFiscal.cliente_id == cliente_id)
    if tipo:
        q = q.where(NotaFiscal.tipo == tipo)
    if inicio:
        q = q.where(NotaFiscal.data_emissao >= inicio)
    if fim:
        q = q.where(NotaFiscal.data_emissao <= fim)
    if busca:
        t = f"%{busca}%"
        q = q.where(or_(NotaFiscal.numero.ilike(t), NotaFiscal.emitente_nome.ilike(t), NotaFiscal.destinatario_nome.ilike(t), NotaFiscal.chave.ilike(t)))
    if pendentes:
        q = q.where(NotaFiscal.id.in_(select(ItemNota.nota_id).where(ItemNota.conta_id.is_(None))))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    itens = db.scalars(q.order_by(NotaFiscal.data_emissao.desc(), NotaFiscal.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
    return Pagina(total=total, itens=[NotaSaida.model_validate(n).model_dump(mode="json") for n in itens])


def _nota(db: Session, usuario: Usuario, nota_id: int) -> NotaFiscal:
    nota = db.scalar(select(NotaFiscal).options(selectinload(NotaFiscal.itens), selectinload(NotaFiscal.duplicatas)).where(NotaFiscal.id == nota_id))
    if not nota:
        raise HTTPException(404, "Nota não encontrada")
    try:
        obter_cliente_autorizado(db, usuario, nota.cliente_id)
    except HTTPException:
        raise HTTPException(404, "Nota não encontrada")
    return nota


@router.get("/notas/{nota_id}", response_model=NotaDetalhe, tags=["Notas fiscais"], summary="Detalhar nota com itens e duplicatas")
def obter_nota(nota_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    return _nota(db, usuario, nota_id)


@router.get("/notas/{nota_id}/xml", tags=["Notas fiscais"], summary="Baixar XML original")
def baixar_xml(nota_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    nota = _nota(db, usuario, nota_id)
    return Response(nota.xml, media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="{nota.chave}.xml"'})


@router.put("/notas/itens/{item_id}/classificacao", response_model=ItemNotaSaida, tags=["Notas fiscais"], summary="Reclassificar item da nota")
def classificar_item(item_id: int, dados: ClassificarItemEntrada, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    item = db.get(ItemNota, item_id)
    if not item:
        raise HTTPException(404, "Item não encontrado")
    _nota(db, usuario, item.nota_id)
    item.conta_id = _conta_plano(db, usuario, dados.conta_id).id
    item.classificacao_origem = "manual"
    db.commit()
    return item


@router.delete("/notas/{nota_id}", status_code=204, tags=["Notas fiscais"], summary="Excluir nota importada")
def excluir_nota(nota_id: int, usuario: Usuario = Depends(equipe_escritorio), db: Session = Depends(get_db)):
    db.delete(_nota(db, usuario, nota_id))
    db.commit()
    return Response(status_code=204)


# ================================================================== contas bancárias
@router.get("/clientes/{cliente_id}/contas-bancarias", response_model=list[ContaBancariaSaida], tags=["Extratos bancários"], summary="Listar contas bancárias")
def listar_contas(cliente_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    obter_cliente_autorizado(db, usuario, cliente_id)
    return db.scalars(select(ContaBancaria).where(ContaBancaria.cliente_id == cliente_id).order_by(ContaBancaria.banco_nome)).all()


@router.post("/contas-bancarias", response_model=ContaBancariaSaida, status_code=201, tags=["Extratos bancários"], summary="Cadastrar conta bancária")
def criar_conta(dados: ContaBancariaEntrada, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    cliente = obter_cliente_autorizado(db, usuario, dados.cliente_id)
    conta = ContaBancaria(escritorio_id=cliente.escritorio_id, **dados.model_dump())
    db.add(conta)
    db.commit()
    return conta


def _conta_bancaria(db: Session, usuario: Usuario, conta_id: int) -> ContaBancaria:
    conta = db.get(ContaBancaria, conta_id)
    if not conta:
        raise HTTPException(404, "Conta bancária não encontrada")
    try:
        obter_cliente_autorizado(db, usuario, conta.cliente_id)
    except HTTPException:
        raise HTTPException(404, "Conta bancária não encontrada")
    return conta


# ================================================================== extratos
def _gravar_lancamentos(db: Session, conta: ContaBancaria, lidos: list[extratos.LancamentoLido], imp: ImportacaoExtrato) -> list[LancamentoBancario]:
    existentes = set(db.scalars(select(LancamentoBancario.hash_dedup).where(LancamentoBancario.conta_bancaria_id == conta.id)))
    novos = []
    for lido in lidos:
        h = lido.hash_dedup()
        if h in existentes:
            imp.duplicados += 1
            continue
        existentes.add(h)
        lanc = LancamentoBancario(
            escritorio_id=conta.escritorio_id,
            cliente_id=conta.cliente_id,
            conta_bancaria_id=conta.id,
            importacao_id=imp.id,
            data=lido.data,
            historico=lido.historico,
            historico_normalizado=extratos.normalizar_historico(lido.historico),
            documento=lido.documento,
            valor=lido.valor,
            natureza=lido.natureza,
            hash_dedup=h,
        )
        db.add(lanc)
        novos.append(lanc)
    imp.quantidade = len(novos)
    db.flush()
    return novos


def _aplicar_ia(db: Session, escritorio_id: int, cliente_id: int, lancs: list[LancamentoBancario]) -> list[SugestaoSaida]:
    minimo = get_settings().ia_confianca_minima
    por_id = {lanc.id: lanc for lanc in lancs}
    saida = []
    for s in classificador.sugerir(db, escritorio_id, cliente_id, lancs):
        aplicar = s.confianca >= minimo and s.metodo != "regra"
        if aplicar:
            lanc = por_id[s.lancamento_id]
            lanc.conta_id = s.conta_id
            lanc.status_classificacao = "ia_sugerida"
            lanc.confianca_ia = s.confianca
        saida.append(SugestaoSaida(lancamento_id=s.lancamento_id, conta_id=s.conta_id, confianca=s.confianca, metodo=s.metodo, aplicada=aplicar))
    return saida


@router.post("/contas-bancarias/{conta_id}/extratos", response_model=ImportacaoSaida, status_code=201, tags=["Extratos bancários"],
             summary="Importar extrato (OFX ou CSV)")
async def importar_extrato(conta_id: int, arquivo: UploadFile = File(...), usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Lançamentos já importados são ignorados (deduplicação por FITID ou data+histórico+valor).
    Após a importação, a IA replica as classificações feitas anteriormente pelo cliente."""
    conta = _conta_bancaria(db, usuario, conta_id)
    conteudo = await _ler_upload(arquivo)
    nome = (arquivo.filename or "extrato")[:200]
    try:
        formato, lidos = extratos.ler(nome, conteudo)
    except extratos.ErroExtrato as e:
        raise HTTPException(422, str(e))
    imp = ImportacaoExtrato(escritorio_id=conta.escritorio_id, cliente_id=conta.cliente_id, conta_bancaria_id=conta.id,
                            arquivo_nome=nome, formato=formato, importado_por_id=usuario.id)
    db.add(imp)
    db.flush()
    novos = _gravar_lancamentos(db, conta, lidos, imp)
    sugestoes = _aplicar_ia(db, conta.escritorio_id, conta.cliente_id, novos)
    db.commit()
    saida = ImportacaoSaida.model_validate(imp)
    saida.classificados_ia = sum(1 for s in sugestoes if s.aplicada)
    return saida


@router.get("/clientes/{cliente_id}/lancamentos", response_model=Pagina, tags=["Extratos bancários"], summary="Listar lançamentos bancários")
def listar_lancamentos(
    cliente_id: int,
    conta_bancaria_id: int | None = None,
    status_classificacao: str | None = Query(default=None, pattern="^(pendente|manual|ia_sugerida|ia_confirmada)$"),
    natureza: str | None = Query(default=None, pattern="^[CD]$"),
    inicio: date | None = None,
    fim: date | None = None,
    busca: str | None = Query(default=None, max_length=100),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    obter_cliente_autorizado(db, usuario, cliente_id)
    q = select(LancamentoBancario).where(LancamentoBancario.cliente_id == cliente_id)
    if conta_bancaria_id:
        q = q.where(LancamentoBancario.conta_bancaria_id == conta_bancaria_id)
    if status_classificacao:
        q = q.where(LancamentoBancario.status_classificacao == status_classificacao)
    if natureza:
        q = q.where(LancamentoBancario.natureza == natureza)
    if inicio:
        q = q.where(LancamentoBancario.data >= inicio)
    if fim:
        q = q.where(LancamentoBancario.data <= fim)
    if busca:
        q = q.where(LancamentoBancario.historico.ilike(f"%{busca}%"))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    itens = db.scalars(q.order_by(LancamentoBancario.data.desc(), LancamentoBancario.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
    return Pagina(total=total, itens=[LancamentoSaida.model_validate(i).model_dump(mode="json") for i in itens])


def _lancamento(db: Session, usuario: Usuario, lanc_id: int) -> LancamentoBancario:
    lanc = db.get(LancamentoBancario, lanc_id)
    if not lanc:
        raise HTTPException(404, "Lançamento não encontrado")
    try:
        obter_cliente_autorizado(db, usuario, lanc.cliente_id)
    except HTTPException:
        raise HTTPException(404, "Lançamento não encontrado")
    return lanc


@router.put("/lancamentos/{lancamento_id}/classificacao", response_model=ResultadoClassificacao, tags=["Extratos bancários"],
            summary="Classificar lançamento (e replicar aos semelhantes)")
def classificar_lancamento(lancamento_id: int, dados: ClassificarLancamentoEntrada, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    lanc = _lancamento(db, usuario, lancamento_id)
    conta = _conta_plano(db, usuario, dados.conta_id)
    lanc.conta_id = conta.id
    lanc.status_classificacao = "manual"
    lanc.confianca_ia = None
    lanc.classificado_por_id = usuario.id
    replicados = 0
    if dados.replicar_semelhantes and lanc.historico_normalizado:
        semelhantes = db.scalars(
            select(LancamentoBancario).where(
                LancamentoBancario.cliente_id == lanc.cliente_id,
                LancamentoBancario.id != lanc.id,
                LancamentoBancario.historico_normalizado == lanc.historico_normalizado,
                LancamentoBancario.natureza == lanc.natureza,
                LancamentoBancario.status_classificacao.in_(("pendente", "ia_sugerida")),
            )
        ).all()
        for s in semelhantes:
            s.conta_id = conta.id
            s.status_classificacao = "ia_sugerida"
            s.confianca_ia = 0.97
        replicados = len(semelhantes)
    db.commit()
    return ResultadoClassificacao(atualizados=1, replicados=replicados)


@router.post("/lancamentos/classificacao-lote", response_model=ResultadoClassificacao, tags=["Extratos bancários"],
             summary="Classificar em lote ou confirmar sugestões da IA")
def classificar_lote(dados: ClassificacaoLoteEntrada, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    conta = _conta_plano(db, usuario, dados.conta_id) if dados.conta_id else None
    n = 0
    for lid in dict.fromkeys(dados.lancamento_ids):
        lanc = _lancamento(db, usuario, lid)
        if conta:
            lanc.conta_id, lanc.status_classificacao, lanc.confianca_ia = conta.id, "manual", None
        elif lanc.status_classificacao == "ia_sugerida" and lanc.conta_id:
            lanc.status_classificacao = "ia_confirmada"
        else:
            continue
        lanc.classificado_por_id = usuario.id
        n += 1
    db.commit()
    return ResultadoClassificacao(atualizados=n)


@router.post("/clientes/{cliente_id}/lancamentos/classificar-ia", response_model=list[SugestaoSaida], tags=["Extratos bancários"],
             summary="Rodar a IA nos lançamentos pendentes")
def rodar_ia(cliente_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Aprende com as classificações confirmadas e aplica (status `ia_sugerida`) as sugestões
    com confiança acima do limite configurado. As demais retornam apenas como sugestão."""
    cliente = obter_cliente_autorizado(db, usuario, cliente_id)
    pendentes = db.scalars(select(LancamentoBancario).where(LancamentoBancario.cliente_id == cliente.id, LancamentoBancario.status_classificacao == "pendente")).all()
    if not pendentes:
        return []
    sugestoes = _aplicar_ia(db, cliente.escritorio_id, cliente.id, list(pendentes))
    db.commit()
    return sugestoes


# ================================================================== aplicações financeiras
def _posicao_saida(p: PosicaoAplicacao) -> PosicaoSaida:
    r = investimentos.calcular(p.saldo_inicial, p.aplicacoes, p.resgates, p.saldo_final_bruto, p.irrf, p.iof, p.taxa_administracao, p.cdi_mes_percentual)
    return PosicaoSaida(**PosicaoSaida.model_validate(p).model_dump(exclude=set(r.__dict__)), **r.__dict__)


@router.get("/clientes/{cliente_id}/aplicacoes", response_model=list[PosicaoSaida], tags=["Aplicações financeiras"],
            summary="Extratos mensais de aplicações com rendimentos calculados")
def listar_aplicacoes(cliente_id: int, inicio: date | None = None, fim: date | None = None, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    obter_cliente_autorizado(db, usuario, cliente_id)
    q = select(PosicaoAplicacao).where(PosicaoAplicacao.cliente_id == cliente_id)
    if inicio:
        q = q.where(PosicaoAplicacao.competencia >= inicio.replace(day=1))
    if fim:
        q = q.where(PosicaoAplicacao.competencia <= fim)
    return [_posicao_saida(p) for p in db.scalars(q.order_by(PosicaoAplicacao.competencia.desc(), PosicaoAplicacao.produto))]


@router.post("/aplicacoes", response_model=PosicaoSaida, status_code=201, tags=["Aplicações financeiras"], summary="Lançar extrato mensal de aplicação")
def criar_aplicacao(dados: PosicaoEntrada, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    conta = _conta_bancaria(db, usuario, dados.conta_bancaria_id)
    p = PosicaoAplicacao(escritorio_id=conta.escritorio_id, cliente_id=conta.cliente_id, **dados.model_dump(exclude={"competencia"}),
                         competencia=dados.competencia.replace(day=1))
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe extrato deste produto nesta competência")
    return _posicao_saida(p)


@router.delete("/aplicacoes/{posicao_id}", status_code=204, tags=["Aplicações financeiras"], summary="Excluir extrato de aplicação")
def excluir_aplicacao(posicao_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    p = db.get(PosicaoAplicacao, posicao_id)
    if not p:
        raise HTTPException(404, "Registro não encontrado")
    _conta_bancaria(db, usuario, p.conta_bancaria_id)
    db.delete(p)
    db.commit()
    return Response(status_code=204)


@router.post("/aplicacoes/simular-tributos", tags=["Aplicações financeiras"], summary="Simular IOF e IRRF de um resgate")
def simular_tributos(dados: SimulacaoTributosEntrada, _: Usuario = Depends(usuario_atual)):
    """Tabela regressiva de IR (22,5% → 15%) e IOF regressivo para resgates com menos de 30 dias."""
    r = investimentos.estimar_tributos_resgate(dados.rendimento, dados.dias)
    return {k: str(v) for k, v in r.items()}


# ================================================================== open finance
@router.get("/open-finance/status", tags=["Open Finance"], summary="Disponibilidade da integração Open Finance")
def status_open_finance(_: Usuario = Depends(usuario_atual)):
    try:
        p = open_finance.provedor()
        return {"disponivel": True, "provedor": p.nome}
    except open_finance.OpenFinanceIndisponivel as e:
        return {"disponivel": False, "motivo": str(e)}


@router.post("/open-finance/consentimentos", response_model=ConsentimentoSaida, status_code=201, tags=["Open Finance"],
             summary="Iniciar consentimento do cliente")
def criar_consentimento(dados: ConsentimentoEntrada, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    cliente = obter_cliente_autorizado(db, usuario, dados.cliente_id)
    try:
        p = open_finance.provedor()
    except open_finance.OpenFinanceIndisponivel as e:
        raise HTTPException(501, str(e))
    ide, url = p.criar_consentimento(cliente.cnpj, open_finance.PERMISSOES_PADRAO)
    c = ConsentimentoOpenFinance(escritorio_id=cliente.escritorio_id, cliente_id=cliente.id, provedor=p.nome, id_externo=ide,
                                 permissoes=open_finance.PERMISSOES_PADRAO)
    db.add(c)
    db.commit()
    return ConsentimentoSaida(**ConsentimentoSaida.model_validate(c).model_dump(exclude={"url_autorizacao"}), url_autorizacao=url)


@router.post("/open-finance/consentimentos/{consentimento_id}/sincronizar", response_model=ImportacaoSaida, tags=["Open Finance"],
             summary="Importar transações autorizadas via Open Finance")
def sincronizar(consentimento_id: int, dados: SincronizarOpenFinanceEntrada, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    c = db.get(ConsentimentoOpenFinance, consentimento_id)
    if not c:
        raise HTTPException(404, "Consentimento não encontrado")
    obter_cliente_autorizado(db, usuario, c.cliente_id)
    conta = _conta_bancaria(db, usuario, dados.conta_bancaria_id)
    if conta.cliente_id != c.cliente_id:
        raise HTTPException(422, "A conta não pertence ao cliente do consentimento")
    try:
        p = open_finance.provedor()
    except open_finance.OpenFinanceIndisponivel as e:
        raise HTTPException(501, str(e))
    c.status = p.status_consentimento(c.id_externo)
    if c.status != "autorizado":
        db.commit()
        raise HTTPException(409, f"Consentimento {c.status}")
    imp = ImportacaoExtrato(escritorio_id=conta.escritorio_id, cliente_id=conta.cliente_id, conta_bancaria_id=conta.id,
                            arquivo_nome=f"open-finance:{p.nome}", formato="open_finance", importado_por_id=usuario.id)
    db.add(imp)
    db.flush()
    novos = _gravar_lancamentos(db, conta, p.transacoes(c.id_externo, dados.inicio, dados.fim), imp)
    sugestoes = _aplicar_ia(db, conta.escritorio_id, conta.cliente_id, novos)
    db.commit()
    saida = ImportacaoSaida.model_validate(imp)
    saida.classificados_ia = sum(1 for s in sugestoes if s.aplicada)
    return saida
