"""제품 필터·Streamlit 입력·fallback·RAG 응답 통합을 확인한다."""

from __future__ import annotations

import unittest
from datetime import datetime

from src.condition_extraction.schema import SurveyAnswer, SurveyResponse
from src.condition_extraction.ui_input import RecommendationFormInput
from src.contracts import ConditionPayload, SearchResponse
from src.recommendation.engine import ProductRecommender
from src.recommendation.schema import ProductCatalog
from src.services.recommendation_agent import RecommendationAgent
from src.services.recommendation_response import build_recommendation_chat_response


def catalog() -> ProductCatalog:
    """서로 다른 기능과 성능을 가진 테스트용 제품 카탈로그를 만든다."""

    return ProductCatalog.model_validate(
        {
            "schema_version": "1.0.0",
            "catalog_version": "test-v1",
            "generated_at": datetime.fromisoformat("2026-08-27T12:00:00+09:00"),
            "sources": [
                {
                    "document_id": "doc-compact",
                    "title": "Official compact hardware source",
                    "source_url": "https://www.raspberrypi.com/documentation/computers/raspberry-pi.html",
                    "retrieved_at": "2026-08-27",
                    "license": "CC BY-SA 4.0",
                },
                {
                    "document_id": "doc-fast",
                    "title": "Official fast hardware source",
                    "source_url": "https://www.raspberrypi.com/products/raspberry-pi-5/",
                    "retrieved_at": "2026-08-27",
                    "license": "official product page terms",
                },
            ],
            "products": [
                {
                    "product_id": "compact-board",
                    "name": "Compact Board",
                    "aliases": [],
                    "family": "zero",
                    "is_current": True,
                    "memory_options_gb": [0.5],
                    "capabilities": {
                        "wireless": True,
                        "ethernet": False,
                        "gpio_header": "unpopulated",
                        "camera_connector_count": 0,
                        "display_output_count": 1,
                        "built_in_keyboard": False,
                    },
                    "display": {
                        "cpu": "1.0 GHz quad-core ARM",
                        "memory": "512 MB",
                        "wireless": "Wi-Fi, Bluetooth",
                        "dimensions": "65 × 30 mm",
                    },
                    "recommendation_profile": {
                        "performance_tier": "low",
                        "beginner_friendly": False,
                        "recommended_use_cases": ["gpio_iot", "smart_farm_monitoring"],
                        "recommended_tasks": ["sensor_monitoring", "gpio_setup"],
                    },
                    "required_accessories": [],
                    "caveats": [],
                    "document_ids": ["doc-compact"],
                    "product_url": "https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/",
                    "image_url": "https://www.raspberrypi.com/example/compact.png",
                },
                {
                    "product_id": "fast-board",
                    "name": "Fast Board",
                    "aliases": ["Fast Board 8GB"],
                    "family": "flagship",
                    "is_current": True,
                    "memory_options_gb": [4, 8],
                    "capabilities": {
                        "wireless": True,
                        "ethernet": True,
                        "gpio_header": "populated",
                        "camera_connector_count": 2,
                        "display_output_count": 2,
                        "built_in_keyboard": False,
                    },
                    "display": {
                        "cpu": "2.4 GHz quad-core ARM",
                        "memory": "4 GB / 8 GB",
                        "wireless": "Wi-Fi, Bluetooth",
                        "dimensions": "85 × 56 mm",
                    },
                    "recommendation_profile": {
                        "performance_tier": "high",
                        "beginner_friendly": True,
                        "recommended_use_cases": ["education_coding", "camera_monitoring"],
                        "recommended_tasks": ["desktop_programming", "camera_setup"],
                    },
                    "required_accessories": ["power supply"],
                    "caveats": ["cooling may be required"],
                    "document_ids": ["doc-fast"],
                    "product_url": "https://www.raspberrypi.com/products/raspberry-pi-5/",
                    "image_url": None,
                },
            ],
        }
    )


def conditions(**overrides) -> ConditionPayload:
    """추천 테스트에 사용할 기본 공통 조건에 필요한 값만 덮어쓴다."""

    payload = {
        "schema_version": "1.1.0",
        "intent": "product_recommendation",
        "use_case": "gpio_iot",
        "product_models": None,
        "os_versions": None,
        "task": "sensor_monitoring",
        "performance_priority": "low",
        "wireless_required": True,
        "camera_required": False,
        "gpio_required": True,
        "monitor_available": False,
        "remote_access_required": True,
        "user_level": "intermediate",
        "needs_clarification": False,
        "clarification_questions": [],
    }
    payload.update(overrides)
    return ConditionPayload.model_validate(payload)


class StaticExtractor:
    """실제 모델 없이 정해진 조건을 반환하는 테스트 대역이다."""

    def __init__(self, output: ConditionPayload):
        """반환할 고정 조건을 저장한다."""

        self.output = output

    def extract(self, survey: SurveyResponse) -> ConditionPayload:
        """입력 설문과 무관하게 지정된 조건을 반환한다."""

        return self.output


def search_response() -> SearchResponse:
    """제품 문서와 인용 ID가 연결된 테스트용 공식 검색 결과를 만든다."""

    return SearchResponse.model_validate(
        {
            "schema_version": "1.1.0",
            "query_id": "query-1",
            "query_language": "ko",
            "retrieval_method": "hybrid",
            "top_k": 3,
            "applied_filters": {
                "product_models": ["Compact Board"],
                "use_cases": ["gpio_iot"],
                "os_versions": [],
                "source_types": ["documentation"],
                "official_only": True,
            },
            "results": [
                {
                    "citation_id": "C1",
                    "rank": 1,
                    "document_id": "doc-compact",
                    "chunk_id": "doc-compact-001",
                    "chunk_index": 0,
                    "title": "Official compact hardware source",
                    "publisher": "Raspberry Pi Ltd",
                    "section": "Zero series",
                    "content": "The compact board provides wireless connectivity and GPIO.",
                    "source_url": "https://www.raspberrypi.com/documentation/computers/raspberry-pi.html",
                    "source_anchor": "zero-series",
                    "language": "en",
                    "source_type": "documentation",
                    "published_at": None,
                    "updated_at": None,
                    "collected_at": "2026-08-27",
                    "indexed_at": "2026-08-27T12:00:00+09:00",
                    "document_version": "commit-test",
                    "license": "CC BY-SA 4.0",
                    "product_models": ["Compact Board"],
                    "use_cases": ["gpio_iot"],
                    "tasks": ["sensor_monitoring"],
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


class RecommendationAgentTests(unittest.TestCase):
    """결정적 추천 Agent의 필터·순위·계약 연동을 검사한다."""

    def test_engine_ranks_compact_iot_product_and_exposes_document_ids(self):
        """저성능 IoT 조건에서 소형 제품과 근거 문서가 우선되는지 확인한다."""

        decision = ProductRecommender(catalog()).recommend(conditions())
        self.assertEqual(decision.candidates[0].product_id, "compact-board")
        self.assertEqual(
            decision.candidates[0].evidence_document_ids, ["doc-compact"]
        )
        self.assertTrue(
            any("GPIO 핀 헤더" in item for item in decision.candidates[0].tradeoffs)
        )
        self.assertIn("사용 목적: GPIO·IoT", decision.candidates[0].matched_conditions)
        self.assertNotIn("gpio_iot", " ".join(decision.candidates[0].matched_conditions))

    def test_hard_camera_requirement_excludes_product_without_connector(self):
        """카메라 필수 조건이 커넥터 없는 제품을 제외하는지 확인한다."""

        decision = ProductRecommender(catalog()).recommend(
            conditions(
                use_case="camera_monitoring",
                task="camera_setup",
                performance_priority="high",
                camera_required=True,
            )
        )
        self.assertEqual(
            [candidate.product_id for candidate in decision.candidates], ["fast-board"]
        )

    def test_explicit_product_alias_is_supported(self):
        """사용자가 제품 별칭을 입력해도 올바른 제품을 찾는지 확인한다."""

        decision = ProductRecommender(catalog()).recommend(
            conditions(
                use_case=None,
                task=None,
                product_models=["Fast Board 8GB"],
                gpio_required=False,
            )
        )
        self.assertEqual(decision.candidates[0].product_id, "fast-board")

    def test_streamlit_widget_values_override_sllm_values(self):
        """화면에서 고른 값이 충돌하는 sLLM 추출값보다 우선하는지 확인한다."""

        form = RecommendationFormInput.from_widget_values(
            request_id="req-1",
            free_text="온습도 센서를 화면 없이 원격 확인하고 싶어요.",
            user_level_label="입문자",
            performance_priority_label="보통",
            wireless_required=True,
            camera_required=False,
            gpio_required=True,
            monitor_absent=True,
        )
        agent = RecommendationAgent(
            extractor=StaticExtractor(
                conditions(
                    wireless_required=False,
                    camera_required=True,
                    gpio_required=False,
                    monitor_available=True,
                    user_level="advanced",
                    performance_priority="high",
                )
            ),
            recommender=ProductRecommender(catalog()),
        )
        result = agent.recommend_form(form)
        merged = result.decision.conditions
        self.assertTrue(merged.wireless_required)
        self.assertFalse(merged.camera_required)
        self.assertTrue(merged.gpio_required)
        self.assertFalse(merged.monitor_available)
        self.assertEqual(merged.user_level, "beginner")
        self.assertEqual(merged.performance_priority, "medium")

    def test_agent_returns_safe_clarification_if_extraction_fails(self):
        """모든 조건 추출이 실패하면 임의 추천 대신 확인 질문을 주는지 확인한다."""

        class BrokenExtractor:
            """항상 예외를 발생시켜 fallback을 확인하는 테스트 대역이다."""

            def extract(self, survey):
                """잘못된 모델 출력 상황을 흉내 내기 위해 예외를 발생시킨다."""

                raise ValueError("invalid JSON")

        survey = SurveyResponse(
            answers=[
                SurveyAnswer(
                    question_id="purpose",
                    question="사용 목적은?",
                    answer="잘 모르겠어요.",
                )
            ]
        )
        result = RecommendationAgent(
            extractor=BrokenExtractor(),
            recommender=ProductRecommender(catalog()),
        ).recommend(survey)
        self.assertEqual(result.decision.status.value, "needs_clarification")
        self.assertEqual(result.extractor_mode.value, "clarification_fallback")

    def test_rag_evidence_builds_canonical_chat_response(self):
        """추천 후보와 공식 검색 근거가 최종 공통 응답으로 결합되는지 확인한다."""

        agent_result = RecommendationAgent(
            extractor=StaticExtractor(conditions()),
            recommender=ProductRecommender(catalog()),
        ).recommend(
            SurveyResponse(
                answers=[
                    SurveyAnswer(
                        question_id="purpose",
                        question="목적은?",
                        answer="센서 모니터링",
                    )
                ]
            )
        )
        response = build_recommendation_chat_response(
            request_id="req-1",
            agent_result=agent_result,
            search_response=search_response(),
        )
        self.assertEqual(response.status, "answered")
        self.assertEqual(response.products[0].product_id, "compact-board")
        self.assertEqual(response.products[0].product_model, "Compact Board")
        self.assertIn("[C1]", response.answer)
        self.assertIn("GPIO·IoT", response.answer)
        self.assertEqual(response.citations[0].document_id, "doc-compact")


if __name__ == "__main__":
    unittest.main()
