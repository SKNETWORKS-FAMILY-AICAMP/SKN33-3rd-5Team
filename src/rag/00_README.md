# RAG 모듈

## 가장 먼저: 실행 위치와 명령어

`demo.py`와 `indexer.py`는 상대 import를 사용하는 패키지 모듈이다. 따라서
`src/rag` 폴더에서 `python demo.py`처럼 직접 실행하지 않는다.

프로젝트 최상위 폴더에서 아래처럼 실행한다.

```bash
cd /Users/choejiheum/SK_AI/skn_33_3rd_5team
source .venv/bin/activate

# Chroma 색인 생성 또는 전체 재색인
python3 -m src.rag.indexer --reset

# Hybrid 검색 실행 (네트워크 없이 캐시된 E5 모델 사용)
# --query를 생략하면 콘솔에 질문을 입력할 수 있고, Enter만 누르면 예시 질문을 무작위로 실행한다.
HF_HUB_OFFLINE=1 python3 -m src.rag.demo --mode hybrid
```

`ImportError: attempted relative import with no known parent package`가 나오면
`python3 demo.py`가 아니라 위의 `python3 -m src.rag.demo` 명령으로 실행한다.

> [!IMPORTANT]
> 현재 이 패키지는 검색 동작을 검증하기 위한 프로토타입입니다. 필드명과 반환 형식의 기준은 기존 `RagResult` 구현이 아니라 `src/contracts/models.py`와 `docs/schemas/search-response.schema.json`입니다. 프로토타입을 서비스에 연결할 때는 공통 계약을 만족하도록 교체하거나 adapter를 구현해야 합니다.

이 패키지는 문서 수집·청킹, sLLM 조건 추출, 챗봇 UI에 의존하지 않는다. 문서·데이터 담당이 검수한 `manifest.json`을 입력으로 받아 E5/Chroma Dense 검색, BM25, RRF, metadata filter와 Hit@k·MRR 평가를 제공한다.

## 프로토타입 입력 형식

아래 형식은 현재 검색 동작 테스트에만 사용하며 확정 계약이 아니다. 신규 수집·검색 구현은 `docs/schemas/search-response.schema.json`의 `collected_at`, `indexed_at`, `citation_id`와 검증 필드를 사용해야 한다.

`manifest.json`은 `chunks` 배열을 포함한다. 현재 프로토타입 청크는 `chunk_id`, `document_id`, `title`, `section`, `content`, `source_url`, `retrieved_at`, `document_version`, `license`, `product_models`, `use_cases`, `os_versions`, `source_type`, `official_verified`를 사용한다.

`official_verified`가 `true`인 청크만 Chroma index에 넣고, 기본 검색 결과에도 포함한다.

## 사용 방법

### `.env` 설정과 로컬 실행

프로젝트 최상위 `.env`에 아래 RAG 설정이 필요하다. 로컬 `PersistentClient`를
사용하므로 Chroma API 키는 필요 없다.

```env
DOCUMENT_MANIFEST=data/corpora/corpus_section_test/manifest.json
CHROMA_PATH=data/indexed/chroma_section_test
CHROMA_COLLECTION_NAME=rpi_official
E5_MODEL_NAME=intfloat/multilingual-e5-base
TOP_K=3
# 현재 테스트 corpus 기준 초기값이며, 실제 Dev qrels로 재조정한다.
DENSE_MAX_DISTANCE=0.48
```

색인은 명시적으로 실행한다. `--reset`은 기존 컬렉션을 삭제한 뒤 manifest 전체를
다시 색인하며, 옵션 없이 실행하면 같은 `chunk_id`만 upsert한다.

```bash
python3 -m src.rag.indexer --reset
python3 -m src.rag.demo --mode bm25
python3 -m src.rag.demo --mode hybrid --query "모니터 없이 SSH로 연결하고 싶어요"

# metadata filter는 필요한 경우에만 명시한다.
python3 -m src.rag.demo --mode hybrid --query "카메라를 연결하고 싶어요" --use-case camera
```

`--mode hybrid`에서 Chroma DB나 collection이 없으면 오류를 숨기고 BM25로 전환하지
않는다. 먼저 indexer를 실행해 원인을 바로 확인한다.

BM25는 점수가 모두 0이면 근거가 없는 것으로 보고 결과를 반환하지 않는다. Hybrid
검색은 BM25 양수 점수 또는 `DENSE_MAX_DISTANCE` 이하의 Dense 거리 중 하나를
통과한 청크만 반환한다. 둘 다 통과하지 못하면 `search_with_decision()`은
`insufficient_evidence` 상태와 보류 사유를 반환한다. 기존 `search()`는 호환성을
위해 결과 목록만 반환하며, 보류 시 빈 목록을 반환한다.

### Python에서 사용

```python
from src.rag import HybridRetriever, RagFilters

retriever = HybridRetriever.from_manifest("data/documents/manifest.json", chroma_path="data/chroma")
results = retriever.search(
    "모니터 없이 카메라를 연결하고 싶어요",
    RagFilters(product_models=("Raspberry Pi 5",), use_cases=("camera",)),
    top_k=5,
)

decision = retriever.search_with_decision("스마트팜을 작게 구현하고 싶어요")
if decision.status == "insufficient_evidence":
    print(decision.reason)
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
