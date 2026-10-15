"""Validação e consulta de CNPJ.

Validação: suporta o CNPJ numérico e o CNPJ alfanumérico (IN RFB nº 2.229/2024, em vigor
a partir de julho/2026): as 12 primeiras posições aceitam [0-9A-Z]; cada caractere vale
(código ASCII − 48) no cálculo do módulo 11; os 2 dígitos verificadores seguem numéricos.

Consulta: o site da Receita Federal (Comprovante de Inscrição) é protegido por captcha e
não pode ser automatizado. Usamos provedores que expõem os dados públicos do CNPJ da RFB:
  * brasilapi  — BrasilAPI (base de dados abertos da RFB), gratuito
  * receitaws  — ReceitaWS, gratuito com limite de requisições
  * serpro     — API oficial "Consulta CNPJ" do SERPRO (contratada, exige token)
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

import httpx

from ..config import get_settings

_PESOS_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_2 = [6] + _PESOS_1


def normalizar(cnpj: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", (cnpj or "").upper())


def _dv(base: str, pesos: list[int]) -> int:
    soma = sum((ord(c) - 48) * p for c, p in zip(base, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def validar(cnpj: str) -> bool:
    c = normalizar(cnpj)
    if not re.fullmatch(r"[0-9A-Z]{12}\d{2}", c):
        return False
    if len(set(c)) == 1:
        return False
    d1 = _dv(c[:12], _PESOS_1)
    d2 = _dv(c[:12] + str(d1), _PESOS_2)
    return c[12:] == f"{d1}{d2}"


def formatar(cnpj: str) -> str:
    c = normalizar(cnpj)
    if len(c) != 14:
        return cnpj
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


@dataclass
class DadosCNPJ:
    cnpj: str
    razao_social: str
    nome_fantasia: str | None = None
    situacao_cadastral: str | None = None
    cnae_principal: str | None = None
    email: str | None = None
    telefone: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    municipio: str | None = None
    uf: str | None = None
    cep: str | None = None
    fonte: str = ""
    bruto: dict | None = None

    def para_dict(self) -> dict:
        return asdict(self)


class ErroConsultaCNPJ(Exception):
    def __init__(self, mensagem: str, status: int = 502):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


def _limpo(v) -> str | None:
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def _so_digitos(v) -> str | None:
    v = re.sub(r"\D", "", str(v or ""))
    return v or None


def _de_brasilapi(d: dict) -> DadosCNPJ:
    cnae = None
    if d.get("cnae_fiscal"):
        cnae = f"{d.get('cnae_fiscal')} - {d.get('cnae_fiscal_descricao') or ''}".strip(" -")
    return DadosCNPJ(
        cnpj=normalizar(d.get("cnpj", "")),
        razao_social=_limpo(d.get("razao_social")) or "",
        nome_fantasia=_limpo(d.get("nome_fantasia")),
        situacao_cadastral=_limpo(d.get("descricao_situacao_cadastral")),
        cnae_principal=cnae,
        email=_limpo(d.get("email")),
        telefone=_limpo(d.get("ddd_telefone_1")),
        logradouro=" ".join(filter(None, [_limpo(d.get("descricao_tipo_de_logradouro")), _limpo(d.get("logradouro"))]))
        or None,
        numero=_limpo(d.get("numero")),
        complemento=_limpo(d.get("complemento")),
        bairro=_limpo(d.get("bairro")),
        municipio=_limpo(d.get("municipio")),
        uf=_limpo(d.get("uf")),
        cep=_so_digitos(d.get("cep")),
        fonte="brasilapi",
        bruto=d,
    )


def _de_receitaws(d: dict) -> DadosCNPJ:
    if d.get("status") == "ERROR":
        raise ErroConsultaCNPJ(d.get("message") or "CNPJ não encontrado", 404)
    ativ = (d.get("atividade_principal") or [{}])[0]
    cnae = f"{ativ.get('code', '')} - {ativ.get('text', '')}".strip(" -") or None
    return DadosCNPJ(
        cnpj=normalizar(d.get("cnpj", "")),
        razao_social=_limpo(d.get("nome")) or "",
        nome_fantasia=_limpo(d.get("fantasia")),
        situacao_cadastral=_limpo(d.get("situacao")),
        cnae_principal=cnae,
        email=_limpo(d.get("email")),
        telefone=_limpo(d.get("telefone")),
        logradouro=_limpo(d.get("logradouro")),
        numero=_limpo(d.get("numero")),
        complemento=_limpo(d.get("complemento")),
        bairro=_limpo(d.get("bairro")),
        municipio=_limpo(d.get("municipio")),
        uf=_limpo(d.get("uf")),
        cep=_so_digitos(d.get("cep")),
        fonte="receitaws",
        bruto=d,
    )


def _de_serpro(d: dict) -> DadosCNPJ:
    end = d.get("endereco") or {}
    cnae = (d.get("cnaePrincipal") or {})
    return DadosCNPJ(
        cnpj=normalizar(d.get("ni", "")),
        razao_social=_limpo(d.get("nomeEmpresarial")) or "",
        nome_fantasia=_limpo(d.get("nomeFantasia")),
        situacao_cadastral=_limpo((d.get("situacaoCadastral") or {}).get("codigo")),
        cnae_principal=f"{cnae.get('codigo', '')} - {cnae.get('descricao', '')}".strip(" -") or None,
        email=_limpo(d.get("correioEletronico")),
        logradouro=_limpo(end.get("logradouro")),
        numero=_limpo(end.get("numero")),
        complemento=_limpo(end.get("complemento")),
        bairro=_limpo(end.get("bairro")),
        municipio=_limpo((end.get("municipio") or {}).get("descricao")),
        uf=_limpo(end.get("uf")),
        cep=_so_digitos(end.get("cep")),
        fonte="serpro",
        bruto=d,
    )


# Permite injetar um transporte HTTP nos testes
transporte_http: httpx.BaseTransport | None = None


def consultar(cnpj: str) -> DadosCNPJ:
    s = get_settings()
    c = normalizar(cnpj)
    if not validar(c):
        raise ErroConsultaCNPJ("CNPJ inválido", 422)
    provedor = s.cnpj_provedor
    if provedor == "desligado":
        raise ErroConsultaCNPJ("Consulta de CNPJ desabilitada; preencha os dados manualmente", 503)
    urls = {
        "brasilapi": (f"https://brasilapi.com.br/api/cnpj/v1/{c}", _de_brasilapi, {}),
        "receitaws": (f"https://receitaws.com.br/v1/cnpj/{c}", _de_receitaws, {}),
        "serpro": (
            f"https://gateway.apiserpro.serpro.gov.br/consulta-cnpj-df/v2/empresa/{c}",
            _de_serpro,
            {"Authorization": f"Bearer {s.serpro_token}"},
        ),
    }
    if provedor not in urls:
        raise ErroConsultaCNPJ(f"Provedor de CNPJ desconhecido: {provedor}", 500)
    url, conversor, headers = urls[provedor]
    try:
        with httpx.Client(timeout=s.cnpj_timeout_segundos, transport=transporte_http) as cli:
            r = cli.get(url, headers={"Accept": "application/json", **headers})
    except httpx.HTTPError:
        raise ErroConsultaCNPJ("Serviço de consulta de CNPJ indisponível; tente novamente ou preencha manualmente")
    if r.status_code == 404:
        raise ErroConsultaCNPJ("CNPJ não encontrado na base da Receita Federal", 404)
    if r.status_code == 429:
        raise ErroConsultaCNPJ("Limite de consultas atingido; aguarde um minuto", 429)
    if r.status_code >= 400:
        raise ErroConsultaCNPJ("Falha na consulta de CNPJ")
    dados = conversor(r.json())
    if not dados.cnpj:
        dados.cnpj = c
    return dados
