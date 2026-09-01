from __future__ import annotations

import csv
import hashlib
import json
from datetime import date

import pytest

from document_pipeline.ingestion import build_media_manifest as media_builder
from src.contracts import ChatCitation
from src.media import MediaManifestError, MediaResolver


def checksum(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def write_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(media_builder, "REPOSITORY_ROOT", tmp_path)
    data_root = tmp_path / "document_pipeline" / "data"
    raw_root = data_root / "raw_v3"
    raw_root.mkdir(parents=True)
    registry_path = data_root / "source_registry_v3.csv"
    fieldnames = [
        "source_id", "title", "official_page_url", "collection_url", "source_format",
        "publisher", "language", "license_id", "source_type", "official_verified",
        "product_models", "use_cases", "tasks", "categories", "collection_decision",
        "collection_method",
    ]
    with registry_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "source_id": "doc-setup",
                "title": "Setup guide",
                "official_page_url": "https://www.raspberrypi.com/documentation/computers/getting-started.html",
                "collection_url": "https://raw.githubusercontent.com/raspberrypi/documentation/master/documentation/asciidoc/computers/getting-started/setup.adoc",
                "source_format": "asciidoc",
                "publisher": "Raspberry Pi Ltd",
                "language": "en",
                "license_id": "CC-BY-SA-4.0",
                "source_type": "documentation",
                "official_verified": "true",
                "product_models": "",
                "use_cases": "education_coding",
                "tasks": "os_installation",
                "categories": "getting_started",
                "collection_decision": "include",
                "collection_method": "git_raw",
            }
        )

    commit = "a" * 40
    raw = b'''[[setup]]\n== Setup\n\nInstall the operating system first.\n\nimage::images/setup.png[Imager setup]\n\nvideo::CQtliTJ41ZE[youtube,title="Setup video"]\n'''
    raw_path = raw_root / "doc-setup.adoc"
    raw_path.write_bytes(raw)
    collection_url = (
        "https://raw.githubusercontent.com/raspberrypi/documentation/"
        f"{commit}/documentation/asciidoc/computers/getting-started/setup.adoc"
    )
    ledger = {
        "schema_version": "1.0.0",
        "repository": "https://github.com/raspberrypi/documentation.git",
        "commit": commit,
        "collected_at": "2026-08-31",
        "source_registry": "document_pipeline/data/source_registry_v3.csv",
        "documents": [
            {
                "source_id": "doc-setup",
                "path": raw_path.name,
                "collection_url": collection_url,
                "document_checksum": checksum(raw),
            }
        ],
    }
    (raw_root / "collection.json").write_text(json.dumps(ledger), encoding="utf-8")

    manifest_path = data_root / "manifest_v3.json"
    manifest = {
        "schema_version": "1.1.0",
        "source_registry": "document_pipeline/data/source_registry_v3.csv",
        "processing": {"source_registry_checksum": checksum(registry_path.read_bytes())},
        "chunks": [
            {
                "chunk_id": "doc-setup-000",
                "document_id": "doc-setup",
                "section": "Setup",
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    media_path = data_root / "media_manifest_v3.json"
    return registry_path, raw_root, manifest_path, media_path


def citation(chunk_id: str = "doc-setup-000") -> ChatCitation:
    return ChatCitation(
        citation_id="C1",
        document_id="doc-setup",
        chunk_id=chunk_id,
        title="Setup guide",
        publisher="Raspberry Pi Ltd",
        section="Setup",
        source_url="https://www.raspberrypi.com/documentation/computers/getting-started.html",
        source_anchor="setup",
        document_version="a" * 40,
        published_at=None,
        updated_at=None,
        collected_at=date(2026, 8, 31),
        license="CC-BY-SA-4.0",
        quote="Install the operating system first.",
    )


def test_builder_links_media_to_chunks_without_media_chunks(tmp_path, monkeypatch) -> None:
    registry, raw_root, manifest, output = write_fixture(tmp_path, monkeypatch)
    payload = media_builder.build_media_manifest(
        document_manifest_path=manifest,
        raw_root=raw_root,
        registry_path=registry,
        output_path=output,
    )

    assert payload["statistics"] == {
        "media_items": 2,
        "media_occurrences": 2,
        "linked_chunks": 1,
        "image_items": 1,
        "video_items": 1,
    }
    assert payload["links"][0]["chunk_id"] == "doc-setup-000"
    assert len(payload["links"][0]["media_ids"]) == 2
    assert payload["items"][0]["url"].endswith("/images/setup.png")
    assert payload["items"][1]["url"] == "https://www.youtube.com/watch?v=CQtliTJ41ZE"


def test_resolver_returns_only_media_for_final_citations(tmp_path, monkeypatch) -> None:
    registry, raw_root, manifest, output = write_fixture(tmp_path, monkeypatch)
    media_builder.build_media_manifest(
        document_manifest_path=manifest,
        raw_root=raw_root,
        registry_path=registry,
        output_path=output,
    )
    resolver = MediaResolver.from_file(output, document_manifest_path=manifest)

    resolved = resolver.resolve([citation()])

    assert [item.media_type for item in resolved] == ["image", "video"]
    assert all(item.source_citation_id == "C1" for item in resolved)
    assert len({item.media_id for item in resolved}) == 2
    assert resolver.resolve([]) == []


def test_resolver_caps_images_and_videos_independently(tmp_path, monkeypatch) -> None:
    registry, raw_root, manifest, output = write_fixture(tmp_path, monkeypatch)
    payload = media_builder.build_media_manifest(
        document_manifest_path=manifest,
        raw_root=raw_root,
        registry_path=registry,
        output_path=output,
    )
    image = next(item for item in payload["items"] if item["media_type"] == "image")
    for suffix in ("b", "c"):
        extra = json.loads(json.dumps(image))
        extra["media_id"] = f"media-{suffix * 20}"
        extra["url"] = f"https://www.raspberrypi.com/documentation/{suffix}.png"
        payload["items"].append(extra)
        payload["links"][0]["media_ids"].append(extra["media_id"])
    payload["statistics"].update(
        media_items=4,
        media_occurrences=4,
        image_items=3,
    )
    output.write_text(json.dumps(payload), encoding="utf-8")

    resolved = MediaResolver.from_file(output, document_manifest_path=manifest).resolve([citation()])

    assert [item.media_type for item in resolved].count("image") == 2
    assert [item.media_type for item in resolved].count("video") == 1


def test_resolver_rejects_stale_document_manifest(tmp_path, monkeypatch) -> None:
    registry, raw_root, manifest, output = write_fixture(tmp_path, monkeypatch)
    media_builder.build_media_manifest(
        document_manifest_path=manifest,
        raw_root=raw_root,
        registry_path=registry,
        output_path=output,
    )
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(MediaManifestError, match="stale"):
        MediaResolver.from_file(output, document_manifest_path=manifest)
