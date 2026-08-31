"""Qwen 답변의 인용 검증과 1회 형식 수정 재생성을 공통 처리한다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from src.lang import (
    AnswerSafetyError,
    PromptEvidence,
    build_citation_repair_messages,
    is_evidence_abstention,
    validate_grounded_answer,
)
from src.rag_to_llm import AnswerGenerator, GenerationResult


def _safety_reason_code(error: AnswerSafetyError) -> str:
    """원문을 노출하지 않고 검증 실패 유형만 trace에 기록한다."""

    message = str(error)
    if "URL" in message:
        return "url_in_answer"
    if "최소 하나의 인용" in message:
        return "missing_citation"
    if "검색 결과에 없는 인용" in message:
        return "unknown_citation"
    if "인용 ID 없는 답변 문단" in message:
        return "uncited_content_block"
    if "본문이 비어" in message:
        return "empty_answer"
    return "citation_validation_failed"


class CitationRepairError(AnswerSafetyError):
    """Qwen의 1회 형식 수정 뒤에도 인용 검증에 실패한 경우다."""

    def __init__(self, *, first_error: AnswerSafetyError, final_error: AnswerSafetyError) -> None:
        self.first_reason_code = _safety_reason_code(first_error)
        self.final_reason_code = _safety_reason_code(final_error)
        super().__init__("Qwen citation repair did not pass grounded-answer validation.")


@dataclass(frozen=True)
class ValidatedGeneration:
    """생성 결과와 인용·재생성 실행 정보를 보관한다.

    ``abstained``인 경우는 모델이 명시적으로 근거 부족을 선언한 정상 종료다.
    이때는 인용 검증이나 형식 수정 재생성을 시도하지 않는다.
    """

    generation: GenerationResult
    used_citation_ids: set[str]
    attempts: int
    repair_attempted: bool
    abstained: bool = False


def generate_validated_grounded_answer(
    *,
    generator: AnswerGenerator,
    messages: Sequence[Mapping[str, str]],
    evidence: Sequence[PromptEvidence],
) -> ValidatedGeneration:
    """Qwen 출력만 1회 형식 수정 후 다시 엄격하게 검증한다.

    Template·테스트 생성기는 기존처럼 한 번만 검증한다. 실제 Qwen만 재생성해야
    로컬 검증 흐름의 성격을 바꾸지 않으며 GPU 비용도 예측 가능하다.
    """

    allowed_citation_ids = [item.citation_id for item in evidence]
    first = generator.generate(messages, evidence)
    if is_evidence_abstention(first.text):
        return ValidatedGeneration(
            generation=first,
            used_citation_ids=set(),
            attempts=1,
            repair_attempted=False,
            abstained=True,
        )
    try:
        used = validate_grounded_answer(
            first.text,
            allowed_citation_ids=allowed_citation_ids,
            require_korean=True,
        )
    except AnswerSafetyError as first_error:
        if first.provider != "huggingface":
            raise
        repair_messages = build_citation_repair_messages(
            messages,
            invalid_answer=first.text,
            evidence=evidence,
        )
        repaired = generator.generate(repair_messages, evidence)
        try:
            used = validate_grounded_answer(
                repaired.text,
                allowed_citation_ids=allowed_citation_ids,
                require_korean=True,
            )
        except AnswerSafetyError as final_error:
            raise CitationRepairError(first_error=first_error, final_error=final_error) from final_error
        return ValidatedGeneration(
            generation=repaired,
            used_citation_ids=used,
            attempts=2,
            repair_attempted=True,
        )
    return ValidatedGeneration(
        generation=first,
        used_citation_ids=used,
        attempts=1,
        repair_attempted=False,
    )


__all__ = [
    "CitationRepairError",
    "ValidatedGeneration",
    "generate_validated_grounded_answer",
]
