# 파인튜닝 검증과 QA·제품추천 서비스 통합

후속 검증: 새 A40에서 최신 `fix/dev`의 실제 GPU 재실행을 완료했다.
[최종 A40 검증 결과](2026-08-31-final-a40-defca71.md)를 참고한다.
아래 내용은 `feat/fine-tuning` 통합 당시의 기록을 보존한 것이다.

검증일: 2026-08-31. 작업 브랜치: `feat/fine-tuning`.
최신 `origin/main`의 `66044965a6d7ad8d6d5ba50f52bb4b95edb5b797`을
fast-forward로 반영한 뒤 기존 미커밋 작업을 복원하고 실제 소스 경로에 통합했다.
별도 패치나 검증용 사본을 실행할 필요가 없다.

## 반영 내용

- QA·추천에서 공통 생성 검증 결과를 실제로 사용해 trace의 `NameError`와 재시도 누락을 수정했다.
- 추천 폼의 `answer_form()`을 연결했다. 명시적인 위젯 선택값은 sLLM 추출값보다 우선하고,
  위험한 자유 입력은 조건 추출·검색 전에 차단한다.
- QA·CLI·Streamlit에 청크별 공식 미디어 조회를 연결했다. 실제 인용한 청크만 표시하고
  URL 중복을 제거하며, 근거 부족 보류에는 미디어를 붙이지 않는다.
- 미디어 연결표가 없는 신규 환경에서는 미디어 없이 QA가 동작한다.
- 인용 뒤 마침표와 쉼표로 묶인 ID는 처리하되, 인용 없는 서론·콜론으로 끝난 주장에
  일괄 예외를 주지 않는다. 답변 평가기가 기대하는 `list[str]` 계약을 유지한다.
- 형식 재요청 후의 보류도 정상 보류로 처리하고, Hugging Face 내부 재시도 횟수를 trace에 전달한다.
- 기존 데이터 검증·QLoRA 사전 검사·평가 보완을 유지한다. 학습 정답 토큰이 잘리는 경우
  가중치 로딩 전에 중단하며, 입력 SHA-256·토큰 통계·최종 dev loss를 저장한다.
- legacy manifest 검사는 Git에 없는 파일 대신 테스트 안에서 만든 임시 입력으로 실행한다.

서비스 연결·폼·미디어 변경은 [동료의 연결 수정안](https://github.com/skn-33-Raspberry-Pi-Assistant/skn_33_3rd_5team/pull/19)의
의도를 반영했다. 해당 브랜치를 merge하거나 cherry-pick하지 않았으며 먼저 병합할 필요도 없다.
발견한 평가 반환 계약 오류와 인용 검사 완화는 제외했다. 동료의 기존 검증 이력 파일은 보존한다.

## 검증 결과

| 대상 | 결과 |
|---|---|
| 최신 main 원본 전체 테스트 | 157 passed / 5 failed / 1 skipped |
| 기존 코드에 통합 후 전체 테스트 | **200 passed / 1 skipped** |
| 받은 학습 파일 검증 | train 300 / dev 40 / holdout 20 통과, 학습 당시 SHA-256과 일치 |
| 현재 Streamlit AppTest | QA·추천 폼 모두 answered, error/exception 0, 미디어 표시 경로 확인 |
| 현재 통합본 A40 재실행 | 미실행 — 현재 SSH 접속 정보 확인 필요 |

Windows의 symlink 생성 권한이 필요한 기존 업로드 방어 검사 1개만 건너뛰었다.
Streamlit 검사는 실제 서비스 클래스를 사용하되 검색·조건 추출을 고정 대역으로 주입하고
답변은 template 생성기를 사용했다. 실제 GPU 추론이나 원격 미디어 다운로드 검증은 아니다.

재현 명령:

```bash
python -m pytest tests -q --tb=short
python -m training.train_qlora --config training/configs/qwen3_4b_qlora.yaml --validate-only
```

집계 지표·데이터 해시·검증한 Python 소스 해시는
[검증 요약 JSON](2026-08-31-finetuning-integration.json)에 있다.
원시 실행 로그·UI 검사 스크립트는 Git 제외 `artifacts/finetuning-integration/`에 보관한다.

## 학습과 실제 GPU 결과의 범위

기존 A40 학습은 완료돼 있으며 이번 통합으로 재학습할 필요는 없다.
고정 holdout 20건의 Base–LoRA 비교는 다음과 같다. 학습 원문이나 개별 응답은 공개하지 않는다.

| 지표 | Base | LoRA |
|---|---:|---:|
| JSON Schema 준수율 | 100% | 100% |
| 전체 조건 Exact Match | 10% | 45% |
| 필드별 Macro F1 평균 | 78.79% | 90.61% |
| 입력에 없는 조건 생성 비율 | 16.34% | 5.88% |

이전 A40 통합 검증에서는 QA 기대 상태 7/7, 실제 LoRA 추천 4/4,
Streamlit QA·추천 폼 제출 2/2를 확인했다. 이 결과는
[이전 A40 검증 기록](2026-08-31-runpod-a40.md)의 소스 버전에 대한 결과다.
현재 통합본의 프롬프트 변경 전후 의미 정확도 평가를 대신하지 않는다.

## 영향 범위와 남은 확인

- main의 corpus·검색·계약 변경은 그대로 유지했다. 이 통합 자체로 재색인·재학습이나
  새 필수 환경변수는 필요하지 않다. 기존 manifest와 Chroma 색인은 서로 일치해야 한다.
- QA 미디어를 표시하려면 같은 corpus로 만든 `document_pipeline/data/media_chunk_map.json`이 필요하다.
  이미지·영상 manifest는 기존 `assets/media/`를 사용한다.
- 학습 JSONL·adapter·환경 비밀은 Git에서 제외한다. clone만으로 실제 모델 실행에 필요한
  데이터·색인·LoRA가 모두 준비되는 것은 아니다.
- 실제 RunPod 연결이 확인되면 이 소스 버전으로 QA·추천·화면을 짧게 재검증한다.
- 조건 추출 Exact Match 45%와 제품 사양 혼동·근거 없는 설명은 남아 있다.
  Dev 기반 개선과 팀 교차 검수가 필요하며, holdout으로 프롬프트를 맞추지 않는다.
- `expected_product_ids`가 비어 있어 제품 추천 Top-1 정확도는 아직 산출하지 못한다.
- 커밋과 PR 작성 준비는 병합 승인이 아니다. 저장소 규칙에 따라 최소 1명 리뷰 후 main에 병합한다.
