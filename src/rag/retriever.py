"""Metadata-filtered BM25 + E5/Chroma Dense retrieval with RRF fusion."""
from __future__ import annotations

import json
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from .models import DocumentChunk, RagFilters, RagResult


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_+.-]+|[가-힣]+", text.lower())


def rrf_fuse(rankings: list[list[str]], rank_constant: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rank_constant + rank)
    return [chunk_id for chunk_id, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]


class HybridRetriever:
    """Independent of UI, LLM, and document collection; receives reviewed manifest only."""

    def __init__(
        self,
        chunks: list[DocumentChunk],
        chroma_path: str | Path | None = None,
        collection_name: str = "rpi_official",
        embedding_model_name: str = "intfloat/multilingual-e5-base",
    ) -> None:
        if not chunks:
            raise ValueError("The RAG manifest must contain at least one validated chunk.")
        self.chunks = chunks
        self.by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self.bm25 = BM25Okapi([_tokenize(chunk.content) for chunk in chunks])
        self.chroma_path = str(chroma_path) if chroma_path else None
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model_name
        self._embedding_model = None

    @classmethod
    def from_manifest(cls, path: str | Path, **kwargs: object) -> "HybridRetriever":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([DocumentChunk.from_dict(value) for value in payload["chunks"]], **kwargs)

    @staticmethod
    def _matches(requested: tuple[str, ...], actual: tuple[str, ...]) -> bool:
        return not requested or not actual or bool(set(requested).intersection(actual))

    def _allowed(self, chunk: DocumentChunk, filters: RagFilters) -> bool:
        return (
            (not filters.official_only or chunk.official_verified)
            and self._matches(filters.product_models, chunk.product_models)
            and self._matches(filters.use_cases, chunk.use_cases)
            and self._matches(filters.os_versions, chunk.os_versions)
            and self._matches(filters.source_types, (chunk.source_type,))
        )

    def _bm25_ids(self, query: str, filters: RagFilters, candidate_k: int) -> list[str]:
        scores = self.bm25.get_scores(_tokenize(query))
        candidates = [
            (float(score), chunk.chunk_id)
            for score, chunk in zip(scores, self.chunks, strict=True)
            if self._allowed(chunk, filters)
        ]
        return [chunk_id for _, chunk_id in sorted(candidates, key=lambda item: (-item[0], item[1]))[:candidate_k]]

    def _dense_ids(self, query: str, filters: RagFilters, candidate_k: int) -> list[str]:
        if not self.chroma_path:
            return []
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer

            if self._embedding_model is None:
                self._embedding_model = SentenceTransformer(self.embedding_model_name)
            vector = self._embedding_model.encode([f"query: {query}"], normalize_embeddings=True)[0].tolist()
            collection = chromadb.PersistentClient(path=self.chroma_path).get_collection(self.collection_name)
            response = collection.query(
                query_embeddings=[vector], n_results=candidate_k, where={"official_verified": True}
            )
            return [
                chunk_id
                for chunk_id in response.get("ids", [[]])[0]
                if chunk_id in self.by_id and self._allowed(self.by_id[chunk_id], filters)
            ]
        except Exception:
            # Dense setup is optional during BM25-only development; callers still receive safe results.
            return []

    def search(self, query: str, filters: RagFilters | None = None, top_k: int = 5) -> list[RagResult]:
        if not query.strip():
            return []
        filters = filters or RagFilters()
        bm25_ids = self._bm25_ids(query, filters, candidate_k=20)
        dense_ids = self._dense_ids(query, filters, candidate_k=20)
        ranked_ids = rrf_fuse([bm25_ids, dense_ids]) if dense_ids else bm25_ids
        return [RagResult.from_chunk(self.by_id[chunk_id], rank) for rank, chunk_id in enumerate(ranked_ids[:top_k], start=1)]
