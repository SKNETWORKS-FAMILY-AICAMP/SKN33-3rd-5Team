"""생성된 청크 연결표와 공식 미디어 manifest의 서비스 연결을 검증한다."""

import json

from src.services.media_lookup import load_media_by_chunk_id


def test_missing_generated_map_keeps_qa_available(tmp_path):
    assert load_media_by_chunk_id(tmp_path) == {}


def test_media_map_resolves_manifest_urls_and_ignores_unknown_assets(tmp_path):
    payloads = {
        "map.json": {"links": [
            {"media_id": "image-1", "chunk_ids": ["chunk-1", "chunk-2"]},
            {"media_id": "video-1", "chunk_ids": ["chunk-1"]},
            {"media_id": "unknown", "chunk_ids": ["chunk-3"]},
        ]},
        "images.json": {"items": [{
            "media_id": "image-1", "media_type": "image", "title": "공식 설정 이미지",
            "source_asset_url": "https://www.raspberrypi.com/setup.png",
        }]},
        "videos.json": {"items": [{
            "media_id": "video-1", "media_type": "video", "title": "공식 설치 영상",
            "embed_url": "https://www.youtube.com/embed/example",
        }]},
    }
    for name, payload in payloads.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    mapping = load_media_by_chunk_id(
        tmp_path, media_chunk_map_path="map.json",
        image_manifest_path="images.json", video_manifest_path="videos.json",
    )
    assert set(mapping) == {"chunk-1", "chunk-2"}
    assert [item["media_type"] for item in mapping["chunk-1"]] == ["image", "video"]
    assert mapping["chunk-2"] == [{
        "media_type": "image", "title": "공식 설정 이미지", "url": "https://www.raspberrypi.com/setup.png",
    }]
