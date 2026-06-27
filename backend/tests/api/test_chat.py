from __future__ import annotations

from pathlib import Path

from app.agents.workflow import AgentEvent, AgentWorkflow, WorkflowResult
from app.domain.models import Evidence
from app.main import create_app
from app.storage.repository import Repository
from fastapi.testclient import TestClient


class FakeSearch:
    def search(self, query: str, *, top_k: int = 8) -> list[Evidence]:
        return [
            Evidence(
                article_id="labor-47",
                law_name="中华人民共和国劳动合同法",
                article_number="第四十七条",
                content="经济补偿按工作年限计算。",
                score=0.9,
            )
        ]


def _client(tmp_path: Path) -> TestClient:
    repository = Repository(tmp_path / "lawagent.db")
    app = create_app(AgentWorkflow(FakeSearch()), repository, admin_api_key="admin-test")
    return TestClient(app)


def test_chat_creates_run_and_replayable_sse_events(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post("/api/v1/chat", json={"message": "劳动合同法第四十七条是什么？"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["result"]["status"] == "completed"
    events = client.get(payload["events_url"])
    assert events.status_code == 200
    assert events.headers["content-type"].startswith("text/event-stream")
    assert "event: run.started" in events.text
    assert "event: run.completed" in events.text


def test_chat_stream_emits_live_agent_events_answer_deltas_and_persists_session(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "劳动合同法第四十七条是什么？"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: session.started" in response.text
    assert "event: agent.event" in response.text
    assert "event: answer.delta" in response.text
    assert "event: chat.completed" in response.text
    assert "经济补偿按工作年限计算" in response.text
    sessions = client.get("/api/v1/sessions").json()
    assert sessions[0]["message_count"] == 2


def test_source_lookup_and_session_delete(tmp_path: Path) -> None:
    client = _client(tmp_path)
    payload = client.post("/api/v1/chat", json={"message": "劳动合同法第四十七条是什么？"}).json()

    source = client.get("/api/v1/sources/labor-47")
    deleted = client.delete(f"/api/v1/sessions/{payload['session_id']}")

    assert source.status_code == 200
    assert source.json()["law_name"] == "中华人民共和国劳动合同法"
    assert deleted.status_code == 204


def test_health_readiness_and_admin_auth_are_separate(tmp_path: Path) -> None:
    client = _client(tmp_path)

    assert client.get("/api/v1/health").json() == {"status": "alive"}
    assert client.get("/api/v1/ready").json() == {"status": "ready"}
    assert client.get("/api/v1/admin/corpus/report").status_code == 401
    assert (
        client.get("/api/v1/admin/corpus/report", headers={"x-admin-key": "admin-test"}).status_code
        == 200
    )


def test_admin_overview_reports_corpus_index_recent_runs_and_eval(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/api/v1/chat", json={"message": "劳动合同法第四十七条是什么？"})

    response = client.get("/api/v1/admin/overview", headers={"x-admin-key": "admin-test"})

    assert response.status_code == 200
    payload = response.json()
    assert {"corpus", "index", "recent_runs", "evaluation"} <= set(payload)
    assert payload["recent_runs"][0]["query"] == "劳动合同法第四十七条是什么？"
    assert payload["evaluation"]["open_ended_case_count"] >= 10


def test_chat_rejects_sensitive_identity_numbers(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/api/v1/chat",
        json={"message": "我的身份证号是 110105199001011234，公司辞退我怎么办？"},
    )

    assert response.status_code == 422
    assert "敏感身份信息" in response.text


def test_chat_rate_limit_returns_429(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "lawagent.db")
    app = create_app(
        AgentWorkflow(FakeSearch()),
        repository,
        admin_api_key="admin-test",
        chat_rate_limit_per_minute=1,
    )
    client = TestClient(app)

    assert client.post("/api/v1/chat", json={"message": "劳动合同法第四十七条是什么？"}).status_code == 201
    limited = client.post("/api/v1/chat", json={"message": "劳动合同解除有什么规定？"})

    assert limited.status_code == 429


def test_sessions_can_be_listed_with_recent_runs(tmp_path: Path) -> None:
    client = _client(tmp_path)
    first = client.post("/api/v1/chat", json={"message": "劳动合同法第四十七条是什么？"}).json()
    second = client.post("/api/v1/chat", json={"message": "劳动合同解除赔偿怎么算？"}).json()

    sessions = client.get("/api/v1/sessions").json()
    runs = client.get(f"/api/v1/sessions/{second['session_id']}/runs").json()
    latest_run = client.get(f"/api/v1/sessions/{second['session_id']}/latest-run")

    assert [session["id"] for session in sessions] == [second["session_id"], first["session_id"]]
    assert sessions[0]["title"] == "劳动合同解除赔偿怎么算？"
    assert sessions[0]["message_count"] == 2
    assert runs[0]["id"] == second["run_id"]
    assert runs[0]["query"] == "劳动合同解除赔偿怎么算？"
    assert runs[0]["status"] == "completed"
    assert latest_run.status_code == 200
    assert latest_run.json()["run_id"] == second["run_id"]
    assert latest_run.json()["result"]["evidence"][0]["article_id"] == "labor-47"


def test_chat_passes_existing_session_context_to_workflow(tmp_path: Path) -> None:
    class ContextAwareWorkflow:
        def __init__(self) -> None:
            self.context_lengths: list[int] = []

        def run(self, query: str, *, context: list[dict[str, str]] | None = None) -> WorkflowResult:
            self.context_lengths.append(len(context or []))
            return WorkflowResult(
                status="completed",
                route="simple",
                risk_level="low",
                answer=f"回答：{query}",
                agents_executed=["supervisor", "legal_research"],
                events=[
                    AgentEvent(sequence=1, type="run.started", summary="开始"),
                    AgentEvent(sequence=2, type="run.completed", summary="完成"),
                ],
            )

    workflow = ContextAwareWorkflow()
    repository = Repository(tmp_path / "lawagent.db")
    app = create_app(workflow, repository, admin_api_key="admin-test")  # type: ignore[arg-type]
    client = TestClient(app)

    first = client.post("/api/v1/chat", json={"message": "民法典保证责任有哪些规定？"}).json()
    second = client.post(
        "/api/v1/chat",
        json={"message": "那保证期间呢？", "session_id": first["session_id"]},
    )

    assert second.status_code == 201
    assert workflow.context_lengths == [0, 2]
