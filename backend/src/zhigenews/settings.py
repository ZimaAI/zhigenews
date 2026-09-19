from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), extra="ignore")
    database_url: str = "mysql+pymysql://zhigenews:local-development@127.0.0.1:13316/zhigenews"
    redis_url: str = "redis://127.0.0.1:56386/0"
    data_dir: Path = Path("data")
    cookie_secure: bool = False
    allowed_origins: list[str] = ["http://127.0.0.1:5173", "http://127.0.0.1:5174"]
    trusted_proxy_cidrs: list[str] = []
    secret_encryption_key: str = ""
    ip_hash_key: str = ""
    admin_email: str = "admin@localhost.test"
    admin_password: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = ""
    openai_api_key: str = ""
    openai_context_window: int = Field(default=32768, ge=1024)
    openai_thinking_enabled: bool = False
    summary_openai_base_url: str = ""
    summary_openai_model: str = ""
    summary_openai_api_key: str = ""
    summary_openai_context_window: int | None = Field(default=None, ge=1024)
    summary_openai_thinking_enabled: bool | None = None
    evaluation_openai_base_url: str = ""
    evaluation_openai_model: str = ""
    evaluation_openai_api_key: str = ""
    evaluation_openai_context_window: int | None = Field(default=None, ge=1024)
    evaluation_openai_thinking_enabled: bool | None = None
    tavily_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr = SecretStr("")
    langsmith_project: str = "my-first-agent"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_workspace_id: str = ""
    newsnow_base_url: str = "https://newsnow.busiyi.world"
    sandbox_image: str = "python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea"
    anonymous_session_days: int = 30
    admin_session_hours: int = 8


@lru_cache
def get_settings() -> Settings:
    return Settings()
