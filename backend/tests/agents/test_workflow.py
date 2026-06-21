from __future__ import annotations

from app.agents.workflow import AgentWorkflow, WorkflowLimits
from app.domain.models import Evidence


class FakeSearch:
    def __init__(self, results: list[Evidence]) -> None:
        self.results = results
        self.queries: list[str] = []

    def search(self, query: str, *, top_k: int = 8) -> list[Evidence]:
        self.queries.append(query)
        return self.results


def _evidence() -> Evidence:
    return Evidence(
        article_id="labor-47",
        law_name="中华人民共和国劳动合同法",
        article_number="第四十七条",
        content="经济补偿按劳动者在本单位工作的年限，每满一年支付一个月工资。",
        score=0.9,
    )


def test_supervisor_requests_clarification_when_question_has_no_legal_facts() -> None:
    workflow = AgentWorkflow(FakeSearch([_evidence()]))

    result = workflow.run("我该怎么办？")

    assert result.status == "waiting_for_user"
    assert result.clarification
    assert result.agents_executed == ["supervisor"]


def test_simple_statute_question_delegates_to_research() -> None:
    workflow = AgentWorkflow(FakeSearch([_evidence()]))

    result = workflow.run("劳动合同法第四十七条规定了什么？")

    assert result.status == "completed"
    assert result.agents_executed == ["supervisor", "legal_research"]
    assert result.evidence[0].article_id == "labor-47"


def test_complex_case_delegates_to_research_and_analysis() -> None:
    workflow = AgentWorkflow(FakeSearch([_evidence()]))

    result = workflow.run("公司违法辞退我，我工作了三年，经济补偿应当如何计算？")

    assert result.status == "completed"
    assert "legal_research" in result.agents_executed
    assert "legal_analysis" in result.agents_executed
    assert result.analysis is not None


def test_high_risk_case_must_invoke_critic() -> None:
    workflow = AgentWorkflow(FakeSearch([_evidence()]))

    result = workflow.run("我涉嫌刑事犯罪，现在应当怎么处理？")

    assert "critic" in result.agents_executed
    assert result.risk_level == "high"
    assert "律师" in result.answer


def test_insufficient_evidence_retries_at_most_twice() -> None:
    search = FakeSearch([])
    workflow = AgentWorkflow(search)

    result = workflow.run("劳动合同解除有什么规定？")

    assert result.status == "insufficient_evidence"
    assert result.retry_count == 2
    assert len(search.queries) == 3


def test_budget_exhaustion_terminates_workflow() -> None:
    workflow = AgentWorkflow(FakeSearch([]), limits=WorkflowLimits(max_tool_calls=1, max_retries=2))

    result = workflow.run("劳动合同解除有什么规定？")

    assert result.status == "budget_exhausted"
    assert result.tool_calls == 1
    assert result.events[-1].type == "run.completed"


def test_online_workflow_uses_independent_structured_agent_calls() -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.system_prompts: list[str] = []

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
            self.system_prompts.append(system_prompt)
            if "Supervisor" in system_prompt:
                return {"route": "complex", "risk_level": "high"}
            if "Legal Analysis Agent" in system_prompt:
                return {"analysis": "模型完成的要件分析"}
            if "Critic Agent" in system_prompt:
                return {"approved": True, "issues": []}
            return {"answer": "模型生成的证据约束回答 [labor-47]"}

    model = FakeModel()
    workflow = AgentWorkflow(FakeSearch([_evidence()]), model=model)

    result = workflow.run("公司违法辞退我，工作三年，应如何主张权利？")

    assert "模型生成的证据约束回答" in result.answer
    assert result.analysis == "模型完成的要件分析"
    assert "critic" in result.agents_executed
    assert len(model.system_prompts) == 4
