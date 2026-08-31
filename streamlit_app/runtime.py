"""Streamlit에서 팀의 QA·제품 추천 서비스를 조립하는 런타임 경계다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.rag import HybridRetriever, RagSettings, load_indexed_at
from src.rag_to_llm import AnswerGeneratorSettings, build_answer_generator
from src.recommendation import (
    ProductRecommender,
    RecommendationSettings,
    build_condition_extractor,
    load_and_validate_catalog,
)
from src.services.integration_adapters import manifest_to_rag_result_metadata
from src.services.rag_qa_service import RagQaService
from src.services.recommendation_agent import RecommendationAgent
from src.services.recommendation_rag_service import RecommendationRagService


@dataclass(frozen=True)
class RuntimeReadiness:
    """모델을 로드하지 않고 확인한 Streamlit 실행 준비 상태다."""

    ready: bool
    message: str


def check_runtime_readiness(project_root: Path) -> RuntimeReadiness:
    """`.env`·manifest·Chroma metadata의 최소 준비 상태를 확인한다."""

    try:
        settings = RagSettings.from_env(project_root)
    except Exception as exc:
        return RuntimeReadiness(False, f"RAG 설정 준비 필요: {exc}")

    index_metadata = settings.chroma_path / "picare-index.json"
    if not index_metadata.is_file():
        return RuntimeReadiness(
            False,
            "Chroma 색인 준비 필요: "
            f"{index_metadata} (먼저 `python -m src.services.rag_qa_cli --action index` 실행)",
        )
    return RuntimeReadiness(True, "실제 Hybrid RAG 런타임 준비 완료")


def _rag_dependencies(project_root: Path):
    rag_settings = RagSettings.from_env(project_root)
    answer_settings = AnswerGeneratorSettings.from_env(project_root)
    retriever = HybridRetriever.from_manifest(
        rag_settings.manifest_path,
        chroma_path=rag_settings.chroma_path,
        collection_name=rag_settings.chroma_collection_name,
        embedding_model_name=rag_settings.e5_model_name,
        dense_max_distance=rag_settings.dense_max_distance,
    )
    return rag_settings, retriever, build_answer_generator(answer_settings)


def build_qa_service(project_root: Path) -> RagQaService:
    """CLI와 동일한 설정으로 Streamlit QA 서비스를 조립한다."""

    rag_settings, retriever, answer_generator = _rag_dependencies(project_root)
    return RagQaService(
        retriever=retriever,
        answer_generator=answer_generator,
        top_k=rag_settings.top_k,
    )


def build_recommendation_service(project_root: Path) -> RecommendationRagService:
    """sLLM→catalog→Hybrid RAG→답변 생성 흐름을 Streamlit용으로 조립한다."""

    rag_settings, retriever, answer_generator = _rag_dependencies(project_root)
    recommendation_settings = RecommendationSettings.from_env(project_root)
    catalog, manifest = load_and_validate_catalog(
        catalog_path=recommendation_settings.catalog_path,
        manifest_path=rag_settings.manifest_path,
    )
    indexed_at = load_indexed_at(
        chroma_path=rag_settings.chroma_path,
        collection_name=rag_settings.chroma_collection_name,
        manifest_path=rag_settings.manifest_path,
    )
    return RecommendationRagService(
        recommendation_agent=RecommendationAgent(
            extractor=build_condition_extractor(recommendation_settings),
            recommender=ProductRecommender(catalog),
        ),
        retriever=retriever,
        metadata_by_chunk_id=manifest_to_rag_result_metadata(
            manifest,
            indexed_at=indexed_at,
        ),
        answer_generator=answer_generator,
        top_k=rag_settings.top_k,
    )


__all__ = [
    "RuntimeReadiness",
    "build_qa_service",
    "build_recommendation_service",
    "check_runtime_readiness",
]
