"""Streamlit 위젯값을 공통 조건 계약과 설문 입력으로 연결한다."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.contracts import ConditionPayload
from src.contracts.models import StrictContract

from .schema import SurveyAnswer, SurveyResponse


USER_LEVEL_LABELS = {
    "입문자": "beginner",
    "중급자": "intermediate",
    "고급자": "advanced",
}
PERFORMANCE_PRIORITY_LABELS = {
    "낮음": "low",
    "보통": "medium",
    "높음": "high",
}


class RecommendationFormInput(StrictContract):
    """제품 추천 화면의 자유 입력·선택값·토글값을 검증하는 계약이다."""

    request_id: str = Field(min_length=1, max_length=120)
    free_text: str = Field(min_length=1, max_length=2_000)
    user_level: Literal["beginner", "intermediate", "advanced"]
    performance_priority: Literal["low", "medium", "high"]
    wireless_required: bool
    camera_required: bool
    gpio_required: bool
    monitor_absent: bool

    @classmethod
    def from_widget_values(
        cls,
        *,
        request_id: str,
        free_text: str,
        user_level_label: str,
        performance_priority_label: str,
        wireless_required: bool,
        camera_required: bool,
        gpio_required: bool,
        monitor_absent: bool,
    ) -> "RecommendationFormInput":
        """화면의 한국어 선택 라벨을 내부 표준 enum 값으로 변환한다."""

        try:
            user_level = USER_LEVEL_LABELS[user_level_label]
            performance_priority = PERFORMANCE_PRIORITY_LABELS[
                performance_priority_label
            ]
        except KeyError as exc:
            raise ValueError(f"지원하지 않는 Streamlit 선택값입니다: {exc.args[0]}") from exc
        return cls(
            request_id=request_id,
            free_text=free_text,
            user_level=user_level,
            performance_priority=performance_priority,
            wireless_required=wireless_required,
            camera_required=camera_required,
            gpio_required=gpio_required,
            monitor_absent=monitor_absent,
        )

    def to_survey(self) -> SurveyResponse:
        """자유 입력과 위젯 선택값을 sLLM이 읽을 설문 답변으로 변환한다."""

        yes_no = {True: "예", False: "아니요"}
        return SurveyResponse(
            session_id=self.request_id,
            answers=[
                SurveyAnswer(
                    question_id="purpose_environment",
                    question="어디에 사용하며 어떤 환경에서 사용할 예정인가요?",
                    answer=self.free_text,
                ),
                SurveyAnswer(
                    question_id="user_level",
                    question="사용자 수준은 무엇인가요?",
                    answer=self.user_level,
                ),
                SurveyAnswer(
                    question_id="performance_priority",
                    question="성능 우선순위는 무엇인가요?",
                    answer=self.performance_priority,
                ),
                SurveyAnswer(
                    question_id="wireless_required",
                    question="Wi-Fi가 필요한가요?",
                    answer=yes_no[self.wireless_required],
                ),
                SurveyAnswer(
                    question_id="camera_required",
                    question="카메라를 사용하나요?",
                    answer=yes_no[self.camera_required],
                ),
                SurveyAnswer(
                    question_id="gpio_required",
                    question="GPIO를 사용하나요?",
                    answer=yes_no[self.gpio_required],
                ),
                SurveyAnswer(
                    question_id="monitor_absent",
                    question="사용 가능한 모니터가 없나요?",
                    answer=yes_no[self.monitor_absent],
                ),
            ],
        )

    def apply_explicit_values(self, extracted: ConditionPayload) -> ConditionPayload:
        """명시적인 UI 선택값을 sLLM 추출값보다 우선해 최종 조건에 반영한다."""

        updated = extracted.model_copy(
            update={
                "intent": "product_recommendation",
                "user_level": self.user_level,
                "performance_priority": self.performance_priority,
                "wireless_required": self.wireless_required,
                "camera_required": self.camera_required,
                "gpio_required": self.gpio_required,
                "monitor_available": not self.monitor_absent,
            }
        )
        return ConditionPayload.model_validate(updated.model_dump())


__all__ = [
    "PERFORMANCE_PRIORITY_LABELS",
    "RecommendationFormInput",
    "USER_LEVEL_LABELS",
]
