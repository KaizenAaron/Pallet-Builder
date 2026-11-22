from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    secret_key: str = "change-me"
    encryption_key: str = ""  # Fernet key for per-company connector secrets
    frontend_base_url: str = "http://localhost:5173"
    backend_base_url: str = "http://localhost:8000"
    cookie_secure: bool = False
    access_token_ttl_minutes: int = 60 * 12

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    # When no email could be sent, return verification/reset/invite links in API responses so
    # they can be shown on screen. Local testing only — must be false in production.
    email_link_fallback: bool = False

    verify_email_ttl_hours: int = 48
    password_reset_ttl_minutes: int = 60
    invite_ttl_days: int = 14


@lru_cache
def get_settings() -> Settings:
    return Settings()
