from __future__ import annotations

from pathlib import Path

from app.agents.workflow import AgentEvent, WorkflowResult
from app.storage.repository import Repository


def _result() -> WorkflowResult:
    return WorkflowResult(
        status="completed",
        route="simple",
        risk_level="low",
        answer="测试回答",
        agents_executed=["supervisor", "legal_research"],
        events=[
            AgentEvent(sequence=1, type="run.started", summary="开始"),
            AgentEvent(sequence=2, type="run.completed", summary="完成"),
        ],
    )


def test_repository_persists_ordered_run_events_and_session(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "lawagent.db")
    session_id = repository.create_session()

    run_id = repository.save_run(session_id, "测试问题", _result())

    events = repository.get_events(run_id)
    assert [event.sequence for event in events] == [1, 2]
    assert repository.get_session(session_id)[0]["content"] == "测试问题"


def test_repository_deletes_session_and_related_runs(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "lawagent.db")
    session_id = repository.create_session()
    run_id = repository.save_run(session_id, "测试问题", _result())

    assert repository.delete_session(session_id) is True
    assert repository.get_session(session_id) == []
    assert repository.get_events(run_id) == []
