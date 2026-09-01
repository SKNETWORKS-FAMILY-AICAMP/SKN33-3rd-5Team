"""RAG QA CLI의 선택·질문 입력 보조 로직을 외부 모델 없이 검증한다."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from src.rag import RagSettings
from src.services import rag_qa_cli


def test_cli_parser_accepts_direct_mode_or_action() -> None:
    assert rag_qa_cli.create_parser().parse_args(["--mode", "bm25"]).mode == "bm25"
    assert rag_qa_cli.create_parser().parse_args(["--action", "index"]).action == "index"


def test_cli_uses_random_demo_question_when_input_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(rag_qa_cli.random, "choice", lambda values: values[-1])

    assert rag_qa_cli.select_query(None) == rag_qa_cli.DEMO_QUERIES[-1]
    assert rag_qa_cli.select_query("   ") == rag_qa_cli.DEMO_QUERIES[-1]
    assert rag_qa_cli.select_query("  SSH를 활성화하려면? ") == "SSH를 활성화하려면?"


def test_cli_defaults_to_hybrid_without_an_operation_option() -> None:
    assert rag_qa_cli.resolve_action(rag_qa_cli.create_parser().parse_args([])) == "hybrid"
    assert rag_qa_cli.resolve_action(
        rag_qa_cli.create_parser().parse_args(["--mode", "bm25"])
    ) == "bm25"
    assert rag_qa_cli.resolve_action(
        rag_qa_cli.create_parser().parse_args(["--action", "index"])
    ) == "index"


def test_loading_indicator_prints_a_plain_progress_message_when_not_a_tty() -> None:
    stream = StringIO()

    with rag_qa_cli._loading_indicator("공식 문서를 검색하는 중입니다...", stream=stream):
        pass

    assert stream.getvalue() == "[loading] 공식 문서를 검색하는 중입니다...\n"


def test_cli_uses_configured_v3_media_chunk_map(monkeypatch, tmp_path) -> None:
    settings = RagSettings(
        project_root=tmp_path,
        manifest_path=tmp_path / "manifest.json",
        chroma_path=tmp_path / "chroma",
        chroma_collection_name="test",
        e5_model_name="test-e5",
        top_k=3,
        dense_max_distance=0.48,
        media_manifest_path=None,
        media_chunk_map_path=tmp_path / "document_pipeline/data/media_chunk_map_v3.json",
    )
    calls: dict[str, object] = {}

    def fake_load(root, **kwargs):
        calls["root"] = root
        calls.update(kwargs)
        return {}

    monkeypatch.setattr(rag_qa_cli, "load_media_by_chunk_id", fake_load)

    assert rag_qa_cli._load_media_by_chunk_id(settings) == {}
    assert calls == {
        "root": tmp_path,
        "media_chunk_map_path": Path(tmp_path / "document_pipeline/data/media_chunk_map_v3.json"),
    }
