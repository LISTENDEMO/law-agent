from __future__ import annotations

import json
import re
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.agents.prompts import (
    ANALYSIS_PROMPT,
    ANSWER_PROMPT,
    CRITIC_PROMPT,
    SUPERVISOR_PROMPT,
)
from app.domain.models import Evidence


class SearchTool(Protocol):
    def search(self, query: str, *, top_k: int = 8) -> list[Evidence]: ...


class StructuredModel(Protocol):
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]: ...


class WorkflowLimits(BaseModel):
    max_tool_calls: int = 12
    max_retries: int = 2


class AgentEvent(BaseModel):
    sequence: int
    type: str
    agent: str | None = None
    summary: str


class WorkflowResult(BaseModel):
    status: Literal["completed", "waiting_for_user", "insufficient_evidence", "budget_exhausted"]
    route: Literal["clarify", "simple", "complex"]
    risk_level: Literal["low", "medium", "high"]
    answer: str = ""
    clarification: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    analysis: str | None = None
    agents_executed: list[str] = Field(default_factory=list)
    retry_count: int = 0
    tool_calls: int = 0
    events: list[AgentEvent] = Field(default_factory=list)


class AgentWorkflow:
    """A bounded supervisor/specialist graph with deterministic offline behavior."""

    def __init__(
        self,
        search_tool: SearchTool,
        limits: WorkflowLimits | None = None,
        model: StructuredModel | None = None,
    ) -> None:
        self._search = search_tool
        self._limits = limits or WorkflowLimits()
        self._model = model

    def run(self, query: str) -> WorkflowResult:
        events: list[AgentEvent] = []
        agents = ["supervisor"]
        _emit(events, "run.started", "supervisor", "Supervisor 开始评估问题")
        route, risk_level = self._supervisor_decision(query)
        _emit(events, "agent.completed", "supervisor", f"路由={route}，风险={risk_level}")

        if route == "clarify":
            _emit(events, "run.completed", None, "等待用户补充关键事实")
            return WorkflowResult(
                status="waiting_for_user",
                route=route,
                risk_level=risk_level,
                clarification="请说明具体发生了什么、发生时间以及你希望解决的法律问题。",
                agents_executed=agents,
                events=events,
            )

        evidence: list[Evidence] = []
        tool_calls = 0
        retry_count = 0
        agents.append("legal_research")
        _emit(events, "agent.started", "legal_research", "开始检索相关现行法规")
        while not evidence and retry_count <= self._limits.max_retries:
            if tool_calls >= self._limits.max_tool_calls:
                _emit(events, "run.completed", None, "工具预算耗尽，停止运行")
                return WorkflowResult(
                    status="budget_exhausted",
                    route=route,
                    risk_level=risk_level,
                    agents_executed=agents,
                    retry_count=retry_count,
                    tool_calls=tool_calls,
                    events=events,
                )
            expanded_query = (
                query if retry_count == 0 else f"{query} 相关法律依据 第{retry_count + 1}轮"
            )
            _emit(events, "tool.started", "legal_research", f"执行第 {retry_count + 1} 轮混合检索")
            evidence = self._search.search(expanded_query, top_k=8)
            tool_calls += 1
            _emit(events, "tool.completed", "legal_research", f"获得 {len(evidence)} 条证据")
            if not evidence and retry_count < self._limits.max_retries:
                retry_count += 1
            elif not evidence:
                break

        if not evidence:
            _emit(events, "agent.completed", "legal_research", "证据不足")
            _emit(events, "run.completed", None, "无法形成有证据支持的确定性结论")
            return WorkflowResult(
                status="insufficient_evidence",
                route=route,
                risk_level=risk_level,
                answer="现有法规库中未找到足以支持确定结论的证据，请补充更具体的事实。",
                agents_executed=agents,
                retry_count=retry_count,
                tool_calls=tool_calls,
                events=events,
            )

        _emit(events, "agent.completed", "legal_research", "检索证据已达到回答门槛")
        analysis = None
        if route == "complex":
            agents.append("legal_analysis")
            _emit(events, "agent.started", "legal_analysis", "映射用户事实与法律要件")
            analysis = self._analyze(query, evidence)
            _emit(events, "agent.completed", "legal_analysis", "完成法律要件分析")

        answer = _ensure_evidence_citation(self._answer(query, evidence, analysis), evidence)
        if risk_level == "high":
            agents.append("critic")
            _emit(events, "agent.started", "critic", "高风险问题进入强制独立审查")
            self._critic(query, answer, evidence)
            answer += "\n\n该问题风险较高，请尽快咨询具备相应专业领域经验的执业律师。"
            _emit(events, "agent.completed", "critic", "已降低确定性并添加专业协助建议")

        _emit(events, "run.completed", None, "工作流完成")
        return WorkflowResult(
            status="completed",
            route=route,
            risk_level=risk_level,
            answer=answer,
            evidence=evidence,
            analysis=analysis,
            agents_executed=agents,
            retry_count=retry_count,
            tool_calls=tool_calls,
            events=events,
        )

    def _supervisor_decision(
        self, query: str
    ) -> tuple[Literal["clarify", "simple", "complex"], Literal["low", "medium", "high"]]:
        fallback = (_route(query), _risk(query))
        if self._model is None:
            return fallback
        try:
            result = self._model.complete_json(
                SUPERVISOR_PROMPT,
                json.dumps({"query": query}, ensure_ascii=False),
            )
            route = result.get("route")
            risk = result.get("risk_level")
            if route in {"clarify", "simple", "complex"} and risk in {"low", "medium", "high"}:
                return route, risk  # type: ignore[return-value]
        except Exception:
            pass
        return fallback

    def _analyze(self, query: str, evidence: list[Evidence]) -> str:
        fallback = _offline_analysis(query, evidence)
        if self._model is None:
            return fallback
        payload = _model_payload(query, evidence)
        try:
            result = self._model.complete_json(ANALYSIS_PROMPT, payload)
            analysis = result.get("analysis")
            return analysis if isinstance(analysis, str) and analysis.strip() else fallback
        except Exception:
            return fallback

    def _answer(self, query: str, evidence: list[Evidence], analysis: str | None) -> str:
        fallback = _offline_answer(query, evidence, analysis)
        if self._model is None:
            return fallback
        payload = _model_payload(query, evidence, analysis=analysis)
        try:
            result = self._model.complete_json(ANSWER_PROMPT, payload)
            answer = result.get("answer")
            return answer if isinstance(answer, str) and answer.strip() else fallback
        except Exception:
            return fallback

    def _critic(self, query: str, answer: str, evidence: list[Evidence]) -> None:
        if self._model is None:
            return
        payload = _model_payload(query, evidence, answer=answer)
        try:
            self._model.complete_json(CRITIC_PROMPT, payload)
        except Exception:
            return


def _route(query: str) -> Literal["clarify", "simple", "complex"]:
    compact = re.sub(r"\s+", "", query)
    if len(compact) < 8 or compact in {"怎么办？", "我该怎么办？", "帮帮我"}:
        return "clarify"
    if re.search(r"第.+条|规定了什么|法条内容", compact):
        return "simple"
    return "complex"


def _risk(query: str) -> Literal["low", "medium", "high"]:
    if any(word in query for word in ("刑事", "犯罪", "被捕", "人身安全", "自杀")):
        return "high"
    if any(word in query for word in ("赔偿", "辞退", "合同", "离婚", "诉讼")):
        return "medium"
    return "low"


def _offline_analysis(query: str, evidence: list[Evidence]) -> str:
    references = "、".join(f"《{item.law_name}》{item.article_number}" for item in evidence[:3])
    return f"已根据用户陈述识别争议焦点，并与 {references} 的法律要件进行匹配。"


def _offline_answer(query: str, evidence: list[Evidence], analysis: str | None) -> str:
    lead = "根据当前检索到的有效法规，"
    body = evidence[0].content
    analysis_text = f"\n\n分析：{analysis}" if analysis else ""
    reference = f"{evidence[0].law_name}{evidence[0].article_number}"
    return f"{lead}{body}{analysis_text}\n\n引用：[1] {reference}"


def _model_payload(
    query: str,
    evidence: list[Evidence],
    *,
    analysis: str | None = None,
    answer: str | None = None,
) -> str:
    return json.dumps(
        {
            "query": query,
            "analysis": analysis,
            "answer": answer,
            "evidence": [item.model_dump(mode="json") for item in evidence],
        },
        ensure_ascii=False,
    )


def _ensure_evidence_citation(answer: str, evidence: list[Evidence]) -> str:
    if any(f"[{item.article_id}]" in answer for item in evidence):
        return answer
    references = "；".join(
        f"[{item.article_id}] 《{item.law_name}》{item.article_number}"
        for item in evidence[:3]
    )
    return f"{answer.rstrip()}\n\n证据引用：{references}"


def _emit(events: list[AgentEvent], event_type: str, agent: str | None, summary: str) -> None:
    events.append(
        AgentEvent(sequence=len(events) + 1, type=event_type, agent=agent, summary=summary)
    )
