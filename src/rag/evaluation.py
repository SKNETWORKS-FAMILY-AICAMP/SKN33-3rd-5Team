"""RAG 검색 성능을 Dev/Holdout 정답셋(qrels)으로 계산한다.

qrels는 ``질문 ID -> 정답 chunk_id 집합``이다. 같은 qrels로 BM25, Dense,
Hybrid 결과를 평가하면 어떤 검색 방식이 더 나은지 비교할 수 있다.
"""
from __future__ import annotations

from dataclasses import dataclass


def hit_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """상위 k개 안에 정답 청크가 하나라도 있으면 1, 없으면 0을 반환한다."""
    return float(bool(set(ranked_ids[:k]).intersection(relevant_ids)))


def mean_reciprocal_rank(rankings: dict[str, list[str]], qrels: dict[str, set[str]]) -> float:
    """각 질문에서 첫 정답이 나온 순위의 역수 평균(MRR)을 계산한다."""
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
    """전체 질문의 Hit@k와 MRR을 한 번에 계산해 실험 결과로 반환한다."""
    if not qrels:
        return RetrievalEvaluation(query_count=0, hit_at_k=0.0, mrr=0.0)
    hits = sum(hit_at_k(rankings.get(query_id, []), relevant_ids, k) for query_id, relevant_ids in qrels.items())
    return RetrievalEvaluation(query_count=len(qrels), hit_at_k=hits / len(qrels), mrr=mean_reciprocal_rank(rankings, qrels))
