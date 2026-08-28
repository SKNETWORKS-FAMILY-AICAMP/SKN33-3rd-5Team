# 받게 되는 파일: sLLM 지도학습 데이터

`data/finetuning/train.jsonl`, `dev.jsonl`, `holdout.jsonl`은 이 코드가 생성하거나 전처리하지 않는다. 팀이 설문 문항과 조건 라벨을 작성·교차 검수하고, 문서·데이터 담당이 중복 제거와 split을 완료한 뒤 전달한다. `data/`는 저장소 정책상 Git에서 제외되므로 실제 파일은 팀 내부 저장소나 RunPod volume로 공유한다.

## 전달 파일

| 파일 | 용도 | 학습 중 사용 |
|---|---|---|
| `train.jsonl` | QLoRA adapter 학습 | 사용 |
| `dev.jsonl` | loss 확인·설정 선택 | 사용 |
| `holdout.jsonl` | 최종 Base–LoRA 비교 | 절대 사용하지 않음 |

각 줄은 독립된 UTF-8 JSON 객체이며 다음 계약을 따른다.

```json
{
  "id": "survey-0001",
  "answers": [
    {
      "question_id": "purpose",
      "question": "사용 목적이 무엇인가요?",
      "answer": "초등학생이 파이썬을 처음 배우는 교육용입니다."
    },
    {
      "question_id": "environment",
      "question": "사용 환경은 어떤가요?",
      "answer": "집의 모니터와 Wi-Fi를 사용합니다."
    }
  ],
  "target": {
    "schema_version": "1.1.0",
    "intent": "product_recommendation",
    "use_case": "education_coding",
    "product_models": null,
    "os_versions": null,
    "task": "desktop_programming",
    "performance_priority": "medium",
    "wireless_required": true,
    "camera_required": false,
    "gpio_required": false,
    "monitor_available": true,
    "remote_access_required": null,
    "user_level": "beginner",
    "needs_clarification": false,
    "clarification_questions": []
  },
  "expected_product_ids": ["team-catalog-product-id"]
}
```

`target`은 [src/contracts/models.py](../../src/contracts/models.py)의 `ConditionPayload`를 그대로 따른다. `expected_product_ids`는 추천 Top-1 정확도까지 평가할 때만 넣으며 학습 loss에는 사용하지 않는다. 사용자가 말하지 않은 조건은 `null`, 명시적으로 불필요하다고 말한 조건만 `false`로 라벨링한다.

## 역할 경계

- 문서·데이터 담당: 원시 응답 정리, JSONL 직렬화, 중복 제거, train/dev/holdout 분리, 파일 전달
- sLLM·파인튜닝 담당: `target` JSON Schema 정의, 라벨 가이드 승인, 전달 파일 검증, QLoRA 학습, Base–LoRA 평가 및 오류 분석
- 팀 공동: 실제 문항과 정답 라벨 작성·교차 검수

즉 sLLM 담당이 공식 문서를 크롤링·청킹하거나 받은 데이터를 다시 전처리하지는 않지만, 모델이 무엇을 학습하는지 결정하는 라벨 계약과 품질 확인은 담당 범위다.

## 받자마자 실행

```bash
python training/train_qlora.py \
  --config training/configs/qwen3_4b_qlora.yaml \
  --validate-only
```

검증기는 파일을 수정하지 않으며 다음 오류에서 즉시 중단한다.

- 누락·추가·오탈자 필드
- 허용되지 않은 enum 또는 모순된 확인 질문
- 한 파일 안의 중복 ID
- train/dev/holdout 사이의 동일 ID 또는 동일 설문 응답
