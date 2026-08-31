"""BM25와 E5/Chroma Dense 검색을 결합하는 Hybrid Retriever.

BM25는 모델명·오류 코드·명령어 같은 정확한 키워드에, Dense 검색은 자연어
의미가 비슷한 질문에 강하다. 두 결과를 RRF로 합쳐 최종 Top-k를 만든다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from .adapters import manifest_to_document_chunks
from .chroma_metadata import chroma_where
from .models import DocumentChunk, RagFilters, RagResult, RetrievalDecision


class DenseRetrievalError(RuntimeError):
    """Chroma가 설정됐지만 Dense 검색을 실행하지 못했을 때 발생한다."""


@dataclass(frozen=True)
class _DenseCandidates:
    """Dense 검색의 임계값 통과 후보와 필터 전 후보 수를 보관한다."""

    ids: list[str]
    eligible_count: int


def _tokenize(text: str) -> list[str]:
    """한국어 덩어리와 영문·숫자·기호 키워드를 BM25 입력 토큰으로 나눈다."""
    return re.findall(r"[A-Za-z0-9_+.-]+|[가-힣]+", text.lower())


def rrf_fuse(rankings: list[list[str]], rank_constant: int = 60) -> list[str]:
    """여러 검색기의 순위만 이용해 결합한다.

    점수 스케일이 다른 BM25와 Dense를 직접 더하지 않고, 상위에 자주 등장한
    청크에 ``1 / (60 + 순위)`` 점수를 더하는 Reciprocal Rank Fusion 방식이다.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rank_constant + rank)
    return [chunk_id for chunk_id, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]


class HybridRetriever:
    """검수된 manifest만 입력으로 받는 독립 검색기.

    UI·LLM·문서 수집 코드에 의존하지 않으므로 다른 팀원이 이 클래스를 import해
    ``search()``만 호출하면 된다.
    """

    def __init__(
        self,
        chunks: list[DocumentChunk],
        chroma_path: str | Path | None = None,
        collection_name: str = "rpi_official",
        embedding_model_name: str = "intfloat/multilingual-e5-base",
        dense_max_distance: float = 0.48,
    ) -> None:
        if not chunks:
            raise ValueError("The RAG manifest must contain at least one validated chunk.")
        self.chunks = chunks
        self.by_id = {chunk.chunk_id: chunk for chunk in chunks}
        # BM25는 초기화 시 전체 corpus의 토큰 통계를 계산한다.
        self.bm25 = BM25Okapi([_tokenize(chunk.content) for chunk in chunks])
        self.chroma_path = str(chroma_path) if chroma_path else None
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model_name
        if not 0 < dense_max_distance < 2:
            raise ValueError("dense_max_distance must be between 0 and 2.")
        self.dense_max_distance = dense_max_distance
        self._embedding_model = None

    @classmethod
    def from_manifest(cls, path: str | Path, **kwargs: object) -> "HybridRetriever":
        """manifest.json을 읽어 HybridRetriever를 생성하는 편의 메서드."""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(manifest_to_document_chunks(payload), **kwargs)

    @staticmethod
    def _matches(requested: tuple[str, ...], actual: tuple[str, ...]) -> bool:
        """요청 조건이 없거나 청크에 tag가 없으면 제외하지 않고 통과시킨다."""
        return not requested or not actual or bool(set(requested).intersection(actual))

    @staticmethod
    def _matches_product(chunk: DocumentChunk, filters: RagFilters) -> bool:
        """추천에서는 선택 제품 태그를 필수로, 일반 QA에서는 범용 청크를 허용한다."""

        if not filters.product_models:
            return True
        if chunk.product_models:
            return bool(set(filters.product_models).intersection(chunk.product_models))
        return not filters.strict_product_match

    def _allowed(self, chunk: DocumentChunk, filters: RagFilters) -> bool:
        """검색 점수를 계산하기 전에 공식 여부와 metadata 조건을 검사한다."""
        return (
            (not filters.official_only or chunk.official_verified)
            # Manifest 1.1의 승인 전 청크는 BM25·Dense의 최종 안전장치에서도
            # 제외한다. Dense DB에는 indexer가 애초에 넣지 않지만, BM25는
            # manifest에서 직접 만들기 때문이다.
            and chunk.quality_status == "approved"
            and self._matches(filters.document_ids, (chunk.document_id,))
            and self._matches_product(chunk, filters)
            and self._matches(filters.use_cases, chunk.use_cases)
            and self._matches(filters.os_versions, chunk.os_versions)
            and self._matches(filters.source_types, (chunk.source_type,))
        )

    def _bm25_ids(self, query: str, filters: RagFilters, candidate_k: int) -> list[str]:
        """점수가 0보다 큰 키워드 후보 Top-k의 chunk_id만 반환한다.

        BM25는 모든 문서가 0점이어도 정렬 순서대로 문서를 반환할 수 있다. 그런
        결과는 질의와의 키워드 근거가 없으므로 후보에서 제외한다.
        """
        scores = self.bm25.get_scores(_tokenize(query))
        # 전체 BM25 점수 중 조건을 만족한 청크만 후보로 남긴다.
        candidates = [
            (float(score), chunk.chunk_id)
            for score, chunk in zip(scores, self.chunks, strict=True)
            if score > 0 and self._allowed(chunk, filters)
        ]
        return [chunk_id for _, chunk_id in sorted(candidates, key=lambda item: (-item[0], item[1]))[:candidate_k]]

    def _dense_candidates(
        self, query: str, filters: RagFilters, candidate_k: int
    ) -> _DenseCandidates | None:
        """거리 임계값을 통과한 의미 기반 Chroma 후보를 반환한다.

        Chroma 경로가 없는 경우에는 빈 결과를 반환해 BM25 단독 검색으로 동작한다.
        반대로 Chroma 경로가 설정됐는데 DB·모델·collection 오류가 나면 오류를
        숨기지 않고 호출자에게 전달한다.
        """
        if not self.chroma_path:
            return None
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer

            # 매 질의마다 모델을 다시 읽지 않도록 최초 한 번만 메모리에 보관한다.
            if self._embedding_model is None:
                self._embedding_model = SentenceTransformer(self.embedding_model_name)
            encoded_vector = self._embedding_model.encode(
                [f"query: {query}"], normalize_embeddings=True
            )[0]
            vector = encoded_vector.tolist() if hasattr(encoded_vector, "tolist") else list(encoded_vector)
            collection = chromadb.PersistentClient(path=self.chroma_path).get_collection(self.collection_name)
            # 제품·목적·OS 조건까지 DB에서 먼저 걸러 후보 누락을 줄인다.
            query_args: dict[str, object] = {"query_embeddings": [vector], "n_results": candidate_k}
            where = chroma_where(filters)
            if where is not None:
                query_args["where"] = where
            response = collection.query(**query_args)
            chunk_ids = response.get("ids", [[]])[0]
            distances = response.get("distances", [[]])[0]
            if len(chunk_ids) != len(distances):
                raise DenseRetrievalError("Dense retrieval returned mismatched Chroma ids and distances.")

            eligible_count = 0
            qualified_ids: list[str] = []
            for chunk_id, distance in zip(chunk_ids, distances, strict=True):
                if chunk_id not in self.by_id or not self._allowed(self.by_id[chunk_id], filters):
                    continue
                eligible_count += 1
                if float(distance) <= self.dense_max_distance:
                    qualified_ids.append(chunk_id)
            return _DenseCandidates(ids=qualified_ids, eligible_count=eligible_count)
        except Exception as exc:
            if isinstance(exc, DenseRetrievalError):
                raise
            raise DenseRetrievalError(
                "Dense retrieval failed. Check CHROMA_PATH and CHROMA_COLLECTION_NAME, "
                "then run `python3 -m src.rag.indexer --reset`."
            ) from exc

    @staticmethod
    def _insufficient_reason(bm25_ids: list[str], dense: _DenseCandidates | None) -> str:
        """통과 후보가 없을 때 챗봇에 전달할 보류 사유를 정한다."""
        if dense is None:
            return "bm25_all_zero"
        if not bm25_ids and dense.eligible_count:
            return "bm25_all_zero_and_dense_below_threshold"
        if not bm25_ids:
            return "bm25_all_zero"
        if dense.eligible_count:
            return "dense_below_threshold"
        return "no_qualified_evidence"

    def search_with_decision(
        self, query: str, filters: RagFilters | None = None, top_k: int = 5
    ) -> RetrievalDecision:
        """검증된 근거 청크 또는 ``insufficient_evidence`` 보류 상태를 반환한다."""
        if not query.strip():
            return RetrievalDecision(status="insufficient_evidence", results=(), reason="empty_query")
        filters = filters or RagFilters()
        # 각 검색기에서 넉넉한 후보 20개를 뽑은 뒤 RRF로 최종 top_k만 선택한다.
        bm25_ids = self._bm25_ids(query, filters, candidate_k=20)
        dense = self._dense_candidates(query, filters, candidate_k=20)
        dense_ids = dense.ids if dense is not None else []

        rankings = [ranking for ranking in (bm25_ids, dense_ids) if ranking]
        if not rankings:
            return RetrievalDecision(
                status="insufficient_evidence",
                results=(),
                reason=self._insufficient_reason(bm25_ids, dense),
            )

        # 두 검색기가 모두 통과했을 때만 RRF로 결합하고, 하나만 통과하면 그
        # 검색기의 원래 순위를 유지한다.
        ranked_ids = rrf_fuse(rankings) if len(rankings) > 1 else rankings[0]
        results = tuple(
            RagResult.from_chunk(self.by_id[chunk_id], rank)
            for rank, chunk_id in enumerate(ranked_ids[:top_k], start=1)
        )
        return RetrievalDecision(status="retrieved", results=results)

    def search(self, query: str, filters: RagFilters | None = None, top_k: int = 5) -> list[RagResult]:
        """기존 호출부 호환용으로 검색 결과 목록만 반환한다."""
        return list(self.search_with_decision(query, filters, top_k).results)
