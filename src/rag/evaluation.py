"""Deterministic retrieval evaluation for the RAG Dev/Holdout qrels."""
from __future__ import annotations

from dataclasses import dataclass


def hit_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    return float(bool(set(ranked_ids[:k]).intersection(relevant_ids)))


def mean_reciprocal_rank(rankings: dict[str, list[str]], qrels: dict[str, set[str]]) -> float:
    if not qrels:
        return 0.0
    reciprocal_total = 0.0
    for query_id, relevant_ids in qrels.items():
        for rank, chunk_id in enumerate(rankings.get(query_id, []), start=1):
            if chunk_id in relevant_ids:
                reciprocal_total += 1.0 / rank
                break
    return reciprocal_total / len(qrels)


@dataclass(frozen=True)
class RetrievalEvaluation:
    query_count: int
    hit_at_k: float
    mrr: float


def evaluate_rankings(rankings: dict[str, list[str]], qrels: dict[str, set[str]], k: int = 5) -> RetrievalEvaluation:
    if not qrels:
        return RetrievalEvaluation(query_count=0, hit_at_k=0.0, mrr=0.0)
    hits = sum(hit_at_k(rankings.get(query_id, []), relevant_ids, k) for query_id, relevant_ids in qrels.items())
    return RetrievalEvaluation(query_count=len(qrels), hit_at_k=hits / len(qrels), mrr=mean_reciprocal_rank(rankings, qrels))
