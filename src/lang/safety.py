"""Deterministic safety gates for document-grounded Raspberry Pi answers"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Sequence


SafetyStatus = Literal[
    "allowed",
    "needs_clarification",
    "insufficient_evidence",
    "out_of_scope",
    "safety_blocked",
]


_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"이전\s*(?:지시|명령|규칙).{0,20}(?:무시|취소|삭제)", re.IGNORECASE),
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"(?:system|developer)\s*(?:prompt|message)", re.IGNORECASE),
    re.compile(r"(?:시스템|개발자)\s*(?:프롬프트|메시지).{0,20}(?:보여|공개|출력)", re.IGNORECASE),
    re.compile(r"(?:출처|근거|URL|링크).{0,12}(?:만들|조작|지어내)", re.IGNORECASE),
    re.compile(r"(?:API\s*key|토큰|비밀번호).{0,20}(?:보여|공개|출력)", re.IGNORECASE),
)

_COMMERCE_PATTERNS = (
    re.compile(r"실시간\s*(?:가격|재고)", re.IGNORECASE),
    re.compile(r"(?:최저가|가장\s*저렴한|제일\s*싼|할인\s*가격)", re.IGNORECASE),
    re.compile(r"(?:가격|재고).{0,15}(?:알려|확인|조회|비교|추천)", re.IGNORECASE),
    re.compile(r"(?:재고\s*(?:수량|현황|유무)|품절\s*여부)", re.IGNORECASE),
    re.compile(r"(?:쇼핑몰|판매처|구매처).{0,20}(?:추천|순위|비교)", re.IGNORECASE),
)

_UNSUPPORTED_MODIFICATION_PATTERNS = (
    re.compile(r"오버\s*클럭", re.IGNORECASE),
    re.compile(r"비공식.{0,12}(?:개조|펌웨어|드라이버|설정)", re.IGNORECASE),
    re.compile(r"(?:보호|안전|인증).{0,10}(?:우회|해제|무력화)", re.IGNORECASE),
    re.compile(r"(?:전압|클럭).{0,10}(?:강제|개조|해제)", re.IGNORECASE),
)

_CITATION_PATTERN = re.compile(r"\[(C[1-9][0-9]*)\]")
_URL_PATTERN = re.compile(
    r"(?i)(?:https?://|www\.|(?:raspberrypi|github)\.com/)[^\s)>\]]+"
)


@dataclass(frozen=True)
class SafetyDecision:
    """A deterministic decision made before answer generation."""

    status: SafetyStatus
    reason_code: str
    message: str

    @property
    def allowed(self) -> bool:
        return self.status == "allowed"


class AnswerSafetyError(ValueError):
    """Raised when generated text violates citation or metadata rules."""


def _matches_any(question: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    return any(pattern.search(question) for pattern in patterns)


def evaluate_request(
    question: str,
    *,
    evidence_count: int | None = None,
) -> SafetyDecision:
    """Classify a question before retrieval or answer generation.

    Injection detection runs first because a malicious request can also contain
    price, stock, or modification keywords. Evidence availability is evaluated
    only after the question itself is considered in scope.
    """

    normalized = question.strip()
    if not normalized:
        return SafetyDecision(
            status="needs_clarification",
            reason_code="empty_question",
            message="질문을 한 문장 이상 입력해 주세요.",
        )
    if _matches_any(normalized, _PROMPT_INJECTION_PATTERNS):
        return SafetyDecision(
            status="safety_blocked",
            reason_code="prompt_injection",
            message=(
                "사용자 입력의 명령은 실행하지 않으며, 시스템 지시·비밀정보·"
                "확인되지 않은 출처를 제공할 수 없습니다."
            ),
        )
    if _matches_any(normalized, _COMMERCE_PATTERNS):
        return SafetyDecision(
            status="out_of_scope",
            reason_code="live_commerce_data",
            message=(
                "실시간 가격·재고·판매처 순위는 PiCare의 공식 기술 문서 "
                "지원 범위에 포함되지 않습니다."
            ),
        )
    if _matches_any(normalized, _UNSUPPORTED_MODIFICATION_PATTERNS):
        return SafetyDecision(
            status="out_of_scope",
            reason_code="unsupported_modification",
            message=(
                "비공식 오버클럭·개조·안전 장치 우회 절차는 안내하지 않습니다. "
                "공식 설치·구성·문제 해결 방법을 물어봐 주세요."
            ),
        )
    if evidence_count is not None and evidence_count <= 0:
        return SafetyDecision(
            status="insufficient_evidence",
            reason_code="no_official_evidence",
            message=(
                "검색된 공식 문서에서 질문을 뒷받침할 근거를 찾지 못했습니다. "
                "추측하지 않고 답변을 보류합니다."
            ),
        )
    return SafetyDecision(
        status="allowed",
        reason_code="allowed",
        message="공식 검색 근거 안에서 답변을 생성할 수 있습니다.",
    )


def extract_citation_ids(answer: str) -> set[str]:
    """Return citation IDs referenced by generated answer text."""

    return set(_CITATION_PATTERN.findall(answer))


def validate_grounded_answer(
    answer: str,
    *,
    allowed_citation_ids: Sequence[str],
) -> set[str]:
    """Reject generated answers that invent citations, URLs, or uncited claims.

    Source cards are assembled by server code from retrieval metadata. The LLM
    therefore returns answer prose with citation IDs only and never a URL.
    """

    normalized = answer.strip()
    if not normalized:
        raise AnswerSafetyError("답변 본문이 비어 있습니다.")
    if _URL_PATTERN.search(normalized):
        raise AnswerSafetyError(
            "LLM 답변에 URL이 포함되었습니다. URL은 검색 metadata로만 구성합니다."
        )

    allowed = set(allowed_citation_ids)
    referenced = extract_citation_ids(normalized)
    if not referenced:
        raise AnswerSafetyError("근거 기반 답변에는 최소 하나의 인용 ID가 필요합니다.")
    unknown = referenced - allowed
    if unknown:
        raise AnswerSafetyError(
            f"검색 결과에 없는 인용 ID가 포함되었습니다: {', '.join(sorted(unknown))}"
        )

    uncited_lines = []
    for line in normalized.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not _CITATION_PATTERN.search(stripped):
            uncited_lines.append(stripped)
    if uncited_lines:
        raise AnswerSafetyError(
            "인용 ID가 없는 답변 문단이 있습니다: " + " | ".join(uncited_lines)
        )
    return referenced


__all__ = [
    "AnswerSafetyError",
    "SafetyDecision",
    "SafetyStatus",
    "evaluate_request",
    "extract_citation_ids",
    "validate_grounded_answer",
]
