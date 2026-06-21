from __future__ import annotations

from collections.abc import Iterable
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
        return self.save_items(articles, vectors.items(), embedding_model=embedding_model)

    def save_items(
        self,
        articles: list[LegalArticle],
        vector_items: Iterable[tuple[str, list[float]]],
        *,
        embedding_model: str,
    ) -> IndexMetadata:
        """Persist a vector stream without materializing a dict of Python floats."""
        if not articles:
            raise ValueError("cannot save an empty index")
        positions = {article.article_id: index for index, article in enumerate(articles)}
        seen = np.zeros(len(articles), dtype=np.bool_)
        matrix: np.ndarray | None = None
        dimension = 0
        for article_id, vector in vector_items:
            position = positions.get(article_id)
            if position is None:
                continue
            if matrix is None:
                dimension = len(vector)
                if dimension == 0:
                    raise ValueError("inconsistent vector dimension")
                matrix = np.empty((len(articles), dimension), dtype=np.float32)
            if len(vector) != dimension:
                raise ValueError("inconsistent vector dimension")
            matrix[position] = vector
            seen[position] = True
        missing_count = int((~seen).sum())
        if missing_count:
            raise ValueError(f"missing vectors for {missing_count} articles")
        if matrix is None:
            raise ValueError("missing vectors for all articles")

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
