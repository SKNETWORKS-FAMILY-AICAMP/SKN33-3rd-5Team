# Document Pipeline

Raspberry Pi 공식 문서 corpus의 출처 검토, 수집, 정제, 청킹 및 manifest 생성을 한곳에서 관리한다.

## 현재 구현 범위

- `contracts/manifest.schema.json`: 문서 담당자가 RAG에 전달할 정적 manifest 계약
- `contracts/manifest-contract.md`: 필드 소유권과 RAG 통합 규칙
- `contracts/media-manifest.schema.json`: `chunk_id`와 `media_id`의 별도 연결 계약
- `data/source_registry.csv`: README의 우선 수집 후보와 수집 허용 상태
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
│   ├── media_manifest.json       # 생성물, Git 제외
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

성공하면 registry 레코드 수, 포함 대상 수, 참고 전용 대상 수를 출력한다.

## 핵심 문서 수집·파싱 실행

아래 명령은 `source_registry.csv`에서 `collection_decision=include`인 AsciiDoc 문서만 수집한다. 실행 시점의 Raspberry Pi 공식 `master` commit을 한 번 조회한 뒤, 모든 원문 URL을 해당 SHA로 고정한다.

```bash
python -m document_pipeline.ingestion.run_pipeline
```

실행 결과는 다음과 같다.

- `data/raw/*.adoc`: 변경하지 않은 공식 원문과 `collection.json` 수집 대장
- `data/processed/parsed_sections.json`: 실제 anchor와 heading 경로, 문단·목록·코드·주의문·표·이미지·탭 블록을 보존한 중간 결과
- `data/processed/qa_report.json`: 파싱 검수 대상, 자동 제외한 완전 중복과 검토할 근접 중복
- `data/manifest.json`: `official_verified=true`, `quality_status=approved`인 청크와 재현 설정 metadata
- `data/media_manifest.json`: 공식 이미지·영상 URL, 권리 정보와 `chunk_id ↔ media_id` 링크

이 파일들은 모두 Git 제외 대상이다. 파싱 로직만 다시 실행하려면 `python -m document_pipeline.ingestion.build_manifest`를 사용한다. 미디어 링크만 다시 만들 때는 `python -m document_pipeline.ingestion.build_media_manifest`를 사용한다. 기본값은 `multilingual-e5-base` 토크나이저 기준 목표 360 tokens, 하드 최대 460 tokens다. 제한은 본문만이 아니라 `passage: + 제목 + 섹션 경로 + 본문` 전체에 적용한다. 완전한 서술 블록만 60 tokens 이내로 겹친다.

파서는 AsciiDoc 표의 선언 열 수, 셀 내부 이미지 캡션, `[tabs]`의 분기, description label과 continuation을 구조적으로 처리한다. 이미지·영상 블록은 중간 구조에는 보존하지만 검색 청크·임베딩에는 넣지 않는다. Media Linker가 같은 공식 문서와 섹션의 승인 청크에 결정적 `media_id`를 연결하며, 원문 checksum·commit·manifest checksum이 다르면 생성을 중단한다. 제품 태그는 `product_media_registry.json`에서 승인된 정확한 모델명만 결정적으로 대조하며 LLM으로 추론하지 않는다.

## 다음 합의 사항

1. RAG 담당자가 manifest의 정적 필드와 런타임 필드 분리를 검토한다.
2. `src/rag/adapters.py`가 canonical `collected_at`을 기존 RAG 모델의 `retrieved_at`으로 변환한다. 새 manifest 계약은 줄이지 않는다.
3. 제품 카드 UI에 `CC BY-SA 4.0` 출처 표기와 비공식 프로젝트 고지를 구현한다.
