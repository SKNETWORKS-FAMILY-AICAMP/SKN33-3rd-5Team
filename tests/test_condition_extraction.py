"""조건 추출 스키마·파서·전달 데이터 검증 동작을 확인한다."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.condition_extraction.dataset import (
    assert_no_split_leakage,
    load_received_jsonl,
)
from src.condition_extraction.parser import ConditionOutputError, parse_condition_output
from src.condition_extraction.schema import SurveyAnswer, SurveyResponse
from src.contracts import ConditionPayload


def condition_payload(**overrides):
    """테스트마다 필요한 필드만 바꿀 수 있는 정상 조건 JSON을 만든다."""

    payload = {
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
    return payload


def record_payload(record_id="r1", answer="교육용"):
    """전달받는 JSONL 한 줄과 같은 테스트용 학습 레코드를 만든다."""

    return {
        "id": record_id,
        "answers": [
            {
                "question_id": "purpose",
                "question": "목적은?",
                "answer": answer,
            }
        ],
        "target": condition_payload(),
        "expected_product_ids": [],
    }


class ConditionExtractionTests(unittest.TestCase):
    """조건 계약과 read-only 데이터 검증기의 핵심 실패 조건을 검사한다."""

    def test_survey_rejects_duplicate_question_ids(self):
        """한 설문에서 같은 질문 ID를 두 번 사용하면 거부하는지 확인한다."""

        with self.assertRaises(ValidationError):
            SurveyResponse(
                answers=[
                    SurveyAnswer(question_id="purpose", question="목적?", answer="교육"),
                    SurveyAnswer(question_id="purpose", question="다시?", answer="학습"),
                ]
            )

    def test_extractor_uses_canonical_condition_contract(self):
        """필수 공통 조건 필드가 빠진 모델 출력을 거부하는지 확인한다."""

        payload = condition_payload()
        del payload["wireless_required"]
        with self.assertRaises(ValidationError):
            ConditionPayload.model_validate(payload)

    def test_parser_accepts_json_code_fence_but_rejects_trailing_explanation(self):
        """코드 블록은 허용하되 JSON 뒤의 추가 설명은 거부하는지 확인한다."""

        raw = "```json\n" + json.dumps(condition_payload(), ensure_ascii=False) + "\n```"
        parsed = parse_condition_output(raw)
        self.assertEqual(parsed.use_case, "education_coding")

        with self.assertRaises(ConditionOutputError):
            parse_condition_output(json.dumps(condition_payload()) + "\n설명입니다")

    def test_received_jsonl_is_validated_without_rewriting(self):
        """전달 JSONL을 검증한 뒤 원본 내용을 변경하지 않는지 확인한다."""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "train.jsonl"
            original = json.dumps(record_payload(), ensure_ascii=False) + "\n"
            path.write_text(original, encoding="utf-8")
            records = load_received_jsonl(path)
            self.assertEqual(len(records), 1)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_split_leakage_detects_same_normalized_answer(self):
        """공백만 다른 동일 답변도 split 누수로 탐지하는지 확인한다."""

        with tempfile.TemporaryDirectory() as temp_dir:
            train_path = Path(temp_dir) / "train.jsonl"
            dev_path = Path(temp_dir) / "dev.jsonl"
            train_path.write_text(
                json.dumps(record_payload("train-1", "교육용")), encoding="utf-8"
            )
            dev_path.write_text(
                json.dumps(record_payload("dev-1", "  교육용  ")), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "누수"):
                assert_no_split_leakage(
                    train=load_received_jsonl(train_path),
                    dev=load_received_jsonl(dev_path),
                )


if __name__ == "__main__":
    unittest.main()
