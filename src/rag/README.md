# RAG 모듈

> [!IMPORTANT]
> 현재 이 패키지는 검색 동작을 검증하기 위한 프로토타입입니다. 필드명과 반환 형식의 기준은 기존 `RagResult` 구현이 아니라 `src/contracts/models.py`와 `docs/schemas/search-response.schema.json`입니다. 프로토타입을 서비스에 연결할 때는 공통 계약을 만족하도록 교체하거나 adapter를 구현해야 합니다.

이 패키지는 문서 수집·청킹, sLLM 조건 추출, 챗봇 UI에 의존하지 않는다. 문서·데이터 담당이 검수한 `manifest.json`을 입력으로 받아 E5/Chroma Dense 검색, BM25, RRF, metadata filter와 Hit@k·MRR 평가를 제공한다.

## 프로토타입 입력 형식

아래 형식은 현재 검색 동작 테스트에만 사용하며 확정 계약이 아니다. 신규 수집·검색 구현은 `docs/schemas/search-response.schema.json`의 `collected_at`, `indexed_at`, `citation_id`와 검증 필드를 사용해야 한다.

`manifest.json`은 `chunks` 배열을 포함한다. 현재 프로토타입 청크는 `chunk_id`, `document_id`, `title`, `section`, `content`, `source_url`, `retrieved_at`, `document_version`, `license`, `product_models`, `use_cases`, `os_versions`, `source_type`, `official_verified`를 사용한다.

`official_verified`가 `true`인 청크만 Chroma index에 넣고, 기본 검색 결과에도 포함한다.

## 사용 방법

```python
from src.rag import HybridRetriever, RagFilters

retriever = HybridRetriever.from_manifest("data/documents/manifest.json", chroma_path="data/chroma")
results = retriever.search(
    "모니터 없이 카메라를 연결하고 싶어요",
    RagFilters(product_models=("Raspberry Pi 5",), use_cases=("camera",)),
    top_k=5,
)
```

현재 반환값은 테스트용 `list[RagResult]`다. 실제 챗봇 연결 전에는 `SearchResponse` 계약으로 변환하고, 서버가 `citation_id`와 출처 metadata를 조합해야 한다.

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
