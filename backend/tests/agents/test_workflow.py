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
        source_date="2012-12-28",
        status="effective",
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
    assert result.retrieval_metrics is not None
    assert result.retrieval_metrics.k == 8
    assert result.retrieval_metrics.retrieved_count == 1
    assert result.retrieval_metrics.recall_at_k is None
    assert result.retrieval_metrics.status == "pending_gold"


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


def test_online_answer_gets_a_verified_evidence_id_when_model_omits_citation() -> None:
    class CitationOmittingModel:
        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
            if "Supervisor" in system_prompt:
                return {"route": "simple", "risk_level": "low"}
            return {"answer": "模型给出了结论，但漏掉了引用。"}

    result = AgentWorkflow(
        FakeSearch([_evidence()]), model=CitationOmittingModel()
    ).run("劳动合同法第四十七条规定了什么？")

    assert "[labor-47]" in result.answer
    assert "《中华人民共和国劳动合同法》第四十七条" in result.answer


def test_workflow_uses_recent_context_for_follow_up_retrieval() -> None:
    search = FakeSearch([_evidence()])
    workflow = AgentWorkflow(search)

    workflow.run(
        "那赔偿怎么计算？",
        context=[
            {"role": "user", "content": "公司违法辞退我，劳动合同法有什么依据？"},
            {"role": "assistant", "content": "可以重点看经济补偿和违法解除。"},
        ],
    )

    assert "公司违法辞退我" in search.queries[0]
    assert "那赔偿怎么计算？" in search.queries[0]


def test_online_model_payload_contains_context_messages() -> None:
    class PayloadCapturingModel:
        def __init__(self) -> None:
            self.payloads: list[str] = []

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
            self.payloads.append(user_prompt)
            if "Supervisor" in system_prompt:
                return {"route": "simple", "risk_level": "low"}
            return {"answer": "模型回答 [labor-47]"}

    model = PayloadCapturingModel()
    workflow = AgentWorkflow(FakeSearch([_evidence()]), model=model)

    workflow.run(
        "那赔偿怎么计算？",
        context=[{"role": "user", "content": "公司违法辞退我，劳动合同法有什么依据？"}],
    )

    assert any('"context"' in payload for payload in model.payloads)
    assert any("公司违法辞退我" in payload for payload in model.payloads)


def test_offline_answer_includes_structured_legal_risk_and_version_notice() -> None:
    result = AgentWorkflow(FakeSearch([_evidence()])).run("劳动合同法第四十七条规定了什么？")

    assert result.answer.startswith("先说结论：")
    assert "适用提示" in result.answer
    assert "2012-12-28" in result.answer
    assert "不构成正式法律意见" in result.answer


def test_workflow_emits_agent_events_in_real_time_and_returns_structured_answer() -> None:
    emitted = []

    result = AgentWorkflow(FakeSearch([_evidence()])).run(
        "公司违法辞退我，工作三年，赔偿如何计算？",
        on_event=emitted.append,
    )

    assert emitted == result.events
    assert emitted[0].type == "run.started"
    assert emitted[-1].type == "run.completed"
    assert result.structured_answer is not None
    assert result.structured_answer.summary
    assert result.structured_answer.citations == ["labor-47"]
    assert "不构成正式法律意见" in result.structured_answer.notice


def test_answer_agent_is_instructed_to_reply_like_a_natural_conversation() -> None:
    class PromptCapturingModel:
        def __init__(self) -> None:
            self.answer_prompt = ""

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
            if "Supervisor" in system_prompt:
                return {"route": "simple", "risk_level": "low"}
            self.answer_prompt = system_prompt
            return {"answer": "先说结论：可以依法核对补偿标准。[labor-47]"}

    model = PromptCapturingModel()
    AgentWorkflow(FakeSearch([_evidence()]), model=model).run(
        "劳动合同法第四十七条规定了什么？"
    )

    assert "自然对话" in model.answer_prompt
    assert "不要写成报告" in model.answer_prompt


def test_structured_answer_splits_model_bullet_points_into_distinct_items() -> None:
    class BulletAnswerModel:
        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
            if "Supervisor" in system_prompt:
                return {"route": "simple", "risk_level": "low"}
            return {
                "answer": (
                    "先说结论：可以依法主张经济补偿。[labor-47]\n\n"
                    "- 先核对工作年限。[labor-47]\n"
                    "- 再核对解除是否合法。[labor-47]"
                )
            }

    result = AgentWorkflow(FakeSearch([_evidence()]), model=BulletAnswerModel()).run(
        "劳动合同法第四十七条规定了什么？"
    )

    assert result.structured_answer is not None
    assert result.structured_answer.key_points == [
        "先核对工作年限。[labor-47]",
        "再核对解除是否合法。[labor-47]",
    ]


def test_structured_answer_merges_standalone_citation_lines_into_previous_point() -> None:
    evidence_id = "822dd54d44335ef318746ffa"

    class StandaloneCitationAnswerModel:
        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
            if "Supervisor" in system_prompt:
                return {"route": "simple", "risk_level": "low"}
            return {
                "answer": (
                    f"结论：需要核对诉讼时效。[{evidence_id}]\n\n"
                    "1. 现行规则是三年。\n"
                    f"[{evidence_id}]\n"
                    "2. 起算点是知道权利受损之日。\n"
                    f"[{evidence_id}]"
                )
            }

    evidence = Evidence(
        article_id=evidence_id,
        law_name="中华人民共和国民法典",
        article_number="第一百八十八条",
        content="向人民法院请求保护民事权利的诉讼时效期间为三年。",
        score=0.9,
    )

    result = AgentWorkflow(FakeSearch([evidence]), model=StandaloneCitationAnswerModel()).run(
        "民法典诉讼时效怎么计算？"
    )

    assert result.structured_answer is not None
    assert result.structured_answer.key_points == [
        f"现行规则是三年。[{evidence_id}]",
        f"起算点是知道权利受损之日。[{evidence_id}]",
    ]
