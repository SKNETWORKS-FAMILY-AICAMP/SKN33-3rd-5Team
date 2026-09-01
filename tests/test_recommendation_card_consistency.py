"""추천 본문·제품 카드·근거가 서로 어긋나지 않는지 검사한다.

문서 단위 근거만 보면 다른 제품의 사양 문서가 이 후보의 출처로 붙고,
부분문자열 검사만 하면 본문이 부정한 제품의 카드가 그대로 남는다.
두 경우 모두 카드를 만들지 않고 보류하는지 확인한다.
"""

from datetime import datetime

from src.condition_extraction.schema import SurveyAnswer, SurveyResponse
from src.contracts import ConditionPayload, SearchResponse
from src.recommendation.engine import ProductRecommender
from src.recommendation.schema import ProductCatalog
from src.services.recommendation_agent import RecommendationAgent
from src.services.recommendation_rag_service import RecommendationRagService
from src.services.recommendation_response import (
    build_recommendation_chat_response,
    candidate_condition_document_ids,
    condition_evidence_fields,
)


def _evidence(document_id: str) -> dict[str, list[str]]:
    """제품의 모든 필수 사실이 한 공식 문서에 근거한다고 표현한다."""

    fields = (
        "identity",
        "wireless",
        "ethernet",
        "gpio_header",
        "camera_connector_count",
        "display_output_count",
        "built_in_keyboard",
        "cpu",
        "memory",
        "performance_tier",
        "beginner_friendly",
        "recommended_use_cases",
        "recommended_tasks",
    )
    return {field: [document_id] for field in fields}


def _catalog() -> ProductCatalog:
    """공유 문서 하나를 두 제품이 함께 근거로 쓰는 카탈로그를 만든다."""

    capabilities = {
        "wireless": True,
        "ethernet": True,
        "gpio_header": "populated",
        "camera_connector_count": 1,
        "display_output_count": 1,
        "built_in_keyboard": False,
    }
    profile = {
        "performance_tier": "high",
        "beginner_friendly": True,
        "recommended_use_cases": ["education_coding"],
        "recommended_tasks": ["desktop_programming"],
    }
    display = {
        "cpu": "Test CPU",
        "memory": "4 GB",
        "wireless": "Wi-Fi",
        "dimensions": None,
    }
    # Spec Board는 doc-shared를 identity 근거로만 쓰고, doc-caveat은 조건과
    # 무관한 caveats 근거로만 쓴다.
    spec_evidence = _evidence("doc-spec") | {
        "identity": ["doc-shared", "doc-spec"],
        "caveats": ["doc-caveat"],
    }
    return ProductCatalog.model_validate(
        {
            "schema_version": "1.2.0",
            "catalog_version": "test-card-consistency",
            "generated_at": datetime.fromisoformat("2026-09-01T10:00:00+09:00"),
            "recommendation_policy": {
                "policy_id": "test-card-consistency-policy",
                "reviewed_at": "2026-09-01",
                "review_status": "approved",
                "scope": "테스트용 추천 등급·용도 기준 검수",
            },
            "sources": [
                {
                    "document_id": document_id,
                    "title": document_id,
                    "source_url": "https://www.raspberrypi.com/documentation/",
                    "retrieved_at": "2026-09-01",
                    "license": "CC BY-SA 4.0",
                }
                for document_id in ("doc-caveat", "doc-shared", "doc-spec")
            ],
            "products": [
                {
                    "product_id": "spec-board",
                    "name": "Spec Board",
                    "aliases": [],
                    "family": "flagship",
                    "is_current": True,
                    "memory_options_gb": [4],
                    "capabilities": capabilities,
                    "display": display,
                    "recommendation_profile": profile,
                    "required_accessories": [],
                    "conditional_accessories": [],
                    "caveats": ["발열 관리가 필요합니다."],
                    "evidence_by_field": spec_evidence,
                    "document_ids": ["doc-caveat", "doc-shared", "doc-spec"],
                    "product_url": "https://www.raspberrypi.com/products/",
                    "image_url": None,
                },
                {
                    "product_id": "keyboard-board",
                    "name": "Keyboard Board",
                    "aliases": [],
                    "family": "keyboard",
                    "is_current": True,
                    "memory_options_gb": [4],
                    "capabilities": capabilities | {"built_in_keyboard": True},
                    "display": display,
                    "recommendation_profile": profile,
                    "required_accessories": [],
                    "conditional_accessories": [],
                    "caveats": [],
                    "evidence_by_field": _evidence("doc-shared"),
                    "document_ids": ["doc-shared"],
                    "product_url": "https://www.raspberrypi.com/products/",
                    "image_url": None,
                },
            ],
        }
    )


def _conditions() -> ConditionPayload:
    return ConditionPayload.model_validate(
        {
            "schema_version": "1.1.0",
            "intent": "product_recommendation",
            "use_case": "education_coding",
            "product_models": None,
            "os_versions": None,
            "task": "desktop_programming",
            "performance_priority": "high",
            "wireless_required": True,
            "camera_required": None,
            "gpio_required": None,
            "monitor_available": None,
            "remote_access_required": None,
            "user_level": "beginner",
            "needs_clarification": False,
            "clarification_questions": [],
        }
    )


class _StaticExtractor:
    """실제 모델 없이 정해진 조건을 반환하는 테스트 대역이다."""

    def __init__(self, output: ConditionPayload):
        self.output = output

    def extract(self, survey: SurveyResponse) -> ConditionPayload:
        return self.output


def _agent_result():
    return RecommendationAgent(
        extractor=_StaticExtractor(_conditions()),
        recommender=ProductRecommender(_catalog()),
    ).recommend(
        SurveyResponse(
            answers=[
                SurveyAnswer(
                    question_id="purpose",
                    question="목적은?",
                    answer="교육용 코딩",
                )
            ]
        )
    )


def _search_response(*, document_id: str, product_models: list[str]) -> SearchResponse:
    """검색 결과 한 건의 문서와 제품 태그만 바꿔 가며 만든다."""

    return SearchResponse.model_validate(
        {
            "schema_version": "1.1.0",
            "query_id": "query-1",
            "query_language": "ko",
            "retrieval_method": "hybrid",
            "top_k": 3,
            "applied_filters": {
                "product_models": product_models,
                "use_cases": ["education_coding"],
                "os_versions": [],
                "source_types": ["documentation"],
                "official_only": True,
            },
            "results": [
                {
                    "citation_id": "C1",
                    "rank": 1,
                    "document_id": document_id,
                    "chunk_id": f"{document_id}-001",
                    "chunk_index": 0,
                    "title": document_id,
                    "publisher": "Raspberry Pi Ltd",
                    "section": "Specifications",
                    "content": "Official specification table.",
                    "source_url": "https://www.raspberrypi.com/documentation/",
                    "source_anchor": "specs",
                    "language": "en",
                    "source_type": "documentation",
                    "published_at": None,
                    "updated_at": None,
                    "collected_at": "2026-09-01",
                    "indexed_at": "2026-09-01T10:00:00+09:00",
                    "document_version": "commit-test",
                    "license": "CC BY-SA 4.0",
                    "product_models": product_models,
                    "use_cases": ["education_coding"],
                    "tasks": ["desktop_programming"],
                    "categories": ["computer"],
                    "os_versions": [],
                    "document_checksum": "sha256:doc",
                    "chunk_checksum": "sha256:chunk",
                    "embedding_checksum": "sha256:embedding",
                    "parser_version": "1.0.0",
                    "official_verified": True,
                    "quality_status": "approved",
                    "image_url": None,
                    "video_url": None,
                }
            ],
        }
    )


# --- 문제 1: 근거가 문서 단위로만 연결되던 문제 -------------------------------


def test_condition_evidence_fields_skip_unasked_and_legacy_fields() -> None:
    """요구하지 않은 조건과 v1.1 묶음 근거는 근거 요구 대상이 아니다."""

    fields = condition_evidence_fields(_conditions())

    assert "recommended_use_cases" in fields
    assert "beginner_friendly" in fields
    assert "wireless" in fields
    # 사용자가 요구하지 않은 조건이다.
    assert "camera_connector_count" not in fields
    assert "gpio_header" not in fields
    # v1.1 잔재인 묶음 근거는 어느 조건에도 매핑하지 않는다.
    assert "recommendation_profile" not in fields


def test_condition_evidence_excludes_documents_backing_only_other_fields() -> None:
    """조건과 무관한 필드만 뒷받침하는 문서는 후보 근거가 아니다."""

    candidates = {c.name: c for c in _agent_result().decision.candidates}
    document_ids = candidate_condition_document_ids(
        candidates["Spec Board"], _conditions()
    )

    assert "doc-spec" in document_ids
    # caveats 전용 근거는 조건 판단에 쓰이지 않는다.
    assert "doc-caveat" not in document_ids


def test_other_product_chunk_is_not_cited_on_this_product_card() -> None:
    """공유 문서라도 다른 제품을 다룬 청크는 이 카드의 출처로 붙지 않는다."""

    agent_result = _agent_result()
    # doc-shared는 Spec Board의 identity 근거이기도 하지만, 이 청크는
    # Keyboard Board만 다룬다.
    response = build_recommendation_chat_response(
        request_id="req-1",
        agent_result=agent_result,
        search_response=_search_response(
            document_id="doc-shared", product_models=["Keyboard Board"]
        ),
    )

    assert response.status == "answered"
    cited_products = {product.product_model for product in response.products}
    assert cited_products == {"Keyboard Board"}
    assert "Spec Board" not in cited_products


def test_card_is_not_built_when_only_unrelated_evidence_is_retrieved() -> None:
    """조건과 무관한 근거만 검색되면 카드를 만들지 않고 보류한다."""

    response = build_recommendation_chat_response(
        request_id="req-1",
        agent_result=_agent_result(),
        search_response=_search_response(
            document_id="doc-caveat", product_models=["Spec Board"]
        ),
    )

    assert response.status == "insufficient_evidence"
    assert response.products == []
    assert response.citations == []


# --- 문제 2: 본문과 카드가 따로 놀던 문제 --------------------------------------


def test_candidate_mentioned_only_in_negative_context_loses_its_card() -> None:
    """본문이 부정으로만 언급한 후보는 카드에서 제외된다."""

    agent_result = _agent_result()
    answer = (
        "Keyboard Board를 추천합니다. 내장 키보드로 교육용 코딩에 적합합니다 [C1]. "
        "Spec Board는 근거가 부족해 추천할 수 없습니다."
    )

    filtered = RecommendationRagService._drop_candidates_negated_by_answer(
        answer, agent_result, provider="huggingface"
    )

    kept = [candidate.name for candidate in filtered.decision.candidates]
    assert "Spec Board" not in kept
    assert "Keyboard Board" in kept


def test_positive_mention_elsewhere_keeps_the_card() -> None:
    """한 문장이 부정이어도 다른 문장이 긍정이면 후보를 유지한다."""

    agent_result = _agent_result()
    answer = (
        "Spec Board를 추천합니다 [C1]. "
        "다만 저전력 환경이라면 Spec Board는 적합하지 않습니다."
    )

    filtered = RecommendationRagService._drop_candidates_negated_by_answer(
        answer, agent_result, provider="huggingface"
    )

    assert "Spec Board" in [c.name for c in filtered.decision.candidates]


def test_all_candidates_negated_leaves_no_card_and_holds_the_answer() -> None:
    """모든 후보가 부정되면 카드 없이 insufficient_evidence로 보류한다."""

    agent_result = _agent_result()
    answer = (
        "Spec Board는 근거가 부족해 추천할 수 없습니다. "
        "Keyboard Board도 확인되지 않아 추천하지 않습니다."
    )

    filtered = RecommendationRagService._drop_candidates_negated_by_answer(
        answer, agent_result, provider="huggingface"
    )
    assert filtered.decision.candidates == []

    response = build_recommendation_chat_response(
        request_id="req-1",
        agent_result=filtered,
        search_response=_search_response(
            document_id="doc-spec", product_models=["Spec Board"]
        ),
    )
    assert response.status == "insufficient_evidence"
    assert response.products == []


def test_template_provider_keeps_candidates() -> None:
    """검색 원문만 보여주는 로컬 template은 부정 검사 대상이 아니다."""

    agent_result = _agent_result()
    answer = "Spec Board는 추천할 수 없습니다. Keyboard Board도 추천하지 않습니다."

    filtered = RecommendationRagService._drop_candidates_negated_by_answer(
        answer, agent_result, provider="template"
    )

    assert len(filtered.decision.candidates) == len(agent_result.decision.candidates)
