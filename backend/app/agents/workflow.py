from __future__ import annotations

import json
import re
from collections.abc import Callable
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


MessageContext = list[dict[str, str]]


class WorkflowLimits(BaseModel):
    max_tool_calls: int = 12
    max_retries: int = 2


class AgentEvent(BaseModel):
    sequence: int
    type: str
    agent: str | None = None
    summary: str


class StructuredAnswer(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)
    analysis: str | None = None
    citations: list[str] = Field(default_factory=list)
    notice: str


class RetrievalMetrics(BaseModel):
    k: int = 8
    retrieved_count: int = 0
    recall_at_k: float | None = None
    status: Literal["pending_gold", "evaluated"] = "pending_gold"


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
    structured_answer: StructuredAnswer | None = None
    retrieval_metrics: RetrievalMetrics | None = None


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

    def run(
        self,
        query: str,
        *,
        context: MessageContext | None = None,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> WorkflowResult:
        context = _compact_context(context or [])
        events: list[AgentEvent] = []
        agents = ["supervisor"]
        def emit(event_type: str, agent: str | None, summary: str) -> None:
            _emit(events, event_type, agent, summary, on_event=on_event)
        emit("run.started", "supervisor", "Supervisor 开始评估问题")
        route, risk_level = self._supervisor_decision(query, context)
        emit("agent.completed", "supervisor", f"路由={route}，风险={risk_level}")

        if route == "clarify":
            emit("run.completed", None, "等待用户补充关键事实")
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
        emit("agent.started", "legal_research", "开始检索相关现行法规")
        while not evidence and retry_count <= self._limits.max_retries:
            if tool_calls >= self._limits.max_tool_calls:
                emit("run.completed", None, "工具预算耗尽，停止运行")
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
                _query_with_context(query, context)
                if retry_count == 0
                else f"{_query_with_context(query, context)} 相关法律依据 第{retry_count + 1}轮"
            )
            emit("tool.started", "legal_research", f"执行第 {retry_count + 1} 轮混合检索")
            evidence = self._search.search(expanded_query, top_k=8)
            tool_calls += 1
            emit("tool.completed", "legal_research", f"获得 {len(evidence)} 条证据")
            if not evidence and retry_count < self._limits.max_retries:
                retry_count += 1
            elif not evidence:
                break

        if not evidence:
            emit("agent.completed", "legal_research", "证据不足")
            emit("run.completed", None, "无法形成有证据支持的确定性结论")
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

        emit("agent.completed", "legal_research", "检索证据已达到回答门槛")
        analysis = None
        if route == "complex":
            agents.append("legal_analysis")
            emit("agent.started", "legal_analysis", "映射用户事实与法律要件")
            analysis = self._analyze(query, evidence, context)
            emit("agent.completed", "legal_analysis", "完成法律要件分析")

        answer = _append_legal_notice(
            _ensure_evidence_citation(self._answer(query, evidence, analysis, context), evidence),
            evidence,
        )
        if risk_level == "high":
            agents.append("critic")
            emit("agent.started", "critic", "高风险问题进入强制独立审查")
            self._critic(query, answer, evidence, context)
            answer += "\n\n该问题风险较高，请尽快咨询具备相应专业领域经验的执业律师。"
            emit("agent.completed", "critic", "已降低确定性并添加专业协助建议")

        structured_answer = _structure_answer(answer, evidence, analysis)
        emit("run.completed", None, "工作流完成")
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
            structured_answer=structured_answer,
            retrieval_metrics=RetrievalMetrics(k=8, retrieved_count=len(evidence)),
        )

    def _supervisor_decision(
        self, query: str, context: MessageContext
    ) -> tuple[Literal["clarify", "simple", "complex"], Literal["low", "medium", "high"]]:
        fallback = (_route(query), _risk(query))
        if self._model is None:
            return fallback
        try:
            result = self._model.complete_json(
                SUPERVISOR_PROMPT,
                json.dumps({"query": query, "context": context}, ensure_ascii=False),
            )
            route = result.get("route")
            risk = result.get("risk_level")
            if route in {"clarify", "simple", "complex"} and risk in {"low", "medium", "high"}:
                return route, risk  # type: ignore[return-value]
        except Exception:
            pass
        return fallback

    def _analyze(self, query: str, evidence: list[Evidence], context: MessageContext) -> str:
        fallback = _offline_analysis(query, evidence)
        if self._model is None:
            return fallback
        payload = _model_payload(query, evidence, context=context)
        try:
            result = self._model.complete_json(ANALYSIS_PROMPT, payload)
            analysis = result.get("analysis")
            return analysis if isinstance(analysis, str) and analysis.strip() else fallback
        except Exception:
            return fallback

    def _answer(
        self,
        query: str,
        evidence: list[Evidence],
        analysis: str | None,
        context: MessageContext,
    ) -> str:
        fallback = _offline_answer(query, evidence, analysis)
        if self._model is None:
            return fallback
        payload = _model_payload(query, evidence, analysis=analysis, context=context)
        try:
            result = self._model.complete_json(ANSWER_PROMPT, payload)
            answer = result.get("answer")
            return answer if isinstance(answer, str) and answer.strip() else fallback
        except Exception:
            return fallback

    def _critic(
        self,
        query: str,
        answer: str,
        evidence: list[Evidence],
        context: MessageContext,
    ) -> None:
        if self._model is None:
            return
        payload = _model_payload(query, evidence, answer=answer, context=context)
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


def _compact_context(context: MessageContext, *, limit: int = 8) -> MessageContext:
    compacted: MessageContext = []
    for message in context[-limit:]:
        role = message.get("role", "")
        content = re.sub(r"\s+", " ", message.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            compacted.append({"role": role, "content": content[:1200]})
    return compacted


def _query_with_context(query: str, context: MessageContext) -> str:
    if not context:
        return query
    context_text = "\n".join(
        f"{message['role']}: {message['content']}" for message in context[-4:]
    )
    return f"{query}\n\n最近对话上下文：\n{context_text}"


def _offline_analysis(query: str, evidence: list[Evidence]) -> str:
    references = "、".join(f"《{item.law_name}》{item.article_number}" for item in evidence[:3])
    return f"已根据用户陈述识别争议焦点，并与 {references} 的法律要件进行匹配。"


def _offline_answer(query: str, evidence: list[Evidence], analysis: str | None) -> str:
    primary = evidence[0]
    sections = [
        f"先说结论：{primary.content.strip()} [{primary.article_id}]",
        f"1. 直接依据：《{primary.law_name}》{primary.article_number}。[{primary.article_id}]",
    ]
    if analysis:
        sections.append(f"2. 结合你目前提供的信息：{analysis}")
        next_number = 3
    else:
        next_number = 2
    sections.append(
        f"{next_number}. 你接下来可以先核对案件发生时间、合同或通知、付款记录等材料；"
        "如果关键事实还有缺口，可以继续补充，我会接着帮你缩小判断范围。"
    )
    return "\n\n".join(sections)


def _model_payload(
    query: str,
    evidence: list[Evidence],
    *,
    analysis: str | None = None,
    answer: str | None = None,
    context: MessageContext | None = None,
) -> str:
    return json.dumps(
        {
            "query": query,
            "context": context or [],
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


def _append_legal_notice(answer: str, evidence: list[Evidence]) -> str:
    if "适用提示" in answer:
        return answer
    primary = evidence[0] if evidence else None
    version = primary.source_date.isoformat() if primary and primary.source_date else "法规库未标明发布日期"
    status = primary.status if primary else "unknown"
    return (
        f"{answer.rstrip()}\n\n"
        "适用提示："
        f"主要依据的法规状态为 {status}，来源发布日期/版本日期为 {version}；"
        "仍需结合案件发生时间、地域管辖、证据材料和司法裁量判断。"
        "本回答仅作法律信息检索与研究辅助，不构成正式法律意见。"
    )


def _structure_answer(
    answer: str,
    evidence: list[Evidence],
    analysis: str | None,
) -> StructuredAnswer:
    main_text, separator, notice_text = answer.partition("\n\n适用提示：")
    notice = f"适用提示：{notice_text.strip()}" if separator else "请结合完整案情咨询专业律师。"
    numbered_points = [
        match.strip()
        for match in re.findall(r"(?:^|\n)\s*\d+[.、]\s*(.+?)(?=\n\s*\d+[.、]|$)", main_text, re.S)
    ]
    if not numbered_points:
        numbered_points = [
            match.strip()
            for match in re.findall(r"(?:^|\n)\s*[-•]\s+([^\n]+)", main_text)
        ]
    prefix = re.split(
        r"(?:^|\n)\s*(?:\d+[.、]|[-•])\s+", main_text, maxsplit=1
    )[0].strip()
    paragraphs = [item.strip() for item in main_text.split("\n\n") if item.strip()]
    summary = prefix or (paragraphs[0] if paragraphs else main_text.strip())
    if not numbered_points:
        numbered_points = [
            paragraph
            for paragraph in paragraphs[1:]
            if not paragraph.startswith(("分析：", "引用：", "证据引用："))
        ]
    numbered_points = [
        point
        for point in (
            _merge_standalone_citation_lines(point, evidence) for point in numbered_points
        )
        if point
    ]
    citations = [
        item.article_id for item in evidence if f"[{item.article_id}]" in answer
    ]
    return StructuredAnswer(
        summary=summary,
        key_points=numbered_points,
        analysis=analysis,
        citations=citations,
        notice=notice,
    )


def _merge_standalone_citation_lines(point: str, evidence: list[Evidence]) -> str:
    evidence_ids = {item.article_id for item in evidence}
    lines = [line.strip() for line in point.splitlines() if line.strip()]
    merged: list[str] = []
    for line in lines:
        citation = _standalone_citation(line, evidence_ids)
        if citation:
            if merged and f"[{citation}]" not in merged[-1]:
                merged[-1] = f"{merged[-1].rstrip()}[{citation}]"
            continue
        merged.append(line)
    return " ".join(merged).strip()


def _standalone_citation(line: str, evidence_ids: set[str]) -> str | None:
    match = re.fullmatch(r"\[?([A-Za-z0-9_-]{8,})\]?", line.strip())
    if not match:
        return None
    citation = match.group(1)
    return citation if citation in evidence_ids else None


def _emit(
    events: list[AgentEvent],
    event_type: str,
    agent: str | None,
    summary: str,
    *,
    on_event: Callable[[AgentEvent], None] | None = None,
) -> None:
    event = AgentEvent(
        sequence=len(events) + 1,
        type=event_type,
        agent=agent,
        summary=summary,
    )
    events.append(event)
    if on_event is not None:
        on_event(event)
