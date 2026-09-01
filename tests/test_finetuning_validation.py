"""학습 전 입력 검사와 실패 표본을 포함한 평가 지표를 검증한다."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.condition_extraction.dataset import FinetuningRecord, load_received_jsonl, validate_expected_product_ids
from src.condition_extraction.prompts import FEW_SHOT_EXAMPLES
from src.condition_extraction.parser import ConditionOutputError, parse_condition_output
from src.evaluation.extractor_eval import calculate_metrics
from training.preflight import validate_token_lengths


def record_payload(record_id="train-1"):
    survey, target = FEW_SHOT_EXAMPLES[0]
    return {
        "id": record_id,
        "answers": [answer.model_dump() for answer in survey.answers],
        "target": target.model_dump(),
        "expected_product_ids": [],
    }


@pytest.mark.parametrize("case", ["duplicate_question", "long_id", "blank_question", "blank_answer", "string_bool"])
def test_invalid_training_input_is_rejected_on_load(tmp_path, case):
    payload = record_payload()
    if case == "duplicate_question":
        payload["answers"].append(payload["answers"][0])
    elif case == "long_id":
        payload["id"] = "x" * 101
    elif case == "string_bool":
        payload["target"]["wireless_required"] = "true"
    else:
        payload["answers"][0][case.removeprefix("blank_")] = " \t "
    path = tmp_path / "train.jsonl"
    original = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    path.write_bytes(original)
    with pytest.raises(ValueError, match="train.jsonl:1"):
        load_received_jsonl(path)
    assert path.read_bytes() == original


def test_recommendation_accuracy_counts_failed_json_as_incorrect():
    records = [FinetuningRecord.model_validate(record_payload(f"eval-{i}")) for i in range(2)]
    for record in records:
        record.expected_product_ids = ["known-board"]
    recommender = Mock()
    recommender.recommend.return_value = SimpleNamespace(
        candidates=[SimpleNamespace(product_id="known-board")]
    )
    metrics = calculate_metrics(records, [records[0].target, None], recommender)
    assert metrics["json_schema_valid_rate"] == 0.5
    assert metrics["recommendation_evaluated_count"] == 2
    assert metrics["recommendation_top1_accuracy"] == 0.5
    recommender.recommend.assert_called_once()


@pytest.mark.parametrize("predictions", [[], [None, None]])
def test_metrics_reject_mismatched_prediction_counts(predictions):
    records = [FinetuningRecord.model_validate(record_payload())]
    with pytest.raises(ValueError, match="예측"):
        calculate_metrics(records, predictions, None)


def test_metrics_reject_empty_evaluation():
    with pytest.raises(ValueError, match="비어"):
        calculate_metrics([], [], None)


def test_unknown_evaluation_product_is_rejected():
    record = FinetuningRecord.model_validate(record_payload())
    record.expected_product_ids = ["typo-board"]
    with pytest.raises(ValueError, match="train-1.*typo-board"):
        validate_expected_product_ids([record], ["known-board"])


def test_model_string_boolean_is_invalid_and_preserves_raw_output():
    target = record_payload()["target"]
    target["wireless_required"] = "false"
    raw = json.dumps(target, ensure_ascii=False)
    with pytest.raises(ConditionOutputError) as exc:
        parse_condition_output(raw)
    assert exc.value.raw_output == raw


class BoundaryTokenizer:
    """토큰 수·경계 조건을 재현하며 외부 모델 다운로드는 하지 않는다."""

    def __init__(self, prompt, full):
        self.prompt = prompt
        self.full = full

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt=False):
        return self.prompt if add_generation_prompt else self.full


@pytest.mark.parametrize("limit", [3, 5])
def test_token_preflight_blocks_fully_or_partly_truncated_answer(limit):
    record = FinetuningRecord.model_validate(record_payload())
    tokenizer = BoundaryTokenizer([1, 2, 3, 4], [1, 2, 3, 4, 5, 6])
    with pytest.raises(ValueError, match="train/train-1.*정답이 잘립니다"):
        validate_token_lengths(tokenizer, max_length=limit, train=[record])


@pytest.mark.parametrize("full", [[1, 2], [9, 2, 3]])
def test_token_preflight_rejects_empty_completion_or_mismatched_boundary(full):
    record = FinetuningRecord.model_validate(record_payload())
    tokenizer = BoundaryTokenizer([1, 2], full)
    with pytest.raises(ValueError):
        validate_token_lengths(tokenizer, max_length=10, train=[record])


def test_token_preflight_accepts_exact_limit_without_using_holdout():
    record = FinetuningRecord.model_validate(record_payload())
    tokenizer = BoundaryTokenizer([1, 2, 3, 4], [1, 2, 3, 4, 5, 6])
    report = validate_token_lengths(tokenizer, max_length=6, train=[record], dev=[record])
    assert set(report) == {"train", "dev"}
    assert report["train"]["min_completion_tokens"] == 2
    assert report["dev"]["max_total_tokens"] == 6


def test_training_rejects_invalid_data_before_importing_gpu_packages(tmp_path):
    from training.train_qlora import train

    config = {"data": {"train_file": str(tmp_path / "missing-train.jsonl")}}
    with pytest.raises(FileNotFoundError, match="missing-train.jsonl"):
        train(config)


@pytest.mark.parametrize("too_short", [False, True])
def test_training_boundary_preserves_holdout_and_checks_lengths_before_weights(tmp_path, monkeypatch, too_short):
    """학습 연결부 대역 검사이며 CUDA나 실제 최적화 성공을 의미하지 않는다."""
    import hashlib
    import sys
    from training import train_qlora

    config = train_qlora.load_config("training/configs/qwen3_4b_qlora.yaml")
    originals = {}
    for split in ("train", "dev", "holdout"):
        path = tmp_path / f"{split}.jsonl"
        payload = record_payload(f"{split}-1")
        payload["answers"][0]["answer"] = f"{split} 전용 테스트 입력"
        original = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        path.write_bytes(original)
        originals[split] = original
        config["data"][f"{split}_file"] = str(path)
    config["training"]["output_dir"] = str(tmp_path / "adapter")
    config["training"]["max_length"] = 3 if too_short else 6
    tokenizer = Mock()
    tokenizer.apply_chat_template.side_effect = BoundaryTokenizer([1, 2, 3, 4], [1, 2, 3, 4, 5, 6]).apply_chat_template
    model_loader = Mock(return_value=SimpleNamespace(config=SimpleNamespace(_commit_hash="test-revision")))
    trainer = Mock()
    trainer.train.return_value = SimpleNamespace(metrics={"train_loss": 1.25})
    trainer.evaluate.return_value = {"eval_loss": 1.5}
    trainer_factory = Mock(return_value=trainer)
    config_factory = Mock(side_effect=lambda **values: SimpleNamespace(**values))
    seed = Mock()
    modules = {
        "torch": SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True, is_bf16_supported=lambda: True), bfloat16=object(), float16=object()),
        "transformers": SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=Mock(return_value=tokenizer)),
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=model_loader),
            BitsAndBytesConfig=lambda **values: values, set_seed=seed,
        ),
        "peft": SimpleNamespace(LoraConfig=lambda **values: values),
        "trl": SimpleNamespace(SFTConfig=config_factory, SFTTrainer=trainer_factory),
        "datasets": SimpleNamespace(Dataset=SimpleNamespace(from_list=lambda rows: rows)),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    if too_short:
        with pytest.raises(ValueError, match="정답이 잘립니다"):
            train_qlora.train(config)
        model_loader.assert_not_called()
        trainer.train.assert_not_called()
        return

    train_qlora.train(config)
    seed.assert_called_once_with(42)
    passed = trainer_factory.call_args.kwargs
    assert "train 전용" in passed["train_dataset"][0]["prompt"][-1]["content"]
    assert "dev 전용" in passed["eval_dataset"][0]["prompt"][-1]["content"]
    assert "holdout 전용" not in str(passed)
    assert config_factory.call_args.kwargs["completion_only_loss"] is True
    assert config_factory.call_args.kwargs["push_to_hub"] is False
    trainer.save_model.assert_called_once_with(str(tmp_path / "adapter"))
    tokenizer.save_pretrained.assert_called_once_with(str(tmp_path / "adapter"))
    manifest = json.loads((tmp_path / "adapter" / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["eval_metrics"]["eval_loss"] == 1.5
    assert manifest["dataset_sizes"]["holdout_not_used_for_training"] == 1
    assert set(manifest["token_validation"]) == {"train", "dev"}
    for split, original in originals.items():
        assert (tmp_path / f"{split}.jsonl").read_bytes() == original
        assert manifest["dataset_sha256"][split] == hashlib.sha256(original).hexdigest()
