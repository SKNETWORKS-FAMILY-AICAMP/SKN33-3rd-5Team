"""답변 생성기 provider 설정과 로컬 기본값을 검증한다."""

from __future__ import annotations

import pytest

from src.rag_to_llm import AnswerGeneratorSettings, AnswerGeneratorSettingsError, HuggingFaceAnswerGenerator
from src.rag_to_llm.factory import build_answer_generator


def test_answer_generator_settings_defaults_to_template(tmp_path, monkeypatch) -> None:
    for name in (
        "ANSWER_GENERATOR",
        "ANSWER_MODEL_ID",
        "ANSWER_MODEL_REVISION",
        "ANSWER_LOAD_IN_4BIT",
        "ANSWER_MAX_NEW_TOKENS",
        "INFERENCE_DEVICE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = AnswerGeneratorSettings.from_env(tmp_path)

    assert settings.provider == "template"
    assert settings.max_new_tokens == 512
    assert settings.device == "auto"


def test_huggingface_settings_build_generator_without_loading_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANSWER_GENERATOR", "huggingface")
    monkeypatch.setenv("ANSWER_MODEL_ID", "Qwen/test")
    monkeypatch.setenv("ANSWER_MODEL_REVISION", "revision-test")
    monkeypatch.setenv("ANSWER_LOAD_IN_4BIT", "true")
    monkeypatch.setenv("ANSWER_MAX_NEW_TOKENS", "32")
    monkeypatch.setenv("INFERENCE_DEVICE", "mps")

    settings = AnswerGeneratorSettings.from_env(tmp_path)
    generator = build_answer_generator(settings)

    assert isinstance(generator, HuggingFaceAnswerGenerator)
    assert generator.model_id == "Qwen/test"
    assert generator.device == "mps"
    assert generator.is_loaded is False


def test_answer_generator_settings_reject_invalid_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANSWER_GENERATOR", "runpod")

    with pytest.raises(AnswerGeneratorSettingsError, match="ANSWER_GENERATOR"):
        AnswerGeneratorSettings.from_env(tmp_path)


def test_answer_generator_settings_rejects_invalid_inference_device(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INFERENCE_DEVICE", "metal")

    with pytest.raises(AnswerGeneratorSettingsError, match="INFERENCE_DEVICE"):
        AnswerGeneratorSettings.from_env(tmp_path)
