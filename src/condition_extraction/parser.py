"""모델 출력의 의미를 임의 보정하지 않고 JSON과 공통 스키마를 검증한다."""

from __future__ import annotations

import json

from src.contracts import ConditionPayload


class ConditionOutputError(ValueError):
    """파싱 실패 이유와 실패한 모델 원문을 함께 전달하는 예외다."""

    def __init__(self, message: str, raw_output: str):
        """오류 메시지와 분석에 필요한 원본 출력을 저장한다."""

        super().__init__(message)
        self.raw_output = raw_output


def parse_condition_output(raw_output: str) -> ConditionPayload:
    """JSON 객체 하나만 허용하고 성공하면 ConditionPayload로 반환한다."""

    text = raw_output.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    decoder = json.JSONDecoder()
    start = text.find("{")
    if start < 0:
        raise ConditionOutputError("모델 출력에 JSON 객체가 없습니다.", raw_output)
    try:
        payload, end = decoder.raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise ConditionOutputError(f"JSON 파싱 실패: {exc}", raw_output) from exc
    if text[start + end :].strip():
        raise ConditionOutputError("JSON 뒤에 허용되지 않은 설명이 있습니다.", raw_output)
    try:
        return ConditionPayload.model_validate(payload)
    except Exception as exc:
        raise ConditionOutputError(f"조건 JSON Schema 검증 실패: {exc}", raw_output) from exc
