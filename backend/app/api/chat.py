from __future__ import annotations

import asyncio
import json
import re
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.agents.workflow import AgentWorkflow
from app.storage.repository import Repository


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=6000)
    session_id: str | None = None

    @field_validator("message")
    @classmethod
    def reject_sensitive_identity_numbers(cls, value: str) -> str:
        if re.search(r"\b\d{17}[\dXx]\b", value):
            raise ValueError("请删除身份证号等敏感身份信息后再提交。")
        return value


class RateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self.limit_per_minute = limit_per_minute
        self._requests: dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - 60
        requests = self._requests[key]
        while requests and requests[0] < window_start:
            requests.popleft()
        if len(requests) >= self.limit_per_minute:
            return False
        requests.append(now)
        return True


def create_chat_router(
    workflow: AgentWorkflow,
    repository: Repository,
    *,
    rate_limit_per_minute: int = 30,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    limiter = RateLimiter(rate_limit_per_minute)

    def enforce_rate_limit(http_request: Request) -> None:
        client_host = http_request.client.host if http_request.client else "local"
        if not limiter.check(client_host):
            raise HTTPException(status_code=429, detail="rate limit exceeded")

    @router.post("/chat", status_code=status.HTTP_201_CREATED)
    def chat(request: ChatRequest, http_request: Request) -> dict[str, object]:
        enforce_rate_limit(http_request)
        session_id = request.session_id or repository.create_session()
        context = repository.get_context(session_id) if request.session_id else []
        result = workflow.run(request.message, context=context)
        run_id = repository.save_run(session_id, request.message, result)
        return {
            "run_id": run_id,
            "session_id": session_id,
            "events_url": f"/api/v1/chat/{run_id}/events",
            "result": result.model_dump(mode="json"),
        }

    @router.post("/chat/stream")
    async def chat_stream(request: ChatRequest, http_request: Request) -> StreamingResponse:
        enforce_rate_limit(http_request)
        session_id = request.session_id or repository.create_session()
        context = repository.get_context(session_id) if request.session_id else []

        async def stream():
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

            def forward_event(event: object) -> None:
                loop.call_soon_threadsafe(queue.put_nowait, ("agent.event", event))

            def execute_workflow() -> None:
                try:
                    result = workflow.run(
                        request.message,
                        context=context,
                        on_event=forward_event,
                    )
                    run_id = repository.save_run(session_id, request.message, result)
                    payload = {
                        "run_id": run_id,
                        "session_id": session_id,
                        "events_url": f"/api/v1/chat/{run_id}/events",
                        "result": result.model_dump(mode="json"),
                    }
                    loop.call_soon_threadsafe(queue.put_nowait, ("result.ready", payload))
                except Exception as error:
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        ("chat.error", {"message": type(error).__name__}),
                    )

            yield _sse("session.started", {"session_id": session_id})
            task = asyncio.create_task(asyncio.to_thread(execute_workflow))
            completed = False
            while not completed:
                event_type, data = await queue.get()
                if event_type == "agent.event":
                    yield _sse(event_type, data)
                    continue
                if event_type == "chat.error":
                    yield _sse(event_type, data)
                    completed = True
                    continue

                payload = data
                if not isinstance(payload, dict):
                    yield _sse("chat.error", {"message": "invalid result"})
                    completed = True
                    continue
                result_data = payload.get("result", {})
                answer = ""
                if isinstance(result_data, dict):
                    answer = str(result_data.get("clarification") or result_data.get("answer") or "")
                yield _sse("answer.started", {"length": len(answer)})
                for start in range(0, len(answer), 18):
                    yield _sse("answer.delta", {"delta": answer[start : start + 18]})
                    # Keep chunks far enough apart to survive TCP/proxy coalescing and
                    # produce an observable progressive render in the browser.
                    await asyncio.sleep(0.045)
                yield _sse("chat.completed", payload)
                completed = True
            await task

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/chat/{run_id}/events")
    def events(run_id: str) -> StreamingResponse:
        stored = repository.get_events(run_id)

        def stream():
            for event in stored:
                event_data = event.model_dump_json()
                yield f"id: {event.sequence}\nevent: {event.type}\ndata: {event_data}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @router.get("/sessions/{session_id}")
    def session(session_id: str) -> list[dict[str, object]]:
        return repository.get_session(session_id)

    @router.get("/sessions")
    def sessions() -> list[dict[str, object]]:
        return repository.list_sessions()

    @router.get("/sessions/{session_id}/runs")
    def session_runs(session_id: str) -> list[dict[str, object]]:
        return repository.get_session_runs(session_id)

    @router.get("/sessions/{session_id}/latest-run")
    def latest_session_run(session_id: str) -> dict[str, object] | None:
        return repository.get_latest_run(session_id)

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


def _sse(event_type: str, data: object) -> str:
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
