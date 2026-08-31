"""Chroma가 지원하는 scalar metadata로 RAG 조건 필터를 표현한다."""
from __future__ import annotations

import hashlib
import re
from typing import Any

from .models import DocumentChunk, RagFilters


def tag_flag_key(group: str, value: str) -> str:
    """제품명·목적 같은 다중 tag를 Chroma scalar boolean key로 바꾼다."""
    normalized = value.strip().casefold()
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    # 한글처럼 ASCII slug를 만들 수 없는 tag도 안정적으로 검색할 수 있게 한다.
    if not slug:
        slug = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"filter_{group}_{slug}"


def _add_tag_flags(metadata: dict[str, Any], group: str, values: tuple[str, ...]) -> None:
    metadata[f"filter_all_{group}"] = not values
    for value in values:
        metadata[tag_flag_key(group, value)] = True


def chunk_to_chroma_metadata(chunk: DocumentChunk) -> dict[str, Any]:
    """문서 청크를 Chroma에 저장할 scalar metadata로 변환한다."""
    metadata: dict[str, Any] = {
        "document_id": chunk.document_id,
        "official_verified": chunk.official_verified,
        "quality_status": chunk.quality_status,
        "source_type": chunk.source_type,
    }
    _add_tag_flags(metadata, "product_models", chunk.product_models)
    _add_tag_flags(metadata, "use_cases", chunk.use_cases)
    _add_tag_flags(metadata, "os_versions", chunk.os_versions)
    return metadata


def _or_conditions(conditions: list[dict[str, Any]]) -> dict[str, Any]:
    if len(conditions) == 1:
        return conditions[0]
    return {"$or": conditions}


def _tag_filter(group: str, values: tuple[str, ...]) -> dict[str, Any] | None:
    """tag가 없는 일반 문서도 통과시키는 Chroma 조건을 만든다."""
    if not values:
        return None
    conditions = [{f"filter_all_{group}": True}]
    conditions.extend({tag_flag_key(group, value): True} for value in values)
    return _or_conditions(conditions)


def chroma_where(filters: RagFilters) -> dict[str, Any] | None:
    """RagFilters를 Chroma ``where`` 형식으로 변환한다.

    다중 제품·목적·OS 조건은 각각 '일반 적용 문서 또는 요청 tag 중 하나'로
    처리한다. 최종 반환 전에는 retriever의 로컬 metadata 검사를 한 번 더 한다.
    """
    conditions: list[dict[str, Any]] = []
    if filters.official_only:
        conditions.append({"official_verified": True})
        conditions.append({"quality_status": "approved"})
    if filters.source_types:
        if len(filters.source_types) == 1:
            conditions.append({"source_type": filters.source_types[0]})
        else:
            conditions.append({"source_type": {"$in": list(filters.source_types)}})
    if filters.document_ids:
        if len(filters.document_ids) == 1:
            conditions.append({"document_id": filters.document_ids[0]})
        else:
            conditions.append({"document_id": {"$in": list(filters.document_ids)}})
    for group, values in (
        ("product_models", filters.product_models),
        ("use_cases", filters.use_cases),
        ("os_versions", filters.os_versions),
    ):
        condition = _tag_filter(group, values)
        if condition is not None:
            conditions.append(condition)

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}
