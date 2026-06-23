"""Application settings, loaded from environment / .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_name: str = "OrderlyAI API"
    env: str = "local"
    debug: bool = False  # opt in via DEBUG=true in .env for local dev
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str

    # Auth / JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Uploads
    upload_dir: str = "uploads"
    max_product_image_bytes: int = 2_000_000

    # WhatsApp Cloud API
    whatsapp_verify_token: str | None = None
    # Meta App Secret — verifies the X-Hub-Signature-256 header on inbound webhooks.
    whatsapp_app_secret: str | None = None
    # Fernet key (urlsafe base64, 32 bytes) encrypting stored access tokens at rest.
    whatsapp_token_encryption_key: str | None = None

    # AI agent (LangChain v1). Provider is pluggable: "anthropic" (direct) or
    # "openrouter" (OpenAI-compatible gateway, many models behind one key).
    llm_provider: str = "openrouter"  # "anthropic" | "openrouter"

    # Direct Anthropic (used when llm_provider == "anthropic").
    anthropic_api_key: str | None = None

    # OpenRouter (used when llm_provider == "openrouter"). Get a key at openrouter.ai.
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Model ids. For "anthropic" use "anthropic:<model>"; for "openrouter" use the
    # OpenRouter slug (e.g. "anthropic/claude-sonnet-4.6", "openai/gpt-5.5").
    agent_model: str = "anthropic/claude-sonnet-4.6"
    agent_escalation_model: str = "anthropic/claude-opus-4.1"
    agent_summary_model: str = "anthropic/claude-3.5-haiku"

    # LangSmith tracing / evals (optional; off unless tracing is enabled).
    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_api_key: str | None = None
    langsmith_project: str = "orderlyai"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
