"""학습이 끝난 Qwen3 어댑터와 토크나이저만 Hugging Face에 별도 보관한다."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REQUIRED_FILES = (
    "adapter_config.json",
    "adapter_model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
)
OPTIONAL_FILES = (
    "README.md",
    "run_manifest.json",
    "special_tokens_map.json",
    "added_tokens.json",
    "vocab.json",
    "merges.txt",
    "chat_template.jinja",
    "generation_config.json",
)


def collect_adapter_files(adapter_path: str | Path) -> list[Path]:
    """최종 어댑터 파일을 확인하고 데이터·로그·checkpoint는 제외한다."""

    root = Path(adapter_path).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"학습 결과 폴더가 없습니다: {root}")
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        raise ValueError(f"학습 결과 파일이 부족합니다: {', '.join(missing)}")

    files = [root / name for name in REQUIRED_FILES + OPTIONAL_FILES if (root / name).is_file()]
    files.extend(path for path in (root / "chat_templates").glob("*.jinja") if path.is_file())
    for path in files:
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"학습 결과 폴더 밖을 가리키는 파일은 업로드하지 않습니다: {path.name}")
        if path.stat().st_size == 0:
            raise ValueError(f"빈 학습 결과 파일입니다: {path.name}")

    config = json.loads((root / "adapter_config.json").read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not config.get("base_model_name_or_path"):
        raise ValueError("adapter_config.json에 원본 base_model_name_or_path가 필요합니다.")
    return sorted(files)


def publish_adapter(
    adapter_path: str | Path,
    repo_id: str,
    *,
    private: bool = True,
    dry_run: bool = False,
) -> str | None:
    """선별한 파일과 checksum을 업로드한다. 로컬 학습 결과는 변경하지 않는다."""

    if repo_id.count("/") != 1 or any(not part.strip() for part in repo_id.split("/")):
        raise ValueError("repo_id는 '허깅페이스ID/모델저장소명' 형식이어야 합니다.")
    root = Path(adapter_path).expanduser().resolve()
    files = collect_adapter_files(root)
    print(f"Hub destination: {repo_id} ({'private' if private else 'public allowed'})")
    for path in files:
        print(f"  {path.relative_to(root).as_posix()} ({path.stat().st_size:,} bytes)")
    print("  SHA256SUMS.txt (generated)")
    if dry_run:
        print("dry run: 원격 조회·저장소 생성·업로드를 하지 않았습니다.")
        return None

    try:
        from huggingface_hub import CommitOperationAdd, HfApi
        from huggingface_hub.utils import validate_repo_id
    except ImportError as exc:
        raise RuntimeError("업로드에는 huggingface_hub 패키지가 필요합니다.") from exc

    validate_repo_id(repo_id)
    operations = []
    checksums = []
    for path in files:
        name = path.relative_to(root).as_posix()
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        checksums.append(f"{digest}  {name}\n")
        operations.append(CommitOperationAdd(path_in_repo=name, path_or_fileobj=str(path)))
    operations.append(
        CommitOperationAdd(
            path_in_repo="SHA256SUMS.txt",
            path_or_fileobj="".join(checksums).encode("utf-8"),
        )
    )

    # HF_TOKEN 또는 hf auth login으로 저장한 인증 정보를 사용한다.
    api = HfApi()
    api.create_repo(repo_id=repo_id, repo_type="model", private=private, exist_ok=True)
    info = api.model_info(repo_id)
    if private and info.private is not True:
        raise ValueError(
            "대상 저장소가 이미 공개되어 있어 업로드를 중단했습니다. "
            "다른 비공개 저장소 이름을 쓰거나 공개 업로드 옵션을 명시하세요."
        )
    result = api.create_commit(
        repo_id=repo_id,
        repo_type="model",
        operations=operations,
        commit_message="Save PiCare QLoRA adapter and tokenizer",
        parent_commit=info.sha,
    )
    print(f"adapter uploaded: {result.commit_url}")
    return result.commit_url


def main() -> None:
    """재학습 없이 기존 결과를 백업하거나 업로드할 파일만 미리 확인한다."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-path", required=True, help="학습이 끝난 output_dir")
    parser.add_argument("--repo-id", required=True, help="예: t91004/picare-qwen3-4b-qlora")
    parser.add_argument("--dry-run", action="store_true", help="파일 확인만 수행, 원격 접근 없음")
    parser.add_argument("--public", action="store_true", help="공개 저장소 생성·업로드 허용")
    args = parser.parse_args()
    publish_adapter(args.adapter_path, args.repo_id, private=not args.public, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
