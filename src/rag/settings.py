"""RAG 모듈이 사용하는 로컬 실행 설정을 `.env`에서 읽는다."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class RagSettingsError(ValueError):
    """`.env`의 RAG 설정이 누락됐거나 잘못됐을 때 발생한다."""


@dataclass(frozen=True)
class RagSettings:
    """색인과 검색이 공통으로 사용하는 파일 경로·모델 설정."""

    project_root: Path
    manifest_path: Path
    chroma_path: Path
    chroma_collection_name: str
    e5_model_name: str
    top_k: int
    dense_max_distance: float

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "RagSettings":
        """프로젝트 최상위 `.env`를 읽고, 상대 경로를 프로젝트 기준으로 바꾼다."""
        root = (project_root or Path(__file__).resolve().parents[2]).resolve()
        # OS 환경변수는 CI·배포 환경에서 우선할 수 있도록 덮어쓰지 않는다.
        load_dotenv(root / ".env", override=False)

        def required(name: str) -> str:
            value = os.getenv(name, "").strip()
            if not value:
                raise RagSettingsError(f"{name} is required. Add it to {root / '.env'}.")
            return value

        def resolve_path(name: str) -> Path:
            path = Path(required(name)).expanduser()
            return path if path.is_absolute() else (root / path).resolve()

        top_k_raw = required("TOP_K")
        try:
            top_k = int(top_k_raw)
        except ValueError as exc:
            raise RagSettingsError("TOP_K must be an integer between 1 and 20.") from exc
        if not 1 <= top_k <= 20:
            raise RagSettingsError("TOP_K must be an integer between 1 and 20.")

        dense_max_distance_raw = os.getenv("DENSE_MAX_DISTANCE", "0.48").strip()
        try:
            dense_max_distance = float(dense_max_distance_raw)
        except ValueError as exc:
            raise RagSettingsError("DENSE_MAX_DISTANCE must be a number between 0 and 2.") from exc
        if not 0 < dense_max_distance < 2:
            raise RagSettingsError("DENSE_MAX_DISTANCE must be a number between 0 and 2.")

        settings = cls(
            project_root=root,
            manifest_path=resolve_path("DOCUMENT_MANIFEST"),
            chroma_path=resolve_path("CHROMA_PATH"),
            chroma_collection_name=required("CHROMA_COLLECTION_NAME"),
            e5_model_name=required("E5_MODEL_NAME"),
            top_k=top_k,
            dense_max_distance=dense_max_distance,
        )
        if not settings.manifest_path.is_file():
            raise RagSettingsError(
                f"DOCUMENT_MANIFEST does not exist: {settings.manifest_path}. "
                "Create the corpus manifest or update .env."
            )
        return settings
