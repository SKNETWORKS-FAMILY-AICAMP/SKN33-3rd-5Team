"""RAG 결과 chunk_id에 연결된 공식 이미지·영상을 조회하는 조회 테이블을 만든다.

`src.media.linker`가 만든 `media_chunk_map.json`(chunk_id ↔ media_id)과 원본
이미지·영상 manifest(media_id ↔ 제목·URL)를 합쳐, 검색 결과가 실제 인용으로
쓰일 때 함께 표시할 media 후보를 chunk_id 기준으로 미리 인덱싱한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, TypedDict


class MediaCandidate(TypedDict):
    """`ChatCitation`에 연결하기 전, chunk_id로 조회한 원시 media 정보다."""

    media_type: str
    title: str
    url: str


DEFAULT_MEDIA_CHUNK_MAP_PATH = "document_pipeline/data/media_chunk_map.json"
DEFAULT_IMAGE_MANIFEST_PATH = "assets/media/manifest.json"
DEFAULT_VIDEO_MANIFEST_PATH = "assets/media/video_manifest.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _media_url(item: dict) -> str | None:
    """이미지는 원본 commit의 raw URL, 영상은 공식 YouTube embed URL을 쓴다."""

    if item.get("media_type") == "image":
        return item.get("source_asset_url")
    if item.get("media_type") == "video":
        return item.get("embed_url")
    return None


def load_media_by_chunk_id(
    project_root: Path,
    *,
    media_chunk_map_path: str = DEFAULT_MEDIA_CHUNK_MAP_PATH,
    image_manifest_path: str = DEFAULT_IMAGE_MANIFEST_PATH,
    video_manifest_path: str = DEFAULT_VIDEO_MANIFEST_PATH,
) -> Mapping[str, list[MediaCandidate]]:
    """chunk_id별 media 후보 목록을 만든다. 산출물이 없으면 빈 매핑을 반환한다.

    `media_chunk_map.json`은 재생성 가능한 산출물이라 Git에 커밋되지 않는다.
    아직 생성하지 않은 환경(신규 clone 등)에서도 QA가 오류 없이 동작하도록,
    파일이 없으면 media 없이 답변만 표시한다.
    """

    chunk_map_file = project_root / media_chunk_map_path
    if not chunk_map_file.is_file():
        return {}

    chunk_map = _read_json(chunk_map_file)
    image_payload = _read_json(project_root / image_manifest_path)
    video_payload = _read_json(project_root / video_manifest_path)
    items_by_id = {
        item["media_id"]: item
        for item in [*image_payload.get("items", []), *video_payload.get("items", [])]
    }

    by_chunk: dict[str, list[MediaCandidate]] = {}
    for link in chunk_map.get("links", []):
        item = items_by_id.get(link.get("media_id"))
        if item is None:
            continue
        url = _media_url(item)
        if not url:
            continue
        candidate: MediaCandidate = {
            "media_type": item["media_type"],
            "title": item["title"],
            "url": url,
        }
        for chunk_id in link.get("chunk_ids", []):
            by_chunk.setdefault(chunk_id, []).append(candidate)
    return by_chunk


__all__ = ["MediaCandidate", "load_media_by_chunk_id"]
