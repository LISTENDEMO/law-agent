from __future__ import annotations

from pathlib import Path

from app.domain.models import LegalArticle
from app.rag.index import IndexMetadata, PersistentIndex


def _article(article_id: str, content: str) -> LegalArticle:
    return LegalArticle(
        article_id=article_id,
        document_id="doc-1",
        law_name="示例法",
        article_number=f"第{article_id}条",
        content=content,
        source_file="示例法.docx",
        status="effective",
    )


def test_persistent_index_round_trip(tmp_path: Path) -> None:
    articles = [_article("1", "劳动合同解除"), _article("2", "专利新颖性")]
    index = PersistentIndex(tmp_path / "index")

    index.save(articles, {"1": [1.0, 0.0], "2": [0.0, 1.0]}, embedding_model="test-v1")
    loaded_articles, vectors, metadata = index.load()

    assert [item.article_id for item in loaded_articles] == ["1", "2"]
    assert vectors == {"1": [1.0, 0.0], "2": [0.0, 1.0]}
    assert metadata == IndexMetadata(embedding_model="test-v1", article_count=2, dimension=2)


def test_persistent_index_reports_missing_article_vectors_for_resume(tmp_path: Path) -> None:
    articles = [_article("1", "劳动合同解除"), _article("2", "专利新颖性")]
    index = PersistentIndex(tmp_path / "index")
    index.save(articles[:1], {"1": [1.0, 0.0]}, embedding_model="test-v1")

    assert index.missing_ids(articles) == ["2"]


def test_persistent_index_rejects_inconsistent_vector_dimensions(tmp_path: Path) -> None:
    index = PersistentIndex(tmp_path / "index")
    articles = [_article("1", "劳动合同解除"), _article("2", "专利新颖性")]

    try:
        index.save(articles, {"1": [1.0, 0.0], "2": [1.0]}, embedding_model="test-v1")
    except ValueError as error:
        assert "dimension" in str(error)
    else:
        raise AssertionError("inconsistent vectors must be rejected")


def test_persistent_index_saves_vectors_from_single_pass_iterable(tmp_path: Path) -> None:
    index = PersistentIndex(tmp_path / "index")
    articles = [_article("1", "劳动合同解除"), _article("2", "专利新颖性")]
    consumed: list[str] = []

    def vector_items():
        for article_id, vector in [("2", [0.0, 1.0]), ("1", [1.0, 0.0])]:
            consumed.append(article_id)
            yield article_id, vector

    metadata = index.save_items(articles, vector_items(), embedding_model="test-v1")
    _articles, vectors, _metadata = index.load()

    assert consumed == ["2", "1"]
    assert vectors == {"1": [1.0, 0.0], "2": [0.0, 1.0]}
    assert metadata.dimension == 2
