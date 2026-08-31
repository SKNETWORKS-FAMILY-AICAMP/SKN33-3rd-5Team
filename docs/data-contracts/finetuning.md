# 받게 되는 파일: sLLM 지도학습 데이터

`data/finetuning/train.jsonl`, `dev.jsonl`, `holdout.jsonl`은 이 코드가 생성하거나 전처리하지 않는다. 팀이 설문 문항과 조건 라벨을 작성·교차 검수하고, 문서·데이터 담당이 중복 제거와 split을 완료한 뒤 전달한다. `data/`는 저장소 정책상 Git에서 제외되므로 실제 파일은 팀 내부 저장소나 RunPod volume로 공유한다.

## 전달 파일

| 파일 | 용도 | 학습 중 사용 |
|---|---|---|
| `train.jsonl` | QLoRA adapter 학습 | 사용 |
| `dev.jsonl` | loss 확인·설정 선택 | 사용 |
| `holdout.jsonl` | 최종 Base–LoRA 비교 | 절대 사용하지 않음 |

각 줄은 독립된 UTF-8 JSON 객체이며 다음 계약을 따른다.
아래는 읽기 쉽게 펼친 **한 레코드**다. 실제 JSONL에서는 이 객체 전체를 한 줄로 저장한다.
자유 문장도 별도 `input` 필드를 만들지 않고 `answers`에 질문·답변 한 쌍으로 넣는다.

```json
{
  "id": "survey-0001",
  "answers": [
    {
      "question_id": "purpose",
      "question": "어떤 용도의 Raspberry Pi를 추천받고 싶나요?",
      "answer": "초등학생이 집의 모니터에서 파이썬을 처음 배우는 교육용 보드를 추천해 주세요."
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
    "performance_priority": null,
    "wireless_required": true,
    "camera_required": null,
    "gpio_required": null,
    "monitor_available": true,
    "remote_access_required": null,
    "user_level": "beginner",
    "needs_clarification": false,
    "clarification_questions": []
  },
  "expected_product_ids": []
}
```

`target`은 [src/contracts/models.py](../../src/contracts/models.py)의 `ConditionPayload`를 그대로 따른다. `expected_product_ids`는 추천 Top-1 정확도까지 평가할 때만 넣으며 학습 loss에는 사용하지 않는다. 사용자가 말하지 않은 조건은 `null`, 명시적으로 불필요하다고 말한 조건만 `false`로 라벨링한다.

## 필드와 라벨 작성 규칙

| 항목 | 전달 규칙 |
|---|---|
| `id` | 세 파일 전체에서 고유한 짧은 문자열. 예: `train-0001`. 학습 레코드는 최대 120자를 허용하지만 입력 세션은 100자 제한이므로 전달 ID는 1~100자로 작성한다. |
| `answers` | 1~20개. 자유 입력 한 문장이면 1개면 충분하다. 각 항목에 `question_id`, `question`, `answer`가 모두 필요하다. |
| `question_id` | 영문 소문자·숫자·`_`·`-`, 1~80자. 예: `purpose`, `environment`, `free_text`. 한 레코드 안에서 중복 금지. 가능한 한 같은 문항 ID·순서를 유지한다. |
| `question`, `answer` | 각각 1~500자, 1~2,000자. 공백만 있는 값은 사용하지 않는다. |
| `target` | 아래 15개 필드를 모두 포함하는 JSON 객체. JSON을 문자열로 감싸거나 답변 설명·제품 사양·URL을 추가하지 않는다. |
| `expected_product_ids` | 선택 항목. 생략 또는 `[]` 가능. 제품 순위 평가용으로 사용할 때만 검수된 `catalog.products[].product_id`를 넣는다. 제품 이름을 대신 넣지 않는다. |

| `target` 필드 | 허용값 / 의미 |
|---|---|
| `schema_version` | 문자열 `"1.1.0"` |
| `intent` | `product_recommendation`, `product_comparison`, `how_to`, `troubleshooting`, `support_recall`, `out_of_scope` 중 하나 |
| `use_case` | `education_coding`, `desktop_computing`, `home_server`, `camera_monitoring`, `smart_farm_monitoring`, `headless_remote_management`, `gpio_iot` 또는 `null` |
| `product_models` | 사용자가 지정한 제품명 문자열 배열 또는 `null`. 추천할 제품을 정답처럼 미리 넣지 않는다. |
| `os_versions` | 사용자가 지정한 OS/버전 문자열 배열 또는 `null` |
| `task` | `desktop_programming`, `os_installation`, `system_configuration`, `remote_access`, `camera_setup`, `gpio_setup`, `sensor_monitoring`, `server_operation`, `troubleshooting`, `support_recall` 또는 `null` |
| `performance_priority` | `low`, `medium`, `high` 또는 `null`. 교육용이라는 이유만으로 `medium`, 센서용이라는 이유만으로 `low`를 넣지 않는다. |
| `wireless_required` | Wi-Fi 등 무선 필요 여부: `true` / `false` / `null` |
| `camera_required` | 카메라 필요 여부: `true` / `false` / `null` |
| `gpio_required` | GPIO 필요 여부: `true` / `false` / `null` |
| `monitor_available` | 모니터 사용 가능 여부: `true` / `false` / `null`. ‘모니터 없음’이면 `false`. |
| `remote_access_required` | 원격 접속 필요 여부: `true` / `false` / `null`. 모니터가 없다는 이유만으로 자동으로 `true`를 넣지 않는다. |
| `user_level` | `beginner`, `intermediate`, `advanced` 또는 `null` |
| `needs_clarification` | 목적이 불명확하거나 답변이 충돌하여 사용자 확인이 필요하면 `true`, 아니면 `false` |
| `clarification_questions` | 확인 필요 시 짧은 한국어 질문 1~3개, 아니면 반드시 `[]`. 현재 코드가 검사하는 것은 확인 여부와 질문 목록의 비어 있음/있음이며, 3개 상한은 프롬프트·작성 규칙이다. |

질문 문맥도 함께 읽는다. 예를 들어 “Wi-Fi가 필요한가요?”에 “네”라고 답했다면 `wireless_required=true`다.
반대로 관련 언급이 없으면 `null`이며, `null` 필드가 있다는 이유만으로 반드시 확인 질문을 만들지는 않는다.
문장의 의미를 허용 태그로 분류하되, 다른 조건까지 추측하지 않는다. 센서를 쓴다는 사실만으로 GPIO 연결 방식을 확정하지 않는다.
중복 목적·충돌 답변의 우선순위가 합의되지 않았다면 작성자가 임의로 결정하지 않고 이양원에게 검수를 요청한다.

## 파일 저장과 데이터 분리

- UTF-8, BOM 없이 저장한다. Python에서는 `json.dumps(record, ensure_ascii=False)` 결과마다 줄바꿈 하나를 붙인다.
- 파일 전체를 `[...]` 배열로 감싸지 않는다. 레코드 사이 쉼표, 주석, Markdown 코드 블록, Excel 헤더를 넣지 않는다.
- JSON 값은 `true` / `false` / `null`을 쓴다. Python 표기 `True` / `False` / `None`이나 문자열 `"false"` / `"null"`을 쓰지 않는다.
- 알 수 없는 배열형 조건은 `null`이며 `[]`가 아니다. `clarification_questions`와 선택 항목 `expected_product_ids`는 빈 배열이 가능하다.
- 검수자 이름, 원본 행 번호, 작성 이유 등 부가 정보는 별도 전달 메모에 둔다. 학습 레코드에 임의 필드를 추가하면 거부된다.
- 팀 계획은 Train 300~500건이며 Dev/Holdout은 별도 구성한다. Dev/Holdout의 정확한 건수는 팀이 합의한다. 코드상 세 파일 모두 1건 이상이어야 한다.
- 같은 원본 문장의 오탈자·표현 변형·증강본은 같은 split에 묶는다. 현재 자동 검사는 ID와 정규화한 입력의 일치만 확인하므로 의미가 비슷한 문장의 누수까지 찾아주지는 않는다.
- 현재 검사 함수는 split 사이뿐 아니라 한 split 안의 같은 정규화 입력도 거부한다. ID만 바꿔 중복 문장을 넣지 않는다.
- Holdout을 프롬프트 예시나 설정 선택에 사용하지 않는다. 먼저 Dev로 개발하고, 최종 비교 시 고정 Holdout으로 Base와 LoRA를 평가한다.
- 일상적인 표현·짧은 문장·부정·모호함·필수 기능의 true/false/null 사례를 포함한다. 비율과 라벨은 팀 교차 검수로 확정한다.

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

이 검증은 GPU나 모델 가중치 없이 실행할 수 있으며 `pydantic`과 `PyYAML`이 필요하다.
`--validate-only`는 `SurveyResponse` 변환도 실행하여 중복 `question_id`, 100자를
넘는 입력 세션 ID, 공백뿐인 질문·답변, 문자열로 적은 boolean도 거부한다.
`expected_product_ids`가 있으면 설정의 `data.catalog_file`(기본
`data/products/catalog.json`)에 존재하는 ID인지 학습 전에 확인한다.

토크나이저를 준비한 환경에서는 아래 명령도 실행한다. GPU나 모델 가중치 없이
train/dev의 정답 토큰 잘림을 확인하며, 실제 학습도 같은 검사를 자동 실행한다.

```bash
python training/train_qlora.py --validate-only --check-token-lengths
```

형식 검사를 통과해도 정답 라벨이 옳다는 뜻은 아니다. 마지막으로 사람이 입력 문장과 `target`을 대조해야 한다.
담당자별 전체 전달 목록은 [팀 데이터 인수인계](team-handoff.md)를 참고한다.
