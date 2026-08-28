"""Self-contained Hybrid RAG module for the Raspberry Pi Assistant."""

from typing import Any

from .evaluation import RetrievalEvaluation, evaluate_rankings, hit_at_k, mean_reciprocal_rank
from .models import DocumentChunk, RagFilters, RagResult
from .retriever import HybridRetriever, rrf_fuse


def build_chroma_index(*args: Any, **kwargs: Any) -> int:
    """Chroma 색인 함수를 공개 API로 제공하되, CLI 실행 시에는 지연 import한다."""
    from .indexer import build_chroma_index as _build_chroma_index

    return _build_chroma_index(*args, **kwargs)

__all__ = [
    "DocumentChunk",
    "HybridRetriever",
    "RagFilters",
    "RagResult",
    "RetrievalEvaluation",
    "build_chroma_index",
    "evaluate_rankings",
    "hit_at_k",
    "mean_reciprocal_rank",
    "rrf_fuse",
]
