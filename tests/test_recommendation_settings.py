"""로컬·Hub 어댑터가 추천 실행 설정과 추출기까지 올바르게 전달되는지 확인한다."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.recommendation.settings import (
    RecommendationSettings,
    RecommendationSettingsError,
    build_condition_extractor,
)


def configure(monkeypatch, tmp_path, adapter):
    (tmp_path / "catalog.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("PRODUCT_CATALOG", "catalog.json")
    monkeypatch.setenv("CONDITION_EXTRACTOR", "lora")
    monkeypatch.setenv("LORA_ADAPTER_PATH", adapter)
    monkeypatch.setenv("CONDITION_LOAD_IN_4BIT", "true")
    return RecommendationSettings.from_env(tmp_path)


def test_hub_adapter_reaches_peft_without_local_path_conversion(monkeypatch, tmp_path):
    repo_id = "t91004/picare-qwen3-4b-qlora"
    settings = configure(monkeypatch, tmp_path, repo_id)
    assert settings.lora_adapter_path == repo_id
    with patch("src.recommendation.settings.LoraConditionExtractor") as extractor:
        build_condition_extractor(settings)
    extractor.assert_called_once_with(repo_id, model_id=settings.condition_model_id, load_in_4bit=True)


def test_existing_relative_directory_still_resolves_locally(monkeypatch, tmp_path):
    directory = tmp_path / "models" / "adapter"
    directory.mkdir(parents=True)
    settings = configure(monkeypatch, tmp_path, "models/adapter")
    assert settings.lora_adapter_path == directory.resolve()
    assert isinstance(settings.lora_adapter_path, Path)


@pytest.mark.parametrize("adapter", ["./models/missing", "missing", "bad owner/adapter", "owner/../adapter"])
def test_missing_explicit_paths_and_invalid_hub_ids_fail(monkeypatch, tmp_path, adapter):
    with pytest.raises(RecommendationSettingsError):
        configure(monkeypatch, tmp_path, adapter)


def test_file_cannot_be_used_as_adapter_directory(monkeypatch, tmp_path):
    with pytest.raises(RecommendationSettingsError):
        configure(monkeypatch, tmp_path, str(tmp_path / "catalog.json"))
