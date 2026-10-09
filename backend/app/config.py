"""Runtime configuration, read from environment variables.

Reading happens when `Settings.from_env()` is called (not at import time) so a
missing key can never crash the process on startup.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 30.0
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)

    @classmethod
    def from_env(cls) -> "Settings":
        origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
        try:
            timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        except ValueError:
            timeout = 30.0
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "mock").strip().lower() or "mock",
            openai_api_key=(os.getenv("OPENAI_API_KEY") or "").strip() or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            llm_timeout_seconds=timeout,
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        )
