"""제품 catalog가 현재 RAG manifest의 공식 근거만 참조하는지 검증한다."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any

from .schema import ProductCatalog


class CatalogManifestValidationError(ValueError):
    """catalog과 manifest의 문서 출처가 불일치할 때 발생한다."""


def load_manifest(path: str | Path) -> dict[str, Any]:
    """canonical manifest JSON을 읽고 최소 구조를 확인한다."""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogManifestValidationError(f"manifest를 읽을 수 없습니다: {path}") from exc
    if not isinstance(payload.get("chunks"), list) or not payload["chunks"]:
        raise CatalogManifestValidationError("manifest에는 비어 있지 않은 chunks 목록이 필요합니다.")
    return payload


def manifest_documents(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """반복된 청크 metadata를 document_id별 공식 출처 하나로 정규화한다."""

    documents: dict[str, dict[str, Any]] = {}
    for chunk in payload["chunks"]:
        document_id = chunk.get("document_id")
        if not isinstance(document_id, str) or not document_id:
            raise CatalogManifestValidationError("manifest chunk의 document_id가 없습니다.")
        source = {
            "title": chunk.get("title"),
            "source_url": chunk.get("source_url"),
            "collected_at": chunk.get("collected_at"),
            "license": chunk.get("license"),
            "official_verified": chunk.get("official_verified"),
        }
        existing = documents.setdefault(document_id, source)
        if existing != source:
            raise CatalogManifestValidationError(
                f"manifest의 {document_id} 문서 metadata가 청크마다 일치하지 않습니다."
            )
    return documents


def validate_catalog_manifest_alignment(
    catalog: ProductCatalog, manifest: dict[str, Any]
) -> None:
    """catalog source와 field evidence가 manifest의 공식 문서에 존재하는지 확인한다."""

    documents = manifest_documents(manifest)
    catalog_sources = {source.document_id: source for source in catalog.sources}

    for document_id, source in catalog_sources.items():
        metadata = documents.get(document_id)
        if metadata is None:
            raise CatalogManifestValidationError(
                f"catalog source가 현재 manifest에 없습니다: {document_id}"
            )
        if metadata["official_verified"] is not True:
            raise CatalogManifestValidationError(
                f"catalog source는 공식 검증 문서여야 합니다: {document_id}"
            )
        if (
            metadata["title"] != source.title
            or str(metadata["source_url"]) != str(source.source_url)
            or metadata["license"] != source.license
        ):
            raise CatalogManifestValidationError(
                f"catalog source metadata가 manifest와 다릅니다: {document_id}"
            )
        try:
            manifest_collected_at = date.fromisoformat(str(metadata["collected_at"]))
        except ValueError as exc:
            raise CatalogManifestValidationError(
                f"manifest collected_at 형식이 잘못되었습니다: {document_id}"
            ) from exc
        if source.retrieved_at > manifest_collected_at:
            raise CatalogManifestValidationError(
                f"catalog source 수집일이 manifest보다 미래입니다: {document_id}"
            )

    for product in catalog.products:
        missing = set(product.document_ids) - set(catalog_sources)
        if missing:
            raise CatalogManifestValidationError(
                f"{product.product_id}의 field evidence가 catalog sources에 없습니다: {sorted(missing)}"
            )


def load_and_validate_catalog(
    *, catalog_path: str | Path, manifest_path: str | Path
) -> tuple[ProductCatalog, dict[str, Any]]:
    """런타임에 catalog와 manifest를 함께 읽고 정합성을 보장한다."""

    catalog = ProductCatalog.from_received_file(catalog_path)
    manifest = load_manifest(manifest_path)
    validate_catalog_manifest_alignment(catalog, manifest)
    return catalog, manifest


__all__ = [
    "CatalogManifestValidationError",
    "load_and_validate_catalog",
    "load_manifest",
    "manifest_documents",
    "validate_catalog_manifest_alignment",
]
