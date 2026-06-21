from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from app.domain.models import LegalArticle
from app.rag.builder import EmbeddingIndexBuilder
from app.rag.index import PersistentIndex


def _write_articles(path: Path, count: int) -> None:
    records = [
        LegalArticle(
            article_id=str(index),
            document_id="doc",
            law_name="示例法",
            article_number=f"第{index}条",
            content=f"第{index}条 测试内容",
            source_file="示例法.docx",
        ).model_dump(mode="json")
        for index in range(count)
    ]
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records), "utf-8"
    )


def test_builder_resumes_from_committed_batches_after_failure(tmp_path: Path) -> None:
    normalized = tmp_path / "articles.jsonl"
    _write_articles(normalized, 5)
    calls: list[list[str]] = []

    def flaky_embed(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        if len(calls) == 2:
            raise RuntimeError("temporary failure")
        return [[float(len(text)), 1.0] for text in texts]

    builder = EmbeddingIndexBuilder(
        normalized,
        tmp_path / "index",
        tmp_path / "cache.db",
        embedding_model="test-v1",
        embed_batch=flaky_embed,
    )

    with pytest.raises(RuntimeError, match="temporary"):
        builder.build(batch_size=2)

    def healthy_embed(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        return [[float(len(text)), 1.0] for text in texts]

    builder = EmbeddingIndexBuilder(
        normalized,
        tmp_path / "index",
        tmp_path / "cache.db",
        embedding_model="test-v1",
        embed_batch=healthy_embed,
    )
    report = builder.build(batch_size=2)
    articles, vectors, metadata = PersistentIndex(tmp_path / "index").load()

    assert report.cached_before == 2
    assert report.embedded_now == 3
    assert len(articles) == len(vectors) == metadata.article_count == 5
    assert sum(len(batch) for batch in calls) == 7


def test_builder_embeds_batches_concurrently_without_concurrent_sqlite_writes(
    tmp_path: Path,
) -> None:
    normalized = tmp_path / "articles.jsonl"
    _write_articles(normalized, 2)
    barrier = threading.Barrier(2, timeout=2)

    def concurrent_embed(texts: list[str]) -> list[list[float]]:
        barrier.wait()
        return [[float(len(texts[0])), 1.0]]

    builder = EmbeddingIndexBuilder(
        normalized,
        tmp_path / "index",
        tmp_path / "cache.db",
        embedding_model="test-v1",
        embed_batch=concurrent_embed,
    )

    report = builder.build(batch_size=1, workers=2)

    assert report.embedded_now == 2
