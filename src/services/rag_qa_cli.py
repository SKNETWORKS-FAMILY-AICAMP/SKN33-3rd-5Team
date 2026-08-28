"""로컬 RAG QA 통합 흐름을 실행하는 CLI 진입점이다.

프로젝트 최상위에서 실행한다.

    python3 -m src.services.rag_qa_cli --mode hybrid --query "SSH를 활성화하려면?"
"""

from __future__ import annotations

import argparse
import random
import sys
import termios
import tty
import uuid
from typing import Literal

from src.rag import HybridRetriever, build_chroma_index
from src.rag.sample_queries import DEMO_QUERIES
from src.rag.settings import RagSettings, RagSettingsError
from src.rag_to_llm import (
    AnswerGeneratorSettings,
    AnswerGeneratorSettingsError,
    build_answer_generator,
)

from .rag_qa_service import RagQaService


CliAction = Literal["index", "bm25", "hybrid"]

_ACTION_MENU: tuple[tuple[CliAction, str, str], ...] = (
    ("hybrid", "Hybrid QA", "BM25 + Chroma Dense 검색으로 답변합니다. (권장)"),
    ("bm25", "BM25 QA", "Chroma 없이 키워드 검색으로 답변합니다."),
    ("index", "Chroma 색인 생성·갱신", "manifest의 검수 문서를 Chroma DB에 upsert합니다."),
)


def create_parser() -> argparse.ArgumentParser:
    """QA CLI가 받는 실행 옵션을 정의한다."""

    parser = argparse.ArgumentParser(description="Run the local Raspberry Pi RAG QA flow.")
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--mode",
        choices=("bm25", "hybrid"),
        help="검색 모드를 바로 지정합니다. 생략하면 화살표 메뉴를 표시합니다.",
    )
    action_group.add_argument(
        "--action",
        choices=("index", "bm25", "hybrid"),
        help="색인 또는 검색 작업을 바로 지정합니다.",
    )
    parser.add_argument("--query", help="질문을 입력합니다. 생략하면 콘솔에서 입력받습니다.")
    parser.add_argument("--request-id", default=None, help="응답 추적 ID. 생략하면 UUID를 생성합니다.")
    parser.add_argument("--json", action="store_true", help="ChatResponse JSON만 출력합니다.")
    parser.add_argument("--trace", action="store_true", help="검색 근거·생성기·인용 검증 정보를 함께 표시합니다.")
    parser.add_argument("--reset", action="store_true", help="색인 작업에서 기존 Chroma collection을 삭제 후 재생성합니다.")
    return parser


def _render_menu(selected_index: int, *, redraw: bool) -> None:
    """화살표 메뉴의 현재 선택 상태를 ANSI 지원 터미널에 표시한다."""

    if redraw:
        # 제목 1줄, 안내 1줄, 선택지 3줄을 덮어쓴다.
        sys.stdout.write(f"\033[{len(_ACTION_MENU) + 2}A")
    sys.stdout.write("\033[2K\rRAG QA 작업을 선택하세요\n")
    sys.stdout.write("\033[2K\r↑/↓ 이동 · Enter 선택 · Ctrl+C 취소\n")
    for index, (_, label, description) in enumerate(_ACTION_MENU):
        marker = "❯" if index == selected_index else " "
        sys.stdout.write(f"\033[2K\r{marker} {label}: {description}\n")
    sys.stdout.flush()


def select_action() -> CliAction:
    """TTY에서 3개 작업을 화살표로 선택하고, 비대화형 실행은 Hybrid로 처리한다."""

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return "hybrid"

    selected_index = 0
    file_descriptor = sys.stdin.fileno()
    previous_terminal_state = termios.tcgetattr(file_descriptor)
    _render_menu(selected_index, redraw=False)
    try:
        tty.setraw(file_descriptor)
        while True:
            key = sys.stdin.read(1)
            if key == "\x03":  # Ctrl+C
                raise KeyboardInterrupt
            if key == "\x1b":  # macOS 터미널의 위/아래 화살표 시퀀스
                key += sys.stdin.read(2)
            if key in ("\x1b[A", "k"):
                selected_index = (selected_index - 1) % len(_ACTION_MENU)
            elif key in ("\x1b[B", "j"):
                selected_index = (selected_index + 1) % len(_ACTION_MENU)
            elif key in ("\r", "\n"):
                sys.stdout.write("\n")
                return _ACTION_MENU[selected_index][0]
            else:
                continue
            _render_menu(selected_index, redraw=True)
    finally:
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, previous_terminal_state)


def select_query(query: str | None) -> str:
    """직접 입력한 질문 또는 기존 데모의 랜덤 예시 질문을 반환한다."""

    return query.strip() if query and query.strip() else random.choice(DEMO_QUERIES)


def prompt_for_query() -> str | None:
    """콘솔에서 질문을 입력받고, 빈 입력은 예시 질문 선택으로 넘긴다."""

    try:
        query = input("질문을 입력하세요 (Enter: 예시 질문 랜덤 선택): ").strip()
    except EOFError:
        return None
    return query or None


def _read_question(query: str | None) -> str:
    """명령행 질문 또는 콘솔 질문을 읽어 예시 질문까지 포함해 반환한다."""

    if query is not None:
        return select_query(query)
    if sys.stdin.isatty():
        return select_query(prompt_for_query())
    return select_query(None)


def _run_indexer(settings: RagSettings, *, reset: bool) -> int:
    """선택된 색인 작업을 실행하고, 저장된 collection 정보를 안내한다."""

    try:
        count = build_chroma_index(
            manifest_path=settings.manifest_path,
            chroma_path=settings.chroma_path,
            collection_name=settings.chroma_collection_name,
            embedding_model_name=settings.e5_model_name,
            reset=reset,
        )
    except Exception as exc:
        print(f"Chroma 색인 중 오류가 발생했습니다: {exc}", file=sys.stderr)
        return 1
    action = "전체 재색인" if reset else "색인 생성·갱신"
    print(f"{action} 완료: {count}개 공식 청크 → '{settings.chroma_collection_name}'")
    return 0


def _print_human_response(response) -> None:
    """터미널 시연용으로 답변과 출처 카드를 읽기 좋게 출력한다."""

    print(f"[{response.status}]")
    print(response.answer)
    if response.clarification_questions:
        print("\n확인 질문:")
        for question in response.clarification_questions:
            print(f"- {question}")
    if response.citations:
        print("\n출처:")
        for citation in response.citations:
            print(f"[{citation.citation_id}] {citation.title} / {citation.section}")
            print(citation.source_url)
    if response.warnings:
        print("\n실행 정보:")
        for warning in response.warnings:
            print(f"- {warning}")


def main() -> int:
    """환경 설정으로 RAG QA 서비스를 조립하고 한 질문을 처리한다."""

    args = create_parser().parse_args()
    action: CliAction = args.action or args.mode or select_action()
    if args.reset and action != "index":
        create_parser().error("--reset은 --action index 또는 메뉴의 색인 작업에서만 사용할 수 있습니다.")
    if args.json and action == "index":
        create_parser().error("--json은 BM25 또는 Hybrid QA 응답에서만 사용할 수 있습니다.")
    try:
        settings = RagSettings.from_env()
    except RagSettingsError as exc:
        print(f"RAG settings error: {exc}", file=sys.stderr)
        return 2

    if action == "index":
        return _run_indexer(settings, reset=args.reset)

    try:
        generator_settings = AnswerGeneratorSettings.from_env(settings.project_root)
        answer_generator = build_answer_generator(generator_settings)
    except AnswerGeneratorSettingsError as exc:
        print(f"Answer generator settings error: {exc}", file=sys.stderr)
        return 2

    question = _read_question(args.query)
    request_id = args.request_id or str(uuid.uuid4())
    print(f"[query] {question}", file=sys.stderr if args.json else sys.stdout)

    retriever = HybridRetriever.from_manifest(
        settings.manifest_path,
        chroma_path=settings.chroma_path if action == "hybrid" else None,
        collection_name=settings.chroma_collection_name,
        embedding_model_name=settings.e5_model_name,
        dense_max_distance=settings.dense_max_distance,
    )
    service = RagQaService(
        retriever=retriever,
        answer_generator=answer_generator,
        top_k=settings.top_k,
    )
    response = service.answer(
        request_id=request_id,
        question=question,
        retrieval_mode=action,
        trace=args.trace,
    )
    if args.json:
        print(response.model_dump_json(indent=2))
    else:
        _print_human_response(response)
    return 1 if response.status == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
