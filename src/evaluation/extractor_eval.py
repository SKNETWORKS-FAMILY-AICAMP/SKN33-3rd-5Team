"""동일 프롬프트와 holdout으로 Base few-shot과 QLoRA를 공정하게 평가한다."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Any

from src.condition_extraction.baseline import BaselineConditionExtractor
from src.condition_extraction.dataset import load_received_jsonl, validate_expected_product_ids
from src.condition_extraction.lora import LoraConditionExtractor
from src.contracts import ConditionPayload
from src.recommendation.engine import ProductRecommender
from src.recommendation.schema import ProductCatalog


SCORABLE_FIELDS = (
    "intent",
    "use_case",
    "product_models",
    "os_versions",
    "task",
    "performance_priority",
    "wireless_required",
    "camera_required",
    "gpio_required",
    "monitor_available",
    "remote_access_required",
    "user_level",
    "needs_clarification",
)


def parse_args() -> argparse.Namespace:
    """평가 모드·데이터·모델·카탈로그·출력 경로 인자를 읽는다."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "lora"), required=True)
    parser.add_argument("--data", default="data/finetuning/holdout.jsonl")
    parser.add_argument("--model-id", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--adapter-path")
    parser.add_argument("--catalog", default=None)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def normalized(value: Any) -> str:
    """enum·null·배열을 필드별 비교에 안정적인 문자열로 정규화한다."""

    if isinstance(value, Enum):
        value = value.value
    if value is None:
        return "__null__"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def field_macro_f1(
    labels: list[ConditionPayload],
    predictions: list[ConditionPayload | None],
) -> dict[str, float]:
    """각 조건 필드의 클래스별 F1을 평균해 Macro F1을 계산한다."""

    results: dict[str, float] = {}
    for field in SCORABLE_FIELDS:
        gold = [normalized(getattr(item, field)) for item in labels]
        pred = [
            normalized(getattr(item, field)) if item is not None else "__invalid__"
            for item in predictions
        ]
        classes = sorted(set(gold) | set(pred))
        f1_values: list[float] = []
        for class_name in classes:
            tp = sum(g == class_name and p == class_name for g, p in zip(gold, pred))
            fp = sum(g != class_name and p == class_name for g, p in zip(gold, pred))
            fn = sum(g == class_name and p != class_name for g, p in zip(gold, pred))
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if precision + recall
                else 0.0
            )
            f1_values.append(f1)
        results[field] = sum(f1_values) / len(f1_values) if f1_values else 0.0
    return results


def calculate_metrics(
    records,
    predictions: list[ConditionPayload | None],
    recommender: ProductRecommender | None,
) -> dict[str, Any]:
    """스키마·정확도·환각 조건·추천 Top-1 지표를 한 번에 계산한다."""

    labels = [record.target for record in records]
    count = len(records)
    if not count:
        raise ValueError("평가 데이터가 비어 있습니다.")
    if len(predictions) != count:
        raise ValueError("평가 레코드와 예측 개수가 다릅니다.")
    valid_count = sum(prediction is not None for prediction in predictions)
    exact_count = sum(
        prediction is not None and prediction == label
        for prediction, label in zip(predictions, labels)
    )

    field_accuracy: dict[str, float] = {}
    for field in SCORABLE_FIELDS:
        correct = sum(
            prediction is not None
            and normalized(getattr(prediction, field)) == normalized(getattr(label, field))
            for prediction, label in zip(predictions, labels)
        )
        field_accuracy[field] = correct / count

    invention_opportunities = 0
    inventions = 0
    for prediction, label in zip(predictions, labels):
        if prediction is None:
            continue
        for field in SCORABLE_FIELDS:
            if field == "needs_clarification":
                continue
            if getattr(label, field) is None:
                invention_opportunities += 1
                if getattr(prediction, field) is not None:
                    inventions += 1

    recommendation_total = 0
    recommendation_correct = 0
    if recommender is not None:
        for record, prediction in zip(records, predictions):
            if not record.expected_product_ids:
                continue
            recommendation_total += 1
            if prediction is None:
                continue
            decision = recommender.recommend(prediction)
            if decision.candidates:
                recommendation_correct += (
                    decision.candidates[0].product_id in record.expected_product_ids
                )

    macro_f1_by_field = field_macro_f1(labels, predictions)
    return {
        "record_count": count,
        "json_schema_valid_rate": valid_count / count,
        "exact_match_rate": exact_count / count,
        "field_accuracy": field_accuracy,
        "field_macro_f1": macro_f1_by_field,
        "overall_macro_f1": sum(macro_f1_by_field.values()) / len(macro_f1_by_field),
        "unprovided_condition_invention_rate": (
            inventions / invention_opportunities if invention_opportunities else 0.0
        ),
        "recommendation_top1_accuracy": (
            recommendation_correct / recommendation_total
            if recommendation_total
            else None
        ),
        "recommendation_evaluated_count": recommendation_total,
    }


def main() -> None:
    """선택한 추출기로 holdout을 예측하고 샘플별 JSON 평가 보고서를 저장한다."""

    args = parse_args()
    records = load_received_jsonl(args.data)
    recommender = None
    if args.catalog:
        catalog = ProductCatalog.from_received_file(args.catalog)
        validate_expected_product_ids(records, (product.product_id for product in catalog.products))
        recommender = ProductRecommender(catalog)

    if args.mode == "baseline":
        extractor = BaselineConditionExtractor(model_id=args.model_id)
    else:
        if not args.adapter_path:
            raise ValueError("--mode lora에는 --adapter-path가 필요합니다.")
        extractor = LoraConditionExtractor(
            args.adapter_path, model_id=args.model_id
        )

    predictions: list[ConditionPayload | None] = []
    samples: list[dict[str, Any]] = []
    error_counts: defaultdict[str, int] = defaultdict(int)
    for index, record in enumerate(records, start=1):
        try:
            result = extractor.extract_with_raw(record.survey())
            prediction = result.conditions
            raw_output = result.raw_output
            error = None
        except Exception as exc:
            prediction = None
            raw_output = getattr(exc, "raw_output", None)
            error = f"{type(exc).__name__}: {exc}"
            error_counts[type(exc).__name__] += 1
        predictions.append(prediction)
        samples.append(
            {
                "id": record.id,
                "prediction": prediction.model_dump(mode="json") if prediction else None,
                "label": record.target.model_dump(mode="json"),
                "raw_output": raw_output,
                "error": error,
            }
        )
        print(f"[{index}/{len(records)}] {record.id}: {'ok' if prediction else 'invalid'}")

    report = {
        "mode": args.mode,
        "model_id": args.model_id,
        "adapter_path": args.adapter_path,
        "data": args.data,
        "metrics": calculate_metrics(records, predictions, recommender),
        "error_counts": dict(error_counts),
        "samples": samples,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"report saved: {output}")


if __name__ == "__main__":
    main()
