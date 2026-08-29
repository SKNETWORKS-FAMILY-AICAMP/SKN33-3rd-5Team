# Manifest 계약

- 계약 버전: `1.0.0`
- 구현 상태: 검토 요청
- 기준 계약: `src/contracts/models.py::SearchResultMetadata`
- 기계 검증 스키마: `manifest.schema.json`

## 목적

문서 담당자가 수집·검수한 청크를 RAG 담당자에게 전달할 때 사용하는 정적 계약이다. 검색 요청마다 달라지는 값은 manifest에 저장하지 않는다.

## 필드 소유권

| 구분 | 담당 | 필드 |
|---|---|---|
| 문서·청크 식별 | 문서·데이터 | `document_id`, `chunk_id`, `chunk_index` |
| 원문과 본문 | 문서·데이터 | `title`, `publisher`, `section`, `content`, `source_url`, `source_anchor`, `language`, `source_type` |
| 날짜와 버전 | 문서·데이터 | `published_at`, `updated_at`, `collected_at`, `document_version` |
| 권리와 출처 | 문서·데이터 | `license`, `official_verified` |
| 검색 filter | 문서·데이터 | `product_models`, `use_cases`, `tasks`, `categories`, `os_versions` |
| 무결성 | 문서·데이터 | `document_checksum`, `chunk_checksum`, `parser_version` |
| 미디어 연결 | 문서·데이터 | `image_url`, `video_url` |
| 색인 시각 | RAG | `indexed_at` |
| 검색 결과 순위 | RAG | `rank` |
| 응답별 인용 번호 | RAG/통합 | `citation_id` |

## 결정 사항

1. manifest의 최상위 객체는 `schema_version`, `generated_at`, `source_registry`, `chunks`를 가진다. `source_registry`는 `document_pipeline/data/source_registry.csv` 또는 `source_registry_vN.csv`처럼 실제 수집에 사용한 검수 대장을 기록한다.
2. `chunks`는 RAG가 문서 조인 없이 검색할 수 있도록 출처 metadata를 청크마다 포함한다.
3. 날짜는 ISO 8601을 사용하고 checksum은 `sha256:<64 hex>` 형식을 사용한다.
4. `official_verified`가 `true`이고 source registry에서 `collection_decision=include`인 자료만 manifest에 포함한다.
5. `rank`, `citation_id`, `indexed_at`은 런타임 필드이므로 manifest에 넣지 않는다.
6. 기존 RAG 프로토타입의 `retrieved_at`은 신규 manifest에서 사용하지 않는다. `src/rag/adapters.py`가 `collected_at`을 보존해 변환하며, manifest 계약 자체는 줄이지 않는다.
7. corpus의 `image_url`, `video_url`은 명확한 재사용 권리가 확인된 공식 URL만 사용하며, 파일 자체는 corpus에 복제하지 않는다.
8. `license_url`, 검토 상태와 attribution 문구는 실제 수집에 사용한 `source_registry*.csv`와 Document Card에서 관리한다. RAG manifest에는 canonical 계약의 `license`만 전달한다.
9. 제품 페이지 사진은 corpus manifest에 넣지 않는다. 교육용 제품 카드의 원격 표시는 `data/product_media_registry.json`에서 별도로 통제한다.

## 현재 RAG 테스트 형식과의 연결

RAG 담당자의 테스트 chunk는 검색 품질을 빠르게 확인하기 위한 축약 형식이다. 테스트 코드를 전면 수정하지 않고, manifest를 읽는 지점에 변환 adapter를 둔다.

| 테스트 chunk 필드 | 최종 manifest 필드 | 처리 |
|---|---|---|
| `chunk_id`, `document_id`, `title`, `section`, `content`, `source_url`, `document_version`, `license`, `product_models`, `use_cases`, `os_versions`, `source_type`, `official_verified` | 같은 이름 | 그대로 사용 |
| `retrieved_at` | `collected_at` | 수집 시각이므로 이름을 바꿔 전달. 검색 시각으로 사용하지 않음 |
| 없음 | `chunk_index`, `publisher`, `source_anchor`, `language` | 문서 파이프라인이 채움 |
| 없음 | `published_at`, `updated_at`, `tasks`, `categories` | 원문과 source registry에서 채움. 값이 없으면 `null` 또는 빈 배열 |
| 없음 | `document_checksum`, `chunk_checksum`, `parser_version` | 문서 파이프라인이 생성하여 재현성·변경 감지에 사용 |
| 없음 | `image_url`, `video_url` | 명확한 재사용 권리가 있는 경우에만 채움 |
| 없음 | `indexed_at`, `rank`, `citation_id` | RAG/통합 계층이 검색·응답 시 생성 |

따라서 테스트 예시의 `source_url`처럼 사람이 바로 열 수 있는 공식 문서 링크는 유지한다. 다만 최종 manifest에는 `source_anchor`를 분리해 넣어, 인용 UI가 같은 문서의 정확한 절을 표시할 수 있게 한다. AsciiDoc 원문에 `[[explicit-anchor]]`가 있으면 그 값을 그대로 사용하고, 없으면 임의로 추정하지 않아 `null`로 둔다.

## RAG 전달 예시

```text
manifest chunk
  → RAG가 Vector DB에 색인하고 indexed_at 기록
  → 질문 검색 후 rank와 citation_id 부여
  → SearchResultMetadata 생성
```

## 팀 검토 체크리스트

- [ ] 문서·데이터 담당: source registry와 manifest 필드 매핑 확인
- [ ] RAG 담당: `retrieved_at` 제거 및 adapter 경계 확인
- [ ] 통합 담당: `SearchResponse` 생성 시 런타임 필드 주입 확인
- [ ] 전체: 호환되지 않는 변경 시 `schema_version` 증가 규칙 확인

체크리스트 승인 전까지 `src/contracts/models.py`의 필드명은 이 작업에서 변경하지 않는다.
