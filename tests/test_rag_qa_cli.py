"""RAG QA CLI의 선택·질문 입력 보조 로직을 외부 모델 없이 검증한다."""

from __future__ import annotations

from src.services import rag_qa_cli


def test_cli_parser_accepts_direct_mode_or_action() -> None:
    assert rag_qa_cli.create_parser().parse_args(["--mode", "bm25"]).mode == "bm25"
    assert rag_qa_cli.create_parser().parse_args(["--action", "index"]).action == "index"


def test_cli_uses_random_demo_question_when_input_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(rag_qa_cli.random, "choice", lambda values: values[-1])

    assert rag_qa_cli.select_query(None) == rag_qa_cli.DEMO_QUERIES[-1]
    assert rag_qa_cli.select_query("   ") == rag_qa_cli.DEMO_QUERIES[-1]
    assert rag_qa_cli.select_query("  SSH를 활성화하려면? ") == "SSH를 활성화하려면?"


def test_cli_uses_hybrid_when_noninteractive(monkeypatch) -> None:
    monkeypatch.setattr(rag_qa_cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(rag_qa_cli.sys.stdout, "isatty", lambda: False)

    assert rag_qa_cli.select_action() == "hybrid"
