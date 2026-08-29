# Document Pipeline

Raspberry Pi 공식 문서 corpus의 출처 검토, 수집, 정제, 청킹 및 manifest 생성을 한곳에서 관리한다.

## 현재 구현 범위

- `contracts/manifest.schema.json`: 문서 담당자가 RAG에 전달할 정적 manifest 계약
- `contracts/manifest-contract.md`: 필드 소유권과 RAG 통합 규칙
- `data/source_registry.csv`: 원본 corpus 기준의 공식 문서 9개와 참고 전용 자료 8개의 수집 허용 상태
- `data/source_registry_v2.csv`: 원본을 보존한 추천 MVP 확장본; 공식 문서 15개와 참고 전용 자료 8개
- `data/product_media_registry.json`: CC BY-SA 4.0 제품 사진 5개의 고정 원문 경로와 출처 표기 조건
- `docs/license-review.md`: 공식 라이선스·이용약관 조사와 수집 정책
- `ingestion/validate_foundation.py`: 계약과 source registry의 기본 정합성 검사

원문 수집, 파싱, 정제, 청킹의 기본 구현이 준비됐다. 제품 사진은 `product_media_registry.json`에 등록된 `documentation/` 원본만 사용하고, UI에는 CC BY-SA 4.0 출처와 변경 여부를 표시한다.

## 구조

```text
document_pipeline/
├── contracts/
├── data/
│   ├── raw/
│   ├── processed/
│   ├── source_registry.csv
│   ├── source_registry_v2.csv
│   └── product_media_registry.json
├── docs/
└── ingestion/
```

`raw/`, `processed/`, 생성된 `manifest.json`은 저장소에 커밋하지 않는다. 공개 저장소에는 계약, 출처 대장, 검토 기록만 포함한다.

## 검증

프로젝트 루트에서 실행한다.

```bash
python document_pipeline/ingestion/validate_foundation.py
```

성공하면 registry 레코드 수, 포함 대상 수, 참고 전용 대상 수를 출력한다. 옵션 없이 실행하면 원본 registry를 검사한다.

## 핵심 문서 수집·파싱 실행

옵션 없이 실행하면 원본 `source_registry.csv`에서 `collection_decision=include`인 9개 AsciiDoc 문서를 수집한다. 실행 시점의 Raspberry Pi 공식 `master` commit을 한 번 조회한 뒤, 모든 원문 URL을 해당 SHA로 고정한다.

```bash
python document_pipeline/ingestion/run_pipeline.py
```

추천 MVP RAG에는 원본을 변경하지 않는 v2 registry와 전용 생성 경로를 사용한다.

```bash
python document_pipeline/ingestion/validate_foundation.py \
  --source-registry document_pipeline/data/source_registry_v2.csv

python document_pipeline/ingestion/run_pipeline.py \
  --commit <40자리_공식_documentation_SHA> \
  --source-registry document_pipeline/data/source_registry_v2.csv \
  --raw-root document_pipeline/data/raw_v2 \
  --processed-root document_pipeline/data/processed_v2 \
  --manifest-path document_pipeline/data/manifest_v2.json
```

실행 결과는 다음과 같다.

- `data/raw/*.adoc`: 변경하지 않은 공식 원문과 `collection.json` 수집 대장
- `data/processed/parsed_sections.json`: 실제 anchor와 heading 경로, 문단·목록·코드·주의문·표·이미지 블록을 보존한 중간 결과
- `data/manifest.json`: RAG에 전달하는 청크와 metadata

기본 실행의 결과는 `data/raw/`, `data/processed/`, `data/manifest.json`에 생성되며, v2 실행의 결과는 각각 `data/raw_v2/`, `data/processed_v2/`, `data/manifest_v2.json`에 생성된다. 이 파일들은 모두 Git 제외 대상이다. 파싱 로직만 다시 실행하려면 `python document_pipeline/ingestion/build_manifest.py`를 사용한다. 기본값은 `multilingual-e5-base` 토크나이저 기준 목표 360 tokens, 하드 최대 460 tokens, 완전한 문단 블록만 60 tokens 이내로 겹치게 한다. 코드·표·이미지는 겹치지 않는다. 제품 페이지와 A/S·리콜 공지는 이 corpus에 자동 수집하지 않는다. 제품 페이지는 제품 카드 URL·이미지 metadata에만 사용하고, A/S·리콜은 후속 공식 웹 검색 단계에서 다룬다.

## 다음 합의 사항

1. RAG 담당자가 manifest의 정적 필드와 런타임 필드 분리를 검토한다.
2. `src/rag/adapters.py`가 canonical `collected_at`을 기존 RAG 모델의 `retrieved_at`으로 변환한다. 새 manifest 계약은 줄이지 않는다.
3. 제품 카드 UI에 `CC BY-SA 4.0` 출처 표기와 비공식 프로젝트 고지를 구현한다.
