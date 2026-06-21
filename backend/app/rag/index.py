from __future__ import annotations

from pathlib import Path

import numpy as np
from pydantic import BaseModel

from app.domain.models import LegalArticle


class IndexMetadata(BaseModel):
    embedding_model: str
    article_count: int
    dimension: int


class PersistentIndex:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def save(
        self,
        articles: list[LegalArticle],
        vectors: dict[str, list[float]],
        *,
        embedding_model: str,
    ) -> IndexMetadata:
        if not articles:
            raise ValueError("cannot save an empty index")
        missing = [article.article_id for article in articles if article.article_id not in vectors]
        if missing:
            raise ValueError(f"missing vectors for {len(missing)} articles")
        dimensions = {len(vectors[article.article_id]) for article in articles}
        if len(dimensions) != 1 or 0 in dimensions:
            raise ValueError("inconsistent vector dimension")

        dimension = dimensions.pop()
        metadata = IndexMetadata(
            embedding_model=embedding_model,
            article_count=len(articles),
            dimension=dimension,
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        articles_path = self.directory / "articles.jsonl"
        articles_path.write_text(
            "".join(article.model_dump_json() + "\n" for article in articles),
            encoding="utf-8",
        )
        ids = np.asarray([article.article_id for article in articles])
        matrix = np.asarray([vectors[article.article_id] for article in articles], dtype=np.float32)
        np.savez_compressed(self.directory / "vectors.npz", ids=ids, vectors=matrix)
        (self.directory / "metadata.json").write_text(
            metadata.model_dump_json(indent=2), encoding="utf-8"
        )
        return metadata

    def load(self) -> tuple[list[LegalArticle], dict[str, list[float]], IndexMetadata]:
        articles, ids, matrix, metadata = self.load_matrix()
        vectors = dict(zip(ids.tolist(), matrix.tolist(), strict=True))
        return articles, vectors, metadata

    def load_matrix(
        self,
    ) -> tuple[list[LegalArticle], np.ndarray, np.ndarray, IndexMetadata]:
        articles = [
            LegalArticle.model_validate_json(line)
            for line in (self.directory / "articles.jsonl").read_text("utf-8").splitlines()
            if line.strip()
        ]
        archive = np.load(self.directory / "vectors.npz", mmap_mode="r")
        ids = archive["ids"].tolist()
        matrix = archive["vectors"]
        metadata = IndexMetadata.model_validate_json(
            (self.directory / "metadata.json").read_text("utf-8")
        )
        if len(articles) != metadata.article_count or len(ids) != metadata.article_count:
            raise ValueError("index article count does not match metadata")
        return articles, np.asarray(ids), matrix, metadata

    def missing_ids(self, articles: list[LegalArticle]) -> list[str]:
        try:
            _stored_articles, vectors, _metadata = self.load()
        except FileNotFoundError:
            vectors = {}
        return [article.article_id for article in articles if article.article_id not in vectors]
