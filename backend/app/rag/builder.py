from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel

from app.domain.models import LegalArticle
from app.rag.index import PersistentIndex


class BuildReport(BaseModel):
    total_articles: int
    cached_before: int
    embedded_now: int
    dimension: int


class EmbeddingIndexBuilder:
    def __init__(
        self,
        normalized_path: str | Path,
        index_dir: str | Path,
        cache_path: str | Path,
        *,
        embedding_model: str,
        embed_batch: Callable[[list[str]], list[list[float]]],
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        self.normalized_path = Path(normalized_path)
        self.index = PersistentIndex(index_dir)
        self.cache_path = Path(cache_path)
        self.embedding_model = embedding_model
        self.embed_batch = embed_batch
        self.progress = progress

    def build(self, *, batch_size: int = 64, workers: int = 1) -> BuildReport:
        articles = self._load_articles()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.cache_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    article_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    PRIMARY KEY (article_id, model)
                )
                """
            )
            cached_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT article_id FROM embeddings WHERE model = ?", (self.embedding_model,)
                )
            }
            current_ids = {article.article_id for article in articles}
            cached_before = len(cached_ids & current_ids)
            missing = [article for article in articles if article.article_id not in cached_ids]
            embedded_now = 0
            batches = [
                missing[start : start + batch_size]
                for start in range(0, len(missing), batch_size)
            ]
            text_batches = [
                [_embedding_text(article) for article in batch] for batch in batches
            ]
            if workers == 1:
                batch_results = (
                    (batch, self.embed_batch(texts))
                    for batch, texts in zip(batches, text_batches, strict=True)
                )
                embedded_now = self._consume_results(
                    connection, batch_results, cached_before, len(articles)
                )
            else:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    results = executor.map(self.embed_batch, text_batches)
                    batch_results = zip(batches, results, strict=True)
                    embedded_now = self._consume_results(
                        connection, batch_results, cached_before, len(articles)
                    )

            rows = connection.execute(
                "SELECT article_id, vector_json FROM embeddings WHERE model = ?",
                (self.embedding_model,),
            ).fetchall()
        vectors_by_id = {
            article_id: json.loads(vector_json)
            for article_id, vector_json in rows
            if article_id in current_ids
        }
        metadata = self.index.save(
            articles, vectors_by_id, embedding_model=self.embedding_model
        )
        return BuildReport(
            total_articles=len(articles),
            cached_before=cached_before,
            embedded_now=embedded_now,
            dimension=metadata.dimension,
        )

    def _commit_batch(
        self,
        connection: sqlite3.Connection,
        batch: list[LegalArticle],
        vectors: list[list[float]],
    ) -> int:
        if len(vectors) != len(batch):
            raise ValueError("embedding provider returned an unexpected number of vectors")
        statement = (
            "INSERT OR REPLACE INTO embeddings "
            "(article_id, model, vector_json) VALUES (?, ?, ?)"
        )
        connection.executemany(
            statement,
            [
                (article.article_id, self.embedding_model, json.dumps(vector))
                for article, vector in zip(batch, vectors, strict=True)
            ],
        )
        connection.commit()
        return len(batch)

    def _consume_results(
        self,
        connection: sqlite3.Connection,
        results: Iterable[tuple[list[LegalArticle], list[list[float]]]],
        cached_before: int,
        total_articles: int,
    ) -> int:
        embedded_now = 0
        for batch, vectors in results:
            embedded_now += self._commit_batch(connection, batch, vectors)
            if self.progress:
                self.progress(cached_before + embedded_now, total_articles)
        return embedded_now

    def _load_articles(self) -> list[LegalArticle]:
        return [
            LegalArticle.model_validate_json(line)
            for line in self.normalized_path.read_text("utf-8").splitlines()
            if line.strip()
        ]


def _embedding_text(article: LegalArticle) -> str:
    return f"{article.law_name}\n{article.article_number}\n{article.content[:6000]}"
