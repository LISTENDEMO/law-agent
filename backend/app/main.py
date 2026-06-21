from __future__ import annotations

from fastapi import FastAPI

from app.agents.workflow import AgentWorkflow
from app.api.admin import create_admin_router
from app.api.chat import create_chat_router
from app.config import Settings
from app.domain.models import Evidence
from app.storage.repository import Repository


class EmptySearch:
    def search(self, query: str, *, top_k: int = 8) -> list[Evidence]:
        return []


def create_app(
    workflow: AgentWorkflow,
    repository: Repository,
    *,
    admin_api_key: str,
) -> FastAPI:
    application = FastAPI(title="LawAgent API", version="0.1.0")
    application.include_router(create_chat_router(workflow, repository))
    application.include_router(create_admin_router(admin_api_key))

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
    return create_app(
        AgentWorkflow(EmptySearch()),
        repository,
        admin_api_key=settings.admin_api_key.get_secret_value(),
    )


app = create_default_app()
