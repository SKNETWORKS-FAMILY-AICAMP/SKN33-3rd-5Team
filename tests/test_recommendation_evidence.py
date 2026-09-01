from datetime import datetime

from src.contracts import ConditionPayload
from src.recommendation.engine import ProductRecommender
from src.recommendation.schema import ProductCatalog


def _catalog_with_field_evidence() -> ProductCatalog:
    return ProductCatalog.model_validate(
        {
            "schema_version": "1.1.0",
            "catalog_version": "test-field-evidence",
            "generated_at": datetime.fromisoformat("2026-09-01T10:00:00+09:00"),
            "sources": [
                {
                    "document_id": document_id,
                    "title": document_id,
                    "source_url": "https://www.raspberrypi.com/documentation/",
                    "retrieved_at": "2026-09-01",
                    "license": "CC BY-SA 4.0",
                }
                for document_id in (
                    "doc-beginner",
                    "doc-spec",
                    "doc-task",
                    "doc-tier",
                    "doc-use-case",
                )
            ],
            "products": [
                {
                    "product_id": "evidence-board",
                    "name": "Evidence Board",
                    "aliases": [],
                    "family": "flagship",
                    "is_current": True,
                    "memory_options_gb": [4],
                    "capabilities": {
                        "wireless": True,
                        "ethernet": True,
                        "gpio_header": "populated",
                        "camera_connector_count": 1,
                        "display_output_count": 1,
                        "built_in_keyboard": False,
                    },
                    "display": {
                        "cpu": "Test CPU",
                        "memory": "4 GB",
                        "wireless": "Wi-Fi",
                        "dimensions": None,
                    },
                    "recommendation_profile": {
                        "performance_tier": "high",
                        "beginner_friendly": True,
                        "recommended_use_cases": ["education_coding"],
                        "recommended_tasks": ["desktop_programming"],
                    },
                    "evidence_by_field": {
                        "identity": ["doc-spec"],
                        "wireless": ["doc-spec"],
                        "ethernet": ["doc-spec"],
                        "gpio_header": ["doc-spec"],
                        "camera_connector_count": ["doc-spec"],
                        "display_output_count": ["doc-spec"],
                        "built_in_keyboard": ["doc-spec"],
                        "cpu": ["doc-spec"],
                        "memory": ["doc-spec"],
                        "performance_tier": ["doc-tier"],
                        "beginner_friendly": ["doc-beginner"],
                        "recommended_use_cases": ["doc-use-case"],
                        "recommended_tasks": ["doc-task"],
                    },
                    "document_ids": [
                        "doc-beginner",
                        "doc-spec",
                        "doc-task",
                        "doc-tier",
                        "doc-use-case",
                    ],
                    "product_url": "https://www.raspberrypi.com/products/",
                    "image_url": None,
                }
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


def test_candidate_preserves_evidence_for_each_recommendation_field() -> None:
    candidate = ProductRecommender(_catalog_with_field_evidence()).recommend(
        _conditions()
    ).candidates[0]

    assert candidate.evidence_by_field.recommended_use_cases == ["doc-use-case"]
    assert candidate.evidence_by_field.recommended_tasks == ["doc-task"]
    assert candidate.evidence_by_field.beginner_friendly == ["doc-beginner"]
    assert candidate.evidence_document_ids == [
        "doc-beginner",
        "doc-spec",
        "doc-task",
        "doc-tier",
        "doc-use-case",
    ]
