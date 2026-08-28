"""테스트 corpus로 BM25 검색을 바로 실행하는 간단한 예제.

프로젝트 최상위 폴더에서 다음처럼 실행한다.

    python3 -m src.rag.demo
"""
from __future__ import annotations

import argparse

from .models import RagFilters
from .retriever import DenseRetrievalError, HybridRetriever
from .settings import RagSettings, RagSettingsError


def main() -> None:
    """`.env` 설정으로 BM25 또는 Hybrid 검색 결과와 출처를 출력한다."""
    parser = argparse.ArgumentParser(description="Run the RAG sample query.")
    parser.add_argument("--mode", choices=("bm25", "hybrid"), default="bm25")
    args = parser.parse_args()
    try:
        settings = RagSettings.from_env()
    except RagSettingsError as exc:
        raise SystemExit(f"RAG settings error: {exc}") from exc
    retriever = HybridRetriever.from_manifest(
        settings.manifest_path,
        chroma_path=settings.chroma_path if args.mode == "hybrid" else None,
        collection_name=settings.chroma_collection_name,
        embedding_model_name=settings.e5_model_name,
    )
    try:
        results = retriever.search(
            # 사용자가 마지막으로 바꾼 스마트팜 질문은 유지한다.
            query="스마트팜을 작게 구현하고싶은데 어떤 모델이 좋을까?",
            filters=RagFilters(use_cases=("headless",)),
            top_k=settings.top_k,
        )
    except DenseRetrievalError as exc:
        raise SystemExit(str(exc)) from exc

    for result in results:
        print(f"[{result.rank}] {result.title} / {result.section}")
        print(result.content)
        print(result.source_url)
        print()


if __name__ == "__main__":
    main()
