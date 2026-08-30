"""Chroma 색인과 manifest가 같은 입력에서 만들어졌는지 확인하는 sidecar다."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path


INDEX_METADATA_FILENAME = "picare-index.json"


class IndexMetadataError(ValueError):
    """색인 sidecar가 없거나 현재 manifest와 맞지 않을 때 발생한다."""


def manifest_checksum(path: str | Path) -> str:
    """색인 입력 manifest의 파일 단위 SHA-256을 계산한다."""

    payload = Path(path).read_bytes()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def metadata_path(chroma_path: str | Path) -> Path:
    """Chroma persistent directory 안의 sidecar 위치를 반환한다."""

    return Path(chroma_path) / INDEX_METADATA_FILENAME


def write_index_metadata(
    *,
    chroma_path: str | Path,
    collection_name: str,
    embedding_model_name: str,
    manifest_path: str | Path,
    indexed_chunk_count: int,
) -> Path:
    """성공한 색인의 입력·시각 정보를 원자적으로 기록한다."""

    destination = metadata_path(chroma_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0.0",
        "collection_name": collection_name,
        "embedding_model_name": embedding_model_name,
        "manifest_checksum": manifest_checksum(manifest_path),
        "indexed_at": datetime.now(UTC).isoformat(),
        "indexed_chunk_count": indexed_chunk_count,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def load_indexed_at(
    *, chroma_path: str | Path, collection_name: str, manifest_path: str | Path
) -> datetime:
    """현재 manifest와 일치하는 Chroma 색인의 실제 생성 시각을 읽는다."""

    path = metadata_path(chroma_path)
    if not path.is_file():
        raise IndexMetadataError(
            "Chroma 색인 metadata가 없습니다. "
            "`python3 -m src.services.rag_qa_cli --action index --reset`으로 재색인하세요."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        indexed_at = datetime.fromisoformat(payload["indexed_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise IndexMetadataError(f"Chroma 색인 metadata 형식이 잘못되었습니다: {path}") from exc
    if payload.get("collection_name") != collection_name:
        raise IndexMetadataError("현재 CHROMA_COLLECTION_NAME과 색인 metadata가 다릅니다.")
    if payload.get("manifest_checksum") != manifest_checksum(manifest_path):
        raise IndexMetadataError(
            "현재 DOCUMENT_MANIFEST가 Chroma 색인 입력과 다릅니다. 재색인하세요."
        )
    return indexed_at


__all__ = [
    "INDEX_METADATA_FILENAME",
    "IndexMetadataError",
    "load_indexed_at",
    "manifest_checksum",
    "metadata_path",
    "write_index_metadata",
]
