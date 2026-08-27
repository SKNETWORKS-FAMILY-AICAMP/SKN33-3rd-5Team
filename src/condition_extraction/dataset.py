"""데이터 담당에게 받은 지도학습 JSONL을 수정 없이 읽고 검증한다."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from pydantic import Field

from src.contracts import ConditionPayload
from src.contracts.models import StrictContract

from .schema import SurveyAnswer, SurveyResponse


class FinetuningRecord(StrictContract):
    """팀 검수를 마친 설문 입력과 정답 조건 JSON 한 건을 표현한다."""

    id: str = Field(min_length=1, max_length=120)
    answers: list[SurveyAnswer] = Field(min_length=1, max_length=20)
    target: ConditionPayload
    expected_product_ids: list[str] = Field(default_factory=list)

    def survey(self) -> SurveyResponse:
        """학습 레코드의 답변 배열을 모델 입력용 설문 객체로 변환한다."""

        return SurveyResponse(session_id=self.id, answers=self.answers)

    def input_fingerprint(self) -> str:
        """같은 설문 답변이 다른 split에 섞였는지 확인할 해시를 만든다."""

        normalized = [
            {
                "question_id": item.question_id,
                "answer": " ".join(item.answer.lower().split()),
            }
            for item in self.answers
        ]
        payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_received_jsonl(path: str | Path) -> list[FinetuningRecord]:
    """전달 파일을 재작성하지 않고 줄별 스키마와 중복 ID를 검증해 읽는다."""

    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"받게 되는 학습 파일이 없습니다: {resolved}. "
            "docs/data-contracts/finetuning.md의 전달 계약을 확인하세요."
        )

    records: list[FinetuningRecord] = []
    seen_ids: set[str] = set()
    with resolved.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                record = FinetuningRecord.model_validate_json(raw_line)
            except Exception as exc:
                raise ValueError(f"{resolved}:{line_number} 스키마 오류: {exc}") from exc
            if record.id in seen_ids:
                raise ValueError(f"{resolved}:{line_number} 중복 id: {record.id}")
            seen_ids.add(record.id)
            records.append(record)

    if not records:
        raise ValueError(f"비어 있는 데이터셋입니다: {resolved}")
    return records


def assert_no_split_leakage(**splits: Iterable[FinetuningRecord]) -> None:
    """train·dev·holdout 사이에 같은 ID나 정규화 입력이 있으면 중단한다."""

    seen_ids: dict[str, str] = {}
    seen_inputs: dict[str, str] = {}
    for split_name, records in splits.items():
        for record in records:
            previous_id_split = seen_ids.get(record.id)
            if previous_id_split is not None:
                raise ValueError(
                    f"id 누수: {record.id!r}가 {previous_id_split}와 {split_name}에 있습니다."
                )
            seen_ids[record.id] = split_name

            fingerprint = record.input_fingerprint()
            previous_input_split = seen_inputs.get(fingerprint)
            if previous_input_split is not None:
                raise ValueError(
                    "동일 설문 응답 누수: "
                    f"{record.id!r} 입력이 {previous_input_split}와 {split_name}에 있습니다."
                )
            seen_inputs[fingerprint] = split_name
