"""Offline answer-quality evaluation; semantic scores require explicit reviews.

No judge model, network call or training dependency is loaded by this module.
The existing ChatResponse contract is embedded unchanged in an evaluation record.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, model_validator

from src.contracts import ChatResponse
from src.contracts.models import StrictContract
from src.lang import AnswerSafetyError, extract_citation_ids, has_korean_prose, validate_grounded_answer
from src.lang.safety import _grounded_content_blocks


class AnswerEvalCase(StrictContract):
    id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=2000)
    route: Literal["qa", "recommendation"] = "qa"
    split: Literal["dev", "holdout", "smoke"]
    expected_status: Literal[
        "answered", "insufficient_evidence", "needs_clarification", "out_of_scope", "safety_blocked"
    ]
    reference_points: list[str] = Field(default_factory=list)
    required_commands: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_commands(self):
        if any(not value.strip() or "\n" in value or "\r" in value for value in self.required_commands):
            raise ValueError("required_commands에는 검수한 단일 행 명령어 원문만 넣으세요.")
        if len(set(self.required_commands)) != len(self.required_commands):
            raise ValueError("required_commands에 중복 명령어가 있습니다.")
        if self.required_commands and self.expected_status != "answered":
            raise ValueError("명령어 출력 정답은 answered 사례에만 지정합니다.")
        return self


class EvaluationEvidence(StrictContract):
    citation_id: str = Field(pattern=r"^C[1-9][0-9]*$")
    content: str = Field(min_length=1)
    title: str | None = None
    section: str | None = None


class AnswerEvalRecord(StrictContract):
    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: str = Field(min_length=1)
    case: AnswerEvalCase
    response: ChatResponse
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_revision: str | None = None
    configuration: dict[str, str] = Field(default_factory=dict)
    generator_invoked: StrictBool
    # Exactly the evidence provided to the generator, including uncited chunks.
    evidence: list[EvaluationEvidence]
    raw_answer: str | None = None

    @model_validator(mode="after")
    def validate_snapshot(self):
        by_id = {item.citation_id: item for item in self.evidence}
        if len(by_id) != len(self.evidence):
            raise ValueError("평가 근거 citation_id가 중복됩니다.")
        if not self.generator_invoked and (self.evidence or self.raw_answer is not None):
            raise ValueError("미호출 실행에 생성기 입력·출력을 기록할 수 없습니다.")
        if self.response.status == "answered" and not self.evidence:
            raise ValueError("answered 평가에는 생성기에 실제 전달한 근거가 필요합니다.")
        for citation in self.response.citations:
            source = by_id.get(citation.citation_id)
            if source is None or source.content != citation.quote:
                raise ValueError("출처 카드와 생성기에 제공한 근거 본문이 다릅니다.")
        return self

    def digest(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ClaimReview(StrictContract):
    unit_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    verdict: Literal["supported", "unsupported", "not_factual", "pending"] = "pending"
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class CitationReview(StrictContract):
    unit_index: int = Field(ge=0)
    citation_id: str = Field(pattern=r"^C[1-9][0-9]*$")
    supports: StrictBool | None = None
    reason: str = ""


class AnswerReview(StrictContract):
    case_id: str
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rubric_version: Literal["picare-answer-v1"] = "picare-answer-v1"
    method: Literal["human", "llm", "fixture"] = "human"
    reviewer: str | None = None
    judge_model: str | None = None
    complete: StrictBool = False
    # A reviewer splits each unit into atomic claims; draft whole-unit claims are placeholders.
    claims: list[ClaimReview]
    citation_links: list[CitationReview]
    answer_relevancy: StrictInt | None = Field(default=None, ge=0, le=2)
    korean_compliant: StrictBool | None = None
    overall_reason: str = ""


def answer_units(record: AnswerEvalRecord) -> list[str]:
    if record.response.status != "answered":
        return []
    # Runtime formatting permits structural headings, but semantic review must not
    # silently discard an unsupported fact hidden in one of those headings.
    units, pending = [], []
    heading = re.compile(r"^(?:#{1,6}\s+\S.*|\*\*\s*\S.*?\s*\*\*|__\s*\S.*?\s*__)$")
    for line in record.response.answer.splitlines():
        if heading.fullmatch(line.strip()):
            units.extend(_grounded_content_blocks("\n".join(pending)))
            pending = []
            units.append(line.strip())
        else:
            pending.append(line)
    units.extend(_grounded_content_blocks("\n".join(pending)))
    return units


def citation_pairs(record: AnswerEvalRecord) -> set[tuple[int, str]]:
    return {
        (index, citation_id)
        for index, unit in enumerate(answer_units(record))
        for citation_id in extract_citation_ids(unit)
    }


def prepare_review(record: AnswerEvalRecord) -> AnswerReview:
    """Create an explicitly unscored draft, never a fabricated judge result."""
    return AnswerReview(
        case_id=record.case.id,
        record_sha256=record.digest(),
        claims=[ClaimReview(unit_index=index, text=unit) for index, unit in enumerate(answer_units(record))],
        citation_links=[CitationReview(unit_index=index, citation_id=cite) for index, cite in sorted(citation_pairs(record))],
    )


def validate_review(record: AnswerEvalRecord, review: AnswerReview) -> None:
    if review.case_id != record.case.id or review.record_sha256 != record.digest():
        raise ValueError(f"{record.case.id}: 답변·근거·정답이 변경된 오래된 검수 파일입니다.")
    if not review.complete:
        return
    if record.response.status != "answered":
        raise ValueError("의미 품질 검수는 answered 본문에만 적용합니다. 보류는 기대 상태로 평가합니다.")
    if not review.reviewer or not review.reviewer.strip() or not review.overall_reason.strip():
        raise ValueError("완료 검수에는 검수자와 종합 판정 이유가 필요합니다.")
    if review.method == "llm" and not review.judge_model:
        raise ValueError("LLM 검수에는 실제 judge 모델 ID가 필요합니다.")
    if review.answer_relevancy is None or review.korean_compliant is None:
        raise ValueError("완료 검수에는 관련성과 한국어 판정이 필요합니다.")
    units = answer_units(record)
    covered = set()
    known = {item.citation_id for item in record.evidence}
    seen_claims = set()
    for claim in review.claims:
        key = (claim.unit_index, claim.text)
        if key in seen_claims:
            raise ValueError("동일 주장을 중복 채점할 수 없습니다.")
        seen_claims.add(key)
        if claim.unit_index >= len(units) or claim.text not in units[claim.unit_index]:
            raise ValueError("주장 text는 지정 문단의 원문 부분 문자열이어야 합니다.")
        if claim.verdict == "pending" or not claim.reason.strip():
            raise ValueError("미판정 주장을 완료 점수에 포함할 수 없습니다.")
        if not set(claim.evidence_ids).issubset(known):
            raise ValueError("주장 검수에 실제 제공되지 않은 근거 ID가 있습니다.")
        if claim.verdict == "supported" and not claim.evidence_ids:
            raise ValueError("supported 주장에는 이를 뒷받침한 근거 ID가 필요합니다.")
        covered.add(claim.unit_index)
    if covered != set(range(len(units))):
        raise ValueError("모든 답변 문단을 검수해야 합니다. 사실이 아닌 문단은 not_factual로 표시하세요.")
    pairs = [(item.unit_index, item.citation_id) for item in review.citation_links]
    if len(pairs) != len(set(pairs)) or set(pairs) != citation_pairs(record):
        raise ValueError("답변의 모든 문단–인용 연결을 중복 없이 검수해야 합니다.")
    if any(item.supports is None or not item.reason.strip() for item in review.citation_links):
        raise ValueError("모든 인용 연결의 근거 지지 여부와 이유가 필요합니다.")


def load_jsonl(path: str | Path, model, *, allow_empty: bool = False):
    records = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(model.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
    if not records and not allow_empty:
        raise ValueError(f"비어 있는 평가 파일: {path}")
    return records


def write_jsonl(path: str | Path, records) -> None:
    """Use exclusive creation so an evaluation or completed review is never overwritten."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json() + "\n")


def _fraction(numerator: float, denominator: int) -> dict:
    return {"value": numerator / denominator if denominator else None, "numerator": numerator, "denominator": denominator}


def command_checks(record: AnswerEvalRecord) -> list[dict]:
    # Whole inline spans, not substring matches: '--enable --unsafe' must not pass '--enable'.
    spans = re.findall(r"(?<!`)`([^`\n]+)`(?!`)", record.response.answer)
    return [
        {
            "command": command,
            "exact_in_answer": record.response.status == "answered" and command in spans,
            "present_in_evidence": any(command in item.content for item in record.evidence),
        }
        for command in record.case.required_commands
    ]


def evaluate_records(records: list[AnswerEvalRecord], reviews: list[AnswerReview] | None = None) -> dict:
    """Aggregate audited semantics separately from deterministic status/format checks."""
    if not records:
        raise ValueError("평가할 실행 기록이 없습니다.")
    ids = [record.case.id for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("한 실행 안에 중복 case ID가 있습니다.")
    run_keys = {
        (record.run_id, record.provider, record.model_id, record.model_revision, record.case.split,
         json.dumps(record.configuration, sort_keys=True))
        for record in records
    }
    if len(run_keys) != 1:
        raise ValueError("다른 실행·모델·설정·split을 한 점수로 섞지 마세요.")
    review_map = {}
    for review in reviews or []:
        if review.case_id in review_map or review.case_id not in ids:
            raise ValueError("중복 검수 또는 실행 기록에 없는 검수 ID입니다.")
        review_map[review.case_id] = review
    supported = claims = good_links = links = reviewed = relevancy = korean = 0
    exact_status = format_pass = answered = korean_presence = errors = 0
    abstention_tp = abstention_tn = abstention_fp = abstention_fn = abstention_eligible = 0
    gold_abstention = gold_answered = 0
    commands_ok = commands_total = 0
    pending = []
    details = []
    for record in records:
        response, case = record.response, record.case
        exact_status += response.status == case.expected_status
        errors += response.status == "error"
        checks = command_checks(record)
        commands_total += len(checks)
        commands_ok += sum(item["exact_in_answer"] and item["present_in_evidence"] for item in checks)
        if case.expected_status in {"answered", "insufficient_evidence"}:
            abstention_eligible += 1
            gold_abstention += case.expected_status == "insufficient_evidence"
            gold_answered += case.expected_status == "answered"
            abstention_tp += case.expected_status == "insufficient_evidence" and response.status == "insufficient_evidence"
            abstention_tn += case.expected_status == "answered" and response.status == "answered"
            abstention_fp += case.expected_status == "answered" and response.status == "insufficient_evidence"
            abstention_fn += case.expected_status == "insufficient_evidence" and response.status != "insufficient_evidence"
        formatting = None
        if response.status == "answered":
            answered += 1
            korean_presence += has_korean_prose(response.answer)
            try:
                validate_grounded_answer(response.answer, allowed_citation_ids=[item.citation_id for item in record.evidence])
                formatting = True
            except AnswerSafetyError:
                formatting = False
            format_pass += formatting
        review = review_map.get(case.id)
        if review is not None:
            validate_review(record, review)
        if response.status == "answered":
            if review is None or not review.complete:
                pending.append(case.id)
            else:
                reviewed += 1
                factual = [item for item in review.claims if item.verdict != "not_factual"]
                claims += len(factual)
                supported += sum(item.verdict == "supported" for item in factual)
                links += len(review.citation_links)
                good_links += sum(item.supports is True for item in review.citation_links)
                relevancy += review.answer_relevancy
                korean += review.korean_compliant
        details.append({
            "case_id": case.id, "route": case.route,
            "expected_status": case.expected_status, "actual_status": response.status,
            "citation_format_valid": formatting, "commands": checks,
            "semantic_review": "complete" if review and review.complete else "pending" if response.status == "answered" else "not_applicable",
        })
    return {
        "schema_version": "1.0.0", "rubric_version": "picare-answer-v1",
        "scope": "final_answer_body; product-card facts require separate catalog review",
        "run_id": records[0].run_id, "split": records[0].case.split,
        "provider": records[0].provider, "model_id": records[0].model_id,
        "model_revision": records[0].model_revision, "configuration": records[0].configuration,
        "semantic_status": "pending_review" if pending else "not_applicable" if not answered else "reviewed",
        "review_methods": sorted({review.method for review in review_map.values() if review.complete}),
        "review_coverage": _fraction(reviewed, answered), "pending_case_ids": pending,
        "metrics": {
            "faithfulness": _fraction(supported, claims),
            "answer_relevancy": _fraction(relevancy, reviewed * 2),
            "citation_precision": _fraction(good_links, links),
            "abstention_accuracy": _fraction(abstention_tp + abstention_tn, abstention_eligible),
            "abstention_precision": _fraction(abstention_tp, abstention_tp + abstention_fp),
            "abstention_recall": _fraction(abstention_tp, gold_abstention),
            "false_abstention_rate": _fraction(abstention_fp, gold_answered),
            "korean_compliance_reviewed": _fraction(korean, reviewed),
            "command_preservation_exact": _fraction(commands_ok, commands_total),
            "korean_prose_presence_heuristic": _fraction(korean_presence, answered),
            "citation_format_validity": _fraction(format_pass, answered),
            "status_accuracy": _fraction(exact_status, len(records)),
            "answer_rate": _fraction(answered, len(records)),
            "error_rate": _fraction(errors, len(records)),
        },
        "abstention_confusion": {
            "tp": abstention_tp, "tn": abstention_tn, "fp": abstention_fp, "fn": abstention_fn,
            "other_incorrect_status": abstention_eligible - abstention_tp - abstention_tn - abstention_fp - abstention_fn,
        },
        "cases": details,
        "limitations": [
            "Semantic metrics are reviewer judgments, not automatic entailment or Ragas scores.",
            "Incomplete reviews are excluded, never treated as passing; compare review coverage too.",
            "Korean script presence is not Korean fluency; reviewed Korean compliance is separate.",
            "Command preservation covers only gold-required single-line inline commands, not every possible technical token.",
        ],
    }
