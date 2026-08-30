"""RAG 모듈이 다른 담당자 모듈과 주고받는 데이터 형식(계약)을 정의한다.

문서 담당자는 ``DocumentChunk`` 형식의 manifest를 만들고, sLLM 담당자는
조건 JSON을 ``RagFilters``로 바꿔 전달한다. 챗봇 담당자는 ``RagResult``를
그대로 근거 카드와 답변 컨텍스트에 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class RagFilters:
    """검색 대상을 좁히기 위한 조건.

    빈 튜플 ``()``은 해당 조건으로 제한하지 않는다는 뜻이다. 예를 들어
    ``use_cases=("camera",)``이면 카메라 목적 청크를 우선 대상으로 삼는다.
    """

    product_models: tuple[str, ...] = ()
    use_cases: tuple[str, ...] = ()
    os_versions: tuple[str, ...] = ()
    # 제품 추천은 catalog가 검증한 근거 문서 안에서만 답해야 한다. 빈 튜플은
    # 기존 QA처럼 문서 ID로 검색 범위를 제한하지 않는다는 뜻이다.
    document_ids: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    official_only: bool = True


@dataclass(frozen=True)
class DocumentChunk:
    """문서·데이터 담당이 검수하여 manifest에 넣는 청크 1개.

    RAG는 원문을 직접 수집하거나 청킹하지 않고, 이 형식으로 전달된 청크만
    색인한다. ``official_verified``가 False이면 공식 근거로 사용하지 않는다.
    """

    chunk_id: str
    document_id: str
    title: str
    section: str
    content: str
    source_url: str
    retrieved_at: str
    document_version: str | None
    license: str
    product_models: tuple[str, ...] = ()
    use_cases: tuple[str, ...] = ()
    os_versions: tuple[str, ...] = ()
    source_type: str = "documentation"
    official_verified: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DocumentChunk":
        """JSON의 목록 값을 불변 tuple로 정규화해 객체로 변환한다."""
        normalized = dict(value)
        # JSON array(list)와 코드 내부 tuple을 같은 방식으로 비교하기 위함이다.
        for key in ("product_models", "use_cases", "os_versions"):
            normalized[key] = tuple(normalized.get(key, ()))
        return cls(**normalized)


@dataclass(frozen=True)
class RagResult:
    """챗봇에 반환하는 검색 결과이자 출처 카드의 원본 데이터.

    URL·라이선스·수집일은 LLM이 새로 만들지 않고 이 객체의 값을 화면에
    표시해야 출처가 변조되거나 누락되는 것을 막을 수 있다.
    """

    rank: int
    content: str
    chunk_id: str
    document_id: str
    title: str
    section: str
    source_url: str
    license: str
    retrieved_at: str
    document_version: str | None

    @classmethod
    def from_chunk(cls, chunk: DocumentChunk, rank: int) -> "RagResult":
        """원본 청크에서 답변에 필요한 본문과 인용 metadata만 복사한다."""
        return cls(
            rank=rank,
            content=chunk.content,
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            title=chunk.title,
            section=chunk.section,
            source_url=chunk.source_url,
            license=chunk.license,
            retrieved_at=chunk.retrieved_at,
            document_version=chunk.document_version,
        )


@dataclass(frozen=True)
class RetrievalDecision:
    """검색 결과와 근거 충분 여부를 함께 표현한다.

    ``search()``의 기존 ``list[RagResult]`` 계약은 유지한다. 챗봇처럼 근거
    부족을 구분해야 하는 호출부는 ``search_with_decision()``의 이 객체를
    사용한다.
    """

    status: Literal["retrieved", "insufficient_evidence"]
    results: tuple[RagResult, ...]
    reason: str | None = None
