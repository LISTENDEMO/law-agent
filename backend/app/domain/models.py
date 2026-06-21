from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class LegalArticle(BaseModel):
    article_id: str
    document_id: str
    law_name: str
    article_number: str
    content: str
    context_path: list[str] = Field(default_factory=list)
    source_file: str
    source_date: date | None = None
    jurisdiction: str = "中国大陆"
    status: Literal["effective", "unknown", "expired"] = "unknown"
    parse_mode: Literal["article", "fallback"] = "article"


class LawDocument(BaseModel):
    document_id: str
    law_name: str
    source_file: str
    source_date: date | None = None
    content_hash: str
    articles: list[LegalArticle]


class Evidence(BaseModel):
    article_id: str
    law_name: str
    article_number: str
    content: str
    score: float = 0.0
    retrieval_mode: str = "hybrid"
    source_date: date | None = None
    status: str = "unknown"


class CorpusIssue(BaseModel):
    source_file: str
    code: str
    message: str


class CorpusReport(BaseModel):
    total_files: int
    accepted: int
    duplicates: int
    quarantined: int
    article_count: int
    issues: list[CorpusIssue] = Field(default_factory=list)
