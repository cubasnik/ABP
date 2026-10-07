"""Конфигурация сервера: все параметры читаются из переменных окружения и файла .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Параметры приложения. Имена совпадают с ключами в .env (регистр не важен)."""

    model_config = SettingsConfigDict(env_file=(ROOT / ".env", Path(".env")), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Обозреватель технической документации"
    app_env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    log_file: str = "logs/app.log"

    database_url: str = "sqlite:///./data/abp.db"
    secret_key: str = Field(default="change-me-in-production", description="Ключ подписи JWT")
    access_token_minutes: int = 30          # сеанс завершается через 30 минут без активности
    max_login_failures: int = 5
    lockout_minutes: int = 15
    allow_registration: bool = True

    # Поиск: opensearch | memory | auto (opensearch, если доступен, иначе память)
    search_backend: str = "auto"
    opensearch_url: str = "http://localhost:9200"
    opensearch_user: str = ""
    opensearch_password: str = ""
    opensearch_index: str = "abp-docs"
    opensearch_retries: int = 3
    opensearch_verify_certs: bool = False

    docs_dir: str = "../sample-docs"

    # СМС: console (код в лог) | http (POST на шлюз)
    sms_provider: str = "console"
    sms_gateway_url: str = ""
    sms_gateway_token: str = ""
    sms_code_minutes: int = 5

    # Искусственный интеллект: mock | openai | anthropic
    ai_provider: str = "mock"
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_top_k: int = 6
    ai_strict_citations: bool = True
    ai_timeout_seconds: int = 60

    cors_origins: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
