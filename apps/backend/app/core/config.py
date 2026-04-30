from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OpsDeck Control Tower API"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"
    default_tenant_slug: str = "demo-steel"
    database_url: str = "postgresql+psycopg://steelops:steelops@localhost:5432/steelops"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    secret_key: str = "change-me"
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = "http://localhost:8000/api/v1/microsoft/callback"
    encryption_key: str = ""
    access_token_expire_minutes: int = 60 * 8
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [
                item.strip().strip('"').strip("'")
                for item in value.strip("[]").split(",")
                if item
            ]
        return value


settings = Settings()
