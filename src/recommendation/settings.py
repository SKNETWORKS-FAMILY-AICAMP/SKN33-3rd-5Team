"""제품 추천 catalog와 sLLM 조건 추출기의 런타임 설정을 읽는다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from src.condition_extraction.extractor import DEFAULT_MODEL_ID, ConditionExtractor
from src.condition_extraction.baseline import BaselineConditionExtractor
from src.condition_extraction.lora import LoraConditionExtractor


class RecommendationSettingsError(ValueError):
    """제품 추천용 환경 변수가 누락됐거나 잘못됐을 때 발생한다."""


@dataclass(frozen=True)
class RecommendationSettings:
    """catalog 위치와 조건 추출기 종류를 하나로 묶은 런타임 설정이다."""

    project_root: Path
    catalog_path: Path
    condition_extractor: Literal["baseline", "lora"]
    condition_model_id: str
    lora_adapter_path: Path | str | None
    condition_load_in_4bit: bool

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "RecommendationSettings":
        root = (project_root or Path(__file__).resolve().parents[2]).resolve()
        load_dotenv(root / ".env", override=False)

        catalog_raw = os.getenv("PRODUCT_CATALOG", "").strip()
        if not catalog_raw:
            raise RecommendationSettingsError(f"PRODUCT_CATALOG is required. Add it to {root / '.env'}.")
        catalog_path = Path(catalog_raw).expanduser()
        catalog_path = catalog_path if catalog_path.is_absolute() else (root / catalog_path).resolve()
        if not catalog_path.is_file():
            raise RecommendationSettingsError(f"PRODUCT_CATALOG does not exist: {catalog_path}")

        extractor = os.getenv("CONDITION_EXTRACTOR", "lora").strip().lower()
        if extractor not in {"baseline", "lora"}:
            raise RecommendationSettingsError("CONDITION_EXTRACTOR must be 'baseline' or 'lora'.")
        model_id = os.getenv("CONDITION_MODEL_ID", DEFAULT_MODEL_ID).strip()
        if not model_id:
            raise RecommendationSettingsError("CONDITION_MODEL_ID must not be empty.")
        bool_values = {"true": True, "false": False}
        load_in_4bit_raw = os.getenv("CONDITION_LOAD_IN_4BIT", "true").strip().lower()
        if load_in_4bit_raw not in bool_values:
            raise RecommendationSettingsError(
                "CONDITION_LOAD_IN_4BIT must be either 'true' or 'false'."
            )

        adapter_path: Path | str | None = None
        if extractor == "lora":
            adapter_raw = os.getenv("LORA_ADAPTER_PATH", "").strip()
            if not adapter_raw:
                raise RecommendationSettingsError(
                    "CONDITION_EXTRACTOR=lora requires LORA_ADAPTER_PATH."
                )
            local_path = Path(adapter_raw).expanduser()
            resolved_path = local_path if local_path.is_absolute() else (root / local_path).resolve()
            if resolved_path.is_dir():
                adapter_path = resolved_path
            elif (
                local_path.is_absolute()
                or adapter_raw.startswith((".", "~"))
                or "\\" in adapter_raw
                or adapter_raw.count("/") != 1
                or resolved_path.exists()
            ):
                raise RecommendationSettingsError(
                    f"LORA_ADAPTER_PATH directory does not exist: {resolved_path}"
                )
            else:
                # Hub 저장소 ID는 로컬 절대경로로 바꾸지 않고 PEFT에 그대로 넘긴다.
                from huggingface_hub.utils import validate_repo_id

                try:
                    validate_repo_id(adapter_raw)
                except ValueError as exc:
                    raise RecommendationSettingsError(
                        "LORA_ADAPTER_PATH must be a local directory or a valid 'owner/repo' Hub ID."
                    ) from exc
                adapter_path = adapter_raw

        return cls(
            project_root=root,
            catalog_path=catalog_path,
            condition_extractor=extractor,  # type: ignore[arg-type]
            condition_model_id=model_id,
            lora_adapter_path=adapter_path,
            condition_load_in_4bit=bool_values[load_in_4bit_raw],
        )


def build_condition_extractor(settings: RecommendationSettings) -> ConditionExtractor:
    """환경 설정에 따라 Base few-shot 또는 QLoRA 추출기를 생성한다."""

    if settings.condition_extractor == "baseline":
        return BaselineConditionExtractor(
            model_id=settings.condition_model_id,
            load_in_4bit=settings.condition_load_in_4bit,
        )
    assert settings.lora_adapter_path is not None
    return LoraConditionExtractor(
        str(settings.lora_adapter_path),
        model_id=settings.condition_model_id,
        load_in_4bit=settings.condition_load_in_4bit,
    )


__all__ = [
    "RecommendationSettings",
    "RecommendationSettingsError",
    "build_condition_extractor",
]
