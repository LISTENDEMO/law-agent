from __future__ import annotations

from pathlib import Path

from app.agents.workflow import AgentWorkflow
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
