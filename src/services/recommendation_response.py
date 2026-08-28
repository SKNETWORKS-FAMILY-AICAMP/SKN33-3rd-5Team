"""추천 후보와 공식 RAG 결과를 팀 공통 ChatResponse로 조립한다."""

from __future__ import annotations

from src.contracts import (
    ChatCitation,
    ChatResponse,
    MediaItem,
    ProductRecommendation,
    SearchResponse,
)

from .recommendation_agent import RecommendationAgentResult


def _citation(result) -> ChatCitation:
    """검증된 검색 metadata 한 건을 화면용 인용 카드로 변환한다."""

    return ChatCitation(
        citation_id=result.citation_id,
        document_id=result.document_id,
        chunk_id=result.chunk_id,
        title=result.title,
        publisher=result.publisher,
        section=result.section,
        source_url=result.source_url,
        source_anchor=result.source_anchor,
        document_version=result.document_version,
        published_at=result.published_at,
        updated_at=result.updated_at,
        collected_at=result.collected_at,
        license=result.license,
        quote=result.content,
    )


def build_recommendation_chat_response(
    *,
    request_id: str,
    agent_result: RecommendationAgentResult,
    search_response: SearchResponse,
    language: str = "ko",
) -> ChatResponse:
    """공식 인용과 연결된 후보만 한국어 상태·설명과 함께 최종 응답에 담는다."""

    decision = agent_result.decision
    common = {
        "schema_version": "1.1.0",
        "request_id": request_id,
        "language": language,
        "conditions": decision.conditions,
        "warnings": agent_result.warnings,
    }

    if decision.status.value == "needs_clarification":
        return ChatResponse(
            **common,
            status="needs_clarification",
            answer="제품을 추천하려면 추가 조건이 필요합니다.",
            citations=[],
            products=[],
            media=[],
            clarification_questions=decision.clarification_questions,
        )
    if decision.status.value == "out_of_scope":
        return ChatResponse(
            **common,
            status="out_of_scope",
            answer="이 요청은 제품 추천 범위가 아닙니다.",
            citations=[],
            products=[],
            media=[],
            clarification_questions=[],
        )
    if decision.status.value == "no_match":
        return ChatResponse(
            **common,
            status="insufficient_evidence",
            answer="현재 공식 제품 카탈로그에서 모든 필수 조건을 만족하는 후보를 찾지 못했습니다.",
            citations=[],
            products=[],
            media=[],
            clarification_questions=decision.clarification_questions,
        )

    contract_products: list[ProductRecommendation] = []
    media: list[MediaItem] = []
    answer_lines: list[str] = []
    used_citation_ids: set[str] = set()
    result_by_citation = {item.citation_id: item for item in search_response.results}

    for candidate in decision.candidates:
        citation_ids = [
            item.citation_id
            for item in search_response.results
            if item.document_id in candidate.evidence_document_ids
        ]
        if not citation_ids:
            continue
        used_citation_ids.update(citation_ids)
        recommendation = ", ".join(candidate.matched_conditions) or "입력 조건 충족"
        limitations = list(candidate.tradeoffs)
        limitations.extend(
            f"필수 구성품: {accessory}" for accessory in candidate.required_accessories
        )
        contract_products.append(
            ProductRecommendation(
                product_id=candidate.product_id,
                product_model=candidate.name,
                recommendation=recommendation,
                matched_conditions=candidate.matched_conditions,
                limitations=limitations,
                citation_ids=citation_ids,
                product_url=candidate.product_url,
                image_url=candidate.image_url,
            )
        )
        answer_lines.append(
            f"{candidate.name}: {recommendation} [{citation_ids[0]}]"
        )
        if candidate.image_url is not None:
            media.append(
                MediaItem(
                    media_type="image",
                    title=f"{candidate.name} 공식 제품 이미지",
                    url=candidate.image_url,
                    source_citation_id=citation_ids[0],
                )
            )

    if not contract_products:
        return ChatResponse(
            **common,
            status="insufficient_evidence",
            answer="추천 후보는 찾았지만 이를 뒷받침하는 공식 검색 근거가 부족합니다.",
            citations=[],
            products=[],
            media=[],
            clarification_questions=[],
        )

    citations = [
        _citation(result_by_citation[citation_id])
        for citation_id in result_by_citation
        if citation_id in used_citation_ids
    ]
    return ChatResponse(
        **common,
        status="answered",
        answer="\n".join(answer_lines),
        citations=citations,
        products=contract_products,
        media=media,
        clarification_questions=[],
    )


__all__ = ["build_recommendation_chat_response"]
