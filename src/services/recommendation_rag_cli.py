"""카탈로그·sLLM·Hybrid RAG·Qwen 제품 추천을 실행하는 CLI 진입점이다."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from itertools import cycle
import sys
from threading import Event, Thread
from time import sleep
from typing import Iterator, TextIO
import uuid

from src.rag import HybridRetriever, RagSettings, RagSettingsError, load_indexed_at
from src.rag_to_llm import (
    AnswerGeneratorSettings,
    AnswerGeneratorSettingsError,
    build_answer_generator,
)
from src.media import MediaManifestError, MediaResolver
from src.recommendation import (
    CatalogManifestValidationError,
    ProductRecommender,
    RecommendationSettings,
    RecommendationSettingsError,
    build_condition_extractor,
    load_and_validate_catalog,
)

from .integration_adapters import manifest_to_rag_result_metadata
from .recommendation_agent import RecommendationAgent
from .recommendation_rag_service import RecommendationRagService


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Raspberry Pi catalog + RAG recommendation flow.")
    parser.add_argument("--query", help="제품 추천 질문. 생략하면 콘솔에서 입력받습니다.")
    parser.add_argument("--request-id", default=None, help="응답 추적 ID. 생략하면 UUID를 생성합니다.")
    parser.add_argument("--json", action="store_true", help="ChatResponse JSON만 출력합니다.")
    parser.add_argument("--trace", action="store_true", help="조건·검색·생성기 실행 정보를 warnings에 포함합니다.")
    return parser


def _read_question(query: str | None) -> str:
    if query and query.strip():
        return query.strip()
    try:
        entered = input("Raspberry Pi 제품 추천 요청을 입력하세요: ").strip()
    except EOFError:
        entered = ""
    if not entered:
        raise ValueError("제품 추천 질문을 입력해 주세요.")
    return entered


@contextmanager
def _loading_indicator(message: str, *, stream: TextIO) -> Iterator[None]:
    """긴 모델·검색 작업 동안 CLI가 멈춘 것처럼 보이지 않게 한다."""

    if not stream.isatty():
        print(f"[loading] {message}", file=stream, flush=True)
        yield
        return
    stopped = Event()

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
        stream.write(f"\r{' ' * (len(message) + 3)}\r")
        stream.flush()


def _print_human_response(response) -> None:
    print(f"[{response.status}]")
    print(response.answer)
    if response.products:
        print("\n추천 제품:")
        for product in response.products:
            print(f"- {product.product_model}: {product.recommendation}")
            if product.limitations:
                print(f"  유의사항: {' / '.join(product.limitations)}")
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
        print("\n관련 미디어:")
        for item in response.media:
            print(f"- [{item.source_citation_id}] {item.title}: {item.url}")
    if response.warnings:
        print("\n실행 정보:")
        for warning in response.warnings:
            print(f"- {warning}")


def main() -> int:
    args = create_parser().parse_args()
    try:
        question = _read_question(args.query)
        rag_settings = RagSettings.from_env()
        recommendation_settings = RecommendationSettings.from_env(rag_settings.project_root)
        catalog, manifest = load_and_validate_catalog(
            catalog_path=recommendation_settings.catalog_path,
            manifest_path=rag_settings.manifest_path,
        )
        indexed_at = load_indexed_at(
            chroma_path=rag_settings.chroma_path,
            collection_name=rag_settings.chroma_collection_name,
            manifest_path=rag_settings.manifest_path,
        )
        answer_settings = AnswerGeneratorSettings.from_env(rag_settings.project_root)
        media_resolver = (
            MediaResolver.from_file(
                rag_settings.media_manifest_path,
                document_manifest_path=rag_settings.manifest_path,
            )
            if rag_settings.media_manifest_path is not None
            else None
        )
    except (
        ValueError,
        RagSettingsError,
        RecommendationSettingsError,
        CatalogManifestValidationError,
        AnswerGeneratorSettingsError,
        MediaManifestError,
    ) as exc:
        print(f"추천 실행 설정 오류: {exc}", file=sys.stderr)
        return 2

    request_id = args.request_id or str(uuid.uuid4())
    print(f"[query] {question}", file=sys.stderr if args.json else sys.stdout)
    output_stream = sys.stderr if args.json else sys.stdout
    with _loading_indicator("조건을 분석하고 공식 문서를 검색해 제품 추천을 생성하는 중입니다...", stream=output_stream):
        try:
            extractor = build_condition_extractor(recommendation_settings)
            retriever = HybridRetriever.from_manifest(
                rag_settings.manifest_path,
                chroma_path=rag_settings.chroma_path,
                collection_name=rag_settings.chroma_collection_name,
                embedding_model_name=rag_settings.e5_model_name,
                dense_max_distance=rag_settings.dense_max_distance,
            )
            service = RecommendationRagService(
                recommendation_agent=RecommendationAgent(
                    extractor=extractor,
                    recommender=ProductRecommender(catalog),
                ),
                retriever=retriever,
                metadata_by_chunk_id=manifest_to_rag_result_metadata(manifest, indexed_at=indexed_at),
                answer_generator=build_answer_generator(answer_settings),
                media_resolver=media_resolver,
                top_k=rag_settings.top_k,
            )
            response = service.answer(request_id=request_id, question=question, trace=args.trace)
        except Exception as exc:
            print(f"추천 실행 준비 중 오류가 발생했습니다: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1

    if args.json:
        print(response.model_dump_json(indent=2))
    else:
        _print_human_response(response)
    return 1 if response.status == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
