# feat/chain Streamlit 통합 검증 재실행 공유

- 기준일: 2026-08-31
- 검증 브랜치: `feat/chain`
- 검증 커밋: `5cfb27f`
- 병합된 main: `e241987`

## 통합된 범위

- 최신 `main`의 Manifest 1.1, RAG, Qwen 인용 수정 재생성, 문서 파이프라인 변경이 `feat/chain`에 병합돼 있다.
- 기존 커밋의 Streamlit 실제 서비스 조립 코드와 QA·제품 추천 화면이 유지돼 있다.
- Streamlit은 `streamlit_app/runtime.py`에서 QA와 추천 서비스를 구성하고 공통 `ChatResponse 1.1.0`을 화면에 표시한다.
- 이번 검증에서는 stash를 적용하지 않았고, 공용 서비스·테스트·README를 수정하지 않았다.

## 현재 연결 흐름

```text
Streamlit 입력
  ├─ QA → RagQaService → HybridRetriever → AnswerGenerator → 인용 검증
  └─ 제품 추천 → RecommendationFormInput → RecommendationRagService
                → catalog 필터 → Hybrid RAG → AnswerGenerator → ChatResponse
```

초기 화면과 HTTP 서버는 실행된다. 하지만 실제 QA·추천 제출 경로는 현재 아래 통합 회귀와
로컬 실행 자료 부재로 인해 E2E 통과 상태가 아니다.

## 검증 결과

| 항목 | 결과 |
|---|---|
| 전체 자동 테스트 | `159 passed, 5 failed in 0.80s` |
| 전체 테스트 통과율 | 0.970 (159/164) |
| Streamlit 문법·import | `py_compile` 통과 |
| Streamlit AppTest | 예외 0건, 오류 0건 |
| 실제 서버 기동 | 성공 |
| health endpoint | `GET /_stcore/health` → `ok` |
| 첫 화면 HTTP | 200 |
| 실제 RAG 런타임 준비 | 실패: `.env`의 `TOP_K`부터 누락 |
| 추천 폼 서비스 진입점 | 실패: `RecommendationRagService.answer_form` 없음 |

### 실패 5건 요약

- `tests/test_rag.py` 1건: 저장소에 없는 legacy manifest fixture 경로를 참조한다.
- `tests/test_rag_qa_service.py` 3건: `generate_validated_grounded_answer()` 연결이 빠져
  `validated_generation`이 정의되지 않고 인용 수정 재생성도 실행되지 않는다.
- `tests/test_recommendation_agent.py` 1건: 추천 서비스도 같은 이유로 trace 응답에서
  `validated_generation` `NameError`가 발생한다.

텍스트 병합 충돌은 없었지만, 자동 병합된 서비스 코드에 논리적 연결 누락이 남아 있다.

## 정량 smoke 평가

### 팀 요청 핵심 지표 상태

| 지표 | 현재 결과 | 정식 측정에 필요한 입력 |
|---|---:|---|
| Hit@5 | 미측정 | 정식 manifest·색인, 질문별 `relevant_chunk_ids` |
| MRR | 미측정 | qrels와 실제 검색 순위 |
| Citation Precision | 미측정 | 실제 답변·근거 snapshot·완료된 주장–인용 검수 |
| 근거 부족 보류 정확도 | 미측정 | 정식 평가셋의 실제 QA·추천 실행 기록 |

현재 `eval/questions_v1.jsonl`에는 검색 정답 청크 ID가 없고, 작업 폴더에는 정식
`manifest_v3.json`과 Chroma 색인이 없다. `eval/answer_cases.example.jsonl`은 예시
4건이며 완료된 실제 답변 및 인용 검수 기록이 아니다. 따라서 핵심 지표에 fixture 값을
넣어 최종 RAG·모델 점수로 제출하지 않는다.

### 현재 재실행한 보조 smoke 지표

stash 보고서와 같은 방식으로 `eval/questions_v1.jsonl` 10건을 저장소의 결정적 smoke
체인에서 다시 실행했다. 제품 추천 3건은 mock 폼 계약·제품·출처 fixture를, 제품 비교
1건은 현재 미지원 보류 경로를, QA 6건은 `ChatService`의 결정적 검색·안전 체인을 사용했다.
positive는 `expected.status=answered`, predicted positive는 실제 `status=answered`다.

| 지표 | 결과 | 의미 |
|---|---:|---|
| 전체 테스트 통과율 | 0.970 (159/164) | 현재 코드 계약 테스트 기준 |
| 응답 상태 Exact Accuracy | 0.800 (8/10) | 예상 상태와 완전히 같은 비율 |
| Answerability Precision | 1.000 (5/5) | 답변 상태로 처리한 5건은 모두 정답 |
| Answerability Recall | 0.714 (5/7) | 답해야 할 7건 중 5건을 답변 처리 |
| Answerability F1 | 0.833 | Precision과 Recall의 조화평균 |
| 보류·범위 외·안전 차단 정확도 | 1.000 (3/3) | Q008∼Q010 상태 일치 |

혼동행렬은 `TP=5`, `FP=0`, `FN=2`, `TN=3`이다. Q004(제품 비교)와
Q005(OS 설치)는 기대 상태가 `answered`이지만 smoke 체인이 `insufficient_evidence`로
보류했다. 근거 없이 답한 FP는 없지만 답해야 할 질문을 과도하게 보류한 FN이 2건이다.

> 이 Precision·Recall·F1은 mock/fixture 기반 연결 smoke 수치다. 정식
> Manifest·Chroma·LoRA·Qwen으로 실행한 최종 모델 성능이 아니다.

기계 판독용 결과는
[`2026-08-31-feat-chain-streamlit-integration-rerun.json`](2026-08-31-feat-chain-streamlit-integration-rerun.json)에 저장했다.

## 정식 산출 방법

- Hit@5: Top 5 검색 결과에 검수된 정답 청크가 하나라도 포함된 질문의 비율
- MRR: 각 질문에서 첫 정답 청크 순위의 역수 평균
- Citation Precision: 주장을 실제로 지지한 인용 연결 수 / 전체 인용 연결 수
- 보류 정확도: 답해야 하는 질문과 근거가 없는 질문의 상태를 모두 맞힌 비율

실제 RAG 실행 후 Hit@5·MRR은 `src.rag.evaluate_rankings`으로 계산한다. Citation
Precision·보류 지표는 `python -m src.evaluation.answer_eval_cli`의
`run → prepare → score --require-complete` 순서로 산출한다.

## 현재 필요한 실행 자료

1. 프로젝트 루트 `.env` (`TOP_K` 포함)
2. 검수된 `document_pipeline/data/manifest_v3.json`
3. 같은 manifest로 생성한 `data/indexed/chroma_official_v3/`
4. 질문별 검수된 `relevant_chunk_ids`
5. 제품 추천용 LoRA adapter 또는 접근 가능한 모델 경로
6. Citation Precision용 완료 검수 기록

이 자료와 서비스 연결 회귀가 해결되기 전에는 첫 화면 기동 성공을 실제 Streamlit–RAG
E2E 성공으로 해석하면 안 된다.

## 충돌 최소화

이번 작업은 이 보고서와 같은 이름의 JSON 파일만 새로 추가했다. stash, 기존 소스,
테스트와 README는 변경하지 않았고 커밋·푸시는 수행하지 않았다.
