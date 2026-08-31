# LLM 담당: 답변 품질 평가와 보류 처리

제품 추천용 **조건 JSON 추출 평가**와 RAG 이후의 **LLM 답변 평가**는 서로 다르다.
전자는 기존 `src.evaluation.extractor_eval`, 후자는 새 `src.evaluation.answer_eval_cli`를 사용한다.
답변 평가 때문에 `ConditionPayload`, `SearchResponse`, `ChatResponse` 필드나 버전을 변경하지 않는다.

## 구현 범위와 실제 모델 평가의 구분

- QA와 제품 추천 서비스의 최종 `ChatResponse.answer`, 실제 생성기에 제공한 모든 근거,
  생성기 원본 출력, 기대 상태, 모델·설정·manifest checksum을 평가 파일에 저장한다.
- 기존 서비스의 입력·출력은 그대로이며 평가 기록은 별도 파일이다. 웹 mock 화면을 연결하지 않아도 백엔드에서 실행 가능하다.
- 인용 ID 형식 통과와 의미상 Citation Precision은 별개다. 같은 ID를 달아도 주장을 지지하지 않는 문서일 수 있다.
- Faithfulness·Answer Relevancy·Citation Precision·한국어 품질은 검수 판정으로 집계한다.
  현재 CLI는 자동 LLM judge나 Ragas를 호출하지 않으며 새 API 키·유료 API·평가용 모델을 요구하지 않는다.
- 미검수 값은 `null`이며 `pending_review`로 표시한다. 부분 검수 점수는 검수 완료 부분에만 대한 값이므로 `review_coverage`를 같이 본다.
- 한국어 글자 존재와 명령어 일치 검사는 자동 점검이다. 한글 한 글자가 있다는 사실을 자연스러운 한국어 답변의 증거로 취급하지 않는다.
- 제품 카드 사양과 추천 순위 자체는 catalog/추천 평가 범위다. 이 평가의 의미 지표 범위는 **최종 답변 본문**이다.
- 실제 Qwen 품질 점수를 얻으려면 실제 모델 환경과 검수된 평가셋으로 실행·검수를 완료해야 한다.
  `provider=template`, `model_id=evidence-template` 실행이나 단위 테스트 fixture 점수를 Qwen 성능으로 발표하면 안 된다.

## 다섯 평가 항목의 정의

| 항목 | 현재 평가 방식 | 분모 / 주의점 |
|---|---|---|
| Faithfulness | 원자적 사실 주장 중 제공 근거로 지지되는 주장 비율 | 완료 검수의 사실 주장 수. 인용 여부와 무관하게 실제 제공된 전체 근거를 대조한다. 비사실적 안내는 `not_factual`로 별도 표시. |
| Answer Relevancy | 사람의 0~2점 rubric을 0~1로 정규화 | 완료 검수 답변 수 × 2. 0=핵심 질문과 무관/미응답, 1=일부만 답하거나 불필요한 내용이 많음, 2=핵심 요청에 직접·충분히 답함. 정확성은 Faithfulness로 별도 평가. |
| Citation Precision | 답변의 문단–인용 연결 중 해당 문단의 관련 주장을 지지하는 연결 비율 | 완료 검수의 모든 문단–인용 연결 수. 동일 문단에서 같은 ID 반복은 한 연결, 다른 문단에서 재사용은 별개. ID 존재율이 아님. |
| 근거 부족 보류 정확도 | 정답이 `answered`/`insufficient_evidence`인 질문에서 실제 상태가 일치하는 비율 | 두 종류 질문 전체. `error`를 보류 성공으로 보지 않는다. 보류 precision/recall 및 과도한 보류율도 함께 표시. |
| 한국어·명령어 보존 | 한국어 품질 검수 비율 + 필수 명령어의 원문 완전 일치율 | 한국어는 완료 검수 답변, 명령어는 정답 사례에 지정한 `required_commands`. 필수 명령어가 없는 경우 100% 대신 `null`. |

별도로 상태 정확도, 답변율, 오류율, 인용 형식 준수율, 한국어 글자 존재 휴리스틱도 출력한다.
범위 밖·인젝션·추가 질문 상태는 전체 상태 정확도에 포함하고, 근거 부족 보류 정확도의 분모에는 섞지 않는다.

위 수치는 프로젝트의 **`picare-answer-v1` 검수 rubric**이다. Faithfulness의 근거 충실성 개념은
[Ragas 공식 문서](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)를,
인용의 의미적 지지 개념은 [ALCE 논문](https://aclanthology.org/2023.emnlp-main.398/)을 참고했다.
Ragas의 질문 역생성·임베딩 기반 관련성 점수나 ALCE의 원래 자동 평가 구현과 동일한 수치라고 주장하지 않는다.

## 팀원에게 받을 평가 질문 파일

이 파일은 학습용 train/dev/holdout JSONL이 아니다. 기존 `eval/questions_v1.jsonl`도 다른 형식이므로
그대로 넣거나 파일명만 바꾸면 안 된다. [실행 가능한 형식 예시](../eval/answer_cases.example.jsonl)를 참고해 별도 작성한다.

```json
{"id":"llm-dev-001","question":"Raspberry Pi OS의 터미널에서 SSH 설정 메뉴를 여는 명령어를 알려주세요.","route":"qa","split":"dev","expected_status":"answered","reference_points":["공식 SSH 문서의 설정 경로를 설명한다."],"required_commands":["sudo raspi-config"]}
```

| 필드 | 전달 규칙 |
|---|---|
| `id` | 전체 파일에서 고유한 ID, 1~100자 |
| `question` | 실제 사용자 질문, 1~2,000자 |
| `route` | `qa` 또는 `recommendation`. 추천이면 실제 sLLM·catalog·Hybrid RAG를 사용한다. |
| `split` | `dev`, `holdout`, `smoke`. CLI에서 실행할 split을 명시해야 한다. |
| `expected_status` | `answered`, `insufficient_evidence`, `needs_clarification`, `out_of_scope`, `safety_blocked`. 시스템 오류를 정답 상태로 지정하지 않는다. |
| `reference_points` | 팀이 검수한 정답의 핵심 내용. 검수자가 관련성을 판정할 때 참조하며 생성 모델에는 전달하지 않는다. |
| `required_commands` | 이 질문에 반드시 출력해야 하는, 공식 자료에서 검수한 단일 행 명령어 원문. 없으면 `[]`. 이 정답도 생성 모델에 전달하지 않는다. |

제품명·파일 경로 등 모든 기술 토큰을 자동으로 판단하는 것은 아니다. 명령어 자동 검사는 단일 행 인라인 백틱의
**전체 문자열**을 비교하므로 인자 추가, 대소문자·공백 변경, 번역, 누락이 있으면 실패한다.
공식 근거 안에 지정 명령어가 없을 때도 성공으로 세지 않는다. 복잡한 여러 줄 스크립트나 제품명·옵션의 문맥상 정확성은
검수자가 Faithfulness와 한국어/기술 표기 품질 판정에서 확인한다. 현재 생성 프롬프트는 코드 펜스를 쓰지 않는다.

정답 문장이나 명령어 목록을 검색 query나 prompt에 자동으로 붙이지 않는다. 생성기는 사용자 질문과 실제 검색 근거만 받는다.
RAG 담당자가 관리하는 정답 `chunk_id` 기반 Hit@k/MRR 평가 자료는 별도로 유지한다.

## 실행: 기록 → 검수 초안 → 채점

프로젝트 루트에서 실행한다. 아래 파일명은 예시이며 기존 결과를 덮어쓰지 않도록 매 실험마다 새 경로를 쓴다.
`run`은 기존 `.env`의 `DOCUMENT_MANIFEST`, `CHROMA_PATH`, `E5_MODEL_NAME`, `ANSWER_GENERATOR` 등을 사용한다.
정식 QA/추천 평가는 Hybrid로 실행하고, BM25는 로컬 개발 점검에만 명시적으로 사용한다.

```bash
python -m src.evaluation.answer_eval_cli run --cases eval/answer_cases.example.jsonl --split smoke --run-id local-template-smoke --mode bm25 --output artifacts/evaluation/local-template-smoke.records.jsonl
python -m src.evaluation.answer_eval_cli prepare --records artifacts/evaluation/local-template-smoke.records.jsonl --output artifacts/evaluation/local-template-smoke.reviews.jsonl
python -m src.evaluation.answer_eval_cli score --records artifacts/evaluation/local-template-smoke.records.jsonl --reviews artifacts/evaluation/local-template-smoke.reviews.jsonl --output artifacts/evaluation/local-template-smoke.pending.json
```

첫 명령은 manifest가 필요하다. 실제 Qwen을 평가할 때는 기존 생성기 설정을 `huggingface`로 준비하고
검수된 Dev/Holdout 파일·Hybrid 모드·새 run ID를 사용한다. 제품 추천은 기존 계약대로 Hybrid만 허용하며
catalog·색인 metadata·조건 추출 모델/어댑터가 필요하다. 부족한 실행 환경을 mock으로 자동 대체하지 않는다.

`prepare`와 `score`는 GPU·모델 다운로드·외부 API 없이 실행된다. `pydantic` 및 프로젝트 코드만 필요하다.
실행 오류가 난 사례는 `run`이 기록을 저장하되 exit 1로 알린다. 잘못된 파일·설정은 exit 2다.
`score`의 exit 0은 보고서 생성 성공이며, 품질 기준 통과나 실제 모델 성능 보장이 아니다.

검수자는 `.records.jsonl`과 `.reviews.jsonl`을 나란히 보며 다음 순서로 입력한다.

1. `response.answer`는 사용자가 실제로 보는 최종 본문, `raw_answer`는 검증·조합 전 생성기 출력이다.
   **최종 본문**을 평가하고 `evidence` 전체를 근거로 사용한다. 현재 표시 출처만으로 전체 검색 근거를 대신하지 않는다.
2. 초안의 `claims`는 문단 단위 자리표시자다. 한 문단에 사실이 여러 개면 원자적 주장 여러 개로 나누고 `unit_index`를 유지한다.
   `text`는 해당 문단의 실제 부분 문자열이어야 한다. 모든 문단과 제목을 빠짐없이 검수한다.
   형식 검사에서 허용한 제목 안에도 근거 없는 사실이 있을 수 있어, 의미 검수에서는 제목을 제외하지 않는다.
3. 각 주장을 `supported`, `unsupported`, `not_factual`로 판정하고 이유를 적는다.
   `supported`에는 이를 뒷받침한 실제 `evidence_ids`가 필요하다. 원문과 모순되거나 근거가 없으면 `unsupported`다.
4. `citation_links`의 문단–인용 연결 각각에 `supports: true/false`와 이유를 적는다.
   인용이 존재하더라도 질문과 무관한 근거나 주장을 지지하지 않는 근거라면 false다.
5. `answer_relevancy`에 0/1/2, `korean_compliant`에 true/false를 적는다.
   한국어 판정은 실제 설명이 한국어인지, 기술 용어·명령어·경로를 부적절하게 번역/변형하지 않았는지 함께 확인한다.
6. `method=human`, `reviewer`, `overall_reason`을 적고 모두 끝났을 때만 `complete=true`로 바꾼다.
   이 CLI는 LLM judge를 호출하지 않는다. 별도 judge를 실제 사용했다면 `method=llm`과 `judge_model`을 기록하고 사람 검수도 권장한다.

검수자를 가장하거나 fixture 점수를 실제 품질 판정으로 제출하지 않는다. 전체 주장 추출의 완전성과 의미 판정은
검수자 책임이며 코드는 생략된 의미나 잘못된 판정을 자동으로 알아내지 못한다.
`record_sha256`은 질문·답변·정답·제공 근거를 묶은 값이다. 모델 출력이나 정답을 바꿨다면 이전 검수를 재사용하지 말고 새로 생성한다.

검수 완료 후 새 보고서 경로에 저장한다.

```bash
python -m src.evaluation.answer_eval_cli score --records artifacts/evaluation/local-template-smoke.records.jsonl --reviews artifacts/evaluation/local-template-smoke.reviews.jsonl --output artifacts/evaluation/local-template-smoke.reviewed.json --require-complete
```

`--require-complete`에서는 답변 본문의 검수가 남으면 보고서를 저장한 뒤 exit 2로 끝난다.
단위 테스트의 `method=fixture`는 평가 코드 수학·검증 동작 확인용이며 발표용 LLM 지표가 아니다.
서로 다른 실행·모델·설정·split을 한 점수로 섞으면 거부한다. 같은 설정의 QA/추천이 함께 있는 경우
전체 점수는 합산이며 `cases[].route`로 구분된다. 과제별 점수는 입력 파일을 분리하여 각각 계산한다.

## 런타임 답변 처리 수정

- 공식 근거가 없으면 기존처럼 생성기를 호출하지 않고 보류한다.
- 근거가 검색되었어도 실제로 답할 수 없으면 모델은 `[INSUFFICIENT_EVIDENCE]` 한 줄만 출력하도록 안내한다.
  QA·추천·mock 체인은 이를 `insufficient_evidence`로 변환한다. 내부 표식·제품 카드·출처 카드는 사용자에게 노출하지 않는다.
- 표식과 답변을 섞은 출력은 안전 검증 오류로 처리한다. 임의 한국어 문구를 보고 보류 상태를 추측하지 않는다.
- QA·추천 백엔드는 한글 설명이 전혀 없는 생성 결과를 `error`로 차단한다. 한국어가 자연스러운지까지 자동 판정하는 규칙은 아니다.
- 명령어·제품명·경로·설정 키·옵션을 원문대로 보존하고, 인용을 명령어 백틱 밖에 붙이도록 프롬프트를 보강했다.
- 인용 형식 검사는 여전히 의미적 근거 지지 여부를 보증하지 않는다. 의미 지표는 위 오프라인 검수로 확인한다.

## 팀 전달 산출물

LLM 담당자는 평가 질문 버전, `.records.jsonl`, 검수 완료 `.reviews.jsonl`, `.reviewed.json`, 실패 사례를 전달한다.
모델/provider, 요청한 revision, prompt hash, manifest checksum, 검색 설정도 함께 저장된다.
모델 revision이 `main`이면 고정 commit으로 실행한 것과 같지 않다. 재현 실험은 고정 revision을 사용한다.
생성기 근거·출력에는 원문이나 사용자 입력이 포함되므로 기록·검수 파일은 기본적으로 Git 제외 `artifacts/` 아래와 승인된 팀 공유 위치에 보관한다.
