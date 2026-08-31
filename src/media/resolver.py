"""Resolve only media linked to citations that survived answer validation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from src.contracts import ChatCitation, MediaItem


class MediaManifestError(ValueError):
    """The media manifest is stale, malformed, or unsafe to serve."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Occurrence(_StrictModel):
    document_id: str = Field(min_length=1)
    section: str = Field(min_length=1)
    source_anchor: str | None


class _StoredMedia(_StrictModel):
    media_id: str = Field(pattern=r"^media-[0-9a-f]{20}$")
    media_type: Literal["image", "video"]
    title: str = Field(min_length=1)
    url: HttpUrl
    alt_text: str | None
    caption: str | None
    display_mode: Literal["inline", "external_embed"]
    license: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    official_verified: Literal[True]
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    occurrences: list[_Occurrence] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_display_mode(self) -> "_StoredMedia":
        if self.media_type == "image" and self.display_mode != "inline":
            raise ValueError("images must use inline display mode")
        if self.media_type == "video" and self.display_mode != "external_embed":
            raise ValueError("videos must use external_embed display mode")
        return self


class _ChunkLink(_StrictModel):
    chunk_id: str = Field(min_length=1)
    media_ids: list[str] = Field(min_length=1)


class _Statistics(_StrictModel):
    media_items: int = Field(ge=0)
    media_occurrences: int = Field(ge=0)
    linked_chunks: int = Field(ge=0)
    image_items: int = Field(ge=0)
    video_items: int = Field(ge=0)


class _MediaManifest(_StrictModel):
    schema_version: Literal["1.0.0"]
    generated_at: str = Field(min_length=1)
    document_manifest: str = Field(pattern=r"^document_pipeline/data/manifest(?:_v[0-9]+)?\.json$")
    document_manifest_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_registry: str = Field(pattern=r"^document_pipeline/data/source_registry(?:_v[0-9]+)?\.csv$")
    source_registry_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    linker_version: str = Field(min_length=1)
    statistics: _Statistics
    items: list[_StoredMedia]
    links: list[_ChunkLink]


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class MediaResolver:
    """Read a validated media manifest and map final citations to display items."""

    def __init__(
        self,
        manifest: _MediaManifest,
        *,
        max_images: int = 2,
        max_videos: int = 1,
    ) -> None:
        if not 0 <= max_images <= 20 or not 0 <= max_videos <= 10:
            raise MediaManifestError("media display limits are invalid")
        if max_images + max_videos == 0:
            raise MediaManifestError("at least one media display limit must be positive")
        self.max_images = max_images
        self.max_videos = max_videos
        self._items = {item.media_id: item for item in manifest.items}
        self._media_ids_by_chunk = {link.chunk_id: tuple(link.media_ids) for link in manifest.links}
        self._validate_internal_consistency(manifest)

    @staticmethod
    def _validate_internal_consistency(manifest: _MediaManifest) -> None:
        item_ids = [item.media_id for item in manifest.items]
        chunk_ids = [link.chunk_id for link in manifest.links]
        if len(item_ids) != len(set(item_ids)):
            raise MediaManifestError("media manifest contains duplicate media_id values")
        if len(chunk_ids) != len(set(chunk_ids)):
            raise MediaManifestError("media manifest contains duplicate chunk links")
        referenced = {media_id for link in manifest.links for media_id in link.media_ids}
        if referenced != set(item_ids):
            raise MediaManifestError("every media item must be linked and every link must reference an item")
        if any(len(link.media_ids) != len(set(link.media_ids)) for link in manifest.links):
            raise MediaManifestError("a chunk link contains duplicate media IDs")
        statistics = manifest.statistics
        expected = {
            "media_items": len(manifest.items),
            "media_occurrences": sum(len(item.occurrences) for item in manifest.items),
            "linked_chunks": len(manifest.links),
            "image_items": sum(item.media_type == "image" for item in manifest.items),
            "video_items": sum(item.media_type == "video" for item in manifest.items),
        }
        if statistics.model_dump() != expected:
            raise MediaManifestError("media manifest statistics do not match its contents")

    @classmethod
    def from_file(
        cls,
        media_manifest_path: str | Path,
        *,
        document_manifest_path: str | Path,
        max_images: int = 2,
        max_videos: int = 1,
    ) -> "MediaResolver":
        media_path = Path(media_manifest_path)
        document_path = Path(document_manifest_path)
        try:
            payload = json.loads(media_path.read_text(encoding="utf-8"))
            manifest = _MediaManifest.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise MediaManifestError(f"invalid media manifest: {media_path}: {exc}") from exc
        if manifest.document_manifest_checksum != _sha256(document_path.read_bytes()):
            raise MediaManifestError(
                "media manifest is stale for the selected document manifest; regenerate it before serving"
            )

        try:
            document_payload = json.loads(document_path.read_text(encoding="utf-8"))
            chunks = document_payload["chunks"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise MediaManifestError(f"invalid document manifest: {document_path}: {exc}") from exc
        chunk_metadata = {
            chunk["chunk_id"]: (chunk["document_id"], chunk["section"])
            for chunk in chunks
            if isinstance(chunk, dict)
            and all(isinstance(chunk.get(key), str) for key in ("chunk_id", "document_id", "section"))
        }
        if len(chunk_metadata) != len(chunks):
            raise MediaManifestError("document manifest contains malformed or duplicate chunk IDs")
        for link in manifest.links:
            metadata = chunk_metadata.get(link.chunk_id)
            if metadata is None:
                raise MediaManifestError(f"media link references an unknown chunk_id: {link.chunk_id}")
            for media_id in link.media_ids:
                item = next((candidate for candidate in manifest.items if candidate.media_id == media_id), None)
                if item is None:
                    raise MediaManifestError(f"media link references an unknown media_id: {media_id}")
                if metadata not in {(entry.document_id, entry.section) for entry in item.occurrences}:
                    raise MediaManifestError(
                        f"{link.chunk_id} and {media_id} do not share the same document and section"
                    )
        return cls(manifest, max_images=max_images, max_videos=max_videos)

    def resolve(self, citations: Sequence[ChatCitation]) -> list[MediaItem]:
        """Return de-duplicated media for the supplied final citation cards only."""

        resolved: list[MediaItem] = []
        seen: set[str] = set()
        counts = {"image": 0, "video": 0}
        for citation in citations:
            for media_id in self._media_ids_by_chunk.get(citation.chunk_id, ()):
                if media_id in seen:
                    continue
                stored = self._items[media_id]
                limit = self.max_images if stored.media_type == "image" else self.max_videos
                if counts[stored.media_type] >= limit:
                    continue
                resolved.append(
                    MediaItem(
                        media_id=stored.media_id,
                        media_type=stored.media_type,
                        title=stored.title,
                        url=stored.url,
                        alt_text=stored.alt_text,
                        display_mode=stored.display_mode,
                        license=stored.license,
                        attribution=stored.attribution,
                        source_citation_id=citation.citation_id,
                    )
                )
                seen.add(media_id)
                counts[stored.media_type] += 1
                if counts["image"] >= self.max_images and counts["video"] >= self.max_videos:
                    return resolved
        return resolved
