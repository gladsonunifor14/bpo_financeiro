"""Modelo de dados. Toda entidade de negócio carrega escritorio_id (isolamento multi-tenant)."""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

Dinheiro = Numeric(16, 2)


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Timestamps:
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)


class EnderecoMixin:
    logradouro: Mapped[str | None] = mapped_column(String(200))
    numero: Mapped[str | None] = mapped_column(String(20))
    complemento: Mapped[str | None] = mapped_column(String(120))
    bairro: Mapped[str | None] = mapped_column(String(120))
    municipio: Mapped[str | None] = mapped_column(String(120))
    uf: Mapped[str | None] = mapped_column(String(2))
    cep: Mapped[str | None] = mapped_column(String(8))


# --------------------------------------------------------------------------- cadastros
class Escritorio(Base, Timestamps, EnderecoMixin):
    __tablename__ = "escritorio"
    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    razao_social: Mapped[str] = mapped_column(String(200))
    nome_fantasia: Mapped[str | None] = mapped_column(String(200))
    crc: Mapped[str | None] = mapped_column(String(30))
    responsavel_tecnico: Mapped[str | None] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(200))
    telefone: Mapped[str | None] = mapped_column(String(30))
    cnae_principal: Mapped[str | None] = mapped_column(String(200))
    situacao_cadastral: Mapped[str | None] = mapped_column(String(50))
    dados_receita: Mapped[dict | None] = mapped_column(JSON)


class Usuario(Base, Timestamps):
    __tablename__ = "usuario"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("cliente.id"), index=True)
    nome: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[str] = mapped_column(String(20), default="analista")  # admin|analista|cliente
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verificado: Mapped[bool] = mapped_column(Boolean, default=False)
    tentativas_falhas: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    senha_alterada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Incrementada ao trocar a senha: invalida todos os access tokens já emitidos
    versao_token: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_login_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    escritorio: Mapped[Escritorio] = relationship()


class DesafioOTP(Base):
    __tablename__ = "desafio_otp"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    finalidade: Mapped[str] = mapped_column(String(20))  # login | recuperacao
    codigo_hash: Mapped[str] = mapped_column(String(255))
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class SessaoRefresh(Base):
    __tablename__ = "sessao_refresh"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class ChaveApi(Base):
    """Chaves para integração sistema-a-sistema (header X-API-Key)."""

    __tablename__ = "chave_api"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    nome: Mapped[str] = mapped_column(String(100))
    prefixo: Mapped[str] = mapped_column(String(12), index=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    revogada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_uso_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Cliente(Base, Timestamps, EnderecoMixin):
    __tablename__ = "cliente"
    __table_args__ = (UniqueConstraint("escritorio_id", "cnpj"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    cnpj: Mapped[str] = mapped_column(String(14), index=True)
    razao_social: Mapped[str] = mapped_column(String(200))
    nome_fantasia: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    telefone: Mapped[str | None] = mapped_column(String(30))
    cnae_principal: Mapped[str | None] = mapped_column(String(200))
    situacao_cadastral: Mapped[str | None] = mapped_column(String(50))
    regime_tributario: Mapped[str | None] = mapped_column(String(20))  # simples|presumido|real|mei
    dados_receita: Mapped[dict | None] = mapped_column(JSON)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


# --------------------------------------------------------------------------- contratos/LGPD
class ModeloContrato(Base, Timestamps):
    __tablename__ = "modelo_contrato"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    titulo: Mapped[str] = mapped_column(String(200))
    versao: Mapped[int] = mapped_column(Integer, default=1)
    conteudo: Mapped[str] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Contrato(Base, Timestamps):
    __tablename__ = "contrato"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    modelo_id: Mapped[int] = mapped_column(ForeignKey("modelo_contrato.id"))
    numero: Mapped[str] = mapped_column(String(30))
    conteudo: Mapped[str] = mapped_column(Text)
    hash_sha256: Mapped[str] = mapped_column(String(64))
    valor_mensal: Mapped[Decimal] = mapped_column(Dinheiro)
    dia_vencimento: Mapped[int] = mapped_column(Integer)
    inicio_vigencia: Mapped[date] = mapped_column(Date)
    fim_vigencia: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="aguardando_aceite")
    aceito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aceito_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    aceite_ip: Mapped[str | None] = mapped_column(String(64))
    aceite_user_agent: Mapped[str | None] = mapped_column(String(300))
    rescindido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_rescisao: Mapped[str | None] = mapped_column(String(500))

    cliente: Mapped[Cliente] = relationship()


class TermoVersao(Base):
    __tablename__ = "termo_versao"
    __table_args__ = (UniqueConstraint("escritorio_id", "tipo", "versao"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(40))  # termos_uso|politica_privacidade|confidencialidade|tratamento_dados
    versao: Mapped[int] = mapped_column(Integer)
    titulo: Mapped[str] = mapped_column(String(200))
    conteudo: Mapped[str] = mapped_column(Text)
    hash_sha256: Mapped[str] = mapped_column(String(64))
    obrigatorio: Mapped[bool] = mapped_column(Boolean, default=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    publicado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class AceiteTermo(Base):
    __tablename__ = "aceite_termo"
    __table_args__ = (UniqueConstraint("termo_id", "usuario_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    termo_id: Mapped[int] = mapped_column(ForeignKey("termo_versao.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    hash_sha256: Mapped[str] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    aceito_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Procuracao(Base, Timestamps):
    __tablename__ = "procuracao"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))  # ecac|particular|publica|sefaz|prefeitura|outra
    outorgado_nome: Mapped[str] = mapped_column(String(200))
    outorgado_documento: Mapped[str] = mapped_column(String(14))
    poderes: Mapped[str] = mapped_column(Text)
    data_inicio: Mapped[date] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)
    revogada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arquivo_nome: Mapped[str | None] = mapped_column(String(200))
    arquivo_sha256: Mapped[str | None] = mapped_column(String(64))
    arquivo: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)


# --------------------------------------------------------------------------- plano de contas
class PlanoConta(Base):
    __tablename__ = "plano_conta"
    __table_args__ = (UniqueConstraint("escritorio_id", "codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nome: Mapped[str] = mapped_column(String(150))
    # grupo da DRE (ver services/plano_contas.py) ou 'nao_dre' (transferências, liquidações, ativo)
    grupo: Mapped[str] = mapped_column(String(40))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


# --------------------------------------------------------------------------- notas fiscais
class NotaFiscal(Base):
    __tablename__ = "nota_fiscal"
    __table_args__ = (UniqueConstraint("cliente_id", "chave"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    chave: Mapped[str] = mapped_column(String(44), index=True)
    modelo: Mapped[str] = mapped_column(String(2))
    serie: Mapped[str | None] = mapped_column(String(5))
    numero: Mapped[str] = mapped_column(String(15))
    data_emissao: Mapped[date] = mapped_column(Date, index=True)
    tipo: Mapped[str] = mapped_column(String(10))  # emitida | recebida
    tipo_operacao: Mapped[str] = mapped_column(String(10))  # entrada | saida (tpNF)
    natureza_operacao: Mapped[str | None] = mapped_column(String(200))
    emitente_documento: Mapped[str] = mapped_column(String(14))
    emitente_nome: Mapped[str] = mapped_column(String(200))
    destinatario_documento: Mapped[str | None] = mapped_column(String(14))
    destinatario_nome: Mapped[str | None] = mapped_column(String(200))
    valor_produtos: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    valor_desconto: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    valor_frete: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    valor_icms: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    valor_icms_st: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    valor_ipi: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    valor_pis: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    valor_cofins: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    valor_total: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    xml_sha256: Mapped[str] = mapped_column(String(64))
    xml: Mapped[str] = mapped_column(Text, deferred=True)
    importado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    importado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    itens: Mapped[list["ItemNota"]] = relationship(back_populates="nota", cascade="all, delete-orphan")
    duplicatas: Mapped[list["Duplicata"]] = relationship(back_populates="nota", cascade="all, delete-orphan")


class ItemNota(Base):
    __tablename__ = "item_nota"
    id: Mapped[int] = mapped_column(primary_key=True)
    nota_id: Mapped[int] = mapped_column(ForeignKey("nota_fiscal.id", ondelete="CASCADE"), index=True)
    numero_item: Mapped[int] = mapped_column(Integer)
    codigo: Mapped[str | None] = mapped_column(String(60))
    descricao: Mapped[str] = mapped_column(String(300))
    ncm: Mapped[str | None] = mapped_column(String(8))
    cfop: Mapped[str] = mapped_column(String(4), index=True)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    valor_total: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("plano_conta.id"))
    classificacao_origem: Mapped[str] = mapped_column(String(10), default="cfop")  # cfop|manual|pendente

    nota: Mapped[NotaFiscal] = relationship(back_populates="itens")
    conta: Mapped[PlanoConta | None] = relationship()


class Duplicata(Base):
    __tablename__ = "duplicata"
    id: Mapped[int] = mapped_column(primary_key=True)
    nota_id: Mapped[int] = mapped_column(ForeignKey("nota_fiscal.id", ondelete="CASCADE"), index=True)
    numero: Mapped[str | None] = mapped_column(String(60))
    vencimento: Mapped[date] = mapped_column(Date, index=True)
    valor: Mapped[Decimal] = mapped_column(Dinheiro)

    nota: Mapped[NotaFiscal] = relationship(back_populates="duplicatas")


# --------------------------------------------------------------------------- bancos
class ContaBancaria(Base, Timestamps):
    __tablename__ = "conta_bancaria"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    banco_codigo: Mapped[str | None] = mapped_column(String(5))
    banco_nome: Mapped[str] = mapped_column(String(120))
    agencia: Mapped[str | None] = mapped_column(String(10))
    numero_conta: Mapped[str | None] = mapped_column(String(20))
    tipo: Mapped[str] = mapped_column(String(20), default="corrente")  # corrente | aplicacao
    descricao: Mapped[str | None] = mapped_column(String(150))
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)


class ImportacaoExtrato(Base):
    __tablename__ = "importacao_extrato"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    conta_bancaria_id: Mapped[int] = mapped_column(ForeignKey("conta_bancaria.id"))
    arquivo_nome: Mapped[str] = mapped_column(String(200))
    formato: Mapped[str] = mapped_column(String(10))  # ofx|csv|open_finance
    quantidade: Mapped[int] = mapped_column(Integer, default=0)
    duplicados: Mapped[int] = mapped_column(Integer, default=0)
    importado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    importado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class LancamentoBancario(Base):
    __tablename__ = "lancamento_bancario"
    __table_args__ = (UniqueConstraint("conta_bancaria_id", "hash_dedup"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    conta_bancaria_id: Mapped[int] = mapped_column(ForeignKey("conta_bancaria.id"), index=True)
    importacao_id: Mapped[int | None] = mapped_column(ForeignKey("importacao_extrato.id"))
    data: Mapped[date] = mapped_column(Date, index=True)
    historico: Mapped[str] = mapped_column(String(300))
    historico_normalizado: Mapped[str] = mapped_column(String(300), index=True)
    documento: Mapped[str | None] = mapped_column(String(60))
    valor: Mapped[Decimal] = mapped_column(Dinheiro)  # sempre positivo
    natureza: Mapped[str] = mapped_column(String(1))  # C crédito | D débito
    hash_dedup: Mapped[str] = mapped_column(String(64))
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("plano_conta.id"))
    status_classificacao: Mapped[str] = mapped_column(String(20), default="pendente")
    # pendente | manual | ia_sugerida | ia_confirmada
    confianca_ia: Mapped[float | None] = mapped_column()
    classificado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))

    conta: Mapped[PlanoConta | None] = relationship()


class PosicaoAplicacao(Base, Timestamps):
    """Extrato mensal de uma aplicação financeira (uma linha por produto/competência)."""

    __tablename__ = "posicao_aplicacao"
    __table_args__ = (UniqueConstraint("conta_bancaria_id", "produto", "competencia"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    conta_bancaria_id: Mapped[int] = mapped_column(ForeignKey("conta_bancaria.id"), index=True)
    produto: Mapped[str] = mapped_column(String(150))
    tipo_produto: Mapped[str] = mapped_column(String(20))  # cdb|fundo|lci|lca|tesouro|poupanca|outro
    competencia: Mapped[date] = mapped_column(Date, index=True)  # 1º dia do mês
    saldo_inicial: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    aplicacoes: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    resgates: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    saldo_final_bruto: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    irrf: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    iof: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    taxa_administracao: Mapped[Decimal] = mapped_column(Dinheiro, default=0)
    cdi_mes_percentual: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))


# --------------------------------------------------------------------------- open finance
class ConsentimentoOpenFinance(Base, Timestamps):
    __tablename__ = "consentimento_open_finance"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int] = mapped_column(ForeignKey("escritorio.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    provedor: Mapped[str] = mapped_column(String(40))
    id_externo: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="aguardando_autorizacao")
    permissoes: Mapped[list | None] = mapped_column(JSON)
    expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------- auditoria
class Auditoria(Base):
    """Trilha de auditoria append-only: quem, quando e o que foi alterado."""

    __tablename__ = "auditoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[int | None] = mapped_column(Integer, index=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer, index=True)
    usuario_email: Mapped[str | None] = mapped_column(String(200))
    acao: Mapped[str] = mapped_column(String(30), index=True)  # INSERT|UPDATE|DELETE|LOGIN|...
    tabela: Mapped[str | None] = mapped_column(String(60), index=True)
    registro_id: Mapped[str | None] = mapped_column(String(60))
    dados_antes: Mapped[dict | None] = mapped_column(JSON)
    dados_depois: Mapped[dict | None] = mapped_column(JSON)
    campos_alterados: Mapped[list | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    request_id: Mapped[str | None] = mapped_column(String(36))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)
