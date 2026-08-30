"""Contract tests for isolated sLLM-to-RAG and RAG-to-chat adapters."""

from __future__ import annotations

import unittest
from datetime import datetime

from src.contracts import ConditionPayload
from src.rag import RagFilters, RagResult
from src.services.integration_adapters import (
    IntegrationAdapterError,
    RagResultMetadata,
    condition_payload_to_rag_filters,
    manifest_to_rag_result_metadata,
    rag_results_to_search_response,
)


def condition_payload(**updates: object) -> ConditionPayload:
    payload: dict[str, object] = {
        "schema_version": "1.1.0",
        "intent": "troubleshooting",
        "use_case": "camera_monitoring",
        "product_models": ["Raspberry Pi 5"],
        "os_versions": ["Raspberry Pi OS"],
        "task": "troubleshooting",
        "performance_priority": None,
        "wireless_required": True,
        "camera_required": True,
        "gpio_required": None,
        "monitor_available": None,
        "remote_access_required": None,
        "user_level": "beginner",
        "needs_clarification": False,
        "clarification_questions": [],
    }
    payload.update(updates)
    return ConditionPayload.model_validate(payload)


def rag_result(*, retrieved_at: str = "2026-08-27", rank: int = 1) -> RagResult:
    return RagResult(
        rank=rank,
        content="Connect the camera cable while the Raspberry Pi is powered off.",
        chunk_id="camera-001",
        document_id="camera-guide",
        title="Camera hardware",
        section="Install a Raspberry Pi camera",
        source_url="https://www.raspberrypi.com/documentation/accessories/camera.html",
        license="CC BY-SA 4.0",
        retrieved_at=retrieved_at,
        document_version="commit-test",
    )


def metadata(*, official_verified: bool = True) -> RagResultMetadata:
    return RagResultMetadata(
        chunk_index=0,
        publisher="Raspberry Pi Ltd",
        language="en",
        source_type="documentation",
        indexed_at=datetime.fromisoformat("2026-08-28T12:00:00+09:00"),
        document_checksum="sha256:document",
        chunk_checksum="sha256:chunk",
        parser_version="1.0.0",
        official_verified=official_verified,
        product_models=("Raspberry Pi 5",),
        use_cases=("camera_monitoring",),
        tasks=("troubleshooting",),
        categories=("camera",),
        os_versions=("Raspberry Pi OS",),
    )


class IntegrationAdapterTests(unittest.TestCase):
    def test_condition_payload_maps_only_explicit_rag_filters(self) -> None:
        filters = condition_payload_to_rag_filters(condition_payload())

        self.assertEqual(filters.product_models, ("Raspberry Pi 5",))
        self.assertEqual(filters.use_cases, ("camera_monitoring",))
        self.assertEqual(filters.os_versions, ("Raspberry Pi OS",))
        self.assertEqual(filters.source_types, ())
        self.assertTrue(filters.official_only)

    def test_null_conditions_become_unrestricted_filter_tuples(self) -> None:
        filters = condition_payload_to_rag_filters(
            condition_payload(
                use_case=None,
                product_models=None,
                os_versions=None,
            )
        )

        self.assertEqual(filters, RagFilters(official_only=True))

    def test_rag_result_maps_retrieved_at_to_collected_at(self) -> None:
        filters = condition_payload_to_rag_filters(condition_payload())
        response = rag_results_to_search_response(
            [rag_result(retrieved_at="2026-08-27T23:30:00+09:00")],
            query_id="query-1",
            query_language="ko",
            retrieval_method="hybrid",
            top_k=5,
            applied_filters=filters,
            metadata_by_chunk_id={"camera-001": metadata()},
        )

        result = response.results[0]
        self.assertEqual(result.citation_id, "C1")
        self.assertEqual(result.collected_at.isoformat(), "2026-08-27")
        self.assertEqual(result.publisher, "Raspberry Pi Ltd")
        self.assertEqual(response.applied_filters.product_models, ["Raspberry Pi 5"])
        self.assertEqual(response.applied_filters.document_ids, [])

    def test_manifest_metadata_adapter_preserves_canonical_chunk_metadata(self) -> None:
        mapped = manifest_to_rag_result_metadata(
            {
                "chunks": [
                    {
                        "chunk_id": "camera-001",
                        "chunk_index": 0,
                        "publisher": "Raspberry Pi Ltd",
                        "language": "en",
                        "source_type": "documentation",
                        "document_checksum": "sha256:document",
                        "chunk_checksum": "sha256:chunk",
                        "parser_version": "asciidoc-semantic-2.0.0",
                        "official_verified": True,
                        "source_anchor": "camera",
                        "published_at": None,
                        "updated_at": None,
                        "product_models": ["Raspberry Pi 5"],
                        "use_cases": ["camera_monitoring"],
                        "tasks": ["camera_setup"],
                        "categories": ["camera"],
                        "os_versions": ["Raspberry Pi OS"],
                        "image_url": None,
                        "video_url": None,
                    }
                ]
            },
            indexed_at=datetime.fromisoformat("2026-08-30T12:00:00+00:00"),
        )

        self.assertEqual(mapped["camera-001"].source_anchor, "camera")
        self.assertEqual(mapped["camera-001"].tasks, ("camera_setup",))

    def test_missing_metadata_is_not_silently_invented(self) -> None:
        with self.assertRaisesRegex(IntegrationAdapterError, "metadata가 없습니다"):
            rag_results_to_search_response(
                [rag_result()],
                query_id="query-1",
                query_language="ko",
                retrieval_method="bm25",
                top_k=3,
                applied_filters=RagFilters(),
                metadata_by_chunk_id={},
            )

    def test_invalid_retrieved_at_is_rejected(self) -> None:
        with self.assertRaisesRegex(IntegrationAdapterError, "collected_at"):
            rag_results_to_search_response(
                [rag_result(retrieved_at="not-a-date")],
                query_id="query-1",
                query_language="ko",
                retrieval_method="bm25",
                top_k=3,
                applied_filters=RagFilters(),
                metadata_by_chunk_id={"camera-001": metadata()},
            )

    def test_unverified_result_is_rejected(self) -> None:
        with self.assertRaisesRegex(IntegrationAdapterError, "공식 검증되지 않은"):
            rag_results_to_search_response(
                [rag_result()],
                query_id="query-1",
                query_language="ko",
                retrieval_method="dense",
                top_k=3,
                applied_filters=RagFilters(),
                metadata_by_chunk_id={
                    "camera-001": metadata(official_verified=False)
                },
            )


if __name__ == "__main__":
    unittest.main()
