"""Resolve only media linked to citations that survived answer validation."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

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


@dataclass(frozen=True)
class _CuratedMedia:
    """Reviewed asset-registry media merged through ``media_chunk_map``."""

    media_id: str
    media_type: Literal["image", "video"]
    title: str
    url: str
    alt_text: str | None
    display_mode: Literal["inline", "external_embed"]
    license: str
    attribution: str


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
        manifest: _MediaManifest | None = None,
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
        self._items: dict[str, _StoredMedia | _CuratedMedia] = {}
        self._media_ids_by_chunk: dict[str, tuple[str, ...]] = {}
        if manifest is not None:
            self._items = {item.media_id: item for item in manifest.items}
            self._media_ids_by_chunk = {
                link.chunk_id: tuple(link.media_ids) for link in manifest.links
            }
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

    @classmethod
    def from_paths(
        cls,
        *,
        document_manifest_path: str | Path,
        media_manifest_path: str | Path | None,
        media_chunk_map_path: str | Path | None,
        image_manifest_path: str | Path | None,
        video_manifest_path: str | Path | None,
        max_images: int = 2,
        max_videos: int = 1,
    ) -> "MediaResolver | None":
        """Build one citation-media resolver from all configured v3 artifacts.

        The generated document media manifest is authoritative for media parsed
        directly from the corpus.  The reviewed asset image/video registries
        are added through ``media_chunk_map``.  Both routes are resolved only
        after the final answer citations are known.
        """

        document_path = Path(document_manifest_path)
        resolver = (
            cls.from_file(
                media_manifest_path,
                document_manifest_path=document_path,
                max_images=max_images,
                max_videos=max_videos,
            )
            if media_manifest_path is not None
            else cls(max_images=max_images, max_videos=max_videos)
        )

        if media_chunk_map_path is not None and Path(media_chunk_map_path).is_file():
            if image_manifest_path is None or video_manifest_path is None:
                raise MediaManifestError(
                    "media_chunk_map requires both reviewed image and video manifests"
                )
            resolver._merge_curated_chunk_map(
                document_manifest_path=document_path,
                media_chunk_map_path=Path(media_chunk_map_path),
                image_manifest_path=Path(image_manifest_path),
                video_manifest_path=Path(video_manifest_path),
            )
        return resolver if resolver._items else None

    @staticmethod
    def _read_object(path: Path, *, label: str) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MediaManifestError(f"invalid {label}: {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise MediaManifestError(f"invalid {label}: JSON root must be an object")
        return payload

    @staticmethod
    def _require_checksum(payload: dict[str, Any], key: str, path: Path, *, label: str) -> None:
        expected = payload.get(key)
        try:
            actual = _sha256(path.read_bytes())
        except OSError as exc:
            raise MediaManifestError(f"{label} cannot read {path}: {exc}") from exc
        if expected != actual:
            raise MediaManifestError(f"{label} checksum does not match {path}")

    @staticmethod
    def _curated_record(
        item: dict[str, Any],
        *,
        image_payload: dict[str, Any],
        video_payload: dict[str, Any],
    ) -> _CuratedMedia:
        media_id = item.get("media_id")
        media_type = item.get("media_type")
        title = item.get("title")
        if (
            not isinstance(media_id, str)
            or not re.fullmatch(r"rpi-(?:product|guide|video)-[0-9]{4}", media_id)
            or media_type not in {"image", "video"}
            or not isinstance(title, str)
            or not title.strip()
            or item.get("category") != "guide"
        ):
            raise MediaManifestError("reviewed media registry item is malformed")

        if media_type == "image":
            url = item.get("source_asset_url")
            alt_text = item.get("alt_text_ko")
            license_value = image_payload.get("license")
            attribution = image_payload.get("attribution")
            if not all(isinstance(value, str) and value.strip() for value in (url, license_value, attribution)):
                raise MediaManifestError(f"reviewed image metadata is incomplete: {media_id}")
            return _CuratedMedia(
                media_id=media_id,
                media_type="image",
                title=title,
                url=url,
                alt_text=alt_text if isinstance(alt_text, str) and alt_text.strip() else title,
                display_mode="inline",
                license=license_value,
                attribution=attribution,
            )

        if item.get("official_verified") is not True or item.get("embed_allowed") is not True:
            raise MediaManifestError(f"video is not approved for official embedding: {media_id}")
        url = item.get("embed_url")
        channel_name = item.get("channel_name") or video_payload.get("source_channel_name")
        channel_url = item.get("channel_url") or video_payload.get("source_channel_url")
        if (
            not isinstance(url, str)
            or not url.startswith("https://www.youtube.com/embed/")
            or not isinstance(channel_name, str)
            or not isinstance(channel_url, str)
        ):
            raise MediaManifestError(f"reviewed video metadata is incomplete: {media_id}")
        return _CuratedMedia(
            media_id=media_id,
            media_type="video",
            title=title,
            url=url,
            alt_text=title,
            display_mode="external_embed",
            license="YouTube Terms of Service",
            attribution=f"{channel_name} official channel: {channel_url}",
        )

    def _merge_curated_chunk_map(
        self,
        *,
        document_manifest_path: Path,
        media_chunk_map_path: Path,
        image_manifest_path: Path,
        video_manifest_path: Path,
    ) -> None:
        """Merge reviewed assets by their validated cited chunk IDs."""

        mapping = self._read_object(media_chunk_map_path, label="media chunk map")
        image_payload = self._read_object(image_manifest_path, label="reviewed image manifest")
        video_payload = self._read_object(video_manifest_path, label="reviewed video manifest")
        self._require_checksum(
            mapping,
            "document_manifest_checksum",
            document_manifest_path,
            label="media chunk map document manifest",
        )
        self._require_checksum(
            mapping,
            "image_manifest_checksum",
            image_manifest_path,
            label="media chunk map image manifest",
        )
        self._require_checksum(
            mapping,
            "video_manifest_checksum",
            video_manifest_path,
            label="media chunk map video manifest",
        )

        document_payload = self._read_object(document_manifest_path, label="document manifest")
        chunks = document_payload.get("chunks")
        if not isinstance(chunks, list):
            raise MediaManifestError("document manifest must contain chunks")
        known_chunk_ids = {
            chunk.get("chunk_id")
            for chunk in chunks
            if isinstance(chunk, dict) and isinstance(chunk.get("chunk_id"), str)
        }
        if len(known_chunk_ids) != len(chunks):
            raise MediaManifestError("document manifest contains malformed or duplicate chunk IDs")

        def indexed_items(payload: dict[str, Any], *, label: str) -> dict[str, dict[str, Any]]:
            raw_items = payload.get("items")
            if not isinstance(raw_items, list):
                raise MediaManifestError(f"{label} must contain an items array")
            items = {
                item.get("media_id"): item
                for item in raw_items
                if isinstance(item, dict) and isinstance(item.get("media_id"), str)
            }
            if len(items) != len(raw_items):
                raise MediaManifestError(f"{label} has malformed or duplicate media IDs")
            return items

        image_items = indexed_items(image_payload, label="reviewed image manifest")
        video_items = indexed_items(video_payload, label="reviewed video manifest")
        if image_items.keys() & video_items.keys():
            raise MediaManifestError("reviewed image and video manifests reuse a media ID")
        reviewed_items = {**image_items, **video_items}
        links = mapping.get("links")
        if not isinstance(links, list):
            raise MediaManifestError("media chunk map must contain a links array")

        curated_ids_by_chunk: dict[str, list[str]] = {}
        for link in links:
            if not isinstance(link, dict):
                raise MediaManifestError("media chunk map link is malformed")
            media_id = link.get("media_id")
            chunk_ids = link.get("chunk_ids")
            item = reviewed_items.get(media_id)
            if item is None or not isinstance(chunk_ids, list) or not chunk_ids:
                raise MediaManifestError("media chunk map references an unknown item or no chunks")
            record = self._curated_record(
                item,
                image_payload=image_payload,
                video_payload=video_payload,
            )
            if link.get("media_type") != record.media_type:
                raise MediaManifestError(f"media type mismatch in media chunk map: {media_id}")
            existing = self._items.get(media_id)
            if existing is not None and existing != record:
                raise MediaManifestError(f"conflicting media metadata: {media_id}")
            self._items[media_id] = record
            for chunk_id in chunk_ids:
                if not isinstance(chunk_id, str) or chunk_id not in known_chunk_ids:
                    raise MediaManifestError(f"media chunk map references an unknown chunk_id: {chunk_id}")
                candidates = curated_ids_by_chunk.setdefault(chunk_id, [])
                if media_id not in candidates:
                    candidates.append(media_id)

        # Curated guide assets carry user-facing Korean titles and verified video
        # embed policy, so prefer them over duplicate corpus-parsed media.
        for chunk_id, curated_ids in curated_ids_by_chunk.items():
            existing_ids = self._media_ids_by_chunk.get(chunk_id, ())
            self._media_ids_by_chunk[chunk_id] = tuple(
                dict.fromkeys([*curated_ids, *existing_ids])
            )

    def resolve(self, citations: Sequence[ChatCitation]) -> list[MediaItem]:
        """Return de-duplicated media for the supplied final citation cards only."""

        resolved: list[MediaItem] = []
        seen: set[str] = set()
        seen_urls: set[str] = set()
        counts = {"image": 0, "video": 0}
        for citation in citations:
            for media_id in self._media_ids_by_chunk.get(citation.chunk_id, ()):
                if media_id in seen:
                    continue
                stored = self._items[media_id]
                media_url = str(stored.url)
                if media_url in seen_urls:
                    continue
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
                seen_urls.add(media_url)
                counts[stored.media_type] += 1
                if counts["image"] >= self.max_images and counts["video"] >= self.max_videos:
                    return resolved
        return resolved
