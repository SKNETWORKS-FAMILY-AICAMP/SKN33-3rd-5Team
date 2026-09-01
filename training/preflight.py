"""모델 가중치를 로드하지 않고 정답 토큰의 잘림을 검사한다."""

from src.condition_extraction.prompts import build_training_example


def validate_token_lengths(tokenizer, *, max_length: int, **splits) -> dict:
    """train/dev의 전체 입력과 completion 경계를 같은 chat template로 확인한다."""

    if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length <= 0:
        raise ValueError("max_length는 양의 정수여야 합니다.")
    report = {}
    for split_name, records in splits.items():
        lengths = []
        completion_lengths = []
        for record in records:
            example = build_training_example(record.survey(), record.target)
            prompt_ids = tokenizer.apply_chat_template(
                example["prompt"], tokenize=True, add_generation_prompt=True,
            )
            full_ids = tokenizer.apply_chat_template(
                example["prompt"] + example["completion"], tokenize=True,
            )
            if full_ids[:len(prompt_ids)] != prompt_ids:
                raise ValueError(f"{split_name}/{record.id}: prompt와 completion의 토큰 경계가 다릅니다.")
            completion_length = len(full_ids) - len(prompt_ids)
            if completion_length <= 0:
                raise ValueError(f"{split_name}/{record.id}: 학습할 정답 토큰이 없습니다.")
            if len(full_ids) > max_length:
                raise ValueError(
                    f"{split_name}/{record.id}: 전체 {len(full_ids)}토큰 "
                    f"(prompt {len(prompt_ids)}, 정답 {completion_length})이 "
                    f"max_length={max_length}를 초과해 정답이 잘립니다. "
                    "train/dev 길이를 확인해 설정을 늘리세요. 원본은 수정하지 않습니다."
                )
            lengths.append(len(full_ids))
            completion_lengths.append(completion_length)
        if not lengths:
            raise ValueError(f"{split_name}: 비어 있는 데이터셋입니다.")
        report[split_name] = {
            "record_count": len(lengths),
            "max_total_tokens": max(lengths),
            "min_completion_tokens": min(completion_lengths),
            "max_completion_tokens": max(completion_lengths),
        }
    return report
