from __future__ import annotations

from datetime import date

from app.domain.models import LegalArticle
from app.rag.retriever import HybridRetriever, reciprocal_rank_fusion


def _article(
    article_id: str,
    content: str,
    *,
    source_date: date | None = None,
    jurisdiction: str = "中国大陆",
    status: str = "effective",
) -> LegalArticle:
    return LegalArticle(
        article_id=article_id,
        document_id=f"doc-{article_id}",
        law_name="示例法",
        article_number=f"第{article_id}条",
        content=content,
        source_file="示例法.docx",
        source_date=source_date,
        jurisdiction=jurisdiction,
        status=status,
    )


def test_reciprocal_rank_fusion_is_deterministic_and_deduplicated() -> None:
    result = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]], k=60)

    assert result[:2] == ["a", "b"]
    assert len(result) == len(set(result))


def test_hybrid_search_combines_lexical_and_semantic_results() -> None:
    articles = [
        _article("1", "用人单位违法解除劳动合同应当支付赔偿金。"),
        _article("2", "劳动者可以依法申请劳动仲裁。"),
        _article("3", "专利申请应当具备新颖性。"),
    ]
    vectors = {"1": [1.0, 0.0], "2": [0.8, 0.2], "3": [0.0, 1.0]}
    retriever = HybridRetriever(articles, vectors, lambda _query: [1.0, 0.0])

    evidence = retriever.search("公司辞退赔偿", top_k=2)

    assert evidence[0].article_id == "1"
    assert {item.article_id for item in evidence} == {"1", "2"}
    assert all(item.score > 0 for item in evidence)


def test_hybrid_search_filters_status_date_and_jurisdiction() -> None:
    articles = [
        _article("1", "劳动合同解除", source_date=date(2020, 1, 1)),
        _article("2", "劳动合同解除", source_date=date(2025, 1, 1), status="expired"),
        _article("3", "劳动合同解除", jurisdiction="其他地区"),
    ]
    retriever = HybridRetriever(
        articles,
        {article.article_id: [1.0, 0.0] for article in articles},
        lambda _query: [1.0, 0.0],
    )

    evidence = retriever.search(
        "解除劳动合同",
        top_k=5,
        as_of_date=date(2024, 6, 1),
        jurisdiction="中国大陆",
    )

    assert [item.article_id for item in evidence] == ["1"]


def test_embedding_failure_falls_back_to_bm25() -> None:
    articles = [_article("1", "民法典规定合同应当依法履行。"), _article("2", "专利权保护。")]

    def fail_embedding(_query: str) -> list[float]:
        raise RuntimeError("embedding unavailable")

    retriever = HybridRetriever(articles, {}, fail_embedding)

    evidence = retriever.search("合同履行", top_k=1)

    assert evidence[0].article_id == "1"
    assert evidence[0].retrieval_mode == "bm25_fallback"
