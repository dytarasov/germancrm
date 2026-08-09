from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/crm/infrastructure/config.py -> backend/migrations
_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_dsn: str = "postgresql://crm:crm@localhost:5432/crm"

    app_password: str = "admin"
    secret_key: str = "dev-secret-change-me"
    session_ttl_days: int = 180
    # Для прода за HTTPS/Cloudflare: cookie не уйдёт по plain-HTTP
    cookie_secure: bool = False

    migrations_dir: Path = _DEFAULT_MIGRATIONS_DIR
    # Каталог с дампами pg_dump (маунт ./backups в docker) — для выгрузки на Google Drive
    backups_dir: Path | None = None

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    mail_worker_enabled: bool = True
    public_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"

    @property
    def gmail_configured(self) -> bool:
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret)
