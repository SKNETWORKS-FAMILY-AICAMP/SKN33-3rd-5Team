"""Run QA/recommendation cases, prepare reviews and score recorded answers offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from .answer_eval import (
    AnswerEvalCase, AnswerEvalRecord, AnswerReview, evaluate_records,
    load_jsonl, prepare_review, write_jsonl,
)


def create_parser():
    parser = argparse.ArgumentParser(description="PiCare LLM 답변 평가: 실행 기록 → 의미 검수 → 점수")
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run", help="기존 QA/추천 서비스를 실행합니다. 모델·RAG 환경이 필요합니다.")
    run.add_argument("--cases", required=True)
    run.add_argument("--split", choices=("dev", "holdout", "smoke"), required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--mode", choices=("bm25", "hybrid"), default="hybrid")
    run.add_argument("--output", required=True)
    prepare = sub.add_parser("prepare", help="점수가 비어 있는 검수 초안을 생성합니다.")
    prepare.add_argument("--records", required=True)
    prepare.add_argument("--output", required=True)
    score = sub.add_parser("score", help="정답 상태·원문 검사와 완료된 의미 검수를 집계합니다.")
    score.add_argument("--records", required=True)
    score.add_argument("--reviews")
    score.add_argument("--output", required=True)
    score.add_argument("--require-complete", action="store_true", help="의미 검수 미완료 시 보고서는 저장하되 exit 2")
    return parser


def _print_fact_error_table(report):
    """완료 검수에서 집계한 사실 오류 유형과 건수를 표준 출력에 표시한다."""

    print("fact_error_type\tcount")
    for error_type, count in report["fact_error_summary"]["type_counts"].items():
        print(f"{error_type}\t{count}")


def _run(args):
    cases = load_jsonl(args.cases, AnswerEvalCase)
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("평가 질문 ID가 중복됩니다.")
    cases = [case for case in cases if case.split == args.split]
    if not cases:
        raise ValueError("선택한 split에 평가 질문이 없습니다.")
    routes = {case.route for case in cases}
    if "recommendation" in routes and args.mode != "hybrid":
        raise ValueError("제품 추천 통합 평가는 기존 계약대로 Hybrid 모드만 지원합니다.")

    # Heavy runtime dependencies are never imported by prepare/score.
    from src.rag import HybridRetriever, RagSettings
    from src.rag.index_metadata import manifest_checksum
    from src.rag_to_llm import AnswerGeneratorSettings, build_answer_generator
    from src.lang.prompts import GROUNDED_ANSWER_SYSTEM_PROMPT, RECOMMENDATION_ANSWER_SYSTEM_PROMPT
    from src.services.rag_qa_service import RagQaService
    from .answer_capture import recording_generator

    settings = RagSettings.from_env()
    generator_settings = AnswerGeneratorSettings.from_env(settings.project_root)
    capture = recording_generator(build_answer_generator(generator_settings))
    retriever = HybridRetriever.from_manifest(
        settings.manifest_path,
        chroma_path=settings.chroma_path if args.mode == "hybrid" else None,
        collection_name=settings.chroma_collection_name,
        embedding_model_name=settings.e5_model_name,
        dense_max_distance=settings.dense_max_distance,
    )
    services = {"qa": RagQaService(retriever=retriever, answer_generator=capture, top_k=settings.top_k)}
    configuration = {
        "manifest_checksum": manifest_checksum(settings.manifest_path),
        "retrieval_mode": args.mode, "embedding_model": settings.e5_model_name,
        "top_k": str(settings.top_k), "dense_max_distance": str(settings.dense_max_distance),
        "load_in_4bit": str(generator_settings.load_in_4bit),
        "max_new_tokens": str(generator_settings.max_new_tokens),
        "prompt_sha256": hashlib.sha256((GROUNDED_ANSWER_SYSTEM_PROMPT + RECOMMENDATION_ANSWER_SYSTEM_PROMPT).encode()).hexdigest(),
    }
    if "recommendation" in routes:
        from src.rag import load_indexed_at
        from src.recommendation import ProductRecommender, RecommendationSettings, build_condition_extractor, load_and_validate_catalog
        from src.services.integration_adapters import manifest_to_rag_result_metadata
        from src.services.recommendation_agent import RecommendationAgent
        from src.services.recommendation_rag_service import RecommendationRagService

        recommendation_settings = RecommendationSettings.from_env(settings.project_root)
        catalog, manifest = load_and_validate_catalog(
            catalog_path=recommendation_settings.catalog_path, manifest_path=settings.manifest_path,
        )
        indexed_at = load_indexed_at(
            chroma_path=settings.chroma_path, collection_name=settings.chroma_collection_name,
            manifest_path=settings.manifest_path,
        )
        services["recommendation"] = RecommendationRagService(
            recommendation_agent=RecommendationAgent(
                extractor=build_condition_extractor(recommendation_settings), recommender=ProductRecommender(catalog),
            ),
            retriever=retriever,
            metadata_by_chunk_id=manifest_to_rag_result_metadata(manifest, indexed_at=indexed_at),
            answer_generator=capture, top_k=settings.top_k,
        )
        configuration["catalog_sha256"] = hashlib.sha256(recommendation_settings.catalog_path.read_bytes()).hexdigest()
        configuration["condition_extractor"] = recommendation_settings.condition_extractor
        configuration["condition_model"] = recommendation_settings.condition_model_id
        configuration["adapter_path"] = str(recommendation_settings.lora_adapter_path or "")
    records = []
    for case in cases:
        capture.reset()
        kwargs = {"request_id": case.id, "question": case.question, "trace": True}
        if case.route == "qa":
            kwargs["retrieval_mode"] = args.mode
        response = services[case.route].answer(**kwargs)
        records.append(capture.record(
            case=case, response=response, run_id=args.run_id, configuration=configuration,
            model_revision=generator_settings.model_revision if capture.provider != "template" else None,
        ))
        print(f"{case.id}: {response.status}", file=sys.stderr)
    write_jsonl(args.output, records)
    print(f"saved {len(records)} records: {args.output}")
    return 1 if any(record.response.status == "error" for record in records) else 0


def main(argv=None):
    args = create_parser().parse_args(argv)
    try:
        if Path(args.output).exists():
            raise FileExistsError("기존 결과를 덮어쓰지 않습니다. 새 --output 경로를 지정하세요.")
        if args.action == "run":
            return _run(args)
        records = load_jsonl(args.records, AnswerEvalRecord)
        if args.action == "prepare":
            # Validate duplicate IDs and mixed runs before writing a review draft.
            evaluate_records(records)
            drafts = [prepare_review(record) for record in records if record.response.status == "answered"]
            write_jsonl(args.output, drafts)
            print(f"saved {len(drafts)} pending reviews: {args.output}")
            return 0
        reviews = load_jsonl(args.reviews, AnswerReview, allow_empty=True) if args.reviews else []
        report = evaluate_records(records, reviews)
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(f"{report['semantic_status']}: {args.output}")
        _print_fact_error_table(report)
        return 2 if args.require_complete and report["pending_case_ids"] else 0
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        print(f"답변 평가 오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
