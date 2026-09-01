"""Streamlit runtime이 RAG 공통 미디어 맵 설정을 따르는지 검증한다."""

from __future__ import annotations

from pathlib import Path

from src.rag import RagSettings
from streamlit_app import runtime


def _settings(project_root: Path, *, media_chunk_map_path: Path | None) -> RagSettings:
    return RagSettings(
        project_root=project_root,
        manifest_path=project_root / "manifest.json",
        chroma_path=project_root / "chroma",
        chroma_collection_name="test",
        e5_model_name="test-e5",
        top_k=3,
        dense_max_distance=0.48,
        media_manifest_path=None,
        media_chunk_map_path=media_chunk_map_path,
    )


def test_streamlit_builds_one_resolver_with_configured_v3_media_chunk_map(monkeypatch, tmp_path) -> None:
    configured_path = tmp_path / "document_pipeline/data/media_chunk_map_v3.json"
    calls: dict[str, object] = {}

    def fake_from_paths(**kwargs):
        calls.update(kwargs)
        return "resolver"

    monkeypatch.setattr(runtime.MediaResolver, "from_paths", fake_from_paths)

    assert runtime._build_media_resolver(_settings(tmp_path, media_chunk_map_path=configured_path)) == "resolver"
    assert calls == {
        "media_manifest_path": None,
        "document_manifest_path": tmp_path / "manifest.json",
        "media_chunk_map_path": configured_path,
        "image_manifest_path": tmp_path / "assets/media/manifest.json",
        "video_manifest_path": tmp_path / "assets/media/video_manifest.json",
    }


def test_streamlit_keeps_no_media_fallback_when_media_chunk_map_is_unset(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}

    def fake_from_paths(**kwargs):
        calls.update(kwargs)
        return None

    monkeypatch.setattr(runtime.MediaResolver, "from_paths", fake_from_paths)

    assert runtime._build_media_resolver(_settings(tmp_path, media_chunk_map_path=None)) is None
    assert calls["media_chunk_map_path"] is None
