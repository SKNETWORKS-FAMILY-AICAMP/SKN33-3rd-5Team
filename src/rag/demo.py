"""테스트 corpus로 BM25 검색을 바로 실행하는 간단한 예제.

프로젝트 최상위 폴더에서 다음처럼 실행한다.

    python3 -m src.rag.demo
"""
from __future__ import annotations

import argparse
import random
import sys

from .models import RagFilters
from .retriever import DenseRetrievalError, HybridRetriever
from .sample_queries import DEMO_QUERIES
from .settings import RagSettings, RagSettingsError

def create_parser() -> argparse.ArgumentParser:
    """질문과 선택 metadata filter를 받는 데모 CLI parser를 만든다."""
    parser = argparse.ArgumentParser(description="Run the RAG sample query.")
    parser.add_argument("--mode", choices=("bm25", "hybrid"), default="bm25")
    parser.add_argument("--query", help="직접 실행할 질문. 생략하면 콘솔에서 입력받습니다.")
    parser.add_argument(
        "--use-case",
        action="append",
        dest="use_cases",
        help="검색할 목적 tag. 여러 번 지정할 수 있습니다. 예: --use-case headless",
    )
    return parser


def select_query(query: str | None) -> str:
    """직접 지정한 질문 또는 예시 질문 목록의 무작위 항목을 반환한다."""
    return query if query else random.choice(DEMO_QUERIES)


def prompt_for_query() -> str | None:
    """터미널에서 질문을 입력받고, 빈 입력은 예시 질문 선택으로 넘긴다."""
    try:
        query = input("질문을 입력하세요 (Enter: 예시 질문 랜덤 선택): ").strip()
    except EOFError:
        return None
    return query or None


def main() -> None:
    """`.env` 설정으로 BM25 또는 Hybrid 검색 결과와 출처를 출력한다."""
    args = create_parser().parse_args()
    entered_query = args.query
    if entered_query is None and sys.stdin.isatty():
        entered_query = prompt_for_query()
    query = select_query(entered_query)
    print(f"[query] {query}")
    try:
        settings = RagSettings.from_env()
    except RagSettingsError as exc:
        raise SystemExit(f"RAG settings error: {exc}") from exc
    retriever = HybridRetriever.from_manifest(
        settings.manifest_path,
        chroma_path=settings.chroma_path if args.mode == "hybrid" else None,
        collection_name=settings.chroma_collection_name,
        embedding_model_name=settings.e5_model_name,
        dense_max_distance=settings.dense_max_distance,
    )
    try:
        decision = retriever.search_with_decision(
            query=query,
            filters=RagFilters(use_cases=tuple(args.use_cases or ())),
            top_k=settings.top_k,
        )
    except DenseRetrievalError as exc:
        raise SystemExit(str(exc)) from exc

    if decision.status == "insufficient_evidence":
        print(f"[{decision.status}] {decision.reason}")
        print("공식 문서에서 질문을 뒷받침할 충분한 근거를 찾지 못했습니다.")
        return

    for result in decision.results:
        print(f"[{result.rank}] {result.title} / {result.section}")
        print(result.content)
        print(result.source_url)
        print()


if __name__ == "__main__":
    main()
