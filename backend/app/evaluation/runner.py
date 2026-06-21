from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from typing import Protocol

from pydantic import BaseModel, Field

from app.domain.models import Evidence, LegalArticle


class SearchProtocol(Protocol):
    def search(self, query: str, *, top_k: int = 10) -> list[Evidence]: ...


class EvaluationCase(BaseModel):
    case_id: str
    query: str
    expected_ids: set[str] = Field(default_factory=set)
    category: str = "exact_article"


class EvaluationResult(BaseModel):
    case_id: str
    retrieved_ids: list[str]
    recall: float
    reciprocal_rank: float
    latency_ms: float


class RetrievalEvaluationReport(BaseModel):
    case_count: int
    recall_at_k: float
    mrr: float
    p50_latency_ms: float
    p95_latency_ms: float
    results: list[EvaluationResult]


def recall_at_k(retrieved: Sequence[str], expected: set[str], *, k: int) -> float:
    if not expected:
        return 1.0
    return len(set(retrieved[:k]) & expected) / len(expected)


def mean_reciprocal_rank(cases: Iterable[tuple[Sequence[str], set[str]]]) -> float:
    values: list[float] = []
    for retrieved, expected in cases:
        reciprocal = 0.0
        for rank, article_id in enumerate(retrieved, start=1):
            if article_id in expected:
                reciprocal = 1.0 / rank
                break
        values.append(reciprocal)
    return sum(values) / len(values) if values else 0.0


def citation_precision(predicted: Sequence[set[str]], expected: Sequence[set[str]]) -> float:
    values = [
        len(actual & gold) / len(actual)
        for actual, gold in zip(predicted, expected, strict=True)
        if actual
    ]
    return sum(values) / len(values) if values else 1.0


def citation_completeness(predicted: Sequence[set[str]], expected: Sequence[set[str]]) -> float:
    values = [
        len(actual & gold) / len(gold)
        for actual, gold in zip(predicted, expected, strict=True)
        if gold
    ]
    return sum(values) / len(values) if values else 1.0


def run_retrieval_evaluation(
    search: SearchProtocol,
    cases: Sequence[EvaluationCase],
    *,
    k: int = 10,
) -> RetrievalEvaluationReport:
    results: list[EvaluationResult] = []
    rankings: list[tuple[list[str], set[str]]] = []
    for case in cases:
        started = time.perf_counter()
        evidence = search.search(case.query, top_k=k)
        latency_ms = (time.perf_counter() - started) * 1000
        retrieved = [item.article_id for item in evidence]
        reciprocal_rank = mean_reciprocal_rank([(retrieved, case.expected_ids)])
        results.append(
            EvaluationResult(
                case_id=case.case_id,
                retrieved_ids=retrieved,
                recall=recall_at_k(retrieved, case.expected_ids, k=k),
                reciprocal_rank=reciprocal_rank,
                latency_ms=latency_ms,
            )
        )
        rankings.append((retrieved, case.expected_ids))

    recalls = [result.recall for result in results]
    latencies = sorted(result.latency_ms for result in results)
    return RetrievalEvaluationReport(
        case_count=len(results),
        recall_at_k=sum(recalls) / len(recalls) if recalls else 0.0,
        mrr=mean_reciprocal_rank(rankings),
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        results=results,
    )


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, round((len(values) - 1) * fraction))
    return values[index]


def generate_exact_dataset(
    articles: Sequence[LegalArticle | Evidence], *, count: int = 150
) -> list[EvaluationCase]:
    selected = sorted(articles, key=lambda article: article.article_id)[:count]
    return [
        EvaluationCase(
            case_id=f"exact-{index:03d}",
            query=f"《{article.law_name}》{article.article_number}的内容是什么？",
            expected_ids={article.article_id},
            category="exact_article",
        )
        for index, article in enumerate(selected, start=1)
    ]
