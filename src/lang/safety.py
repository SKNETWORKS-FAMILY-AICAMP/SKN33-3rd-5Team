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

_PROMPT_DISCLOSURE_PATTERNS = (
    re.compile(
        r"(?:(?:시스템|개발자|내부)\s*)?(?:프롬프트|prompt).{0,20}"
        r"(?:보여|공개|출력|알려|말해)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:보여|공개|출력|알려).{0,20}"
        r"(?:(?:시스템|개발자|내부)\s*)?(?:프롬프트|prompt)",
        re.IGNORECASE,
    ),
)

_COMMERCE_PATTERNS = (
    re.compile(r"실시간\s*(?:가격|재고)", re.IGNORECASE),
    re.compile(r"(?:최저가|가장\s*저렴한|제일\s*싼|할인\s*가격)", re.IGNORECASE),
    re.compile(r"(?:가격|재고).{0,15}(?:알려|확인|조회|비교|추천)", re.IGNORECASE),
    re.compile(r"(?:재고\s*(?:수량|현황|유무)|품절\s*여부)", re.IGNORECASE),
    re.compile(r"(?:쇼핑몰|판매처|구매처).{0,20}(?:추천|순위|비교)", re.IGNORECASE),
)

# 현재 로컬 공식 corpus에는 A/S·보증·리콜 공지가 포함되지 않는다. 이 질문은
# Dense 검색이 의미적으로 가까운 일반 문서를 반환하더라도 근거 부족으로 보류한다.
_SUPPORT_RECALL_PATTERNS = (
    re.compile(r"(?:리콜|recall)", re.IGNORECASE),
    re.compile(r"(?:a\s*/?\s*s)(?=\s|[가-힣]|$)|after[-\s]?sales|애프터\s*서비스", re.IGNORECASE),
    re.compile(r"(?:서비스\s*센터|수리\s*(?:접수|신청)|보증\s*(?:기간|수리)|warranty)", re.IGNORECASE),
)

_UNSUPPORTED_MODIFICATION_PATTERNS = (
    re.compile(r"오버\s*클럭", re.IGNORECASE),
    re.compile(r"비공식.{0,12}(?:개조|펌웨어|드라이버|설정)", re.IGNORECASE),
    re.compile(r"(?:보호|안전|인증).{0,10}(?:우회|해제|무력화)", re.IGNORECASE),
    re.compile(r"(?:전압|클럭).{0,10}(?:강제|개조|해제)", re.IGNORECASE),
)

_CITATION_PATTERN = re.compile(r"\[(C[1-9][0-9]*)\]")
INSUFFICIENT_EVIDENCE_MARKER = "[INSUFFICIENT_EVIDENCE]"
_CITATION_SUFFIX_PATTERN = re.compile(r"(?:\s*\[C[1-9][0-9]*\])+\s*$")
_MARKDOWN_HEADING_PATTERN = re.compile(
    r"^(?:#{1,6}\s+\S.*|\*\*\s*\S.*?\s*\*\*|__\s*\S.*?\s*__)$"
)
_LIST_ITEM_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?P<marker>[-+*]|[1-9][0-9]*[.)])\s+\S"
)
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
    if _matches_any(normalized, _PROMPT_DISCLOSURE_PATTERNS):
        return SafetyDecision(
            status="safety_blocked",
            reason_code="prompt_disclosure",
            message=(
                "시스템·개발자 프롬프트와 내부 지시는 공개할 수 없습니다. "
                "Raspberry Pi 제품·설치·문제 해결에 관해 질문해 주세요."
            ),
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
    if _matches_any(normalized, _SUPPORT_RECALL_PATTERNS):
        return SafetyDecision(
            status="insufficient_evidence",
            reason_code="support_recall_corpus_unavailable",
            message=(
                "현재 로컬 공식 corpus에는 A/S·보증·리콜 공지가 포함되지 않아 "
                "확인 가능한 근거가 없습니다. 추측하지 않고 답변을 보류합니다."
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


def is_evidence_abstention(answer: str) -> bool:
    """Only the exact protocol marker requests a model-side abstention."""

    return answer.strip() == INSUFFICIENT_EVIDENCE_MARKER


def has_korean_prose(answer: str) -> bool:
    """A minimal script check, not a judgement of Korean fluency or relevance."""

    prose = re.sub(r"```[\s\S]*?```|`[^`]*`", "", answer)
    return bool(re.search(r"[가-힣]", prose))


def _grounded_content_blocks(answer: str) -> list[str]:
    """Group prose by paragraph or top-level Markdown list item.

    Markdown headings are structural labels, not factual content. Wrapped lines
    and child items remain part of their parent paragraph/list item, including
    across blank lines, so one citation at the end can ground the complete block.
    """

    blocks: list[str] = []
    current_lines: list[str] = []
    current_list_indent: int | None = None
    current_list_kind: Literal["ordered", "unordered"] | None = None
    pending_blank = False

    def flush_current() -> None:
        nonlocal current_lines, current_list_indent, current_list_kind, pending_blank
        if current_lines:
            blocks.append("\n".join(current_lines))
        current_lines = []
        current_list_indent = None
        current_list_kind = None
        pending_blank = False

    for line in answer.splitlines():
        stripped = line.strip()
        if not stripped:
            if current_list_indent is None:
                flush_current()
            else:
                pending_blank = True
            continue
        if _MARKDOWN_HEADING_PATTERN.fullmatch(stripped):
            flush_current()
            continue

        expanded = line.expandtabs(4)
        list_item = _LIST_ITEM_PATTERN.match(expanded)
        if list_item:
            indent = len(list_item.group("indent"))
            marker = list_item.group("marker")
            list_kind: Literal["ordered", "unordered"] = (
                "ordered" if marker[0].isdigit() else "unordered"
            )
            is_child = current_list_indent is not None and (
                indent > current_list_indent
                or (current_list_kind == "ordered" and list_kind == "unordered")
            )
            if current_lines and not is_child:
                flush_current()
            if not current_lines:
                current_list_indent = indent
                current_list_kind = list_kind
        elif pending_blank and current_list_indent is not None:
            continuation_indent = len(expanded) - len(expanded.lstrip())
            if continuation_indent <= current_list_indent:
                flush_current()

        current_lines.append(stripped)
        pending_blank = False

    flush_current()
    return blocks


def validate_grounded_answer(
    answer: str,
    *,
    allowed_citation_ids: Sequence[str],
    require_korean: bool = False,
) -> set[str]:
    """Reject generated answers that invent citations, URLs, or uncited claims.

    Source cards are assembled by server code from retrieval metadata. The LLM
    therefore returns answer prose with citation IDs only and never a URL.
    """

    normalized = answer.strip()
    if not normalized:
        raise AnswerSafetyError("답변 본문이 비어 있습니다.")
    if INSUFFICIENT_EVIDENCE_MARKER in normalized:
        raise AnswerSafetyError("근거 부족 표식은 다른 답변과 섞어 출력할 수 없습니다.")
    if require_korean and not has_korean_prose(normalized):
        raise AnswerSafetyError("답변에 한국어 설명이 없습니다.")
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

    uncited_blocks = [
        block
        for block in _grounded_content_blocks(normalized)
        if not _CITATION_SUFFIX_PATTERN.search(block)
    ]
    if uncited_blocks:
        raise AnswerSafetyError(
            "마지막에 인용 ID가 없는 답변 문단 또는 목록 항목이 있습니다: "
            + " | ".join(block.replace("\n", " ") for block in uncited_blocks)
        )
    return referenced


__all__ = [
    "INSUFFICIENT_EVIDENCE_MARKER",
    "AnswerSafetyError",
    "SafetyDecision",
    "SafetyStatus",
    "evaluate_request",
    "extract_citation_ids",
    "has_korean_prose",
    "is_evidence_abstention",
    "validate_grounded_answer",
]
