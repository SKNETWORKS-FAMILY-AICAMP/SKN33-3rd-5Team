"""BM25와 E5/Chroma Dense 검색을 결합하는 Hybrid Retriever.

BM25는 모델명·오류 코드·명령어 같은 정확한 키워드에, Dense 검색은 자연어
의미가 비슷한 질문에 강하다. 두 결과를 RRF로 합쳐 최종 Top-k를 만든다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from .chroma_metadata import chroma_where
from .models import DocumentChunk, RagFilters, RagResult


class DenseRetrievalError(RuntimeError):
    """Chroma가 설정됐지만 Dense 검색을 실행하지 못했을 때 발생한다."""


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
        self._embedding_model = None

    @classmethod
    def from_manifest(cls, path: str | Path, **kwargs: object) -> "HybridRetriever":
        """manifest.json을 읽어 HybridRetriever를 생성하는 편의 메서드."""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([DocumentChunk.from_dict(value) for value in payload["chunks"]], **kwargs)

    @staticmethod
    def _matches(requested: tuple[str, ...], actual: tuple[str, ...]) -> bool:
        """요청 조건이 없거나 청크에 tag가 없으면 제외하지 않고 통과시킨다."""
        return not requested or not actual or bool(set(requested).intersection(actual))

    def _allowed(self, chunk: DocumentChunk, filters: RagFilters) -> bool:
        """검색 점수를 계산하기 전에 공식 여부와 metadata 조건을 검사한다."""
        return (
            (not filters.official_only or chunk.official_verified)
            and self._matches(filters.product_models, chunk.product_models)
            and self._matches(filters.use_cases, chunk.use_cases)
            and self._matches(filters.os_versions, chunk.os_versions)
            and self._matches(filters.source_types, (chunk.source_type,))
        )

    def _bm25_ids(self, query: str, filters: RagFilters, candidate_k: int) -> list[str]:
        """키워드 기반 후보 Top-k의 chunk_id만 반환한다."""
        scores = self.bm25.get_scores(_tokenize(query))
        # 전체 BM25 점수 중 조건을 만족한 청크만 후보로 남긴다.
        candidates = [
            (float(score), chunk.chunk_id)
            for score, chunk in zip(scores, self.chunks, strict=True)
            if self._allowed(chunk, filters)
        ]
        return [chunk_id for _, chunk_id in sorted(candidates, key=lambda item: (-item[0], item[1]))[:candidate_k]]

    def _dense_ids(self, query: str, filters: RagFilters, candidate_k: int) -> list[str]:
        """의미 기반 Chroma 후보 Top-k의 chunk_id만 반환한다.

        Chroma 경로가 없는 경우에는 빈 결과를 반환해 BM25 단독 검색으로 동작한다.
        반대로 Chroma 경로가 설정됐는데 DB·모델·collection 오류가 나면 오류를
        숨기지 않고 호출자에게 전달한다.
        """
        if not self.chroma_path:
            return []
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer

            # 매 질의마다 모델을 다시 읽지 않도록 최초 한 번만 메모리에 보관한다.
            if self._embedding_model is None:
                self._embedding_model = SentenceTransformer(self.embedding_model_name)
            vector = self._embedding_model.encode([f"query: {query}"], normalize_embeddings=True)[0].tolist()
            collection = chromadb.PersistentClient(path=self.chroma_path).get_collection(self.collection_name)
            # 제품·목적·OS 조건까지 DB에서 먼저 걸러 후보 누락을 줄인다.
            query_args: dict[str, object] = {"query_embeddings": [vector], "n_results": candidate_k}
            where = chroma_where(filters)
            if where is not None:
                query_args["where"] = where
            response = collection.query(**query_args)
            return [
                chunk_id
                for chunk_id in response.get("ids", [[]])[0]
                if chunk_id in self.by_id and self._allowed(self.by_id[chunk_id], filters)
            ]
        except Exception as exc:
            raise DenseRetrievalError(
                "Dense retrieval failed. Check CHROMA_PATH and CHROMA_COLLECTION_NAME, "
                "then run `python3 -m src.rag.indexer --reset`."
            ) from exc

    def search(self, query: str, filters: RagFilters | None = None, top_k: int = 5) -> list[RagResult]:
        """질문에 대한 최종 근거 청크를 순위·출처 metadata와 함께 반환한다."""
        if not query.strip():
            return []
        filters = filters or RagFilters()
        # 각 검색기에서 넉넉한 후보 20개를 뽑은 뒤 RRF로 최종 top_k만 선택한다.
        bm25_ids = self._bm25_ids(query, filters, candidate_k=20)
        dense_ids = self._dense_ids(query, filters, candidate_k=20)
        # Dense가 준비된 경우에만 Hybrid, 아니면 BM25를 baseline으로 사용한다.
        ranked_ids = rrf_fuse([bm25_ids, dense_ids]) if dense_ids else bm25_ids
        return [RagResult.from_chunk(self.by_id[chunk_id], rank) for rank, chunk_id in enumerate(ranked_ids[:top_k], start=1)]
