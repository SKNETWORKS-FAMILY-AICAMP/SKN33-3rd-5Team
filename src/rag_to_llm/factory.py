"""환경 설정에 맞는 답변 생성기를 조립한다."""

from __future__ import annotations

from .answer_generator import AnswerGenerator, EvidenceTemplateGenerator, HuggingFaceAnswerGenerator
from .settings import AnswerGeneratorSettings


def build_answer_generator(settings: AnswerGeneratorSettings) -> AnswerGenerator:
    """설정의 provider 값에 맞는 생성기를 만들되, 모델은 아직 로드하지 않는다."""

    if settings.provider == "template":
        return EvidenceTemplateGenerator()
    return HuggingFaceAnswerGenerator(
        model_id=settings.model_id,
        model_revision=settings.model_revision,
        load_in_4bit=settings.load_in_4bit,
        max_new_tokens=settings.max_new_tokens,
        device=settings.device,
    )


__all__ = ["build_answer_generator"]
