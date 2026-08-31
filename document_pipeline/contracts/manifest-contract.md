# Manifest 계약

- 계약 버전: `1.1.0`
- 구현 상태: 구현 및 자동 검증 완료
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
| 권리와 출처 | 문서·데이터 | `license`, `official_verified`, `quality_status` |
| 검색 filter | 문서·데이터 | `product_models`, `use_cases`, `tasks`, `categories`, `os_versions` |
| 무결성 | 문서·데이터 | `document_checksum`, `chunk_checksum`, `embedding_checksum`, `parser_version` |
| 미디어 호환 필드 | 문서·데이터 | `image_url`, `video_url`(항상 `null`, 별도 media manifest 사용) |
| 색인 시각 | RAG | `indexed_at` |
| 검색 결과 순위 | RAG | `rank` |
| 응답별 인용 번호 | RAG/통합 | `citation_id` |

## 결정 사항

1. manifest의 최상위 객체는 `schema_version`, `generated_at`, `source_registry`, `processing`, `chunks`를 가진다. `processing`은 tokenizer revision, token limit, registry checksum과 설정 fingerprint를 기록한다.
2. `chunks`는 RAG가 문서 조인 없이 검색할 수 있도록 출처 metadata를 청크마다 포함한다.
3. 날짜는 ISO 8601을 사용하고 checksum은 `sha256:<64 hex>` 형식을 사용한다.
4. `official_verified=true`, `quality_status=approved`이고 source registry에서 `collection_decision=include`인 자료만 manifest에 포함한다. 파싱 검수 대상은 `processed/qa_report.json`에만 기록한다.
5. `rank`, `citation_id`, `indexed_at`은 런타임 필드이므로 manifest에 넣지 않는다.
6. 기존 RAG 프로토타입의 `retrieved_at`은 신규 manifest에서 사용하지 않는다. `src/rag/adapters.py`가 `collected_at`과 `source_anchor`를 보존해 변환하며, manifest 계약 자체는 줄이지 않는다.
7. 이미지·영상은 검색 문장이 아니므로 청크나 임베딩에 포함하지 않는다. 기존 `image_url`, `video_url`은 하위 호환을 위해 `null`로 유지하고, 생성된 `media_manifest_vN.json`의 `chunk_id ↔ media_id` 링크를 사용한다.
8. 가이드 미디어의 URL·license·attribution·원문 commit은 `media-manifest.schema.json`으로 관리한다. 실제 답변에서 검증을 통과해 남은 citation의 `chunk_id`만 Media Resolver에 전달한다.
9. 제품 페이지 사진은 corpus/media manifest에 넣지 않는다. 제품 카드의 원격 표시는 `data/products/catalog.json`의 검수된 `image_url`로 별도 통제한다.

## 현재 RAG 테스트 형식과의 연결

RAG 담당자의 테스트 chunk는 검색 품질을 빠르게 확인하기 위한 축약 형식이다. 테스트 코드를 전면 수정하지 않고, manifest를 읽는 지점에 변환 adapter를 둔다.

| 테스트 chunk 필드 | 최종 manifest 필드 | 처리 |
|---|---|---|
| `chunk_id`, `document_id`, `title`, `section`, `content`, `source_url`, `document_version`, `license`, `product_models`, `use_cases`, `os_versions`, `source_type`, `official_verified`, `quality_status` | 같은 이름 | 그대로 사용 |
| `retrieved_at` | `collected_at` | 수집 시각이므로 이름을 바꿔 전달. 검색 시각으로 사용하지 않음 |
| 없음 | `chunk_index`, `publisher`, `source_anchor`, `language` | 문서 파이프라인이 채움 |
| 없음 | `published_at`, `updated_at`, `tasks`, `categories` | 원문과 source registry에서 채움. 값이 없으면 `null` 또는 빈 배열 |
| 없음 | `document_checksum`, `chunk_checksum`, `embedding_checksum`, `parser_version` | 문서 파이프라인이 생성하여 원문·인용문·실제 임베딩 입력의 변경을 각각 추적 |
| 없음 | `image_url`, `video_url` | 항상 `null`; 미디어 URL은 별도 media manifest에서 조회 |
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

계약 1.1.0의 `embedding_checksum`과 `quality_status`는 `src/contracts/models.py`와 배포용 JSON Schema에 동기화한다.
