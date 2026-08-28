"""Base 추론·QLoRA 학습·LoRA 추론이 공유하는 단일 조건 추출 프롬프트다."""

from __future__ import annotations

import json
from typing import Any

from src.contracts import ConditionPayload

from .schema import SurveyAnswer, SurveyResponse


SYSTEM_PROMPT = """당신은 Raspberry Pi 서비스의 조건 추출기입니다.
사용자의 설문 답변에 명시된 정보만 제공된 JSON Schema로 변환하세요.
제품을 직접 추천하거나 제품 사양, 가격, 재고, URL, 출처를 만들지 마세요.
언급되지 않은 선택 조건은 null로 두고, false는 사용자가 아니라고 명시한 경우에만 사용하세요.
product_models와 os_versions는 값이 있으면 배열, 없으면 null입니다.
답변이 충돌하거나 핵심 목적이 모호하면 needs_clarification을 true로 하고 최대 3개의 짧은 한국어 확인 질문을 작성하세요.
JSON 객체 하나만 출력하고 Markdown 코드 블록이나 설명을 덧붙이지 마세요.

허용값:
- intent: product_recommendation, product_comparison, how_to, troubleshooting, support_recall, out_of_scope
- use_case: education_coding, desktop_computing, home_server, camera_monitoring, smart_farm_monitoring, headless_remote_management, gpio_iot
- task: desktop_programming, os_installation, system_configuration, remote_access, camera_setup, gpio_setup, sensor_monitoring, server_operation, troubleshooting, support_recall
- performance_priority: low, medium, high
- user_level: beginner, intermediate, advanced
"""


def _target(**overrides: Any) -> ConditionPayload:
    """few-shot 예시용 기본 조건에 필요한 정답 필드만 덮어쓴다."""

    payload: dict[str, Any] = {
        "schema_version": "1.1.0",
        "intent": "product_recommendation",
        "use_case": None,
        "product_models": None,
        "os_versions": None,
        "task": None,
        "performance_priority": None,
        "wireless_required": None,
        "camera_required": None,
        "gpio_required": None,
        "monitor_available": None,
        "remote_access_required": None,
        "user_level": None,
        "needs_clarification": False,
        "clarification_questions": [],
    }
    payload.update(overrides)
    return ConditionPayload.model_validate(payload)


FEW_SHOT_EXAMPLES = (
    (
        SurveyResponse(
            answers=[
                SurveyAnswer(
                    question_id="purpose",
                    question="사용 목적이 무엇인가요?",
                    answer="초등학생이 처음 파이썬과 스크래치를 배우는 교육용이에요.",
                ),
                SurveyAnswer(
                    question_id="environment",
                    question="어떤 환경에서 사용하나요?",
                    answer="집의 모니터에 연결하고 Wi-Fi를 쓸 거예요.",
                ),
            ]
        ),
        _target(
            use_case="education_coding",
            task="desktop_programming",
            user_level="beginner",
            performance_priority="medium",
            wireless_required=True,
            monitor_available=True,
        ),
    ),
    (
        SurveyResponse(
            answers=[
                SurveyAnswer(
                    question_id="purpose",
                    question="사용 목적이 무엇인가요?",
                    answer="온습도 센서를 달아 화면 없이 원격으로 확인하고 싶어요.",
                ),
                SurveyAnswer(
                    question_id="features",
                    question="꼭 필요한 기능은 무엇인가요?",
                    answer="GPIO와 Wi-Fi가 꼭 필요하고 카메라는 필요 없어요.",
                ),
            ]
        ),
        _target(
            use_case="smart_farm_monitoring",
            task="sensor_monitoring",
            performance_priority="low",
            wireless_required=True,
            camera_required=False,
            gpio_required=True,
            monitor_available=False,
            remote_access_required=True,
        ),
    ),
)


def schema_text() -> str:
    """공통 ConditionPayload JSON Schema를 한국어 보존 문자열로 만든다."""

    return json.dumps(ConditionPayload.model_json_schema(), ensure_ascii=False, indent=2)


def user_message(survey: SurveyResponse) -> str:
    """JSON Schema와 사용자의 설문 답변을 하나의 모델 입력으로 조합한다."""

    return f"JSON Schema:\n{schema_text()}\n\n설문 답변:\n{survey.to_prompt_text()}"


def build_inference_messages(
    survey: SurveyResponse, *, include_few_shots: bool = True
) -> list[dict[str, str]]:
    """선택적 few-shot 예시를 포함한 Qwen chat 메시지 배열을 만든다."""

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if include_few_shots:
        for example_survey, example_target in FEW_SHOT_EXAMPLES:
            messages.extend(
                [
                    {"role": "user", "content": user_message(example_survey)},
                    {"role": "assistant", "content": example_target.model_dump_json()},
                ]
            )
    messages.append({"role": "user", "content": user_message(survey)})
    return messages


def build_training_example(
    survey: SurveyResponse, target: ConditionPayload
) -> dict[str, list[dict[str, str]]]:
    """정답 completion에만 loss를 적용할 TRL 대화형 학습 샘플을 만든다."""

    return {
        "prompt": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message(survey)},
        ],
        "completion": [{"role": "assistant", "content": target.model_dump_json()}],
    }
