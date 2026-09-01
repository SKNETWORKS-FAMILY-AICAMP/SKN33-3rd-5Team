"""동일 프롬프트와 holdout으로 Base few-shot과 QLoRA를 공정하게 평가한다."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from enum import Enum
from pathlib import Path
from typing import Any

from src.condition_extraction.baseline import BaselineConditionExtractor
from src.condition_extraction.dataset import load_received_jsonl, validate_expected_product_ids
from src.condition_extraction.lora import LoraConditionExtractor
from src.condition_extraction.prompts import SYSTEM_PROMPT
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

DIAGNOSTIC_FIELDS = tuple(
    field for field in ConditionPayload.model_fields if field != "schema_version"
)
BOUNDARY_FIELDS = ("intent", "use_case", "task")


def parse_args() -> argparse.Namespace:
    """평가 모드·데이터·모델·카탈로그·출력 경로 인자를 읽는다."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "lora"))
    parser.add_argument("--data", default="data/finetuning/holdout.jsonl")
    parser.add_argument("--model-id", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--adapter-path")
    parser.add_argument("--catalog", default=None)
    parser.add_argument(
        "--diagnose-report",
        help="이미 생성한 extractor_eval JSON 보고서를 모델 재실행 없이 진단한다.",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.diagnose_report and args.mode:
        parser.error("--diagnose-report와 --mode는 함께 사용할 수 없습니다.")
    if not args.diagnose_report and not args.mode:
        parser.error("모델 평가에는 --mode가 필요합니다.")
    return args


def normalized(value: Any) -> str:
    """enum·null·배열을 필드별 비교에 안정적인 문자열로 정규화한다."""

    if isinstance(value, Enum):
        value = value.value
    if value is None:
        return "__null__"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _raw_json_object(raw_output: str | None) -> dict[str, Any] | None:
    """스키마 실패 원인을 보기 위해 원문 JSON만 읽고 값은 보정하지 않는다."""

    if not raw_output:
        return None
    text = raw_output.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        payload, end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    if text[start + end :].strip() or not isinstance(payload, dict):
        return None
    return payload


def _difference_kind(label: Any, prediction: Any) -> str:
    """오류를 누락·미제공 값 생성·다른 값으로만 분류해 측정 기준을 고정한다."""

    if label is not None and prediction is None:
        return "omission"
    if label is None and prediction is not None:
        return "unprovided_value"
    return "different_value"


def _diagnostic_value(value: str) -> Any:
    """그룹 키로 정규화한 값을 보고서에서 원래 JSON 타입으로 되돌린다."""

    if value == "__null__":
        return None
    if value == "True":
        return True
    if value == "False":
        return False
    if value.startswith(("[", "{")):
        return json.loads(value)
    return value


def _prompt_boundary_audit(records) -> dict[str, Any]:
    """세 경계 필드의 프롬프트 정의 유무와 라벨 스키마 상태를 나란히 둔다."""

    prompt_lines: dict[str, list[str]] = {}
    semantic_definition_lines: dict[str, list[str]] = {}
    for field in BOUNDARY_FIELDS:
        occurrences = [
            line.strip()
            for line in SYSTEM_PROMPT.splitlines()
            if field in line
        ]
        allowed_prefix = f"- {field}:"
        prompt_lines[field] = occurrences
        semantic_definition_lines[field] = [
            line for line in occurrences if not line.startswith(allowed_prefix)
        ]

    label_value_counts = {
        field: dict(
            sorted(
                Counter(normalized(getattr(record.target, field)) for record in records).items()
            )
        )
        for field in BOUNDARY_FIELDS
    }
    missing = [
        field for field, lines in semantic_definition_lines.items() if not lines
    ]
    return {
        "prompt_lines": prompt_lines,
        "semantic_definition_lines": semantic_definition_lines,
        "fields_without_semantic_definition": missing,
        "labels_schema_valid": True,
        "label_value_counts": label_value_counts,
        "finding": (
            "프롬프트에는 intent/use_case/task 허용값만 있고 세 필드의 의미·경계 정의가 없습니다. "
            "라벨은 공통 ConditionPayload 스키마에는 모두 유효하지만, 의미 경계의 일관성은 이 "
            "프롬프트만으로 판정할 수 없어 아래 실제 혼동 사례와 함께 사람 검수가 필요합니다."
            if missing
            else "세 경계 필드 모두 허용값 외의 의미 정의가 프롬프트에 있습니다."
        ),
    }


def diagnose_samples(records, samples: list[dict[str, Any]]) -> dict[str, Any]:
    """입력·라벨·원출력을 보존하며 불일치와 필드 혼동 횟수를 집계한다."""

    if len(records) != len(samples):
        raise ValueError("평가 데이터와 보고서 samples 개수가 다릅니다.")

    field_error_counts: Counter[str] = Counter()
    error_type_counts: Counter[str] = Counter()
    confusion_groups: defaultdict[
        tuple[str, str, str, str], list[str]
    ] = defaultdict(list)
    schema_confusion_groups: defaultdict[
        tuple[str, str, str, str, str | None], list[str]
    ] = defaultdict(list)
    mismatches: list[dict[str, Any]] = []
    schema_failures: list[dict[str, Any]] = []

    for record, sample in zip(records, samples):
        if sample.get("id") != record.id:
            raise ValueError(
                f"평가 데이터와 보고서 ID 순서가 다릅니다: {record.id!r} != {sample.get('id')!r}"
            )
        label = record.target.model_dump(mode="json")
        if sample.get("label") != label:
            raise ValueError(f"{record.id}: 보고서 정답 라벨이 평가 데이터와 다릅니다.")

        raw_output = sample.get("raw_output")
        error = sample.get("error")
        prediction_payload = sample.get("prediction")
        differences: list[dict[str, Any]] = []
        invalid = prediction_payload is None
        if invalid:
            error_type_counts["schema_or_extraction_failure"] += 1
            raw_payload = _raw_json_object(raw_output)
            raw_differences: list[dict[str, Any]] = []
            if raw_payload is not None:
                for field in BOUNDARY_FIELDS:
                    if field not in raw_payload:
                        continue
                    prediction = raw_payload[field]
                    expected = label[field]
                    if normalized(prediction) == normalized(expected):
                        continue
                    source_field = next(
                        (
                            other
                            for other in BOUNDARY_FIELDS
                            if other != field
                            and normalized(prediction) == normalized(label[other])
                        ),
                        None,
                    )
                    raw_differences.append(
                        {
                            "field": field,
                            "label": expected,
                            "prediction": prediction,
                            "kind": (
                                "cross_field_value" if source_field else _difference_kind(expected, prediction)
                            ),
                            "source_field": source_field,
                        }
                    )
                    schema_confusion_groups[
                        (
                            field,
                            normalized(expected),
                            normalized(prediction),
                            "cross_field_value" if source_field else "schema_failure_value",
                            source_field,
                        )
                    ].append(record.id)
            schema_failures.append(
                {
                    "id": record.id,
                    "answers": [
                        item.model_dump(mode="json") for item in record.answers
                    ],
                    "label": label,
                    "raw_output": raw_output,
                    "error": error,
                    "raw_boundary_differences": raw_differences,
                }
            )
        else:
            try:
                prediction = ConditionPayload.model_validate(prediction_payload, strict=True)
            except ValueError as exc:
                raise ValueError(f"{record.id}: valid sample의 prediction 스키마가 잘못됐습니다.") from exc
            prediction = prediction.model_dump(mode="json")
            for field in DIAGNOSTIC_FIELDS:
                expected = label[field]
                actual = prediction[field]
                if normalized(expected) == normalized(actual):
                    continue
                kind = _difference_kind(expected, actual)
                field_error_counts[field] += 1
                error_type_counts[kind] += 1
                differences.append(
                    {
                        "field": field,
                        "kind": kind,
                        "label": expected,
                        "prediction": actual,
                    }
                )
                confusion_groups[
                    (field, normalized(expected), normalized(actual), kind)
                ].append(record.id)

        if differences:
            mismatches.append(
                {
                    "id": record.id,
                    "answers": [item.model_dump(mode="json") for item in record.answers],
                    "label": label,
                    "prediction": prediction_payload,
                    "raw_output": raw_output,
                    "error": error,
                    "differences": differences,
                }
            )

    field_confusions = [
        {
            "field": field,
            "label": _diagnostic_value(label),
            "prediction": _diagnostic_value(prediction),
            "kind": kind,
            "count": len(record_ids),
            "record_ids": record_ids,
        }
        for (field, label, prediction, kind), record_ids in sorted(
            confusion_groups.items(), key=lambda item: (-len(item[1]), item[0])
        )
    ]
    schema_boundary_confusions = [
        {
            "field": field,
            "label": _diagnostic_value(label),
            "prediction": _diagnostic_value(prediction),
            "kind": kind,
            "source_field": source_field,
            "count": len(record_ids),
            "record_ids": record_ids,
        }
        for (
            field,
            label,
            prediction,
            kind,
            source_field,
        ), record_ids in sorted(
            schema_confusion_groups.items(),
            key=lambda item: (
                -len(item[1]),
                tuple("" if value is None else str(value) for value in item[0]),
            ),
        )
    ]
    return {
        "summary": {
            "record_count": len(records),
            "mismatched_records": len(mismatches),
            "schema_failure_records": len(schema_failures),
            "problematic_records": len(mismatches) + len(schema_failures),
            "field_error_counts": dict(field_error_counts.most_common()),
            "error_types": dict(error_type_counts.most_common()),
        },
        "boundary_definition_audit": _prompt_boundary_audit(records),
        "field_confusions": field_confusions,
        "boundary_confusions": [
            row for row in field_confusions if row["field"] in BOUNDARY_FIELDS
        ] + schema_boundary_confusions,
        "schema_boundary_confusions": schema_boundary_confusions,
        "schema_failures": schema_failures,
        "mismatches": mismatches,
    }


def _load_existing_report(path: str | Path) -> dict[str, Any]:
    """모델 재실행 없이 진단할 기존 평가 보고서의 최소 구조를 확인한다."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("samples"), list):
        raise ValueError("진단할 보고서에 samples 배열이 없습니다.")
    return payload


def _print_diagnostic_table(diagnostics: dict[str, Any]) -> None:
    """PM 전달용 필드·혼동·건수 표를 표준 출력에도 남긴다."""

    print("field\tlabel\tprediction\tkind\tcount")
    for row in diagnostics["field_confusions"]:
        print(
            f"{row['field']}\t{json.dumps(row['label'], ensure_ascii=False)}\t"
            f"{json.dumps(row['prediction'], ensure_ascii=False)}\t{row['kind']}\t{row['count']}"
        )
    for row in diagnostics["schema_boundary_confusions"]:
        print(
            f"{row['field']}\t{json.dumps(row['label'], ensure_ascii=False)}\t"
            f"{json.dumps(row['prediction'], ensure_ascii=False)}\t"
            f"schema_{row['kind']}\t{row['count']}"
        )


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
    if args.diagnose_report:
        source_report = _load_existing_report(args.diagnose_report)
        diagnostics = diagnose_samples(records, source_report["samples"])
        diagnostics["summary"]["metrics"] = source_report.get("metrics")
        diagnostics["source_report"] = args.diagnose_report
        diagnostics["data"] = args.data
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(diagnostics["summary"], ensure_ascii=False, indent=2))
        _print_diagnostic_table(diagnostics)
        print(f"diagnostic report saved: {output}")
        return

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
    report["diagnostics"] = diagnose_samples(records, samples)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    _print_diagnostic_table(report["diagnostics"])
    print(f"report saved: {output}")


if __name__ == "__main__":
    main()
