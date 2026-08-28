"""근거 기반 답변 생성기의 교체 가능한 계약과 구현을 제공한다."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
import re
from time import perf_counter
from typing import Mapping, Protocol, Sequence

from src.lang.prompts import PromptEvidence


class AnswerGenerationError(RuntimeError):
    """답변 모델을 준비하거나 생성하는 과정에서 발생한 명시적 오류다."""


@dataclass(frozen=True)
class GenerationResult:
    """답변 본문과 추론 provider 정보를 함께 전달하는 생성 결과다."""

    text: str
    provider: str
    model_id: str
    elapsed_ms: float

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("생성된 답변 본문은 비어 있을 수 없습니다.")
        if not self.provider.strip() or not self.model_id.strip():
            raise ValueError("생성 provider와 model_id는 비어 있을 수 없습니다.")
        if self.elapsed_ms < 0:
            raise ValueError("elapsed_ms cannot be negative.")


class AnswerGenerator(Protocol):
    """공식 근거 프롬프트를 받아 인용 가능한 답변을 생성하는 제공자 계약이다."""

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        evidence: Sequence[PromptEvidence],
    ) -> GenerationResult:
        """인용 ID가 포함된 답변과 실행 정보를 반환한다."""


_URL_PATTERN = re.compile(r"(?i)(?:https?://|www\.)[^\s)>\]]+")


class EvidenceTemplateGenerator:
    """실제 생성 LLM 없이 공식 원문 근거를 안전하게 표시하는 로컬 생성기."""

    provider = "template"
    model_id = "evidence-template"

    @staticmethod
    def _without_urls(content: str) -> str:
        """답변 본문에 URL을 넣지 않는 안전 정책에 맞춰 URL만 제거한다."""

        return _URL_PATTERN.sub("[원문 링크는 출처 카드 참조]", content).strip()

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        evidence: Sequence[PromptEvidence],
    ) -> GenerationResult:
        """각 검색 청크를 자체 인용과 함께 출력한다."""

        if not messages or not evidence:
            raise ValueError("템플릿 답변에는 질문 메시지와 공식 근거가 필요합니다.")
        started_at = perf_counter()
        first_id = evidence[0].citation_id
        lines = [f"공식 문서에서 확인된 관련 근거입니다. [{first_id}]"]
        for item in evidence:
            lines.append(f"- {self._without_urls(item.content)} [{item.citation_id}]")
        return GenerationResult(
            text="\n".join(lines),
            provider=self.provider,
            model_id=self.model_id,
            elapsed_ms=(perf_counter() - started_at) * 1000,
        )


class HuggingFaceAnswerGenerator:
    """RunPod CUDA Pod에서 Qwen Instruct를 직접 호출하는 lazy 답변 생성기.

    조건 JSON 추출용 LoRA adapter는 적용하지 않는다. 이 구현은 공식 검색 근거를
    받은 뒤에만 Qwen3-4B Base Instruct를 로드해 한국어 답변을 생성한다.
    """

    provider = "huggingface"

    def __init__(
        self,
        *,
        model_id: str,
        model_revision: str = "main",
        load_in_4bit: bool = True,
        max_new_tokens: int = 512,
    ) -> None:
        if not model_id.strip():
            raise ValueError("model_id must not be empty.")
        if not model_revision.strip():
            raise ValueError("model_revision must not be empty.")
        if not 1 <= max_new_tokens <= 512:
            raise ValueError("max_new_tokens must be between 1 and 512.")
        self.model_id = model_id
        self.model_revision = model_revision
        self.load_in_4bit = load_in_4bit
        self.max_new_tokens = max_new_tokens
        self._model = None
        self._tokenizer = None
        self._torch = None

    @property
    def is_loaded(self) -> bool:
        """모델이 실제로 GPU 메모리에 올라갔는지 반환한다."""

        return self._model is not None and self._tokenizer is not None and self._torch is not None

    def _load_model(self) -> None:
        """최초 생성 요청에서만 CUDA·Transformers 의존성과 Base 모델을 준비한다."""

        if self.is_loaded:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        except ImportError as exc:
            raise AnswerGenerationError(
                "Qwen QA 추론 패키지가 없습니다. RunPod Pod에서 "
                "`pip install -r requirements.txt -r runpod/requirements.txt`를 실행하세요."
            ) from exc

        if not torch.cuda.is_available():
            raise AnswerGenerationError(
                "Hugging Face 답변 생성기는 CUDA GPU가 있는 RunPod Pod에서만 실행합니다. "
                "로컬에서는 ANSWER_GENERATOR=template을 사용하세요."
            )

        model_kwargs: dict[str, object] = {
            "revision": self.model_revision,
            "device_map": "auto",
            "torch_dtype": torch.bfloat16,
        }
        if self.load_in_4bit:
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
        try:
            tokenizer = AutoTokenizer.from_pretrained(
                self.model_id,
                revision=self.model_revision,
            )
            if tokenizer.pad_token_id is None:
                tokenizer.pad_token = tokenizer.eos_token
            model = AutoModelForCausalLM.from_pretrained(self.model_id, **model_kwargs)
            model.eval()
        except Exception as exc:
            raise AnswerGenerationError(
                f"Qwen 모델을 로드하지 못했습니다: {self.model_id}@{self.model_revision}. "
                "RunPod GPU, Hugging Face 접근 권한, HF_HOME cache를 확인하세요."
            ) from exc

        self._torch = torch
        self._tokenizer = tokenizer
        self._model = model

    @staticmethod
    def _prompt_length(input_ids: object) -> int:
        """Tensor와 테스트용 list 양쪽에서 입력 토큰 길이를 구한다."""

        shape = getattr(input_ids, "shape", None)
        if shape is not None:
            return int(shape[-1])
        return len(input_ids[0])  # type: ignore[index]

    @staticmethod
    def _completion_ids(output_ids: object, prompt_length: int) -> object:
        """모델 전체 출력에서 새로 생성된 토큰만 분리한다."""

        try:
            return output_ids[0, prompt_length:]  # type: ignore[index]
        except TypeError:
            return output_ids[0][prompt_length:]  # type: ignore[index]

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        evidence: Sequence[PromptEvidence],
    ) -> GenerationResult:
        """공식 근거 프롬프트로 Qwen 답변을 생성하고 신규 토큰만 decode한다."""

        if not messages or not evidence:
            raise ValueError("Qwen 답변 생성에는 질문 메시지와 공식 근거가 필요합니다.")
        started_at = perf_counter()
        self._load_model()
        assert self._model is not None
        assert self._tokenizer is not None
        assert self._torch is not None

        encoded = self._tokenizer.apply_chat_template(
            list(messages),
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        )
        model_device = getattr(self._model, "device", None)
        if model_device is not None and hasattr(encoded, "to"):
            encoded = encoded.to(model_device)
        prompt_length = self._prompt_length(encoded["input_ids"])
        inference_mode = getattr(self._torch, "inference_mode", None)
        context = inference_mode() if callable(inference_mode) else nullcontext()
        with context:
            output_ids = self._model.generate(
                **encoded,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=self._tokenizer.pad_token_id,
                eos_token_id=self._tokenizer.eos_token_id,
            )
        answer = self._tokenizer.decode(
            self._completion_ids(output_ids, prompt_length),
            skip_special_tokens=True,
        ).strip()
        return GenerationResult(
            text=answer,
            provider=self.provider,
            model_id=self.model_id,
            elapsed_ms=(perf_counter() - started_at) * 1000,
        )


__all__ = [
    "AnswerGenerationError",
    "AnswerGenerator",
    "EvidenceTemplateGenerator",
    "GenerationResult",
    "HuggingFaceAnswerGenerator",
]
