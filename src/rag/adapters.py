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
    "document_version",
    "license",
    "product_models",
    "use_cases",
    "os_versions",
    "official_verified",
}


def manifest_chunk_to_document_chunk(value: dict[str, Any]) -> DocumentChunk:
    """Convert one full manifest chunk without weakening the manifest contract.

    ``retrieved_at`` exists only in the legacy RAG prototype. Its value is the
    manifest's collection date; it is not the query execution time.
    """
    missing = RAG_INPUT_FIELDS - set(value)
    if missing:
        raise ValueError(f"manifest chunk is missing RAG adapter fields: {sorted(missing)}")
    # Canonical manifests use ``collected_at``.  Keep old, already-created
    # prototype manifests readable while the corpus is being migrated.
    retrieved_at = value.get("collected_at") or value.get("retrieved_at")
    if not retrieved_at:
        raise ValueError("manifest chunk must contain collected_at or retrieved_at")
    return DocumentChunk(
        chunk_id=value["chunk_id"],
        document_id=value["document_id"],
        title=value["title"],
        section=value["section"],
        content=value["content"],
        source_url=value["source_url"],
        retrieved_at=retrieved_at,
        document_version=value["document_version"],
        license=value["license"],
        product_models=tuple(value["product_models"]),
        use_cases=tuple(value["use_cases"]),
        os_versions=tuple(value["os_versions"]),
        source_type=value.get("source_type", "documentation"),
        official_verified=value["official_verified"],
    )


def manifest_to_document_chunks(payload: dict[str, Any]) -> list[DocumentChunk]:
    """Convert the manifest's static chunks for existing RAG code paths."""
    chunks = payload.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("manifest must contain a chunks array")
    return [manifest_chunk_to_document_chunk(value) for value in chunks]
