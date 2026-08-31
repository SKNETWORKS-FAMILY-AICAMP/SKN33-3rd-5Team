"""Known good/bad fixtures verify metric math, review provenance and capture isolation."""

from __future__ import annotations

import json

import pytest

from src.contracts import ChatResponse
from src.evaluation.answer_capture import recording_generator
from src.evaluation.answer_eval import (
    AnswerEvalCase, AnswerEvalRecord, AnswerReview, ClaimReview, EvaluationEvidence,
    evaluate_records, prepare_review, write_jsonl,
)
from src.evaluation.answer_eval_cli import main
from src.rag_to_llm import EvidenceTemplateGenerator
from src.services.rag_qa_service import RagQaService
from src.rag import RagResult, RetrievalDecision


def record(*, case_id="ssh", expected="answered", actual="answered", answer=None, commands=None):
    text = answer or "SSH는 기본적으로 꺼져 있습니다. `sudo raspi-config`로 설정하세요. [C1]"
    content = "SSH is disabled by default. Use sudo raspi-config to configure SSH."
    response = ChatResponse.model_validate({
        "schema_version": "1.2.0", "request_id": case_id, "status": actual,
        "language": "ko", "answer": text if actual == "answered" else "답변을 보류합니다.",
        "conditions": None, "products": [], "media": [], "clarification_questions": [], "warnings": [],
        "citations": [{
            "citation_id": "C1", "document_id": "ssh-doc", "chunk_id": "ssh-chunk",
            "title": "SSH", "publisher": "Raspberry Pi", "section": "Setup",
            "source_url": "https://www.raspberrypi.com/documentation/",
            "source_anchor": None, "document_version": "fixture", "published_at": None,
            "updated_at": None, "collected_at": "2026-08-31", "license": "test-fixture", "quote": content,
        }] if actual == "answered" else [],
    })
    return AnswerEvalRecord(
        run_id="fixture-run", case=AnswerEvalCase(
            id=case_id, question="SSH를 설정하려면?", split="smoke", expected_status=expected,
            required_commands=commands if commands is not None else ["sudo raspi-config"] if expected == "answered" else [],
        ), response=response, provider="fixture", model_id="not-an-llm",
        generator_invoked=actual == "answered",
        evidence=[EvaluationEvidence(citation_id="C1", content=content)] if actual == "answered" else [],
        raw_answer=text if actual == "answered" else None,
    )


def reviewed(item, *, supported=True, citation_supports=True, relevancy=2, korean=True):
    payload = prepare_review(item).model_dump()
    payload.update(method="fixture", reviewer="unit-test", complete=True, answer_relevancy=relevancy,
                   korean_compliant=korean, overall_reason="Constructed evaluation fixture; not measured model quality.")
    payload["claims"] = [
        {"unit_index": 0, "text": "SSH는 기본적으로 꺼져 있습니다.",
         "verdict": "supported" if supported else "unsupported", "evidence_ids": ["C1"] if supported else [], "reason": "fixture claim 1"},
        {"unit_index": 0, "text": "`sudo raspi-config`로 설정하세요.",
         "verdict": "supported" if supported else "unsupported", "evidence_ids": ["C1"] if supported else [], "reason": "fixture claim 2"},
    ]
    for link in payload["citation_links"]:
        link.update(supports=citation_supports, reason="fixture citation decision")
    return AnswerReview.model_validate(payload)


def test_no_review_does_not_turn_valid_citation_ids_into_semantic_scores():
    result = evaluate_records([record()])
    assert result["semantic_status"] == "pending_review"
    assert result["metrics"]["faithfulness"]["value"] is None
    assert result["metrics"]["citation_precision"]["value"] is None
    assert result["metrics"]["citation_format_validity"]["value"] == 1
    assert result["metrics"]["command_preservation_exact"]["value"] == 1


def test_semantic_judgments_and_relevancy_have_distinct_denominators():
    item = record()
    review = reviewed(item, citation_supports=False, relevancy=1, korean=False)
    report = evaluate_records([item], [review])
    assert report["metrics"]["faithfulness"] == {"value": 1, "numerator": 2, "denominator": 2}
    assert report["metrics"]["citation_precision"]["value"] == 0
    assert report["metrics"]["answer_relevancy"]["value"] == .5
    assert report["metrics"]["korean_compliance_reviewed"]["value"] == 0
    assert report["metrics"]["korean_prose_presence_heuristic"]["value"] == 1


def test_unsupported_claims_fail_even_with_valid_citation_format():
    item = record()
    report = evaluate_records([item], [reviewed(item, supported=False, citation_supports=False)])
    assert report["metrics"]["faithfulness"]["value"] == 0
    assert report["metrics"]["citation_format_validity"]["value"] == 1


def test_always_abstaining_cannot_get_perfect_abstention_accuracy():
    records = [record(case_id="can-answer", actual="insufficient_evidence"),
               record(case_id="cannot-answer", expected="insufficient_evidence", actual="insufficient_evidence")]
    metrics = evaluate_records(records)["metrics"]
    assert metrics["abstention_accuracy"]["value"] == .5
    assert metrics["abstention_recall"]["value"] == 1
    assert metrics["abstention_precision"]["value"] == .5
    assert metrics["false_abstention_rate"]["value"] == 1


def test_error_is_never_counted_as_successful_abstention():
    metrics = evaluate_records([record(expected="insufficient_evidence", actual="error")])["metrics"]
    assert metrics["abstention_accuracy"]["value"] == 0
    assert metrics["error_rate"]["value"] == 1
    assert metrics["faithfulness"]["value"] is None


@pytest.mark.parametrize("command", ["sudo raspi-config --unsafe", "sudo  raspi-config", "sudo Raspi-config", "sudo 라즈베리설정"])
def test_command_flags_spacing_case_and_translation_must_be_preserved(command):
    item = record(answer=f"`{command}`로 설정하세요. [C1]")
    assert evaluate_records([item])["metrics"]["command_preservation_exact"]["value"] == 0


def test_command_not_required_is_not_silently_perfect():
    assert evaluate_records([record(commands=[])])["metrics"]["command_preservation_exact"]["value"] is None


def test_semantic_review_does_not_hide_claims_and_citations_in_headings():
    item = record(answer="# 모든 모델에서 무조건 됩니다 [C1]\n\n설정할 수 있습니다. [C1]")
    draft = prepare_review(item)
    assert len(draft.claims) == 2
    assert "모든 모델" in draft.claims[0].text
    assert {(link.unit_index, link.citation_id) for link in draft.citation_links} == {(0, "C1"), (1, "C1")}


def test_stale_review_is_rejected_when_question_changes():
    item = record()
    review = reviewed(item)
    changed = item.model_copy(update={"case": item.case.model_copy(update={"question": "다른 질문"})})
    with pytest.raises(ValueError, match="오래된"):
        evaluate_records([changed], [review])


@pytest.mark.parametrize("change", [
    {"citation_links": []}, {"claims": []}, {"reviewer": ""},
    {"answer_relevancy": None}, {"korean_compliant": None},
    {"method": "llm", "judge_model": None},
])
def test_completed_review_cannot_skip_claims_citations_or_judge_metadata(change):
    item = record()
    review = reviewed(item).model_copy(update=change)
    with pytest.raises(ValueError):
        evaluate_records([item], [review])


def test_changed_evidence_cannot_be_paired_with_old_source_card():
    payload = record().model_dump()
    payload["evidence"][0]["content"] = "Different source"
    with pytest.raises(ValueError, match="출처 카드"):
        AnswerEvalRecord.model_validate(payload)


def test_duplicate_ids_or_mixed_providers_are_rejected():
    first = record()
    with pytest.raises(ValueError, match="중복"):
        evaluate_records([first, first])
    with pytest.raises(ValueError, match="섞지"):
        evaluate_records([first, record(case_id="other").model_copy(update={"provider": "huggingface"})])


def test_pending_review_is_not_counted_even_if_some_labels_were_filled():
    item = record()
    draft = reviewed(item).model_copy(update={"complete": False})
    assert evaluate_records([item], [draft])["metrics"]["faithfulness"]["value"] is None


def test_cli_prepare_score_and_refuse_overwrite(tmp_path):
    item = record()
    records_path, reviews_path, report_path = (tmp_path / name for name in ("records.jsonl", "reviews.jsonl", "report.json"))
    write_jsonl(records_path, [item])
    assert main(["prepare", "--records", str(records_path), "--output", str(reviews_path)]) == 0
    assert main(["score", "--records", str(records_path), "--reviews", str(reviews_path), "--output", str(report_path), "--require-complete"]) == 2
    assert json.loads(report_path.read_text(encoding="utf-8"))["semantic_status"] == "pending_review"
    original = reviews_path.read_bytes()
    assert main(["prepare", "--records", str(records_path), "--output", str(reviews_path)]) == 2
    assert reviews_path.read_bytes() == original
    completed_path = tmp_path / "completed.jsonl"
    write_jsonl(completed_path, [reviewed(item)])
    assert main(["score", "--records", str(records_path), "--reviews", str(completed_path), "--output", str(tmp_path / "final.json"), "--require-complete"]) == 0


def test_recording_generator_resets_between_answer_and_pre_retrieval_refusal():
    class Retriever:
        def search_with_decision(self, *args, **kwargs):
            return RetrievalDecision(status="retrieved", results=(RagResult(
                rank=1, content="Enable SSH in Imager.", chunk_id="ssh", document_id="ssh",
                title="SSH", section="Setup", source_url="https://www.raspberrypi.com/documentation/",
                license="fixture", retrieved_at="2026-08-31", document_version="fixture",
            ),))
    capture = recording_generator(EvidenceTemplateGenerator())
    service = RagQaService(retriever=Retriever(), answer_generator=capture)
    first = service.answer(request_id="1", question="SSH 활성화 방법?", retrieval_mode="bm25")
    assert first.status == "answered" and capture.invoked
    capture.reset()
    second = service.answer(request_id="2", question="실시간 가격 알려줘", retrieval_mode="bm25")
    case = AnswerEvalCase(id="2", question="실시간 가격 알려줘", split="smoke", expected_status="out_of_scope")
    snapshot = capture.record(case=case, response=second, run_id="fixture")
    assert snapshot.evidence == [] and snapshot.raw_answer is None and not snapshot.generator_invoked
