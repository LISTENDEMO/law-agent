from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import date

import numpy as np
from rank_bm25 import BM25Okapi

from app.domain.models import Evidence, LegalArticle


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], k: int = 60) -> list[str]:
    scores = _rrf_scores(rankings, k)
    return [
        item_id for item_id, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ]


class HybridRetriever:
    def __init__(
        self,
        articles: Sequence[LegalArticle],
        vectors: dict[str, Sequence[float]],
        embed_query: Callable[[str], Sequence[float]],
    ) -> None:
        self._articles = list(articles)
        self._vectors = vectors
        self._embed_query = embed_query

    def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        as_of_date: date | None = None,
        jurisdiction: str = "中国大陆",
    ) -> list[Evidence]:
        candidates = [
            article
            for article in self._articles
            if article.jurisdiction == jurisdiction
            and article.status != "expired"
            and (
                as_of_date is None
                or article.source_date is None
                or article.source_date <= as_of_date
            )
        ]
        if not candidates:
            return []

        bm25_ranking = _bm25_rank(query, candidates)
        mode = "hybrid"
        rankings: list[list[str]] = [bm25_ranking]
        try:
            query_vector = self._embed_query(query)
            vector_ranking = _vector_rank(query_vector, candidates, self._vectors)
            if vector_ranking:
                rankings.append(vector_ranking)
        except Exception:
            mode = "bm25_fallback"

        scores = _rrf_scores(rankings, 60)
        ordered_ids = reciprocal_rank_fusion(rankings, 60)[:top_k]
        articles_by_id = {article.article_id: article for article in candidates}
        return [
            Evidence(
                article_id=articles_by_id[item_id].article_id,
                law_name=articles_by_id[item_id].law_name,
                article_number=articles_by_id[item_id].article_number,
                content=articles_by_id[item_id].content,
                score=scores[item_id],
                retrieval_mode=mode,
                source_date=articles_by_id[item_id].source_date,
                status=articles_by_id[item_id].status,
            )
            for item_id in ordered_ids
        ]


class MatrixHybridRetriever:
    """Memory-efficient hybrid retrieval for the full legal corpus."""

    def __init__(
        self,
        articles: Sequence[LegalArticle],
        matrix: Sequence[Sequence[float]] | np.ndarray | None,
        embed_query: Callable[[str], Sequence[float]] | None,
    ) -> None:
        self._articles = list(articles)
        tokenized = [
            _tokenize(f"{article.law_name} {article.article_number} {article.content}")
            for article in self._articles
        ]
        self._bm25 = BM25Okapi(tokenized)
        self._matrix = None if matrix is None else np.asarray(matrix, dtype=np.float32)
        if self._matrix is not None and len(self._matrix) != len(self._articles):
            raise ValueError("vector matrix row count must match articles")
        self._norms = None if self._matrix is None else np.linalg.norm(self._matrix, axis=1)
        self._embed_query = embed_query

    def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        as_of_date: date | None = None,
        jurisdiction: str = "中国大陆",
    ) -> list[Evidence]:
        eligible = [
            index
            for index, article in enumerate(self._articles)
            if article.jurisdiction == jurisdiction
            and article.status != "expired"
            and (
                as_of_date is None
                or article.source_date is None
                or article.source_date <= as_of_date
            )
        ]
        if not eligible:
            return []
        candidate_count = max(top_k, 20)
        lexical_scores = self._bm25.get_scores(_tokenize(query))
        lexical_indices = sorted(
            eligible,
            key=lambda index: (-lexical_scores[index], self._articles[index].article_id),
        )[:candidate_count]
        rankings = [[self._articles[index].article_id for index in lexical_indices]]
        mode = "bm25"

        if self._matrix is not None and self._embed_query is not None and self._norms is not None:
            try:
                query_vector = np.asarray(self._embed_query(query), dtype=np.float32)
                query_norm = np.linalg.norm(query_vector)
                if query_norm and query_vector.shape[0] == self._matrix.shape[1]:
                    scores = (self._matrix @ query_vector) / (self._norms * query_norm + 1e-12)
                    vector_indices = sorted(
                        eligible,
                        key=lambda index: (-scores[index], self._articles[index].article_id),
                    )[:candidate_count]
                    rankings.append([self._articles[index].article_id for index in vector_indices])
                    mode = "hybrid"
            except Exception:
                mode = "bm25_fallback"

        fused_scores = _rrf_scores(rankings, 60)
        ordered_ids = reciprocal_rank_fusion(rankings, 60)[:top_k]
        articles_by_id = {article.article_id: article for article in self._articles}
        return [
            Evidence(
                article_id=articles_by_id[item_id].article_id,
                law_name=articles_by_id[item_id].law_name,
                article_number=articles_by_id[item_id].article_number,
                content=articles_by_id[item_id].content,
                score=fused_scores[item_id],
                retrieval_mode=mode,
                source_date=articles_by_id[item_id].source_date,
                status=articles_by_id[item_id].status,
            )
            for item_id in ordered_ids
        ]


def _bm25_rank(query: str, articles: Sequence[LegalArticle]) -> list[str]:
    tokenized = [
        _tokenize(f"{article.law_name} {article.article_number} {article.content}")
        for article in articles
    ]
    index = BM25Okapi(tokenized)
    scores = index.get_scores(_tokenize(query))
    pairs = zip(articles, scores, strict=True)
    return [
        article.article_id
        for article, _score in sorted(pairs, key=lambda item: (-item[1], item[0].article_id))
    ]


def _vector_rank(
    query_vector: Sequence[float],
    articles: Sequence[LegalArticle],
    vectors: dict[str, Sequence[float]],
) -> list[str]:
    query = np.asarray(query_vector, dtype=float)
    if query.size == 0 or np.linalg.norm(query) == 0:
        return []
    scored: list[tuple[str, float]] = []
    for article in articles:
        raw_vector = vectors.get(article.article_id)
        if raw_vector is None:
            continue
        vector = np.asarray(raw_vector, dtype=float)
        if vector.shape != query.shape or np.linalg.norm(vector) == 0:
            continue
        score = float(np.dot(query, vector) / (np.linalg.norm(query) * np.linalg.norm(vector)))
        scored.append((article.article_id, score))
    return [item_id for item_id, _score in sorted(scored, key=lambda item: (-item[1], item[0]))]


def _rrf_scores(rankings: Sequence[Sequence[str]], k: int) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] += 1.0 / (k + rank)
    return dict(scores)


def _tokenize(value: str) -> list[str]:
    normalized = re.sub(r"\s+", "", value.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]", normalized)
    bigrams = ["".join(chinese[index : index + 2]) for index in range(len(chinese) - 1)]
    latin = re.findall(r"[a-z0-9]+", normalized)
    return chinese + bigrams + latin
