"""Self-contained Hybrid RAG module for the Raspberry Pi Assistant."""

from typing import Any

from .evaluation import RetrievalEvaluation, evaluate_rankings, hit_at_k, mean_reciprocal_rank
from .adapters import manifest_chunk_to_document_chunk, manifest_to_document_chunks
from .models import DocumentChunk, RagFilters, RagResult, RetrievalDecision
from .retriever import DenseRetrievalError, HybridRetriever, rrf_fuse
from .settings import RagSettings, RagSettingsError
from .index_metadata import IndexMetadataError, load_indexed_at


def build_chroma_index(*args: Any, **kwargs: Any) -> int:
    """Chroma 색인 함수를 공개 API로 제공하되, CLI 실행 시에는 지연 import한다."""
    from .indexer import build_chroma_index as _build_chroma_index

    return _build_chroma_index(*args, **kwargs)


def index_from_settings(*args: Any, **kwargs: Any) -> int:
    """설정 기반 색인 함수를 지연 import로 제공한다."""
    from .indexer import index_from_settings as _index_from_settings

    return _index_from_settings(*args, **kwargs)

__all__ = [
    "DocumentChunk",
    "DenseRetrievalError",
    "HybridRetriever",
    "IndexMetadataError",
    "RagFilters",
    "RagResult",
    "RagSettings",
    "RagSettingsError",
    "RetrievalEvaluation",
    "RetrievalDecision",
    "build_chroma_index",
    "evaluate_rankings",
    "hit_at_k",
    "index_from_settings",
    "load_indexed_at",
    "mean_reciprocal_rank",
    "manifest_chunk_to_document_chunk",
    "manifest_to_document_chunks",
    "rrf_fuse",
]
