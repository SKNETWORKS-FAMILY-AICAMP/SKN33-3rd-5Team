"""검수된 세 JSONL 파일로 조건 추출용 QLoRA adapter를 학습한다.

이 스크립트는 크롤링·정제·라벨링·증강·분할을 하지 않으며, 전달 계약과
split 누수를 검증한 뒤 지도학습을 시작한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

# Allow the README's direct invocation: python training/train_qlora.py ...
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.condition_extraction.dataset import (
    assert_no_split_leakage,
    load_received_jsonl,
    validate_expected_product_ids,
)
from src.condition_extraction.prompts import build_training_example
from training.preflight import validate_token_lengths


def parse_args() -> argparse.Namespace:
    """학습 설정 경로와 데이터 검증 전용 실행 여부를 읽는다."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="training/configs/qwen3_4b_qlora.yaml",
        help="QLoRA YAML configuration",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="받은 파일의 스키마와 split 누수만 확인하고 학습하지 않습니다.",
    )
    parser.add_argument(
        "--check-token-lengths",
        action="store_true",
        help="--validate-only와 함께 train/dev 정답의 토큰 잘림도 검사합니다. 토크나이저만 필요합니다.",
    )
    parser.add_argument(
        "--hub-repo-id",
        help="학습·로컬 저장 완료 후 백업할 Hub 저장소. 예: t91004/picare-qwen3-4b-qlora",
    )
    parser.add_argument(
        "--hub-public",
        action="store_true",
        help="Hub 백업 시 공개 저장소 생성·업로드 허용. 기본은 비공개입니다.",
    )
    args = parser.parse_args()
    if args.hub_public and not args.hub_repo_id:
        parser.error("--hub-public에는 --hub-repo-id가 필요합니다.")
    if args.validate_only and args.hub_repo_id:
        parser.error("--validate-only는 --hub-repo-id와 함께 사용할 수 없습니다.")
    if args.check_token_lengths and not args.validate_only:
        parser.error("--check-token-lengths에는 --validate-only가 필요합니다. 실제 학습은 항상 길이를 검사합니다.")
    return args


def load_config(path: str | Path) -> dict[str, Any]:
    """YAML 학습 설정 파일을 읽고 최상위 mapping 형식을 확인한다."""

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML이 없습니다. requirements-training.txt를 설치하세요."
        ) from exc

    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"설정 파일이 없습니다: {resolved}")
    config = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("config 최상위는 mapping이어야 합니다.")
    return config


def set_seed(seed: int) -> None:
    """Python과 해시 seed를 고정해 가능한 범위에서 실험을 재현한다."""

    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


def received_splits(config: dict[str, Any]):
    """전달받은 train·dev·holdout을 읽고 split 간 누수를 검사한다."""

    data_config = config["data"]
    train = load_received_jsonl(data_config["train_file"])
    dev = load_received_jsonl(data_config["dev_file"])
    holdout = load_received_jsonl(data_config["holdout_file"])
    assert_no_split_leakage(train=train, dev=dev, holdout=holdout)
    if any(record.expected_product_ids for split in (train, dev, holdout) for record in split):
        from src.recommendation.schema import ProductCatalog

        catalog = ProductCatalog.from_received_file(
            data_config.get("catalog_file", "data/products/catalog.json")
        )
        validate_expected_product_ids(
            (record for split in (train, dev, holdout) for record in split),
            (product.product_id for product in catalog.products),
        )
    return train, dev, holdout


def to_hf_dataset(records):
    """검증된 레코드를 TRL이 사용할 prompt-completion Dataset으로 바꾼다."""

    from datasets import Dataset

    rows = [build_training_example(record.survey(), record.target) for record in records]
    return Dataset.from_list(rows)


def train(config: dict[str, Any]) -> None:
    """4-bit Base를 고정하고 LoRA adapter만 학습·저장하며 manifest를 남긴다."""

    # 잘못된 전달 파일은 GPU 패키지 import·가중치 다운로드 전에 거부한다.
    train_records, dev_records, holdout_records = received_splits(config)

    import torch
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed as set_model_seed
    from trl import SFTConfig, SFTTrainer

    if not torch.cuda.is_available():
        raise RuntimeError("QLoRA 학습에는 CUDA GPU가 필요합니다.")

    print(
        "validated records:",
        {"train": len(train_records), "dev": len(dev_records), "holdout": len(holdout_records)},
    )

    model_config = config["model"]
    quant_config = config["quantization"]
    lora_values = config["lora"]
    train_values = config["training"]
    set_model_seed(int(train_values["seed"]))
    model_id = model_config["id"]
    revision = model_config.get("revision", "main")
    output_dir = Path(train_values["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    compute_dtype = (
        torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    )
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=quant_config["quant_type"],
        bnb_4bit_use_double_quant=quant_config["double_quant"],
        bnb_4bit_compute_dtype=compute_dtype,
    )

    tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    token_report = validate_token_lengths(
        tokenizer, max_length=train_values["max_length"], train=train_records, dev=dev_records,
    )
    print("token validation passed:", token_report)

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        revision=revision,
        quantization_config=bnb_config,
        torch_dtype=compute_dtype,
        device_map={"": 0},
    )
    model.config.use_cache = False

    peft_config = LoraConfig(
        r=lora_values["r"],
        lora_alpha=lora_values["alpha"],
        lora_dropout=lora_values["dropout"],
        bias="none",
        target_modules=lora_values["target_modules"],
        task_type="CAUSAL_LM",
    )

    training_args = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=train_values["num_train_epochs"],
        per_device_train_batch_size=train_values["per_device_train_batch_size"],
        per_device_eval_batch_size=train_values["per_device_eval_batch_size"],
        gradient_accumulation_steps=train_values["gradient_accumulation_steps"],
        learning_rate=float(train_values["learning_rate"]),
        lr_scheduler_type=train_values["lr_scheduler_type"],
        warmup_ratio=train_values["warmup_ratio"],
        weight_decay=train_values["weight_decay"],
        max_grad_norm=train_values["max_grad_norm"],
        max_length=train_values["max_length"],
        logging_steps=train_values["logging_steps"],
        eval_strategy="steps",
        eval_steps=train_values["eval_steps"],
        save_strategy="steps",
        save_steps=train_values["save_steps"],
        save_total_limit=train_values["save_total_limit"],
        save_safetensors=True,
        # Hub 백업은 최종 어댑터·토크나이저·manifest 저장이 끝난 뒤에만 수행한다.
        push_to_hub=False,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        bf16=compute_dtype is torch.bfloat16,
        fp16=compute_dtype is torch.float16,
        tf32=True,
        optim=train_values["optim"],
        report_to="none",
        seed=train_values["seed"],
        data_seed=train_values["seed"],
        completion_only_loss=True,
        packing=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=to_hf_dataset(train_records),
        eval_dataset=to_hf_dataset(dev_records),
        peft_config=peft_config,
        processing_class=tokenizer,
    )
    trainer.model.print_trainable_parameters()
    result = trainer.train()
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    # step 간격보다 짧게 실행해도 저장한 최종 adapter의 dev loss를 확인한다.
    eval_metrics = trainer.evaluate()

    resolved_revision = getattr(model.config, "_commit_hash", None) or revision
    manifest = {
        "base_model": model_id,
        "requested_revision": revision,
        "resolved_revision": resolved_revision,
        "dataset_sizes": {
            "train": len(train_records),
            "dev": len(dev_records),
            "holdout_not_used_for_training": len(holdout_records),
        },
        "seed": train_values["seed"],
        "dataset_sha256": {
            split: hashlib.sha256(Path(config["data"][f"{split}_file"]).read_bytes()).hexdigest()
            for split in ("train", "dev", "holdout")
        },
        "token_validation": token_report,
        "train_metrics": result.metrics,
        "eval_metrics": eval_metrics,
        "config": config,
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"adapter saved: {output_dir}")


def main() -> None:
    """검증 전용 모드 또는 실제 QLoRA 학습 모드를 실행한다."""

    args = parse_args()
    config = load_config(args.config)
    seed = int(config["training"]["seed"])
    set_seed(seed)
    if args.validate_only:
        train_records, dev_records, holdout_records = received_splits(config)
        if args.check_token_lengths:
            from transformers import AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(
                config["model"]["id"], revision=config["model"].get("revision", "main"),
            )
            print("token validation passed:", validate_token_lengths(
                tokenizer, max_length=config["training"]["max_length"],
                train=train_records, dev=dev_records,
            ))
        print(
            "validation passed:",
            {"train": len(train_records), "dev": len(dev_records), "holdout": len(holdout_records)},
        )
        return
    train(config)
    if args.hub_repo_id:
        from training.publish_adapter import publish_adapter

        print("로컬 저장 완료. Hub 업로드가 실패해도 재학습 없이 별도로 재시도할 수 있습니다.")
        publish_adapter(
            config["training"]["output_dir"],
            args.hub_repo_id,
            private=not args.hub_public,
        )


if __name__ == "__main__":
    main()
