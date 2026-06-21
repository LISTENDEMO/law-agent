from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.domain.models import Evidence


class Claim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)


class CitationIssue(BaseModel):
    code: str
    claim: str
    detail: str


class CitationResult(BaseModel):
    valid: bool
    issues: list[CitationIssue]


def verify_claims(claims: list[Claim], evidence: list[Evidence]) -> CitationResult:
    evidence_by_id = {item.article_id: item for item in evidence}
    issues: list[CitationIssue] = []
    for claim in claims:
        if not claim.evidence_ids:
            issues.append(
                CitationIssue(
                    code="unsupported_claim",
                    claim=claim.text,
                    detail="关键结论没有关联任何证据",
                )
            )
            continue
        selected: list[Evidence] = []
        for evidence_id in claim.evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                issues.append(
                    CitationIssue(
                        code="unknown_evidence",
                        claim=claim.text,
                        detail=f"证据 ID 不存在：{evidence_id}",
                    )
                )
            else:
                selected.append(item)
        source_text = _normalize(" ".join(item.content for item in selected))
        for quote in claim.quotes:
            if _normalize(quote) not in source_text:
                issues.append(
                    CitationIssue(
                        code="quote_mismatch",
                        claim=claim.text,
                        detail="引用片段与所选法条原文不一致",
                    )
                )
    return CitationResult(valid=not issues, issues=issues)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("“", '"').replace("”", '"')
