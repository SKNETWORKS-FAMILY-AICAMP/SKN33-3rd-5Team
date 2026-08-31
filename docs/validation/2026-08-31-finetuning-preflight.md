# 2026-08-31 파인튜닝 사전 검사

이 문서는 데이터 수령 전 검사 이력이다. 이후 세 파일 수령과 A40 학습을 완료했으며,
현재 상태는 [A40 학습 결과](2026-08-31-runpod-a40.md)와
[기존 코드 통합 검증](2026-08-31-finetuning-integration.md)을 따른다.

## 범위와 현재 결론

- 브랜치: `feat/fine-tuning`, 시작 HEAD: `a77fa98`.
- 이양원 담당인 조건 추출·파인튜닝·평가 코드만 수정했다. 공통 계약 원본,
  catalog, 문서 파이프라인, Retriever, Streamlit 코드는 변경하지 않았다.
- 사용자가 전달받았다고 알린 수량은 train/dev/holdout 300/40/20이다.
  검사 당시 이 작업 폴더에는 `data/finetuning/`과 세 파일이 없었다.
  **360건의 실제 형식·누수·라벨 검수, CUDA 학습, Base–LoRA 성능 비교는 미완료다.**
- 로컬 GPU는 Intel Iris Xe이며 CUDA GPU가 없다. 테스트 환경에 PyTorch,
  PEFT, TRL, datasets도 설치되어 있지 않다. 실제 모델 학습·추론을 수행하지 않았다.

## 재현한 문제와 수정

| 문제 | 확인한 근거 | 수정 |
|---|---|---|
| 학습 정답 전체 잘림 | 공식 Qwen 토크나이저로 기존 프롬프트 예시 2건 측정: prompt 1,510/1,516, 전체 1,601/1,608토큰. 기존 `max_length=1024`에서 남는 정답은 모두 0토큰 | 기본 4,096, train/dev 전체 길이·정답 경계 사전 검사. 넘치면 학습 중단 |
| 검증 통과 후 실제 입력 변환 실패 | 중복 question ID와 101자 record ID가 기존 로더를 통과 | 파일 로딩 시 SurveyResponse 변환까지 검증 |
| 입력 계약의 잘못된 타입을 묵시 보정 | 공백 질문·답변과 문자열 boolean이 기존 검사를 통과 | 공백 검사와 엄격한 타입 검사. 모델 JSON 파서도 문자열 boolean 거부 |
| 추천 정확도 과대평가 | 정답 제품이 있는 2건 중 1건이 JSON 실패하면 기존 정확도 1/1 | 실패도 분모에 넣어 1/2로 계산. 빈 평가·개수 불일치 거부 |
| 정답 제품 ID 오류가 늦게 드러남 | 별도 수동 점검에만 의존 | 학습 사전 검사와 평가 모델 로딩 전에 catalog ID 검사 |

TRL의 `max_length`는 입력과 정답을 합친 시퀀스를 오른쪽에서 자르는 길이다.
completion loss를 사용하면 프롬프트는 loss에서 제외된다.
[TRL 0.28 SFT 문서](https://huggingface.co/docs/trl/v0.28.0/en/sft_trainer)와
[공식 구현](https://github.com/huggingface/trl/blob/v0.28.0/trl/trainer/sft_trainer.py)을 확인했다.
토크나이저 출처는 [Qwen 공식 모델](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)이며
revision은 `cdbee75f17c01a7cc42f958dc650907174af0554`다. 가중치는 다운로드하지 않았다.

학습 manifest에는 입력 파일 SHA-256, 토큰 통계, 최종 dev loss도 기록하도록 했다.
Torch/NumPy 등 모델 측 seed는 adapter 생성 전에 설정한다.
Holdout은 Trainer의 train/eval dataset과 토큰 길이 설정 검사에 전달하지 않는다.

## 로컬 검증

- 수정 전 전체 테스트: **155 passed, 1 skipped**.
- 수정 후 전체 테스트: **174 passed, 1 skipped**.
- 건너뛴 테스트는 Windows symlink 생성 권한이 필요한 업로드 차단 검사다.
- 추가 회귀 검사: 실제 파일을 고치지 않는 입력 검증, 잘린 정답 거부,
  JSON 실패를 포함한 추천 정확도, train/dev/holdout 분리와 가중치 로딩 전 실패.
  학습 연결부의 GPU·Trainer는 대역이므로 실제 최적화 성공을 뜻하지 않는다.
- 실제 토크나이저 검사: 기존 예시 2건은 1,024에서 거부, 4,096에서 통과.
  **사용자에게 전달된 360건의 검사 결과가 아니다.**
- 기존 로컬 smoke 검사 재실행: 로컬 문서 18개에서 임시 228청크, catalog 5개 제품,
  BM25·템플릿·고정 조건 대역으로 추천 4종과 QA 6종 통과.
- Streamlit AppTest: 추천 제출, QA 상태 4종, 빈 입력, 서비스 소개 통과.
  화면은 mock이며 실제 백엔드 연결·브라우저 시각 검수는 포함하지 않는다.
- `git diff --check` 통과. Git push와 Hub 업로드는 실행하지 않았다.

상세 결과는 Git 제외 경로 `artifacts/finetuning-validation/`의
`baseline-tests.xml`, `final-tests.xml`, `tokenizer-probe.json`, `preflight-proof.json`,
`integration-smoke/flow-results.json`에 보관한다.

## 다른 담당에게 확인할 항목

| 담당 | 확인·전달 사항 | 이번 처리 |
|---|---|---|
| 김혜리·데이터 전달 담당 | 300/40/20 JSONL의 실제 저장 경로, 파일 버전·분리/검수 메모 | 파일 위치 요청. 생성·라벨 수정·재분할하지 않음 |
| 김혜리 | 정식 `document_pipeline/data/manifest_v3.json` 전달 | 미배치 확인. 임시 smoke manifest를 정식 파일로 배치하지 않음 |
| 최지흠 | 같은 manifest로 만든 Chroma 색인 또는 재생성 절차 | 미배치 확인. 검색 구현 수정하지 않음 |
| 김나은·통합 담당 | Streamlit mock을 실제 공통 서비스에 연결하고 `use_container_width` 폐기 예정 경고 정리 | 화면 코드 수정하지 않음. 현재 AppTest 자체는 통과 |
| 실행 환경·통합 담당 | RunPod CUDA 환경과 런타임 `.env` 준비 | 현재 CLI는 `.env`의 `TOP_K` 누락에서 중단. 비밀·환경 설정 임의 생성하지 않음 |

## 이어서 실행할 순서

1. 전달된 세 파일을 지정 경로에 배치하고 `--validate-only`로 300/40/20건을 확인한다.
2. `--validate-only --check-token-lengths`와 train/dev 라벨 검수를 수행한다.
3. RunPod에서 실제 QLoRA 학습, 최종 dev loss, adapter 저장·재로딩을 확인한다.
4. 개발 중 비교는 dev로 수행하고, 설정을 확정한 뒤 같은 모델 revision·프롬프트·생성 조건·
   고정 holdout으로 Base–LoRA를 비교한다. 20건에서 1건 차이는 5%p임에 유의한다.
5. 정식 manifest·색인과 adapter로 추천/QA를 실행하고 실제 화면 연결까지 확인한다.

명령과 검사의 의미는 [학습 가이드](../../training/README.md)를 따른다.
