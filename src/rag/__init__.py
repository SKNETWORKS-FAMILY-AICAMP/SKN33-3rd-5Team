"""Self-contained Hybrid RAG module for the Raspberry Pi Assistant."""

from .evaluation import RetrievalEvaluation, evaluate_rankings, hit_at_k, mean_reciprocal_rank
from .indexer import build_chroma_index
from .models import DocumentChunk, RagFilters, RagResult
from .retriever import HybridRetriever, rrf_fuse

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
