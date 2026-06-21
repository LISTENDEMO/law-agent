from __future__ import annotations

from app.domain.models import Evidence
from app.evaluation.runner import (
    EvaluationCase,
    citation_completeness,
    citation_precision,
    generate_exact_dataset,
    mean_reciprocal_rank,
    recall_at_k,
    run_retrieval_evaluation,
)


def test_recall_at_k_handles_hits_misses_and_empty_gold() -> None:
    assert recall_at_k(["a", "b", "c"], {"b", "d"}, k=2) == 0.5
    assert recall_at_k(["a"], {"b"}, k=5) == 0.0
    assert recall_at_k([], set(), k=5) == 1.0


def test_mean_reciprocal_rank_uses_first_relevant_position() -> None:
    assert mean_reciprocal_rank([(["x", "a"], {"a"}), (["b"], {"b"})]) == 0.75
    assert mean_reciprocal_rank([]) == 0.0


def test_citation_metrics_penalize_unknown_and_missing_citations() -> None:
    predicted = [{"a", "invented"}, {"b"}, set()]
    expected = [{"a"}, {"b", "c"}, set()]

    assert citation_precision(predicted, expected) == 0.75
    assert citation_completeness(predicted, expected) == 0.75


def test_retrieval_evaluation_returns_aggregate_and_per_case_results() -> None:
    class Search:
        def search(self, query: str, *, top_k: int = 10) -> list[Evidence]:
            return [
                Evidence(
                    article_id="gold-1",
                    law_name="示例法",
                    article_number="第一条",
                    content="示例内容",
                )
            ]

    report = run_retrieval_evaluation(
        Search(),
        [EvaluationCase(case_id="case-1", query="第一条是什么", expected_ids={"gold-1"})],
        k=10,
    )

    assert report.case_count == 1
    assert report.recall_at_k == 1.0
    assert report.mrr == 1.0
    assert report.results[0].retrieved_ids == ["gold-1"]


def test_exact_dataset_generation_is_deterministic_and_unique() -> None:
    articles = [
        Evidence(
            article_id=f"id-{index}",
            law_name=f"示例法{index}",
            article_number=f"第{index}条",
            content="内容",
        )
        for index in range(4)
    ]

    cases = generate_exact_dataset(articles, count=3)

    assert len(cases) == 3
    assert len({case.case_id for case in cases}) == 3
    assert cases[0].query == "《示例法0》第0条的内容是什么？"
