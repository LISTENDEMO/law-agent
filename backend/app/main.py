from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import FastAPI

from app.agents.model_client import OpenAIEmbeddingClient, OpenAIStructuredClient
from app.agents.workflow import AgentWorkflow
from app.api.admin import create_admin_router
from app.api.chat import create_chat_router
from app.config import Settings
from app.domain.models import Evidence, LegalArticle
from app.rag.index import PersistentIndex
from app.rag.retriever import MatrixHybridRetriever
from app.storage.repository import Repository


class EmptySearch:
    def search(self, query: str, *, top_k: int = 8) -> list[Evidence]:
        return []


class RuntimeSearch:
    """Lazily loads the full corpus only when the first legal query arrives."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._delegate: MatrixHybridRetriever | None = None
        self._lock = threading.Lock()

    def search(self, query: str, *, top_k: int = 8) -> list[Evidence]:
        return self._get_delegate().search(query, top_k=top_k)

    def _get_delegate(self) -> MatrixHybridRetriever:
        if self._delegate is not None:
            return self._delegate
        with self._lock:
            if self._delegate is not None:
                return self._delegate
            index_dir = self._settings.data_dir / "indexes" / "law"
            if (index_dir / "metadata.json").exists():
                articles, _ids, matrix, _metadata = PersistentIndex(index_dir).load_matrix()
                embedding_client = OpenAIEmbeddingClient(
                    self._settings.embedding,
                    max_retries=self._settings.max_retries,
                )
                self._delegate = MatrixHybridRetriever(
                    articles,
                    matrix,
                    lambda query: embedding_client.embed([query])[0],
                )
            else:
                normalized = self._settings.data_dir / "normalized" / "law_articles.jsonl"
                articles = _load_normalized_articles(normalized)
                self._delegate = MatrixHybridRetriever(articles, None, None)
            return self._delegate


def create_app(
    workflow: AgentWorkflow,
    repository: Repository,
    *,
    admin_api_key: str,
    chat_rate_limit_per_minute: int = 30,
    data_dir: Path | None = None,
) -> FastAPI:
    application = FastAPI(title="LawAgent API", version="0.1.0")
    application.include_router(
        create_chat_router(
            workflow,
            repository,
            rate_limit_per_minute=chat_rate_limit_per_minute,
        )
    )
    application.include_router(
        create_admin_router(admin_api_key, repository, data_dir=data_dir or repository.path.parent)
    )

    @application.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "alive"}

    @application.get("/api/v1/ready")
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    return application


def create_default_app() -> FastAPI:
    settings = Settings.load()
    repository = Repository(settings.data_dir / "lawagent.db")
    model = None
    if not settings.offline_mode and settings.chat.api_key.get_secret_value():
        model = OpenAIStructuredClient(
            settings.chat,
            max_retries=settings.max_retries,
            timeout=settings.model_timeout_seconds,
        )
    return create_app(
        AgentWorkflow(RuntimeSearch(settings), model=model),
        repository,
        admin_api_key=settings.admin_api_key.get_secret_value(),
        data_dir=settings.data_dir,
    )


def _load_normalized_articles(path: Path) -> list[LegalArticle]:
    if not path.exists():
        return []
    return [
        LegalArticle.model_validate(json.loads(line))
        for line in path.read_text("utf-8").splitlines()
        if line.strip()
    ]


app = create_default_app()
