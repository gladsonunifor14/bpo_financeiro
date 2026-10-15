"""Configuração central lida de variáveis de ambiente (prefixo BPO_)."""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BPO_", env_file=".env", extra="ignore")

    ambiente: str = "desenvolvimento"  # desenvolvimento | producao | teste
    database_url: str = "sqlite:///./bpo_financeiro.db"

    # JWT: em produção, defina BPO_JWT_SECRET com >= 32 bytes aleatórios.
    jwt_secret: str = "troque-este-segredo-em-producao-com-32-bytes-ou-mais"
    jwt_algoritmo: str = "HS256"
    access_token_minutos: int = 15
    refresh_token_dias: int = 7

    otp_minutos_validade: int = 10
    otp_max_tentativas: int = 5
    login_max_falhas: int = 5
    login_bloqueio_minutos: int = 15

    # Rate limit simples (por IP) nas rotas de autenticação
    rate_limit_auth_por_minuto: int = 20

    # E-mail (SMTP). Sem host configurado, as mensagens vão para o log.
    smtp_host: str | None = None
    smtp_porta: int = 587
    smtp_usuario: str | None = None
    smtp_senha: str | None = None
    smtp_remetente: str = "nao-responda@bpo.local"
    smtp_tls: bool = True

    # Consulta de CNPJ: brasilapi | receitaws | serpro | desligado
    cnpj_provedor: str = "brasilapi"
    cnpj_timeout_segundos: float = 8.0
    serpro_token: str | None = None

    # Uploads
    upload_max_bytes: int = 5 * 1024 * 1024
    zip_max_arquivos: int = 500
    zip_max_bytes_descompactados: int = 50 * 1024 * 1024

    # Classificação por IA: confiança mínima para aplicar a sugestão automaticamente
    ia_confianca_minima: float = 0.75

    cors_origens: list[str] = []
    cookie_seguro: bool = True  # Secure em cookies (desligue apenas em dev http)
    servir_frontend: bool = True

    # Open Finance (via agregador/ITP autorizado pelo BACEN)
    open_finance_provedor: str | None = None
    open_finance_client_id: str | None = None
    open_finance_client_secret: str | None = None

    @field_validator("database_url")
    @classmethod
    def _driver_postgres(cls, v: str) -> str:
        # Render/Heroku entregam "postgres://..."; o SQLAlchemy precisa do driver psycopg 3
        for prefixo in ("postgres://", "postgresql://"):
            if v.startswith(prefixo):
                return "postgresql+psycopg://" + v[len(prefixo):]
        return v

    @property
    def producao(self) -> bool:
        return self.ambiente == "producao"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.producao and (len(s.jwt_secret) < 32 or s.jwt_secret.startswith("troque")):
        raise RuntimeError("BPO_JWT_SECRET inseguro para produção")
    return s
