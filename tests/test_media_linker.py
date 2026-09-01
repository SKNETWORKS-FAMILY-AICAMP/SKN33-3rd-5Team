from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.media.linker import build_media_chunk_map


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_media_chunk_map_links_only_matching_sections(tmp_path: Path) -> None:
    image_path = tmp_path / "guide.png"
    image_path.write_bytes(b"verified-image")
    image_checksum = f"sha256:{hashlib.sha256(image_path.read_bytes()).hexdigest()}"

    document_manifest = tmp_path / "manifest.json"
    image_manifest = tmp_path / "images.json"
    video_manifest = tmp_path / "videos.json"
    output = tmp_path / "media_chunk_map.json"

    _write_json(
        document_manifest,
        {
            "chunks": [
                {
                    "document_id": "doc-1",
                    "chunk_id": "doc-1-000",
                    "source_url": "https://example.com/guide.html#install",
                    "section": "Setup > Install using Imager",
                },
                {
                    "document_id": "doc-1",
                    "chunk_id": "doc-1-001",
                    "source_url": "https://example.com/guide.html",
                    "section": "Setup > Troubleshooting",
                },
            ]
        },
    )
    _write_json(
        image_manifest,
        {
            "items": [
                {
                    "media_id": "image-1",
                    "media_type": "image",
                    "category": "guide",
                    "relative_path": "guide.png",
                    "checksum": image_checksum,
                    "source_document_url": "https://example.com/guide.html",
                    "source_section": "Install using Imager",
                },
                {
                    "media_id": "image-2",
                    "media_type": "image",
                    "category": "product",
                },
            ]
        },
    )
    _write_json(
        video_manifest,
        {
            "items": [
                {
                    "media_id": "video-1",
                    "media_type": "video",
                    "category": "guide",
                    "official_verified": True,
                    "embed_allowed": True,
                    "embed_url": "https://www.youtube.com/embed/example",
                    "source_document_url": "https://example.com/guide.html",
                    "source_section": "Missing section",
                }
            ]
        },
    )

    result = build_media_chunk_map(
        document_manifest_path=document_manifest,
        image_manifest_path=image_manifest,
        video_manifest_path=video_manifest,
        output_path=output,
        repository_root=tmp_path,
    )

    assert result["summary"] == {"guide_media_total": 2, "linked_media": 1, "unmatched_media": 1}
    assert result["links"][0]["chunk_ids"] == ["doc-1-000"]
    assert result["unmatched"][0]["reason"] == "section_not_in_collected_document"
    assert output.is_file()


def test_video_review_keeps_only_directly_demonstrated_chunks(tmp_path: Path) -> None:
    document_manifest = tmp_path / "manifest.json"
    image_manifest = tmp_path / "images.json"
    video_manifest = tmp_path / "videos.json"
    video_review = tmp_path / "video_chunk_audit_v1.json"
    output = tmp_path / "media_chunk_map.json"

    _write_json(
        document_manifest,
        {
            "chunks": [
                {
                    "document_id": "doc-setup",
                    "chunk_id": "doc-setup-000",
                    "source_url": "https://example.com/guide.html",
                    "section": "Setup > Step 1. Attach hardware",
                },
                {
                    "document_id": "doc-setup",
                    "chunk_id": "doc-setup-001",
                    "source_url": "https://example.com/guide.html",
                    "section": "Setup > Step 2. Configure software",
                },
            ]
        },
    )
    _write_json(image_manifest, {"items": []})
    _write_json(
        video_manifest,
        {
            "items": [
                {
                    "media_id": "video-setup",
                    "media_type": "video",
                    "category": "guide",
                    "official_verified": True,
                    "embed_allowed": True,
                    "embed_url": "https://www.youtube.com/embed/example",
                    "source_document_url": "https://example.com/guide.html",
                    "source_section": "Setup",
                }
            ]
        },
    )
    _write_json(
        video_review,
        {
            "video_reviews": [
                {
                    "media_id": "video-setup",
                    "direct_chunk_ids": ["doc-setup-000"],
                }
            ]
        },
    )

    result = build_media_chunk_map(
        document_manifest_path=document_manifest,
        image_manifest_path=image_manifest,
        video_manifest_path=video_manifest,
        video_review_path=video_review,
        output_path=output,
        repository_root=tmp_path,
    )

    assert result["summary"] == {"guide_media_total": 1, "linked_media": 1, "unmatched_media": 0}
    assert result["links"] == [
        {
            "media_id": "video-setup",
            "media_type": "video",
            "document_ids": ["doc-setup"],
            "chunk_ids": ["doc-setup-000"],
        }
    ]


def test_canonical_video_audit_and_media_questions_stay_direct_only() -> None:
    root = Path(__file__).resolve().parents[1]
    audit = json.loads((root / "assets" / "media" / "video_chunk_audit_v1.json").read_text(encoding="utf-8"))
    reviews = audit["video_reviews"]
    direct_by_media = {item["media_id"]: set(item["direct_chunk_ids"]) for item in reviews}

    assert sum(len(item["links"]) for item in reviews) == 46
    assert {item["media_id"] for item in reviews} == {
        "rpi-video-0001", "rpi-video-0002", "rpi-video-0003", "rpi-video-0004"
    }
    assert sum(len(chunk_ids) for chunk_ids in direct_by_media.values()) == 8

    questions = [
        json.loads(line)
        for line in (root / "eval" / "media_questions_v1.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(questions) == 8
    assert {question["expected_media_ids"][0] for question in questions} == set(direct_by_media)
    for question in questions:
        media_id = question["expected_media_ids"][0]
        assert question["media_required"] is True
        assert set(question["expected_chunk_ids"]).intersection(direct_by_media[media_id])
