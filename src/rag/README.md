# RAG 모듈

> [!IMPORTANT]
> 서비스·배포·성능평가의 단일 corpus 기준은 schema `1.1.0`의
> `document_pipeline/data/manifest_v3.json`입니다. 전체 실행 절차와 QA 명령은
> [`00_README.md`](00_README.md)를 기준으로 합니다.

이 패키지는 문서 수집·청킹, sLLM 조건 추출, 챗봇 UI에 의존하지 않는다. 문서·데이터 담당이 검수한 canonical `manifest.json`을 입력으로 받아 E5/Chroma Dense 검색, BM25, RRF, metadata filter와 Hit@k·MRR 평가를 제공한다.

## Canonical manifest 입력 형식

신규 수집·검색 구현은 schema `1.1.0`과 `docs/schemas/search-response.schema.json`의 `collected_at`, `indexed_at`, `citation_id` 및 검증 필드를 사용해야 한다.

`manifest.json`은 `schema_version`, `processing`, `chunks`를 포함한다. 청크는 `chunk_id`, `document_id`, `title`, `section`, `content`, `source_url`, `source_anchor`, `collected_at`, `document_version`, `license`, `product_models`, `use_cases`, `tasks`, `categories`, `os_versions`, `source_type`, `official_verified`, `quality_status`, `embedding_checksum`을 포함한다.

`official_verified=true`, `quality_status=approved`인 청크만 Chroma index와 검색 결과에 포함한다. Dense 임베딩에는 제목·섹션 경로·본문을 사용하지만 Chroma의 `documents`와 사용자 인용에는 원문 기반 `content`만 저장한다.

## 사용 방법

### `.env` 설정과 로컬 실행

프로젝트 최상위 `.env`에 아래 RAG 설정이 필요하다. 로컬 `PersistentClient`를
사용하므로 Chroma API 키는 필요 없다.

```env
DOCUMENT_MANIFEST=document_pipeline/data/manifest_v3.json
CHROMA_PATH=data/indexed/chroma_official_v3
CHROMA_COLLECTION_NAME=rpi_official
E5_MODEL_NAME=intfloat/multilingual-e5-base
TOP_K=5
```

색인은 명시적으로 실행한다. `--reset`은 기존 컬렉션을 삭제한 뒤 manifest 전체를
다시 색인한다. 옵션 없이 실행하면 같은 `chunk_id`를 upsert하고 새 manifest에 없는 stale ID를 삭제한다.

```bash
# 서비스용 v3 corpus 전체 색인
python3 -m src.services.rag_qa_cli --action index --reset

# 서비스 QA 경로 확인
HF_HUB_OFFLINE=1 python3 -m src.services.rag_qa_cli --query "SSH를 활성화하려면?"
```

Retriever 단독 점검과 BM25/Dense/Hybrid 실행 옵션은 [`00_README.md`](00_README.md)의
"Retriever 단위 점검"을 따른다. Chroma DB나 collection이 없으면 오류를 숨기고 BM25로
전환하지 않으므로, 먼저 위 색인 명령을 실행해 원인을 확인한다.

### Legacy test fixtures

`data/corpora/corpus_official_pilot`과 `data/corpora/corpus_section_test`는 이전
프로토타입의 호환성·검색 단위 테스트용 fixture다. 두 manifest는 schema `1.1.0` 이전
형식이므로 `tasks`, `categories`와 canonical 처리 metadata를 포함하지 않는다.

이 fixture들은 서비스, 배포, 성능평가 또는 `.env`의 `DOCUMENT_MANIFEST`로 사용하지
않는다. `HybridRetriever.from_manifest()`는 이 파일을 입력받으면 schema version 오류로
명시적으로 거부해야 한다.

### Python에서 사용

```python
from src.rag import HybridRetriever, RagFilters

retriever = HybridRetriever.from_manifest(
    "document_pipeline/data/manifest_v3.json",
    chroma_path="data/indexed/chroma_official_v3",
)
results = retriever.search(
    "모니터 없이 카메라를 연결하고 싶어요",
    RagFilters(product_models=("Raspberry Pi 5",), use_cases=("camera",)),
    top_k=5,
)
```

현재 반환값은 테스트용 `list[RagResult]`다. 실제 챗봇 연결 전에는 `SearchResponse` 계약으로 변환하고, 서버가 `citation_id`와 출처 metadata를 조합해야 한다.

Chroma 색인에는 `product_models`, `use_cases`, `os_versions`를 tag별 boolean metadata로
저장한다. Dense 검색은 해당 metadata를 Chroma `where`에 먼저 적용하고, 반환 전에는
동일 조건을 다시 검사한다.

## 역할 경계

- 문서·데이터: 공식 문서 수집, 라이선스, 정제·청킹, metadata, Document Card, manifest
- RAG: E5/Chroma, BM25, RRF, metadata filter, Top-k, Hit@k·MRR
- sLLM: 조건 JSON을 통합 계층에서 `RagFilters`로 변환할 입력 제공
- 챗봇: `RagResult`를 사용한 답변·출처 UI·보류 처리

## RAG 담당 체크리스트

- [ ] 문서·데이터 담당에게서 검수 완료된 corpus와 `manifest.json`을 수령한다.
- [ ] 필수 metadata와 `official_verified` 값이 입력 계약에 맞는지 검증한다.
- [ ] manifest 기반으로 E5 임베딩·Chroma 색인을 생성하고 재현 가능하게 저장한다.
- [ ] BM25, Dense, Hybrid RRF 검색을 동일 질의셋에서 비교한다.
- [ ] metadata filter, Top-k 결과, citation metadata 보존을 테스트한다.
- [ ] Dev/Holdout qrels로 Hit@k와 MRR을 기록한다.
