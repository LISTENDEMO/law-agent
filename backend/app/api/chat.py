from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.workflow import AgentWorkflow
from app.storage.repository import Repository


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=6000)
    session_id: str | None = None


def create_chat_router(workflow: AgentWorkflow, repository: Repository) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/chat", status_code=status.HTTP_201_CREATED)
    def chat(request: ChatRequest) -> dict[str, object]:
        session_id = request.session_id or repository.create_session()
        result = workflow.run(request.message)
        run_id = repository.save_run(session_id, request.message, result)
        return {
            "run_id": run_id,
            "session_id": session_id,
            "events_url": f"/api/v1/chat/{run_id}/events",
            "result": result.model_dump(mode="json"),
        }

    @router.get("/chat/{run_id}/events")
    def events(run_id: str) -> StreamingResponse:
        stored = repository.get_events(run_id)

        def stream():
            for event in stored:
                event_data = event.model_dump_json()
                yield f"id: {event.sequence}\nevent: {event.type}\ndata: {event_data}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @router.get("/sessions/{session_id}")
    def session(session_id: str) -> list[dict[str, str]]:
        return repository.get_session(session_id)

    @router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_session(session_id: str) -> Response:
        if not repository.delete_session(session_id):
            raise HTTPException(status_code=404, detail="session not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/sources/{article_id}")
    def source(article_id: str) -> dict[str, object]:
        evidence = repository.get_source(article_id)
        if evidence is None:
            raise HTTPException(status_code=404, detail="source not found")
        return json.loads(evidence.model_dump_json())

    return router
