"""Adapters between the canonical document manifest and the legacy RAG prototype."""
from __future__ import annotations

from typing import Any

from .models import DocumentChunk


RAG_INPUT_FIELDS = {
    "chunk_id",
    "document_id",
    "title",
    "section",
    "content",
    "source_url",
    "source_anchor",
    "collected_at",
    "document_version",
    "license",
    "product_models",
    "use_cases",
    "os_versions",
    "official_verified",
    "quality_status",
    "embedding_checksum",
}


def manifest_chunk_to_document_chunk(value: dict[str, Any]) -> DocumentChunk:
    """Convert one full manifest chunk without weakening the manifest contract.

    ``retrieved_at`` exists only in the legacy RAG prototype. Its value is the
    canonical manifest 1.1의 ``collected_at``이며 query 실행 시각이 아니다.
    """
    missing = RAG_INPUT_FIELDS - set(value)
    if missing:
        raise ValueError(f"manifest chunk is missing RAG adapter fields: {sorted(missing)}")
    retrieved_at = value.get("collected_at")
    if not retrieved_at:
        raise ValueError("manifest 1.1 chunk must contain collected_at")
    return DocumentChunk(
        chunk_id=value["chunk_id"],
        document_id=value["document_id"],
        title=value["title"],
        section=value["section"],
        content=value["content"],
        source_url=value["source_url"],
        source_anchor=value["source_anchor"],
        retrieved_at=retrieved_at,
        document_version=value["document_version"],
        license=value["license"],
        product_models=tuple(value["product_models"]),
        use_cases=tuple(value["use_cases"]),
        os_versions=tuple(value["os_versions"]),
        source_type=value.get("source_type", "documentation"),
        official_verified=value["official_verified"],
        quality_status=value["quality_status"],
        embedding_checksum=value["embedding_checksum"],
    )


def manifest_to_document_chunks(payload: dict[str, Any]) -> list[DocumentChunk]:
    """Convert a canonical manifest 1.1 for existing RAG code paths."""

    if payload.get("schema_version") != "1.1.0":
        raise ValueError("RAG only supports canonical manifest schema_version 1.1.0")
    if not isinstance(payload.get("processing"), dict):
        raise ValueError("manifest 1.1 must contain processing metadata")
    chunks = payload.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("manifest must contain a chunks array")
    return [manifest_chunk_to_document_chunk(value) for value in chunks]
