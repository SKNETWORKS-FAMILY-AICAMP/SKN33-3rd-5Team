"""로컬 RAG QA 통합 흐름을 실행하는 CLI 진입점이다.

프로젝트 최상위에서 실행한다.

    python3 -m src.services.rag_qa_cli --query "SSH를 활성화하려면?"
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from itertools import cycle
import random
import sys
from threading import Event, Thread
from time import sleep
import uuid
from typing import Iterator, Literal, TextIO

from src.rag import HybridRetriever, index_from_settings
from src.rag.sample_queries import DEMO_QUERIES
from src.rag.settings import RagSettings, RagSettingsError
from src.rag_to_llm import (
    AnswerGeneratorSettings,
    AnswerGeneratorSettingsError,
    build_answer_generator,
)
from src.media import MediaManifestError, MediaResolver

from .rag_qa_service import RagQaService


CliAction = Literal["index", "bm25", "hybrid"]

def create_parser() -> argparse.ArgumentParser:
    """QA CLI가 받는 실행 옵션을 정의한다."""

    parser = argparse.ArgumentParser(description="Run the local Raspberry Pi RAG QA flow.")
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--mode",
        choices=("bm25", "hybrid"),
        help="검증용 검색 모드를 지정합니다. 생략하면 최종 Hybrid QA를 실행합니다.",
    )
    action_group.add_argument(
        "--action",
        choices=("index", "bm25", "hybrid"),
        help="운영·검증 작업을 지정합니다. 색인은 index를 사용합니다.",
    )
    parser.add_argument("--query", help="질문을 입력합니다. 생략하면 콘솔에서 입력받습니다.")
    parser.add_argument("--request-id", default=None, help="응답 추적 ID. 생략하면 UUID를 생성합니다.")
    parser.add_argument("--json", action="store_true", help="ChatResponse JSON만 출력합니다.")
    parser.add_argument("--trace", action="store_true", help="검색 근거·생성기·인용 검증 정보를 함께 표시합니다.")
    parser.add_argument("--reset", action="store_true", help="색인 작업에서 기존 Chroma collection을 삭제 후 재생성합니다.")
    return parser


def resolve_action(args: argparse.Namespace) -> CliAction:
    """명시한 운영 옵션이 없으면 최종 사용자용 Hybrid QA를 선택한다."""

    selected = args.action or args.mode
    return selected if selected is not None else "hybrid"


def select_query(query: str | None) -> str:
    """직접 입력한 질문 또는 기존 데모의 랜덤 예시 질문을 반환한다."""

    return query.strip() if query and query.strip() else random.choice(DEMO_QUERIES)


def prompt_for_query() -> str | None:
    """콘솔에서 질문을 입력받고, 빈 입력은 예시 질문 선택으로 넘긴다."""

    try:
        query = input("Raspberry Pi 질문을 입력하세요 (Enter: 예시 질문 랜덤 선택): ").strip()
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


@contextmanager
def _loading_indicator(message: str, *, stream: TextIO) -> Iterator[None]:
    """질의 처리 중 멈춘 것처럼 보이지 않도록 터미널 진행 표시를 출력한다.

    TTY에서는 한 줄 spinner를 갱신한다. JSON·파이프 실행처럼 비대화형 출력에서는
    결과 JSON을 오염시키지 않도록 호출자가 전달한 표준 오류에 한 번만 기록한다.
    """

    if not stream.isatty():
        print(f"[loading] {message}", file=stream, flush=True)
        yield
        return

    stopped = Event()
    rendered_width = len(message) + 3

    def render() -> None:
        for symbol in cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
            if stopped.is_set():
                break
            stream.write(f"\r{symbol} {message}")
            stream.flush()
            sleep(0.1)

    thread = Thread(target=render, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=0.2)
        stream.write(f"\r{' ' * rendered_width}\r")
        stream.flush()


def _run_indexer(settings: RagSettings, *, reset: bool) -> int:
    """선택된 색인 작업을 실행하고, 저장된 collection 정보를 안내한다."""

    try:
        count = index_from_settings(settings, reset=reset)
    except Exception as exc:
        print(f"Chroma 색인 중 오류가 발생했습니다: {exc}", file=sys.stderr)
        return 1
    action = "전체 재색인" if reset else "색인 생성·갱신"
    print(f"{action} 완료: {count}개 공식 청크 → '{settings.chroma_collection_name}'")
    return 0


def _build_media_resolver(settings: RagSettings) -> MediaResolver | None:
    """Resolve every configured citation-media source through one code path."""

    return MediaResolver.from_paths(
        media_manifest_path=settings.media_manifest_path,
        document_manifest_path=settings.manifest_path,
        media_chunk_map_path=settings.media_chunk_map_path,
        image_manifest_path=settings.project_root / "assets/media/manifest.json",
        video_manifest_path=settings.project_root / "assets/media/video_manifest.json",
    )


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
    if response.media:
        print("\n관련 이미지·영상:")
        for item in response.media:
            print(f"[{item.source_citation_id}] ({item.media_type}) {item.title}")
            print(item.url)
    if response.warnings:
        print("\n실행 정보:")
        for warning in response.warnings:
            print(f"- {warning}")


def main() -> int:
    """환경 설정으로 RAG QA 서비스를 조립하고 한 질문을 처리한다."""

    args = create_parser().parse_args()
    action = resolve_action(args)
    if args.reset and action != "index":
        create_parser().error("--reset은 --action index에서만 사용할 수 있습니다.")
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
        media_resolver = _build_media_resolver(settings)
    except (AnswerGeneratorSettingsError, MediaManifestError) as exc:
        print(f"Answer generator settings error: {exc}", file=sys.stderr)
        return 2

    question = _read_question(args.query)
    request_id = args.request_id or str(uuid.uuid4())
    print(f"[query] {question}", file=sys.stderr if args.json else sys.stdout)

    output_stream = sys.stderr if args.json else sys.stdout
    with _loading_indicator("공식 문서를 Hybrid 검색하고 답변을 생성하는 중입니다...", stream=output_stream):
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
            media_resolver=media_resolver,
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
