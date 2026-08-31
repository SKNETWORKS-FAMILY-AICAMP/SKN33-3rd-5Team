"""Validate the manifest contract and source registry without third-party packages."""
from __future__ import annotations

import argparse
import ast
import csv
import json
from pathlib import Path
from urllib.parse import urlparse


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PIPELINE_ROOT.parent
REGISTRY_PATH = PIPELINE_ROOT / "data" / "source_registry.csv"
SCHEMA_PATH = PIPELINE_ROOT / "contracts" / "manifest.schema.json"
MEDIA_REGISTRY_PATH = PIPELINE_ROOT / "data" / "product_media_registry.json"
MEDIA_SCHEMA_PATH = PIPELINE_ROOT / "contracts" / "product-media.schema.json"
CANONICAL_MODELS_PATH = REPOSITORY_ROOT / "src" / "contracts" / "models.py"

REQUIRED_REGISTRY_COLUMNS = {
    "source_id",
    "title",
    "scope",
    "source_type",
    "official_page_url",
    "collection_url",
    "source_format",
    "publisher",
    "language",
    "license_id",
    "license_url",
    "license_review_status",
    "collection_method",
    "collection_decision",
    "official_verified",
    "priority",
    "product_models",
    "use_cases",
    "tasks",
    "categories",
    "notes",
}

SOURCE_TYPES = {
    "documentation",
    "product_page",
    "faq",
    "release_note",
    "support_notice",
    "recall_notice",
}
LICENSE_STATUSES = {"approved", "conditional", "blocked", "pending"}
COLLECTION_METHODS = {"git_raw", "reference_only", "manual", "none"}
COLLECTION_DECISIONS = {"include", "reference_only", "exclude", "pending"}
RUNTIME_FIELDS = {"citation_id", "rank", "indexed_at"}


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _canonical_search_result_fields() -> set[str]:
    tree = ast.parse(CANONICAL_MODELS_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "SearchResultMetadata":
            return {
                statement.target.id
                for statement in node.body
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
            }
    raise ValueError("SearchResultMetadata was not found in src/contracts/models.py")


def validate_manifest_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    chunk_schema = schema["$defs"]["chunk"]
    manifest_fields = set(chunk_schema["properties"])
    required_fields = set(chunk_schema["required"])
    canonical_fields = _canonical_search_result_fields()
    expected_static_fields = canonical_fields - RUNTIME_FIELDS

    missing = expected_static_fields - manifest_fields
    extra = manifest_fields - expected_static_fields
    if missing or extra:
        raise ValueError(
            f"manifest fields differ from canonical static fields: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    unexpected_runtime = RUNTIME_FIELDS.intersection(manifest_fields)
    if unexpected_runtime:
        raise ValueError(f"manifest schema contains runtime fields: {sorted(unexpected_runtime)}")
    if required_fields != manifest_fields:
        optional = sorted(manifest_fields - required_fields)
        missing_required = sorted(required_fields - manifest_fields)
        raise ValueError(
            f"all manifest chunk fields must be explicit; optional={optional}, invalid_required={missing_required}"
        )


def validate_source_registry(registry_path: Path = REGISTRY_PATH) -> tuple[int, int, int]:
    with registry_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        if columns != REQUIRED_REGISTRY_COLUMNS:
            missing = sorted(REQUIRED_REGISTRY_COLUMNS - columns)
            extra = sorted(columns - REQUIRED_REGISTRY_COLUMNS)
            raise ValueError(f"source registry columns differ: missing={missing}, extra={extra}")
        rows = list(reader)

    source_ids: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        source_id = row["source_id"].strip()
        if not source_id:
            raise ValueError(f"line {line_number}: source_id is empty")
        if source_id in source_ids:
            raise ValueError(f"line {line_number}: duplicate source_id {source_id}")
        source_ids.add(source_id)

        if row["source_type"] not in SOURCE_TYPES:
            raise ValueError(f"line {line_number}: invalid source_type {row['source_type']}")
        if row["license_review_status"] not in LICENSE_STATUSES:
            raise ValueError(f"line {line_number}: invalid license_review_status")
        if row["collection_method"] not in COLLECTION_METHODS:
            raise ValueError(f"line {line_number}: invalid collection_method")
        if row["collection_decision"] not in COLLECTION_DECISIONS:
            raise ValueError(f"line {line_number}: invalid collection_decision")
        if row["official_verified"] not in {"true", "false"}:
            raise ValueError(f"line {line_number}: official_verified must be true or false")
        if not _is_https_url(row["official_page_url"]):
            raise ValueError(f"line {line_number}: official_page_url must be HTTPS")
        if row["license_url"] and not _is_https_url(row["license_url"]):
            raise ValueError(f"line {line_number}: license_url must be HTTPS")

        if row["collection_decision"] == "include":
            if row["collection_method"] != "git_raw":
                raise ValueError(f"line {line_number}: included sources must use git_raw")
            if not _is_https_url(row["collection_url"]):
                raise ValueError(f"line {line_number}: included source requires an HTTPS collection_url")
            if row["official_verified"] != "true":
                raise ValueError(f"line {line_number}: included source must be officially verified")
            if row["license_review_status"] not in {"approved", "conditional"}:
                raise ValueError(f"line {line_number}: included source needs an approved licence")

        if row["collection_decision"] == "reference_only" and row["collection_url"]:
            raise ValueError(f"line {line_number}: reference-only source must not have collection_url")

    included = sum(row["collection_decision"] == "include" for row in rows)
    reference_only = sum(row["collection_decision"] == "reference_only" for row in rows)
    return len(rows), included, reference_only


def validate_product_media_registry(registry_path: Path = REGISTRY_PATH) -> int:
    schema = json.loads(MEDIA_SCHEMA_PATH.read_text(encoding="utf-8"))
    required_top_level = {"schema_version", "reviewed_at", "display_scope", "items"}
    if set(schema["required"]) != required_top_level:
        raise ValueError("product media schema top-level fields differ")

    with registry_path.open(encoding="utf-8-sig", newline="") as file:
        source_ids = {row["source_id"] for row in csv.DictReader(file)}

    payload = json.loads(MEDIA_REGISTRY_PATH.read_text(encoding="utf-8"))
    if set(payload) != required_top_level:
        raise ValueError("product media registry fields differ")
    if payload["schema_version"] != "1.1.0":
        raise ValueError("product media registry schema_version must be 1.1.0")
    if payload["display_scope"] != "cc_by_sa_4_0_with_attribution":
        raise ValueError("product media registry has an unsupported display scope")

    product_models: set[str] = set()
    for item in payload["items"]:
        product_model = item["product_model"]
        if product_model in product_models:
            raise ValueError(f"duplicate product media entry: {product_model}")
        product_models.add(product_model)
        if item["source_registry_id"] not in source_ids:
            raise ValueError(f"unknown source registry ID: {item['source_registry_id']}")
        if not _is_https_url(item["product_page_url"]) or not _is_https_url(item["image_url"]):
            raise ValueError(f"{product_model}: product and image URLs must be HTTPS")
        if not urlparse(item["product_page_url"]).netloc.endswith("raspberrypi.com"):
            raise ValueError(f"{product_model}: product page must be on raspberrypi.com")
        image_url = urlparse(item["image_url"])
        if image_url.netloc != "raw.githubusercontent.com":
            raise ValueError(f"{product_model}: image must be sourced from the official GitHub repository")
        expected_path = f"/raspberrypi/documentation/{item['source_commit']}/{item['source_file']}"
        if image_url.path != expected_path:
            raise ValueError(f"{product_model}: image URL must match the pinned source file and commit")
        if not item["source_file"].startswith("documentation/"):
            raise ValueError(f"{product_model}: source file must be inside documentation/")
        if len(item["source_commit"]) != 40 or any(char not in "0123456789abcdef" for char in item["source_commit"]):
            raise ValueError(f"{product_model}: source commit must be a lowercase 40-character SHA")
        if item["license_id"] != "CC-BY-SA-4.0":
            raise ValueError(f"{product_model}: product image must declare CC-BY-SA-4.0")
        if item["display_status"] != "cc_by_sa_4_0":
            raise ValueError(f"{product_model}: invalid display status")
        for key, expected in {
            "remote_only": False,
            "cache_permitted": True,
            "git_commit_permitted": True,
            "transform_permitted": True,
            "public_deployment_permitted": True,
        }.items():
            if item[key] is not expected:
                raise ValueError(f"{product_model}: {key} must be {expected}")
    return len(product_models)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a document pipeline source registry.")
    parser.add_argument("--source-registry", type=Path, default=REGISTRY_PATH)
    args = parser.parse_args()

    validate_manifest_schema()
    total, included, reference_only = validate_source_registry(args.source_registry)
    media_count = validate_product_media_registry(args.source_registry)
    print("foundation validation passed")
    print(f"registry records: {total}")
    print(f"include: {included}")
    print(f"reference_only: {reference_only}")
    print(f"CC BY-SA 4.0 product images: {media_count}")


if __name__ == "__main__":
    main()
