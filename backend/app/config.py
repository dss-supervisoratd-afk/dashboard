from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    secret_key: str = "dev-inseguro-troque-em-producao"
    session_hours: int = 10
    cookie_secure: bool = False
    # URL pública do frontend: destino dos redirecionamentos do OAuth
    frontend_url: str = "http://localhost:5173"

    # primeiro administrador, criado na inicialização se não houver usuários
    admin_email: str | None = None
    admin_password: str | None = None

    google_client_id: str | None = None
    google_client_secret: str | None = None
    # domínios cujas contas Google entram automaticamente (ex.: "amn.org.br,gmail.com");
    # vazio = só entra quem já foi cadastrado por um administrador
    google_allowed_domains: str = ""
    google_default_role: str = "leitor"

    upload_dir: str = "./uploads"
    max_upload_mb: int = 25

    @cached_property
    def allowed_domains(self) -> set[str]:
        return {d.strip().lower() for d in self.google_allowed_domains.split(",") if d.strip()}

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


settings = Settings()
