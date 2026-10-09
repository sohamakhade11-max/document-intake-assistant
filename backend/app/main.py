"""Application wiring. `create_app` accepts overrides so tests can inject doubles."""
from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import build_router, register_error_handlers
from .config import Settings
from .llm.base import LLMProvider
from .llm.factory import create_provider
from .service import ConversationService
from .store import ConversationStore, InMemoryConversationStore


def create_app(
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
    store: ConversationStore | None = None,
) -> FastAPI:
    if settings is None:
        load_dotenv()  # reads .env if present; real env vars win
        settings = Settings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # request logs may contain URLs/ids only, keep quiet
    provider = provider or create_provider(settings)
    service = ConversationService(store or InMemoryConversationStore(), provider)

    app = FastAPI(title="Document Intake Assistant", version="1.0.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"]
    )
    register_error_handlers(app)
    app.include_router(build_router(service, provider))
    return app


app = create_app()
