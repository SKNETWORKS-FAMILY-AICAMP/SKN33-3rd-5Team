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


def test_streamlit_uses_configured_v3_media_chunk_map(monkeypatch, tmp_path) -> None:
    configured_path = tmp_path / "document_pipeline/data/media_chunk_map_v3.json"
    calls: dict[str, object] = {}

    def fake_load(project_root, **kwargs):
        calls["project_root"] = project_root
        calls.update(kwargs)
        return {}

    monkeypatch.setattr(runtime, "load_media_by_chunk_id", fake_load)

    assert runtime._load_media_by_chunk_id(
        _settings(tmp_path, media_chunk_map_path=configured_path)
    ) == {}
    assert calls == {
        "project_root": tmp_path,
        "media_chunk_map_path": configured_path,
    }


def test_streamlit_uses_legacy_default_when_media_chunk_map_is_unset(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}

    def fake_load(project_root, **kwargs):
        calls["project_root"] = project_root
        calls.update(kwargs)
        return {}

    monkeypatch.setattr(runtime, "load_media_by_chunk_id", fake_load)

    assert runtime._load_media_by_chunk_id(_settings(tmp_path, media_chunk_map_path=None)) == {}
    assert calls == {"project_root": tmp_path}
