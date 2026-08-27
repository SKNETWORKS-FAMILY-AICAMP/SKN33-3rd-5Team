# RAG 모듈

이 패키지는 문서 수집·청킹, sLLM 조건 추출, 챗봇 UI에 의존하지 않는다. 문서·데이터 담당이 검수한 `manifest.json`을 입력으로 받아 E5/Chroma Dense 검색, BM25, RRF, metadata filter와 Hit@k·MRR 평가를 제공한다.

## 문서·데이터 담당 입력 계약

`manifest.json`은 `chunks` 배열을 포함한다. 각 청크는 `chunk_id`, `document_id`, `title`, `section`, `content`, `source_url`, `retrieved_at`, `document_version`, `license`, `product_models`, `use_cases`, `os_versions`, `source_type`, `official_verified`를 가져야 한다.

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

반환값은 `list[RagResult]`다. 챗봇은 `content`를 생성 LLM context에 넣고, `title`, `section`, `source_url`, `license`, `retrieved_at`, `chunk_id`를 근거 카드에 그대로 표시한다.

## 역할 경계

- 문서·데이터: 공식 문서 수집, 라이선스, 정제·청킹, metadata, Document Card, manifest
- RAG: E5/Chroma, BM25, RRF, metadata filter, Top-k, Hit@k·MRR
- sLLM: 조건 JSON을 통합 계층에서 `RagFilters`로 변환할 입력 제공
- 챗봇: `RagResult`를 사용한 답변·출처 UI·보류 처리
