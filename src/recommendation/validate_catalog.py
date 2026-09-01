"""제품 카탈로그와 RAG manifest의 배포 전 정합성 검증 CLI다."""

from __future__ import annotations

import argparse
from pathlib import Path

from .catalog_validation import catalog_coverage_summary, load_and_validate_catalog


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate product catalog evidence against a RAG manifest."
    )
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    catalog, manifest = load_and_validate_catalog(
        catalog_path=args.catalog,
        manifest_path=args.manifest,
    )
    print("catalog-manifest validation passed")
    print(f"products: {len(catalog.products)}")
    print(f"sources: {len(catalog.sources)}")
    print(f"chunks: {len(manifest['chunks'])}")
    for product_id, coverage in catalog_coverage_summary(catalog, manifest).items():
        print(
            f"{product_id}: {coverage['evidence_fields']} evidence fields, "
            f"{coverage['evidence_documents']} documents, "
            f"{coverage['evidence_chunks']} product-tagged evidence chunks"
        )


if __name__ == "__main__":
    main()
