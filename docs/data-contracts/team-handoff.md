# 팀 데이터 인수인계: 파일·담당·작성 규칙

2026-08-31 현재 코드와 설정 기준이다. 아래 경로는 프로젝트 루트 기준이며,
기존 스키마를 새로 설계하라는 요청이 아니다. **학습 데이터, 제품 카탈로그,
검색 문서는 서로 다른 자료**다. 같은 파일로 대체하거나 임의로 합치지 않는다.

## 누구에게 무엇을 요청하는가

| 전달 담당 → 받는 담당 | 파일 / 산출물 | 필요한 이유와 현재 상태 |
|---|---|---|
| 팀 공동 작성·검수, 김혜리 정리·분할 → 이양원 | `data/finetuning/train.jsonl` | 300건 수령·검증 및 A40 학습 완료. Git 제외이므로 다른 환경에는 별도로 전달한다. |
| 같은 담당 → 이양원 | `data/finetuning/dev.jsonl` | 40건 수령·검증 및 학습 중 평가 완료. 설정 선택·오류 분석에 사용한다. |
| 같은 담당 → 이양원 | `data/finetuning/holdout.jsonl` | 20건 수령·고정 Base–LoRA 비교 완료. 학습·튜닝에는 사용하지 않는다. |
| 김혜리 수집·정리, 팀 추천 기준 검수 → 이양원·최지흠 | `data/products/catalog.json` | 조건에 맞는 실제 제품 후보와 근거 ID. 현재 5개 제품 파일이 Git에 있으므로 이를 검수·보완하며 새 ID를 임의로 만들지 않음. |
| 김혜리 → 최지흠·이양원 | `document_pipeline/data/manifest_v3.json` | 최신 main 파이프라인으로 A40 검증 corpus 18개 문서·270개 청크를 생성했다. 정식 인계 시 registry·manifest·색인 해시를 함께 확인한다. |
| 김혜리 → 최지흠·통합 담당 | 사용한 `source_registry_v3.csv`, 원문 수집 대장·commit, 라이선스 검토 기록 | manifest가 어느 공식 원문과 검수 기준에서 만들어졌는지 재현·확인하기 위해 필요. registry와 검토 문서는 기존 파일을 활용. |
| 최지흠 → 실행 환경·통합 담당 | `data/indexed/chroma_official_v3/` 전체 또는 같은 manifest로 재생성하는 절차 | 실제 Hybrid 검색에 필요. 문서 담당자가 수작업으로 만드는 파일이 아니라 RAG 색인 코드의 산출물. |
| 팀 공동 작성·교차 검수 → 최지흠·김나은·통합 담당 | QA 평가 질문과 정답 근거 목록 | 검색·답변·인용·보류가 맞는지 확인. 아래 평가 자료 규칙 참고. 조건 JSONL과 별개. |

이양원이 라벨 기준을 정하고 승인해야 한다. 데이터 담당자에게 정답의 의미까지
혼자 결정해 달라는 요청이 아니다. README의 담당표를 기준으로 했으며, 세부 작성 분량은 팀 합의로 정한다.

학습·평가 수치와 한계는 [A40 검증 기록](../validation/2026-08-31-runpod-a40.md),
현재 코드 반영 상태는 [통합 검증 기록](../validation/2026-08-31-finetuning-integration.md)을 참고한다.
360건의 `expected_product_ids`는 아직 비어 있어 추천 정확도 평가용 제품 라벨 인계는 남아 있다.

## 1. 학습·검증·최종평가 JSONL 3개

세 파일은 **같은 형식**이다. 한 줄에 한 사용 사례를 담고,
`id`, `answers`, `target`을 필수로 넣는다. `expected_product_ids`만 선택 항목이다.
전체 필드표·허용값·레코드 예시·검증 코드는 [학습 데이터 계약](finetuning.md)에 있다.
`target`의 기계 기준은 [condition.schema.json](../schemas/condition.schema.json)이다.

- 자유로운 문장도 `answers` 안의 `answer`에 담는다. `input`, `output`, `messages` 등 새 필드를 만들지 않는다.
- `target`은 제품 추천 문장이 아니라 **사용자가 표현한 조건의 JSON**이다.
- 값이 없는 조건도 필드를 지우지 말고 `null`로 둔다. `target`은 15개 필드 모두 필수다.
- “카메라 필요 없음”은 `camera_required=false`, “카메라 필요”는 `true`, 카메라 언급이 없으면 `null`이다.
- 성능·숙련도·원격 접속·GPIO 등 언급하지 않은 조건을 용도만 보고 채우지 않는다.
- `product_models`는 사용자가 지정한 제품이며, 팀이 추천할 정답 제품을 넣는 칸이 아니다.
- 제품 평가용 `expected_product_ids`를 채울 때는 카탈로그의 `product_id`와 정확히 맞춘다. 조건 추출만 평가한다면 생략 가능하다.
- 세 파일의 ID와 입력은 중복되면 안 된다. 같은 원문에서 만든 표현 변형은 같은 split으로 묶고 완전히 같은 입력은 제거한다.
- Train 300~500건 + 별도 Dev/Holdout이 현재 계획이다. Dev/Holdout 수량은 미확정이며, README의 **RAG 평가 40/10**을 조건 학습 데이터 분할 수량으로 오해하지 않는다.
- 먼저 소량의 초안을 만들어 이양원과 라벨 의미를 맞춘 뒤 전체를 작성하는 순서를 권장한다. 이는 새 코드 요구사항이 아닌 작업 제안이다.

전달 시 별도 메모에 데이터 버전, 각 split 건수, 작성·검수자, 중복 제거·분리 기준,
남아 있는 애매한 사례를 적는다. 메모는 실행에 필수인 입력 파일은 아니며,
그 내용을 학습 JSONL에 임의 필드로 추가하지 않는다. 개인정보·계정·토큰은 포함하지 않는다.

받은 뒤 프로젝트 루트에서 실행한다. GPU나 모델 다운로드 없이 형식·정확히 일치하는 입력 누수를 검사한다.
`pydantic`, `PyYAML`이 설치된 Python 환경이 필요하다.

```bash
python training/train_qlora.py --config training/configs/qwen3_4b_qlora.yaml --validate-only
```

현재 이 명령은 `SurveyResponse` 변환과 제품 ID 존재까지 검사하지 않는다.
[학습 계약 마지막의 추가 점검](finetuning.md#받자마자-실행)도 함께 실행한다.
스키마 통과는 라벨 정답률이나 의미상 중복 없음의 증명이 아니므로 사람이 교차 검수한다.

## 2. 제품 카탈로그: 기존 파일을 검수·보완

파일은 `data/products/catalog.json`, 현재 계약 버전은 **`1.1.0`**이다.
[제품 카탈로그 계약](product-catalog.md)과 [ProductCatalog 모델](../../src/recommendation/schema.py)이 기준이다.

| 구분 | 넣어야 할 내용 |
|---|---|
| 파일 상단 | `schema_version`, `catalog_version`, `generated_at`, `sources`, `products` |
| 제품 식별 | 고유한 `product_id`, `name`, `aliases`, `family`, `is_current` |
| 제품 사양 | `memory_options_gb`, `capabilities`의 무선·유선·GPIO·카메라·디스플레이·키보드 기능, `display`의 CPU·메모리·무선 요약 |
| 추천 기준 | `recommendation_profile`의 성능 등급·초보자 적합 여부·추천 용도·작업. 모델이 만든 추측 대신 팀 검수 기준 사용 |
| 안내 정보 | `required_accessories`, `caveats`, 공식 `product_url`, 허용된 `image_url` 또는 `null` |
| 필드별 근거 | `evidence_by_field`에 각 사양·추천 기준을 지지하는 공식 문서 ID |
| 근거 합계 | `document_ids`는 모든 `evidence_by_field.*`를 합쳐 중복 제거 후 정렬한 목록과 정확히 같아야 함 |
| 출처 대장 | `sources`의 문서 ID·제목·URL·수집일·라이선스 |

특히 다음 관계가 맞아야 한다.

```text
학습/평가의 expected_product_ids → catalog.products[].product_id
제품의 evidence_by_field.*     → catalog.sources[].document_id
catalog.sources[].document_id  → manifest.chunks[].document_id
```

catalog와 manifest의 동일 문서는 `title`, `source_url`, `license`가 정확히 같아야 한다.
라이선스 철자만 다르게 적어도 검증이 실패할 수 있으므로 같은 검수 대장에서 가져온다.
catalog의 `retrieved_at`은 대응 manifest의 `collected_at`보다 미래이면 안 된다.
필수 사양을 모르면 임의로 `false`나 `0`으로 채우지 않고 공식 자료를 더 확인한다.
크기만 미확인인 경우 현재 계약이 허용하는 `display.dimensions=null`과 빈 크기 근거 목록을 사용한다.

카탈로그 자체 구조 검사는 모델·GPU 없이 실행할 수 있다.

```bash
python -c "from src.recommendation.schema import ProductCatalog; c=ProductCatalog.from_received_file('data/products/catalog.json'); print('catalog OK:', len(c.products))"
```

이 검사만으로 공식 사양의 사실성이나 근거 연결이 검증되지는 않는다. 아래 manifest와의 결합 검사도 필요하다.

## 3. 공식 문서 manifest와 재현 자료

최종 위치는 `document_pipeline/data/manifest_v3.json`, 현재 manifest 계약 버전은 **`1.0.0`**이다.
파일명 `v3`는 corpus 묶음 버전이다. 조건 JSON·catalog 버전 `1.1.0`과 혼동해 바꾸지 않는다.
전체 형식은 [manifest 계약](../../document_pipeline/contracts/manifest-contract.md)과
[manifest.schema.json](../../document_pipeline/contracts/manifest.schema.json)을 따른다.
이 디렉터리의 예전 `rag-corpus.md`에 있는 최소 청크 형식은 신규 전달용이 아니다.

| 위치 | 필수 필드 |
|---|---|
| 파일 최상위 | `schema_version`, `generated_at`, `source_registry`, 비어 있지 않은 `chunks` |
| 각 청크의 식별 | `document_id`, 고유한 `chunk_id`, 0부터 시작하는 `chunk_index` |
| 각 청크의 본문·출처 | `title`, `publisher`, `section`, `content`, `source_url`, `source_anchor`, `language`, `source_type` |
| 날짜·버전 | `published_at`, `updated_at`, `collected_at`, `document_version` |
| 권리·검수 | `license`, `official_verified` |
| 검색 분류 | `product_models`, `use_cases`, `tasks`, `categories`, `os_versions` |
| 무결성·파서 | `document_checksum`, `chunk_checksum`, `parser_version` |
| 미디어 | `image_url`, `video_url` |

모든 필드를 포함하되, `published_at`, `updated_at`, `source_anchor`, `document_version`,
`image_url`, `video_url`은 계약상 `null`을 허용한다. 실제 수집 파이프라인은 공식 commit을 기록하므로
확인한 버전을 지우지 않는다. 해당 없는 분류 태그는 빈 배열이다. 나머지 항목에 임의 `null`을 넣지 않는다.

- `source_registry`는 `document_pipeline/data/source_registry_v3.csv`를 기록한다.
- 현재 v3 registry의 `collection_decision=include` 18개 공식 문서를 대상으로 생성한다.
- 공식 원문·라이선스·수집 허용 상태를 검수한 자료만 `official_verified=true`로 포함한다. 단순한 오류 회피용으로 true를 넣지 않는다.
- 본문은 원문에 근거한 정제 텍스트다. LLM 요약이나 팀의 추천 문장을 공식 원문처럼 섞지 않는다.
- E5 실제 토크나이저 기준 기본 목표 360 / 최대 460 tokens, 겹침 최대 60 tokens다. 단어 수를 토큰 수로 대신 세지 않는다.
- `document_checksum`, `chunk_checksum`은 실제 원문·본문에서 코드가 계산한 `sha256:<64자리 hex>`를 사용한다.
- `rank`, `citation_id`, `indexed_at`은 RAG가 실행 중 생성하는 값이다. 정적 manifest에 넣지 않는다.
- 원문·수집 대장·파싱 결과는 재현·감사용이다. 본문이 들어 있는 manifest가 런타임 필수 입력이며 raw/processed 파일을 검색기가 직접 읽지는 않는다.

문서 담당자는 기존 파이프라인으로 생성한다. 아래 명령은 네트워크 수집·토크나이저 준비가 가능한 환경에서 실행한다.
`--commit`을 생략하면 실행 시 조회한 공식 commit이 수집 대장에 기록되며, 재현 시에는 기록된 실제 SHA를 지정한다.

```bash
python document_pipeline/ingestion/validate_foundation.py --source-registry document_pipeline/data/source_registry_v3.csv
python document_pipeline/ingestion/run_pipeline.py --source-registry document_pipeline/data/source_registry_v3.csv --raw-root document_pipeline/data/raw_v3 --processed-root document_pipeline/data/processed_v3 --manifest-path document_pipeline/data/manifest_v3.json
```

전달된 manifest의 스키마·본문 checksum·catalog 연결을 아래 Python 코드로 검사한다.
프로젝트 루트에서 실행하며 `jsonschema`, `pydantic` 및 프로젝트 파이프라인 의존성이 필요하다.
이 코드는 데이터를 수정하거나 색인을 만들지 않는다.

```python
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from document_pipeline.ingestion.build_manifest import validate_manifest
from src.recommendation.catalog_validation import load_and_validate_catalog

manifest_path = Path("document_pipeline/data/manifest_v3.json")
schema_path = Path("document_pipeline/contracts/manifest.schema.json")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
schema = json.loads(schema_path.read_text(encoding="utf-8"))
Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
validate_manifest(manifest)
catalog, _ = load_and_validate_catalog(
    catalog_path="data/products/catalog.json",
    manifest_path=manifest_path,
)
print(f"manifest/catalog OK: {len(manifest['chunks'])} chunks, {len(catalog.products)} products")
```

공식 사실·라이선스의 검수, 실제 원문 checksum 대조, E5 토큰 길이 검수는 생성 파이프라인과 사람 검수 단계도 필요하다.
위 읽기 검증만으로 이 품질 항목 모두를 확인하는 것은 아니다.

## 4. RAG 담당자가 준비할 색인과 평가

문서 담당자에게 Chroma 파일을 수작업으로 요청하지 않는다. 최지흠이 같은 manifest로 색인을 만든다.
아래는 `.env`에서 서로 일치시켜야 하는 비밀 아닌 설정 예시다. API 키·토큰은 공유 문서에 넣지 않는다.

```dotenv
DOCUMENT_MANIFEST=document_pipeline/data/manifest_v3.json
PRODUCT_CATALOG=data/products/catalog.json
CHROMA_PATH=data/indexed/chroma_official_v3
CHROMA_COLLECTION_NAME=rpi_official
E5_MODEL_NAME=intfloat/multilingual-e5-base
TOP_K=5
```

처음 색인을 만들 때는 다음 명령을 사용한다.

```bash
python -m src.services.rag_qa_cli --action index
```

색인 폴더를 전달할 경우 DB를 닫고 **폴더 전체**를 공유한다. `chroma.sqlite3` 하나만 복사하면 안 된다.
함께 생성되는 `picare-index.json`에는 collection, embedding model, manifest checksum,
indexed_at 등이 들어 있으므로 누락하거나 수작업으로 조작하지 않는다.
manifest가 바뀌면 기존 색인을 그대로 쓰지 않고 재생성한다. `--reset`은 해당 collection을
삭제·재생성하므로 설정 경로와 보존 필요성을 확인한 뒤 사용한다.

QA 평가는 기존 `eval/questions_v1.jsonl`의 질문·기대 상태를 출발점으로 삼되,
정식 corpus에 대한 근거 정답 검수를 추가한다. 팀 계획의 50문항(Dev 40, Holdout 10)은 이 RAG 평가용이다.
조건 학습 JSONL로 이름만 바꾸지 않는다. 각 질문에 다음 정보를 함께 전달해야 한다.

- 질문 ID·질문·Dev/Holdout 구분과 적용한 제품/OS 등의 검색 필터.
- 답할 수 있는 질문: 정답의 핵심 내용, 근거 `document_id`와 실제 manifest의 `chunk_id` 목록.
- 답할 수 없는 질문: 기대 상태(`insufficient_evidence`, `out_of_scope` 등)와 그렇게 판정한 이유.
- 사용한 manifest 버전/checksum. 다른 버전의 청크 ID를 정답으로 섞지 않는다.

검색 지표 함수는 `질문 ID -> 정답 chunk_id 집합`을 받는다. 위 부가 평가 정보의 저장 형식과
기존 질문 파일에서 지표 함수로 변환하는 연결 코드는 RAG 담당자가 맞춘다.
기존 질문 JSONL에 이 정보를 추가하기만 하면 자동으로 최종 평가가 실행된다고 가정하지 않는다.

LLM 답변 품질은 [별도 평가 파일 계약과 실행 가이드](../llm-answer-evaluation.md)를 따른다.
`id`, `question`, `route`, `split`, `expected_status`, `reference_points`, `required_commands` 형식이며,
기존 질문 파일이나 학습용 JSONL과 혼용하지 않는다. 실행 후 실제 답변·근거 기록과 의미 검수 파일을 함께 전달한다.

## 5. 지금 다른 팀원에게 요청하지 않아도 되는 것

- 학습된 PiCare 어댑터: 아직 학습 전이다. 이양원이 데이터 수령 후 학습하고 어댑터·config·평가 결과·저장 위치를 전달한다.
- Qwen 사전학습 가중치: 모델 실행 환경에서 준비한다. 문서 담당자가 만드는 산출물이 아니다.
- Streamlit용 별도 학습 JSONL: 필요 없다. 김나은은 기존 `RecommendationFormInput`과 `ChatResponse` 계약에 실제 백엔드를 연결한다.
- QA를 위한 조건 추출 어댑터 학습 파일: 현재 QA는 공식 문서 검색 + 기본 Qwen 답변 구조이며, 조건 추출 학습 데이터와 역할이 다르다.

학습 JSONL·원문·manifest·색인·가중치는 승인된 팀 공유 위치나 실행 volume로 전달한다.
검수된 catalog와 계약 문서는 Git에서 관리한다. 로컬 smoke 테스트 결과는 정식 corpus 검수나 실제 모델 정확도 평가를 대신하지 않는다.
