"""Fetch approved Raspberry Pi AsciiDoc sources at one fixed Git commit."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PIPELINE_ROOT.parent
REGISTRY_PATH = PIPELINE_ROOT / "data" / "source_registry.csv"
RAW_ROOT = PIPELINE_ROOT / "data" / "raw"
GITHUB_REPOSITORY = "https://github.com/raspberrypi/documentation.git"
RAW_GITHUB_PREFIX = "https://raw.githubusercontent.com/raspberrypi/documentation/"
USER_AGENT = "PiCare-document-pipeline/1.0 (educational project)"


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    title: str
    official_page_url: str
    collection_url: str
    source_format: str
    publisher: str
    language: str
    license_id: str
    source_type: str
    official_verified: bool
    product_models: list[str]
    use_cases: list[str]
    tasks: list[str]
    categories: list[str]


def split_values(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def included_sources(registry_path: Path = REGISTRY_PATH) -> list[SourceRecord]:
    """Return only reviewed sources that are explicitly approved for collection."""
    with registry_path.open(encoding="utf-8-sig", newline="") as file:
        rows = csv.DictReader(file)
        records = []
        for row in rows:
            if row["collection_decision"] != "include":
                continue
            if row["collection_method"] != "git_raw" or row["source_format"] != "asciidoc":
                raise ValueError(f"{row['source_id']}: included source must be git_raw AsciiDoc")
            if row["official_verified"] != "true":
                raise ValueError(f"{row['source_id']}: included source must be officially verified")
            records.append(
                SourceRecord(
                    source_id=row["source_id"],
                    title=row["title"],
                    official_page_url=row["official_page_url"],
                    collection_url=row["collection_url"],
                    source_format=row["source_format"],
                    publisher=row["publisher"],
                    language=row["language"],
                    license_id=row["license_id"],
                    source_type=row["source_type"],
                    official_verified=row["official_verified"] == "true",
                    product_models=split_values(row["product_models"]),
                    use_cases=split_values(row["use_cases"]),
                    tasks=split_values(row["tasks"]),
                    categories=split_values(row["categories"]),
                )
            )
    return records


def resolve_commit(repository: str = GITHUB_REPOSITORY) -> str:
    """Resolve the current master SHA once so a collection run is reproducible."""
    completed = subprocess.run(
        ["git", "ls-remote", repository, "refs/heads/master"],
        check=True,
        capture_output=True,
        text=True,
    )
    line = completed.stdout.strip().splitlines()
    if len(line) != 1:
        raise ValueError("could not resolve exactly one Raspberry Pi documentation master commit")
    commit = line[0].split()[0]
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise ValueError(f"invalid commit SHA returned by git: {commit!r}")
    return commit


def pinned_raw_url(collection_url: str, commit: str) -> str:
    """Replace the mutable master ref in a known official raw GitHub URL."""
    if not collection_url.startswith(f"{RAW_GITHUB_PREFIX}master/"):
        raise ValueError(f"collection URL is not the expected official GitHub raw URL: {collection_url}")
    return collection_url.replace(f"{RAW_GITHUB_PREFIX}master/", f"{RAW_GITHUB_PREFIX}{commit}/", 1)


def _safe_raw_path(raw_root: Path, source_id: str) -> Path:
    if not source_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"unsafe source ID: {source_id}")
    return raw_root / f"{source_id}.adoc"


def registry_reference(registry_path: Path) -> str:
    """Return a reproducible project-relative registry reference for the ledger."""

    try:
        return registry_path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("source registry must be inside the project repository") from exc


def _download_text(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:  # nosec B310 - registry URLs are validated by project policy
        if response.status != 200:
            raise ValueError(f"unexpected HTTP status {response.status} for {url}")
        return response.read()


def fetch_sources(
    *,
    commit: str | None = None,
    raw_root: Path = RAW_ROOT,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, object]:
    """Download approved raw documents and write one local collection ledger."""
    registry_path = registry_path.resolve()
    raw_root.mkdir(parents=True, exist_ok=True)
    resolved_commit = commit or resolve_commit()
    collected_at = datetime.now(UTC).date().isoformat()
    documents: list[dict[str, str]] = []
    for source in included_sources(registry_path):
        url = pinned_raw_url(source.collection_url, resolved_commit)
        payload = _download_text(url)
        destination = _safe_raw_path(raw_root, source.source_id)
        destination.write_bytes(payload)
        documents.append(
            {
                "source_id": source.source_id,
                "path": destination.name,
                "collection_url": url,
                "document_checksum": f"sha256:{hashlib.sha256(payload).hexdigest()}",
            }
        )
    ledger: dict[str, object] = {
        "schema_version": "1.0.0",
        "repository": GITHUB_REPOSITORY,
        "commit": resolved_commit,
        "collected_at": collected_at,
        "source_registry": registry_reference(registry_path),
        "documents": documents,
    }
    (raw_root / "collection.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return ledger


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch approved Raspberry Pi AsciiDoc sources.")
    parser.add_argument("--commit", help="Optional 40-character Raspberry Pi documentation commit SHA")
    parser.add_argument("--source-registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    args = parser.parse_args()

    ledger = fetch_sources(
        commit=args.commit,
        registry_path=args.source_registry,
        raw_root=args.raw_root,
    )
    print(f"fetched {len(ledger['documents'])} approved documents")
    print(f"commit: {ledger['commit']}")


if __name__ == "__main__":
    main()
