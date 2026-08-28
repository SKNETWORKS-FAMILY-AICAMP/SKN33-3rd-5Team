"""파인튜닝 전 성능 기준이 되는 Base few-shot 조건 추출기를 제공한다."""

from __future__ import annotations

from .extractor import DEFAULT_MODEL_ID, HuggingFaceConditionExtractor


class BaselineConditionExtractor(HuggingFaceConditionExtractor):
    """LoRA adapter 없이 Base 모델과 few-shot 예시만 사용하는 추출기다."""

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_MODEL_ID,
        load_in_4bit: bool = True,
    ) -> None:
        """Base 모델 ID와 4-bit 로딩 여부를 받아 추출기를 초기화한다."""

        super().__init__(
            model_id=model_id,
            adapter_path=None,
            include_few_shots=True,
            load_in_4bit=load_in_4bit,
        )
