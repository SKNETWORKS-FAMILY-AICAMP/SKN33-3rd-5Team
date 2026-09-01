# 이양원 담당: sLLM 제품 추천 Agent 구현 가이드

## 결론부터

담당 기능은 “LLM이 Raspberry Pi 제품 지식을 외워서 바로 추천하는 챗봇”이 아니다. 사용자가 기존 설문에 입력한 여러 답변을 sLLM이 고정된 조건 JSON으로 바꾸고, 코드가 검수된 제품 카탈로그를 필터링·점수화하며, RAG가 추천 근거를 붙이는 Agent다.

```text
기존 설문 답변
  → Qwen3-4B 조건 추출(Base 또는 QLoRA)
  → Pydantic JSON Schema 검증
  → 제품 catalog 하드 필터 + 투명한 점수 규칙
  → 후보 1~3개 + 공식 근거 document_id
  → RAG/Streamlit 담당이 공식 근거·설명·링크 표시
```

제품 사실을 파인튜닝 데이터에 넣어 암기시키면 문서가 바뀔 때 adapter를 다시 학습해야 하고 출처도 보장할 수 없다. 따라서 QLoRA는 한국어 설문 표현, `null` 처리, 확인 질문, JSON 형식을 학습하고 제품 사양은 catalog/RAG에서 가져온다.

## 주요 담당 업무를 쉬운 말로

### 1. 조건 JSON Schema

팀 모듈 사이의 공통 답안지를 정하는 일이다. 예를 들어 “초등학생 교육용이고 집에서 Wi-Fi와 모니터를 쓸 거예요”를 다음처럼 정규화한다.

```json
{
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
}
```

실제 출력은 팀 공통 계약인 [models.py](../src/contracts/models.py)의 `ConditionPayload`를 단일 기준으로 사용한다. 사용자가 말하지 않은 값은 `null`이며 모델이 추측해 채우면 감점한다.

### 2. 학습 데이터

공식 문서 원문이 아니라 `설문 답변 → 정답 조건 JSON` 쌍이다. README의 역할표에는 학습 데이터가 이양원 담당으로 적혀 있으므로 라벨의 의미와 품질 승인은 담당해야 한다. 다만 크롤링, 파일 정리, 중복 제거와 split 작업은 문서·데이터 담당에게 요청하고, 코드는 전달받은 세 파일만 읽도록 만들었다.

- 받는 위치: `data/finetuning/train.jsonl`, `dev.jsonl`, `holdout.jsonl`
- 계약: [학습 데이터 전달 문서](./data-contracts/finetuning.md)
- 권장 수량: train 300~500건 + 별도 dev/holdout
- 꼭 포함할 사례: 조건 누락, 모순 답변, 제품명을 이미 지정한 답변, 범위 밖 목적, 확인 질문이 필요한 답변

### 3. Base few-shot baseline

파인튜닝 전 모델에게 예시 몇 개를 prompt로 주고 바로 JSON을 뽑아 보는 기준점이다. 이 점수보다 QLoRA가 좋아져야 학습 가치가 있다. Base와 LoRA는 모델·prompt·holdout·생성 설정을 같게 하고 adapter 유무만 바꾼다.

### 4. RunPod QLoRA

Base 4B 가중치를 NF4 4-bit로 GPU에 올려 고정하고, 작은 LoRA adapter만 학습한다. 전체 모델을 다시 학습하는 것보다 메모리와 저장 공간이 적게 든다. 수업 노트북과 같은 `messages/chat template → BitsAndBytesConfig → LoraConfig → SFTTrainer → adapter 저장` 흐름이다.

이 구현은 `Qwen/Qwen3-4B-Instruct-2507`을 사용한다.

- 기존 1.7B보다 파라미터 여유가 있고, Qwen 공식 모델 카드가 다국어 지식·지시 수행 개선을 명시한다.
- non-thinking 전용이라 JSON 앞에 `<think>` 블록이 붙는 문제를 피하기 쉽다.
- 4B QLoRA는 팀이 계획한 24GB급 단일 GPU 범위에서 현실적이다.
- “무조건 더 좋다”는 가정은 하지 않는다. 동일 holdout 결과가 나쁘면 1.7B 또는 Base fallback을 유지한다.

### 5. 모델 평가

일반 BLEU/ROUGE보다 이 과업의 성공 조건을 직접 잰다.

- JSON Schema 준수율
- 전체 Exact Match
- 필드별 accuracy와 Macro F1
- 사용자가 말하지 않은 조건을 채운 비율
- 정답 제품 ID가 있는 표본의 추천 Top-1 정확도
- 실패 샘플 원문과 오류 유형

## 왜 공식 하드웨어 페이지 하나만 학습하면 안 되는가

핵심 하드웨어 페이지는 제품 계열과 사양 비교에 유용하지만 제품 추천 전체를 완성하지는 못한다. 개별 제품 변형·공식 구성품, 카메라 케이블, 전원, 헤드리스 설치, Compute Module의 baseboard 요구처럼 다른 공식 페이지에만 있는 조건이 있다.

그렇다고 일반 쇼핑몰·블로그까지 바로 넓힐 필요는 없다. 현재 MVP는 Raspberry Pi 공식 온라인 문서와 공식 제품 페이지만으로 충분히 구성할 수 있다. 실시간 가격·재고·제3자 액세서리까지 다루려면 그때 별도 데이터 소스와 갱신·검증 정책을 추가한다.

그리고 이 자료는 sLLM 학습 원문이 아니라 문서·데이터 담당에게 받아야 할 `data/products/catalog.json`과 RAG corpus의 근거다. 형식은 [제품 catalog 전달 문서](./data-contracts/product-catalog.md)에 있다.

## 실행 순서

RunPod에서 저장소를 `/workspace` 아래에 두고 실행한다.

```bash
pip install -r requirements-training.txt

# 1) 받은 파일만 검증: 쓰거나 고치지 않음
python training/train_qlora.py \
  --config training/configs/qwen3_4b_qlora.yaml \
  --validate-only

# 2) adapter 학습
python training/train_qlora.py \
  --config training/configs/qwen3_4b_qlora.yaml

# 3) Base few-shot 고정 holdout 평가
python -m src.evaluation.extractor_eval \
  --mode baseline \
  --data data/finetuning/holdout.jsonl \
  --catalog data/products/catalog.json \
  --output artifacts/evaluation/baseline.json

# 4) 같은 조건에서 QLoRA 평가
python -m src.evaluation.extractor_eval \
  --mode lora \
  --adapter-path /workspace/models/picare-qwen3-4b-qlora \
  --data data/finetuning/holdout.jsonl \
  --catalog data/products/catalog.json \
  --output artifacts/evaluation/qlora.json
```

## Agent를 Streamlit 서비스에 연결하는 코드

학습 결과는 [모델 별도 저장 가이드](./guides/finetuning-training.md)에 따라 Hugging Face에
비공개 백업할 수 있다. `train_qlora.py`의 `--hub-repo-id`로 학습 직후 백업하거나,
`publish_adapter.py`로 이미 저장된 어댑터를 재학습 없이 업로드한다.

자유 입력은 sLLM이 해석하고, 선택 위젯의 값은 프론프트에만 맡기지 않고 백엔드가 최종 조건에 직접 덮어쓴다. 따라서 화면 구현 담당자는 위젯과 카드를 그리고, sLLM 담당 코드는 값 변환·조건 필터·순위 계산을 맡는다.

```python
from src.condition_extraction.lora import LoraConditionExtractor
from src.condition_extraction.ui_input import RecommendationFormInput
from src.recommendation.engine import ProductRecommender
from src.recommendation.schema import ProductCatalog
from src.services.recommendation_agent import RecommendationAgent

catalog = ProductCatalog.from_received_file("data/products/catalog.json")
extractor = LoraConditionExtractor("/workspace/models/picare-qwen3-4b-qlora")
agent = RecommendationAgent(
    extractor=extractor,
    recommender=ProductRecommender(catalog),
)

form = RecommendationFormInput.from_widget_values(
    request_id="request-001",
    free_text="초등학생이 집에서 코딩을 처음 배우려고 해요.",
    user_level_label="입문자",
    performance_priority_label="보통",
    wireless_required=True,
    camera_required=False,
    gpio_required=False,
    monitor_absent=False,
)

agent_result = agent.recommend_form(form)
payload = agent_result.model_dump(mode="json")
```

`monitor_absent=True`는 공통 계약의 `monitor_available=False`로 변환된다. `payload.decision.candidates`는 제품 후보·선정 조건·주의점·필수 구성품·근거 `document_id`를 담는다. 이후 RAG `SearchResponse`를 [recommendation_response.py](../src/services/recommendation_response.py)에 넘기면 Streamlit이 바로 표시할 공통 `ChatResponse`가 된다. catalog와 RAG에서 확인되지 않은 URL을 LLM이 만들게 해서는 안 된다.

## 담당자별 실제 인수인계

| 받는 사람/주는 사람 | 파일 또는 인터페이스 | 이양원이 하는 일 |
|---|---|---|
| 문서·데이터 → 이양원 | `catalog.json`, `train/dev/holdout.jsonl` | 스키마·누수 검증 후 그대로 사용 |
| 이양원 → RAG·검색 | `ConditionPayload`, 후보의 `evidence_by_field`·`evidence_document_ids` | `document_id`로 근거를 검색하고, 조건 관련 필드 근거와 청크 제품 태그가 모두 맞을 때만 후보·인용으로 연결 |
| 이양원 → 챗봇·Streamlit | `RecommendationFormInput`, `RecommendationAgentResult`, `ChatResponse` | 위젯 라벨 변환과 화면용 최종 JSON 공유 |
| 이양원 → PM·통합 | adapter 경로, config, manifest, Base–LoRA 평가표 | 채택 근거와 실패 사례 보고 |

## 완료 기준

- 받은 세 split이 스키마·누수 검사를 통과한다.
- Base와 QLoRA가 동일 holdout·prompt·greedy 생성으로 평가됐다.
- QLoRA가 JSON 준수율·Macro F1·추천 정확도 중 합의한 핵심 지표를 개선한다.
- adapter 실패 시 같은 base의 few-shot 또는 확인 질문으로 안전하게 전환한다.
- 추천 결과의 모든 제품 사실과 출처가 catalog/RAG metadata에서 온다.
- 가격·재고·제3자 호환성은 공식 근거와 갱신 정책 없이는 답하지 않는다.
