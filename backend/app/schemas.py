"""Schemas de entrada/saída da API (documentados automaticamente no Swagger/OpenAPI)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .services import cnpj as cnpj_svc


class Modelo(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _validar_cnpj(v: str) -> str:
    c = cnpj_svc.normalizar(v)
    if not cnpj_svc.validar(c):
        raise ValueError("CNPJ inválido")
    return c


class Mensagem(BaseModel):
    mensagem: str


# ------------------------------------------------------------------ auth
class CadastroEscritorioEntrada(BaseModel):
    """Cria o escritório (dados importados da Receita pelo CNPJ) e o usuário administrador."""

    cnpj: str = Field(examples=["11.222.333/0001-81"])
    nome: str = Field(min_length=2, max_length=150)
    email: EmailStr
    senha: str = Field(min_length=10, max_length=128)
    crc: str | None = Field(default=None, max_length=30)
    razao_social: str | None = Field(
        default=None, max_length=200, description="Usado apenas se a consulta à Receita estiver indisponível"
    )
    aceite_termos: bool = Field(description="Aceite dos Termos de Uso e Política de Privacidade")

    _v_cnpj = field_validator("cnpj")(_validar_cnpj)


class LoginEntrada(BaseModel):
    email: EmailStr
    senha: str = Field(max_length=128)


class DesafioSaida(BaseModel):
    desafio_id: str
    mensagem: str
    expira_em_segundos: int


class VerificarOTPEntrada(BaseModel):
    desafio_id: str = Field(max_length=36)
    codigo: str = Field(pattern=r"^\d{6}$")


class TokenSaida(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em_segundos: int
    usuario: "UsuarioSaida"


class RecuperarSenhaEntrada(BaseModel):
    email: EmailStr


class RedefinirSenhaEntrada(BaseModel):
    desafio_id: str = Field(max_length=36)
    codigo: str = Field(pattern=r"^\d{6}$")
    nova_senha: str = Field(min_length=10, max_length=128)


class AlterarSenhaEntrada(BaseModel):
    senha_atual: str = Field(max_length=128)
    nova_senha: str = Field(min_length=10, max_length=128)


# ------------------------------------------------------------------ usuários
Papel = Literal["admin", "analista", "cliente"]


class UsuarioSaida(Modelo):
    id: int
    nome: str
    email: str
    papel: str
    escritorio_id: int
    cliente_id: int | None
    ativo: bool
    ultimo_login_em: datetime | None = None


class UsuarioEntrada(BaseModel):
    nome: str = Field(min_length=2, max_length=150)
    email: EmailStr
    papel: Papel
    cliente_id: int | None = None
    senha_inicial: str = Field(min_length=10, max_length=128)


class UsuarioAtualizacao(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=150)
    papel: Papel | None = None
    ativo: bool | None = None


class ChaveApiEntrada(BaseModel):
    nome: str = Field(min_length=2, max_length=100)


class ChaveApiSaida(Modelo):
    id: int
    nome: str
    prefixo: str
    criado_em: datetime
    revogada_em: datetime | None
    ultimo_uso_em: datetime | None


class ChaveApiCriada(ChaveApiSaida):
    chave: str = Field(description="Exibida apenas uma vez. Guarde com segurança.")


# ------------------------------------------------------------------ cadastros
class Endereco(BaseModel):
    logradouro: str | None = Field(default=None, max_length=200)
    numero: str | None = Field(default=None, max_length=20)
    complemento: str | None = Field(default=None, max_length=120)
    bairro: str | None = Field(default=None, max_length=120)
    municipio: str | None = Field(default=None, max_length=120)
    uf: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    cep: str | None = Field(default=None, pattern=r"^\d{8}$")


class ConsultaCNPJSaida(BaseModel):
    cnpj: str
    razao_social: str
    nome_fantasia: str | None
    situacao_cadastral: str | None
    cnae_principal: str | None
    email: str | None
    telefone: str | None
    logradouro: str | None
    numero: str | None
    complemento: str | None
    bairro: str | None
    municipio: str | None
    uf: str | None
    cep: str | None
    fonte: str


class EscritorioSaida(Modelo, Endereco):
    id: int
    cnpj: str
    razao_social: str
    nome_fantasia: str | None
    crc: str | None
    responsavel_tecnico: str | None
    email: str | None
    telefone: str | None
    cnae_principal: str | None
    situacao_cadastral: str | None


class EscritorioAtualizacao(Endereco):
    razao_social: str | None = Field(default=None, max_length=200)
    nome_fantasia: str | None = Field(default=None, max_length=200)
    crc: str | None = Field(default=None, max_length=30)
    responsavel_tecnico: str | None = Field(default=None, max_length=150)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=30)


Regime = Literal["simples", "presumido", "real", "mei"]


class ClienteEntrada(Endereco):
    cnpj: str
    importar_receita: bool = Field(default=True, description="Busca os dados na base da Receita Federal")
    razao_social: str | None = Field(default=None, max_length=200)
    nome_fantasia: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=30)
    regime_tributario: Regime | None = None

    _v_cnpj = field_validator("cnpj")(_validar_cnpj)


class ClienteAtualizacao(Endereco):
    razao_social: str | None = Field(default=None, max_length=200)
    nome_fantasia: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=30)
    regime_tributario: Regime | None = None
    ativo: bool | None = None


class ClienteSaida(Modelo, Endereco):
    id: int
    cnpj: str
    razao_social: str
    nome_fantasia: str | None
    email: str | None
    telefone: str | None
    cnae_principal: str | None
    situacao_cadastral: str | None
    regime_tributario: str | None
    ativo: bool
    criado_em: datetime


# ------------------------------------------------------------------ contratos / LGPD
class ModeloContratoEntrada(BaseModel):
    titulo: str = Field(min_length=3, max_length=200)
    conteudo: str = Field(min_length=50, max_length=100_000)


class ModeloContratoSaida(Modelo):
    id: int
    titulo: str
    versao: int
    conteudo: str
    ativo: bool


class ContratoEntrada(BaseModel):
    cliente_id: int
    modelo_id: int | None = Field(default=None, description="Vazio = modelo ativo mais recente")
    valor_mensal: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    dia_vencimento: int = Field(ge=1, le=28)
    inicio_vigencia: date
    fim_vigencia: date | None = None


class ContratoSaida(Modelo):
    id: int
    numero: str
    cliente_id: int
    modelo_id: int
    valor_mensal: Decimal
    dia_vencimento: int
    inicio_vigencia: date
    fim_vigencia: date | None
    status: str
    hash_sha256: str
    aceito_em: datetime | None
    aceite_ip: str | None
    rescindido_em: datetime | None
    criado_em: datetime


class ContratoDetalhe(ContratoSaida):
    conteudo: str


class AceiteContratoEntrada(BaseModel):
    hash_sha256: str = Field(description="Hash do conteúdo exibido ao usuário (garante que aceitou o texto exato)")
    li_e_concordo: bool


class RescisaoEntrada(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


class TermoEntrada(BaseModel):
    tipo: Literal["termos_uso", "politica_privacidade", "confidencialidade", "tratamento_dados"]
    titulo: str = Field(min_length=3, max_length=200)
    conteudo: str = Field(min_length=20, max_length=100_000)
    obrigatorio: bool = True


class TermoSaida(Modelo):
    id: int
    tipo: str
    versao: int
    titulo: str
    conteudo: str
    hash_sha256: str
    obrigatorio: bool
    ativo: bool
    publicado_em: datetime
    aceito_em: datetime | None = None


class AceiteTermoEntrada(BaseModel):
    hash_sha256: str


class ProcuracaoSaida(Modelo):
    id: int
    cliente_id: int
    tipo: str
    outorgado_nome: str
    outorgado_documento: str
    poderes: str
    data_inicio: date
    data_fim: date | None
    revogada_em: datetime | None
    arquivo_nome: str | None
    arquivo_sha256: str | None
    situacao: str = ""


# ------------------------------------------------------------------ plano de contas
class PlanoContaSaida(Modelo):
    id: int
    codigo: str
    nome: str
    grupo: str
    ativo: bool


class PlanoContaEntrada(BaseModel):
    codigo: str = Field(pattern=r"^[0-9.]{1,20}$")
    nome: str = Field(min_length=2, max_length=150)
    grupo: str


# ------------------------------------------------------------------ notas
class ItemNotaSaida(Modelo):
    id: int
    numero_item: int
    codigo: str | None
    descricao: str
    ncm: str | None
    cfop: str
    quantidade: Decimal
    valor_unitario: Decimal
    valor_total: Decimal
    conta_id: int | None
    classificacao_origem: str


class DuplicataSaida(Modelo):
    numero: str | None
    vencimento: date
    valor: Decimal


class NotaSaida(Modelo):
    id: int
    cliente_id: int
    chave: str
    modelo: str
    serie: str | None
    numero: str
    data_emissao: date
    tipo: str
    tipo_operacao: str
    natureza_operacao: str | None
    emitente_documento: str
    emitente_nome: str
    destinatario_documento: str | None
    destinatario_nome: str | None
    valor_total: Decimal
    valor_icms: Decimal
    valor_ipi: Decimal
    valor_pis: Decimal
    valor_cofins: Decimal
    importado_em: datetime


class NotaDetalhe(NotaSaida):
    valor_produtos: Decimal
    valor_desconto: Decimal
    valor_frete: Decimal
    valor_icms_st: Decimal
    itens: list[ItemNotaSaida]
    duplicatas: list[DuplicataSaida]


class ResultadoImportacaoSaida(BaseModel):
    arquivo: str
    status: str
    mensagem: str
    nota_id: int | None = None
    chave: str | None = None


class ClassificarItemEntrada(BaseModel):
    conta_id: int


# ------------------------------------------------------------------ bancos
class ContaBancariaEntrada(BaseModel):
    cliente_id: int
    banco_codigo: str | None = Field(default=None, pattern=r"^\d{3}$")
    banco_nome: str = Field(min_length=2, max_length=120)
    agencia: str | None = Field(default=None, max_length=10)
    numero_conta: str | None = Field(default=None, max_length=20)
    tipo: Literal["corrente", "aplicacao"] = "corrente"
    descricao: str | None = Field(default=None, max_length=150)


class ContaBancariaSaida(Modelo):
    id: int
    cliente_id: int
    banco_codigo: str | None
    banco_nome: str
    agencia: str | None
    numero_conta: str | None
    tipo: str
    descricao: str | None
    ativa: bool


class ImportacaoSaida(Modelo):
    id: int
    conta_bancaria_id: int
    arquivo_nome: str
    formato: str
    quantidade: int
    duplicados: int
    importado_em: datetime
    classificados_ia: int = 0


class LancamentoSaida(Modelo):
    id: int
    conta_bancaria_id: int
    data: date
    historico: str
    documento: str | None
    valor: Decimal
    natureza: str
    conta_id: int | None
    status_classificacao: str
    confianca_ia: float | None


class ClassificarLancamentoEntrada(BaseModel):
    conta_id: int
    replicar_semelhantes: bool = Field(
        default=True, description="Aplica a mesma conta a lançamentos pendentes com histórico e natureza equivalentes"
    )


class ClassificacaoLoteEntrada(BaseModel):
    lancamento_ids: list[int] = Field(min_length=1, max_length=1000)
    conta_id: int | None = Field(default=None, description="Vazio = confirmar a sugestão da IA")


class SugestaoSaida(BaseModel):
    lancamento_id: int
    conta_id: int
    confianca: float
    metodo: str
    aplicada: bool


class ResultadoClassificacao(BaseModel):
    atualizados: int
    replicados: int = 0


# ------------------------------------------------------------------ aplicações
class PosicaoEntrada(BaseModel):
    conta_bancaria_id: int
    produto: str = Field(min_length=2, max_length=150)
    tipo_produto: Literal["cdb", "fundo", "lci", "lca", "tesouro", "poupanca", "outro"]
    competencia: date = Field(description="Qualquer dia do mês de referência")
    saldo_inicial: Decimal = Field(ge=0, max_digits=16, decimal_places=2)
    aplicacoes: Decimal = Field(default=Decimal(0), ge=0, max_digits=16, decimal_places=2)
    resgates: Decimal = Field(default=Decimal(0), ge=0, max_digits=16, decimal_places=2)
    saldo_final_bruto: Decimal = Field(ge=0, max_digits=16, decimal_places=2)
    irrf: Decimal = Field(default=Decimal(0), ge=0, max_digits=16, decimal_places=2)
    iof: Decimal = Field(default=Decimal(0), ge=0, max_digits=16, decimal_places=2)
    taxa_administracao: Decimal = Field(default=Decimal(0), ge=0, max_digits=16, decimal_places=2)
    cdi_mes_percentual: Decimal | None = Field(default=None, ge=0, le=100, description="CDI do mês em %, ex.: 0.95")


class PosicaoSaida(Modelo):
    id: int
    conta_bancaria_id: int
    produto: str
    tipo_produto: str
    competencia: date
    saldo_inicial: Decimal
    aplicacoes: Decimal
    resgates: Decimal
    saldo_final_bruto: Decimal
    irrf: Decimal
    iof: Decimal
    taxa_administracao: Decimal
    cdi_mes_percentual: Decimal | None
    rendimento_bruto: Decimal | None = None
    rendimento_liquido: Decimal | None = None
    capital_medio: Decimal | None = None
    taxa_bruta_mes: Decimal | None = None
    taxa_liquida_mes: Decimal | None = None
    taxa_bruta_ano: Decimal | None = None
    taxa_liquida_ano: Decimal | None = None
    aliquota_efetiva_ir: Decimal | None = None
    percentual_cdi: Decimal | None = None


class SimulacaoTributosEntrada(BaseModel):
    rendimento: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    dias: int = Field(ge=1, le=36500)


# ------------------------------------------------------------------ auditoria / open finance
class AuditoriaSaida(Modelo):
    id: int
    usuario_id: int | None
    usuario_email: str | None
    acao: str
    tabela: str | None
    registro_id: str | None
    dados_antes: dict | None
    dados_depois: dict | None
    campos_alterados: list | None
    ip: str | None
    request_id: str | None
    criado_em: datetime


class Pagina(BaseModel):
    total: int
    itens: list


class ConsentimentoEntrada(BaseModel):
    cliente_id: int


class ConsentimentoSaida(Modelo):
    id: int
    cliente_id: int
    provedor: str
    status: str
    permissoes: list | None
    url_autorizacao: str | None = None


class SincronizarOpenFinanceEntrada(BaseModel):
    conta_bancaria_id: int
    inicio: date
    fim: date


TokenSaida.model_rebuild()
