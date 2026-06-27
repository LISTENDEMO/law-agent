from __future__ import annotations

from pathlib import Path

from app.agents.workflow import AgentEvent, StructuredAnswer, WorkflowResult
from app.storage.repository import Repository


def _result() -> WorkflowResult:
    return WorkflowResult(
        status="completed",
        route="simple",
        risk_level="low",
        answer="测试回答",
        structured_answer=StructuredAnswer(
            summary="测试结论",
            key_points=["测试要点"],
            analysis="测试分析",
            citations=["law-1"],
            notice="测试提示",
        ),
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
    assert repository.get_session(session_id)[1]["structured_answer"] == {
        "summary": "测试结论",
        "key_points": ["测试要点"],
        "analysis": "测试分析",
        "citations": ["law-1"],
        "notice": "测试提示",
    }
    latest = repository.get_latest_run(session_id)
    assert latest is not None
    assert latest["run_id"] == run_id
    assert latest["session_id"] == session_id
    assert latest["result"]["structured_answer"]["summary"] == "测试结论"
    assert latest["result"]["events"][1]["summary"] == "完成"


def test_repository_deletes_session_and_related_runs(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "lawagent.db")
    session_id = repository.create_session()
    run_id = repository.save_run(session_id, "测试问题", _result())

    assert repository.delete_session(session_id) is True
    assert repository.get_session(session_id) == []
    assert repository.get_events(run_id) == []
    assert repository.get_latest_run(session_id) is None


def test_repository_lists_sessions_with_conversation_summaries(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "lawagent.db")
    first_session = repository.create_session()
    second_session = repository.create_session()

    repository.save_run(first_session, "劳动合同解除赔偿怎么算？", _result())
    repository.save_run(second_session, "民法典保证责任有哪些规定？", _result())
    repository.save_run(second_session, "保证期间怎么计算？", _result())

    sessions = repository.list_sessions()

    assert [session["id"] for session in sessions] == [second_session, first_session]
    assert sessions[0]["title"] == "民法典保证责任有哪些规定？"
    assert sessions[0]["last_message"] == "测试回答"
    assert sessions[0]["message_count"] == 4
    assert sessions[0]["run_count"] == 2
    assert sessions[0]["updated_at"] >= sessions[0]["created_at"]


def test_repository_returns_recent_context_before_new_turn(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "lawagent.db")
    session_id = repository.create_session()

    repository.save_run(session_id, "民法典保证责任有哪些规定？", _result())
    repository.save_run(session_id, "保证期间怎么计算？", _result())

    context = repository.get_context(session_id, limit=3)

    assert [message["role"] for message in context] == ["assistant", "user", "assistant"]
    assert context[-2]["content"] == "保证期间怎么计算？"
