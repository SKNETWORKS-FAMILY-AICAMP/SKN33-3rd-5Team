"""실제 Qwen 다운로드 없이 Hugging Face QA 생성기의 계약을 검증한다."""

from __future__ import annotations

from contextlib import nullcontext

from src.lang import PromptEvidence
from src.rag_to_llm import HuggingFaceAnswerGenerator


class FakeInputIds:
    shape = (1, 3)


class FakeEncoded(dict):
    def __init__(self) -> None:
        super().__init__(input_ids=FakeInputIds())
        self.device = None

    def to(self, device):
        self.device = device
        return self


class FakeTokenizer:
    pad_token_id = 0
    eos_token_id = 2
    eos_token = "</s>"

    def __init__(self) -> None:
        self.messages = None
        self.options = None

    def apply_chat_template(self, messages, **kwargs):
        self.messages = messages
        self.options = kwargs
        return FakeEncoded()

    def decode(self, token_ids, *, skip_special_tokens):
        assert token_ids == [7, 8]
        assert skip_special_tokens is True
        return "SSH는 Raspberry Pi Imager에서 활성화할 수 있습니다. [C1]"


class FakeModel:
    device = "cuda:0"

    def __init__(self) -> None:
        self.generate_kwargs = None

    def generate(self, **kwargs):
        self.generate_kwargs = kwargs
        return [[1, 2, 3, 7, 8]]


class FakeTorch:
    @staticmethod
    def inference_mode():
        return nullcontext()


def _messages():
    return ({"role": "system", "content": "근거만 사용하세요."},)


def _evidence():
    return (PromptEvidence(citation_id="C1", content="Enable SSH in Imager."),)


def test_huggingface_generator_is_lazy_and_decodes_only_new_tokens(monkeypatch) -> None:
    generator = HuggingFaceAnswerGenerator(model_id="Qwen/test", max_new_tokens=32)
    tokenizer = FakeTokenizer()
    model = FakeModel()
    load_calls = 0

    def fake_load_model() -> None:
        nonlocal load_calls
        if generator.is_loaded:
            return
        load_calls += 1
        generator._tokenizer = tokenizer
        generator._model = model
        generator._torch = FakeTorch()

    monkeypatch.setattr(generator, "_load_model", fake_load_model)

    assert generator.is_loaded is False
    response = generator.generate(_messages(), _evidence())

    assert load_calls == 1
    assert generator.is_loaded is True
    assert response.provider == "huggingface"
    assert response.model_id == "Qwen/test"
    assert response.text.endswith("[C1]")
    assert tokenizer.messages == list(_messages())
    assert tokenizer.options["add_generation_prompt"] is True
    assert tokenizer.options["return_tensors"] == "pt"
    assert model.generate_kwargs["max_new_tokens"] == 32
    assert model.generate_kwargs["do_sample"] is False

    generator.generate(_messages(), _evidence())
    assert load_calls == 1
