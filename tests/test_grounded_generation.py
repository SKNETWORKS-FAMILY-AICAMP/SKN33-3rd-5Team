"""인용 검증·안전한 보류·실제 생성 횟수의 서비스 계약을 검증한다."""
from unittest.mock import Mock

import pytest

from src.lang import AnswerSafetyError, PromptEvidence, validate_grounded_answer
from src.rag_to_llm import AnswerGenerationError, GenerationResult, HuggingFaceAnswerGenerator
from src.services.grounded_generation import generate_validated_grounded_answer


@pytest.mark.parametrize("answer", [
    "근거 없는 제품 기능을 보장합니다.\n\n- SSH를 설정하세요. [C1]",
    "근거 없는 제품 기능을 보장합니다:\n\nSSH를 설정하세요. [C1]",
    "- 근거 없는 제품 기능을 보장합니다:\n- SSH를 설정하세요. [C1]",
])
def test_no_uncited_claim_exemption_for_list_or_colon(answer):
    with pytest.raises(AnswerSafetyError):
        validate_grounded_answer(answer, allowed_citation_ids=["C1"], require_korean=True)


MESSAGES = [{"role": "system", "content": "공식 근거만 사용하세요."}]
EVIDENCE = [PromptEvidence(citation_id="C1", content="Enable SSH.")]


def test_repaired_abstention_remains_a_safe_abstention():
    generator = Mock()
    generator.generate.side_effect = [
        GenerationResult("인용 없는 출력", "huggingface", "test", 1),
        GenerationResult("[INSUFFICIENT_EVIDENCE]", "huggingface", "test", 1),
    ]
    result = generate_validated_grounded_answer(
        generator=generator, messages=MESSAGES, evidence=EVIDENCE, require_korean=True,
    )
    assert result.generation.text == "[INSUFFICIENT_EVIDENCE]"
    assert result.used_citation_ids == set()
    assert result.attempts == generator.generate.call_count == 2


def test_trace_reports_internal_retry_without_generating_four_times(monkeypatch):
    generator = HuggingFaceAnswerGenerator(model_id="test")
    monkeypatch.setattr(generator, "_load_model", lambda: None)
    raw = Mock(side_effect=["인용 없는 출력", "SSH를 설정하세요 [C1]."])
    monkeypatch.setattr(generator, "_generate_text", raw)
    result = generate_validated_grounded_answer(
        generator=generator, messages=MESSAGES, evidence=EVIDENCE, require_korean=True,
    )
    assert raw.call_count == result.attempts == 2
    assert result.repair_attempted


def test_repeated_invalid_generation_stops_after_two_raw_calls(monkeypatch):
    generator = HuggingFaceAnswerGenerator(model_id="test")
    monkeypatch.setattr(generator, "_load_model", lambda: None)
    raw = Mock(return_value="알 수 없는 근거입니다 [C99].")
    monkeypatch.setattr(generator, "_generate_text", raw)
    with pytest.raises(AnswerGenerationError):
        generate_validated_grounded_answer(generator=generator, messages=MESSAGES, evidence=EVIDENCE)
    assert raw.call_count == 2
