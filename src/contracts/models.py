"""Canonical, versioned contracts for integration between project modules."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


CONTRACT_VERSION = "1.1.0"

NonEmptyText = Annotated[str, Field(min_length=1)]
NonEmptyTextList = Annotated[list[NonEmptyText], Field(min_length=1)]

UseCase = Literal[
    "education_coding",
    "desktop_computing",
    "home_server",
    "camera_monitoring",
    "smart_farm_monitoring",
    "headless_remote_management",
    "gpio_iot",
]
Intent = Literal[
    "product_recommendation",
    "product_comparison",
    "how_to",
    "troubleshooting",
    "support_recall",
    "out_of_scope",
]
Task = Literal[
    "desktop_programming",
    "os_installation",
    "system_configuration",
    "remote_access",
    "camera_setup",
    "gpio_setup",
    "sensor_monitoring",
    "server_operation",
    "troubleshooting",
    "support_recall",
]
SourceType = Literal[
    "documentation",
    "product_page",
    "faq",
    "release_note",
    "support_notice",
    "recall_notice",
]
AnswerStatus = Literal[
    "answered",
    "needs_clarification",
    "insufficient_evidence",
    "out_of_scope",
    "safety_blocked",
    "error",
]


class StrictContract(BaseModel):
    """Reject undeclared fields so independently developed modules cannot drift."""

    model_config = ConfigDict(extra="forbid")


class ConditionPayload(StrictContract):
    """Complete sLLM condition output; unmentioned user constraints are null."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"needs_clarification": {"const": True}}},
                    "then": {"properties": {"clarification_questions": {"minItems": 1}}},
                    "else": {"properties": {"clarification_questions": {"maxItems": 0}}},
                }
            ]
        },
    )

    schema_version: Literal[CONTRACT_VERSION]
    intent: Intent
    use_case: UseCase | None
    product_models: NonEmptyTextList | None
    os_versions: NonEmptyTextList | None
    task: Task | None
    performance_priority: Literal["low", "medium", "high"] | None
    wireless_required: bool | None
    camera_required: bool | None
    gpio_required: bool | None
    monitor_available: bool | None
    remote_access_required: bool | None
    user_level: Literal["beginner", "intermediate", "advanced"] | None
    needs_clarification: bool
    clarification_questions: list[NonEmptyText]

    @model_validator(mode="after")
    def validate_clarification(self) -> "ConditionPayload":
        if self.needs_clarification and not self.clarification_questions:
            raise ValueError("clarification_questions is required when needs_clarification is true")
        if not self.needs_clarification and self.clarification_questions:
            raise ValueError("clarification_questions must be empty when needs_clarification is false")
        return self


class SearchFilters(StrictContract):
    """Metadata filters applied by the integration layer before retrieval."""

    product_models: list[NonEmptyText]
    use_cases: list[NonEmptyText]
    os_versions: list[NonEmptyText]
    source_types: list[SourceType]
    official_only: bool


class SearchResultMetadata(StrictContract):
    """One citation-safe retrieved chunk returned by the RAG module."""

    citation_id: Annotated[str, Field(pattern=r"^C[1-9][0-9]*$")]
    rank: Annotated[int, Field(ge=1)]
    document_id: NonEmptyText
    chunk_id: NonEmptyText
    chunk_index: Annotated[int, Field(ge=0)]
    title: NonEmptyText
    publisher: NonEmptyText
    section: NonEmptyText
    content: NonEmptyText
    source_url: HttpUrl
    source_anchor: NonEmptyText | None
    language: Annotated[str, Field(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")]
    source_type: SourceType
    published_at: date | None
    updated_at: date | None
    collected_at: date
    indexed_at: datetime
    document_version: NonEmptyText | None
    license: NonEmptyText
    product_models: list[NonEmptyText]
    use_cases: list[NonEmptyText]
    tasks: list[NonEmptyText]
    categories: list[NonEmptyText]
    os_versions: list[NonEmptyText]
    document_checksum: NonEmptyText
    chunk_checksum: NonEmptyText
    parser_version: NonEmptyText
    official_verified: Literal[True]
    image_url: HttpUrl | None
    video_url: HttpUrl | None


class SearchResponse(StrictContract):
    """RAG-to-chatbot response contract."""

    schema_version: Literal[CONTRACT_VERSION]
    query_id: NonEmptyText
    query_language: Annotated[str, Field(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")]
    retrieval_method: Literal["dense", "bm25", "hybrid"]
    top_k: Annotated[int, Field(ge=1, le=20)]
    applied_filters: SearchFilters
    results: list[SearchResultMetadata]

    @model_validator(mode="after")
    def validate_rank_and_citation_order(self) -> "SearchResponse":
        for expected_rank, result in enumerate(self.results, start=1):
            if result.rank != expected_rank or result.citation_id != f"C{expected_rank}":
                raise ValueError("results must be ordered and use citation IDs C1, C2, ...")
        chunk_ids = [result.chunk_id for result in self.results]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("results must not contain duplicate chunk_id values")
        return self


class ChatCitation(StrictContract):
    """Server-built source card referenced from the answer with [C1], [C2], ..."""

    citation_id: Annotated[str, Field(pattern=r"^C[1-9][0-9]*$")]
    document_id: NonEmptyText
    chunk_id: NonEmptyText
    title: NonEmptyText
    publisher: NonEmptyText
    section: NonEmptyText
    source_url: HttpUrl
    source_anchor: NonEmptyText | None
    document_version: NonEmptyText | None
    published_at: date | None
    updated_at: date | None
    collected_at: date
    license: NonEmptyText
    quote: NonEmptyText


class ProductRecommendation(StrictContract):
    """Structured card for product recommendation or comparison UI."""

    product_id: NonEmptyText
    product_model: NonEmptyText
    recommendation: NonEmptyText
    matched_conditions: list[NonEmptyText]
    limitations: list[NonEmptyText]
    citation_ids: NonEmptyTextList
    product_url: HttpUrl
    image_url: HttpUrl | None


class MediaItem(StrictContract):
    """Official image or video linked to a verified citation."""

    media_type: Literal["image", "video"]
    title: NonEmptyText
    url: HttpUrl
    source_citation_id: Annotated[str, Field(pattern=r"^C[1-9][0-9]*$")]


class ChatResponse(StrictContract):
    """Stable chatbot-to-Streamlit response contract."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"status": {"const": "answered"}}},
                    "then": {"properties": {"citations": {"minItems": 1}}},
                },
                {
                    "if": {"properties": {"status": {"const": "needs_clarification"}}},
                    "then": {"properties": {"clarification_questions": {"minItems": 1}}},
                },
            ]
        },
    )

    schema_version: Literal[CONTRACT_VERSION]
    request_id: NonEmptyText
    status: AnswerStatus
    language: Annotated[str, Field(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")]
    answer: NonEmptyText
    conditions: ConditionPayload | None
    citations: list[ChatCitation]
    products: list[ProductRecommendation]
    media: list[MediaItem]
    clarification_questions: list[NonEmptyText]
    warnings: list[NonEmptyText]

    @model_validator(mode="after")
    def validate_status_and_citations(self) -> "ChatResponse":
        citation_ids = {citation.citation_id for citation in self.citations}
        if len(citation_ids) != len(self.citations):
            raise ValueError("citations must not contain duplicate citation_id values")
        referenced_ids = set(re.findall(r"\[(C[1-9][0-9]*)\]", self.answer))
        if not referenced_ids.issubset(citation_ids):
            raise ValueError("answer references a citation ID missing from citations")
        if self.status == "answered" and (not self.citations or not referenced_ids):
            raise ValueError("answered responses require at least one inline citation")
        if self.status == "needs_clarification" and not self.clarification_questions:
            raise ValueError("needs_clarification responses require clarification_questions")
        product_citation_ids = {item for product in self.products for item in product.citation_ids}
        media_citation_ids = {item.source_citation_id for item in self.media}
        if not product_citation_ids.issubset(citation_ids):
            raise ValueError("product cards reference a citation ID missing from citations")
        if not media_citation_ids.issubset(citation_ids):
            raise ValueError("media items reference a citation ID missing from citations")
        return self
