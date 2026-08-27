from datetime import date

import pytest
from pydantic import ValidationError

from src.contracts import ChatCitation, ChatResponse, ConditionPayload, SearchResponse


def valid_conditions(**overrides: object) -> ConditionPayload:
    payload: dict[str, object] = {
        "schema_version": "1.0.0",
        "intent": "product_recommendation",
        "use_case": "education_coding",
        "product_models": None,
        "os_versions": None,
        "task": "desktop_programming",
        "performance_priority": "medium",
        "wireless_required": True,
        "camera_required": None,
        "gpio_required": None,
        "monitor_available": True,
        "remote_access_required": None,
        "user_level": "beginner",
        "needs_clarification": False,
        "clarification_questions": [],
    }
    payload.update(overrides)
    return ConditionPayload.model_validate(payload)


def test_condition_contract_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        valid_conditions(unapproved_field="value")


def test_condition_contract_requires_a_clarification_question() -> None:
    with pytest.raises(ValidationError):
        valid_conditions(needs_clarification=True, clarification_questions=[])


def test_condition_json_schema_forbids_extra_fields() -> None:
    schema = ConditionPayload.model_json_schema()
    assert schema["additionalProperties"] is False
    assert "allOf" in schema


def test_search_response_requires_ordered_citation_ids() -> None:
    with pytest.raises(ValidationError):
        SearchResponse.model_validate(
            {
                "schema_version": "1.0.0",
                "query_id": "query-0001",
                "query_language": "ko",
                "retrieval_method": "hybrid",
                "top_k": 5,
                "applied_filters": {
                    "product_models": [],
                    "use_cases": [],
                    "os_versions": [],
                    "source_types": [],
                    "official_only": True,
                },
                "results": [
                    {
                        "citation_id": "C2",
                        "rank": 1,
                        "document_id": "doc-1",
                        "chunk_id": "chunk-1",
                        "chunk_index": 0,
                        "title": "Title",
                        "publisher": "Raspberry Pi Ltd",
                        "section": "Section",
                        "content": "Official evidence",
                        "source_url": "https://www.raspberrypi.com/documentation/",
                        "source_anchor": None,
                        "language": "en",
                        "source_type": "documentation",
                        "published_at": None,
                        "updated_at": None,
                        "collected_at": "2026-08-27",
                        "indexed_at": "2026-08-27T09:00:00+09:00",
                        "document_version": None,
                        "license": "CC BY-SA 4.0",
                        "product_models": [],
                        "use_cases": [],
                        "tasks": [],
                        "categories": [],
                        "os_versions": [],
                        "document_checksum": "sha256:document",
                        "chunk_checksum": "sha256:chunk",
                        "parser_version": "1.0.0",
                        "official_verified": True,
                        "image_url": None,
                        "video_url": None,
                    }
                ],
            }
        )


def test_answered_chat_response_requires_a_known_inline_citation() -> None:
    citation = ChatCitation(
        citation_id="C1",
        document_id="rpi-doc-0001",
        chunk_id="rpi-doc-0001-0001",
        title="Raspberry Pi documentation",
        publisher="Raspberry Pi Ltd",
        section="Getting started",
        source_url="https://www.raspberrypi.com/documentation/",
        source_anchor=None,
        document_version="commit-abc",
        published_at=None,
        updated_at=None,
        collected_at=date(2026, 8, 27),
        license="CC BY-SA 4.0",
        quote="Install Raspberry Pi OS using Raspberry Pi Imager.",
    )
    response = ChatResponse(
        schema_version="1.0.0",
        request_id="req-0001",
        status="answered",
        language="ko",
        answer="Raspberry Pi Imager를 사용해 설치할 수 있습니다. [C1]",
        conditions=valid_conditions(),
        citations=[citation],
        products=[],
        media=[],
        clarification_questions=[],
        warnings=[],
    )
    assert response.citations[0].chunk_id == "rpi-doc-0001-0001"


def test_answered_chat_response_rejects_an_unknown_citation() -> None:
    with pytest.raises(ValidationError):
        ChatResponse(
            schema_version="1.0.0",
            request_id="req-0002",
            status="answered",
            language="ko",
            answer="근거가 있습니다. [C9]",
            conditions=valid_conditions(),
            citations=[],
            products=[],
            media=[],
            clarification_questions=[],
            warnings=[],
        )
