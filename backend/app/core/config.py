from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/happyhour"

    # ── The model that runs the conversational agent ──────────────────────
    # Nothing else in the app needs it. Planning, quantities, costing and the
    # shopping list all run without any of these being set.
    #
    # LLM_PROVIDER is one of the keys in app/services/llm.py PRESETS:
    #   anthropic | groq | gemini | openrouter
    # LLM_BASE_URL is optional and only needed to point at something the
    # presets do not cover, such as a locally hosted server.
    LLM_PROVIDER: str = "anthropic"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_BASE_URL: str = ""

    # Kept so an existing backend/.env written before providers were an option
    # keeps working untouched. resolved_* below prefer the new names.
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = ""

    @property
    def resolved_llm_key(self) -> str:
        return self.LLM_API_KEY or self.ANTHROPIC_API_KEY

    @property
    def resolved_llm_model(self) -> str:
        if self.LLM_MODEL:
            return self.LLM_MODEL
        if self.LLM_PROVIDER == "anthropic" and self.CLAUDE_MODEL:
            return self.CLAUDE_MODEL
        from app.services.llm import PRESETS
        return PRESETS.get(self.LLM_PROVIDER, {}).get("default_model", "")

    # App defaults (stored as config, not buried in prompts)
    DEFAULT_DRINKS_PER_GUEST: float = 2.5
    DEFAULT_WASTE_BUFFER_PCT: float = 0.08
    DEFAULT_NON_ALCOHOLIC_PCT: float = 0.25
    DEFAULT_DURATION_HOURS: float = 2.5
    # VAT. Israeli rate rose from 17% to 18% on 1 Jan 2025.
    # DEFAULT_VAT_RATE applies to every NEW supplier price created in-app.
    # Prices imported from the source Excel files predate the change and are
    # stored at HISTORICAL_VAT_RATE with is_historical=True — never rewritten,
    # so past events stay auditable at the rate actually paid.
    DEFAULT_VAT_RATE: float = 0.18
    HISTORICAL_VAT_RATE: float = 0.17

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # App
    APP_NAME: str = "Happy Hour AI"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False


settings = Settings()
