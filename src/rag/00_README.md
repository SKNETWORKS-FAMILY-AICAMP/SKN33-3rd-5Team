# RAG 모듈

## 팀 공통 QA 실행 명령

RAG 검색, 답변 생성기, 인용 검증을 함께 확인하는 기본 실행 명령은 아래다.
발표·시연·통합 확인에는 `src.rag.demo`가 아니라 이 QA CLI를 사용한다.

```bash
python3 -m src.services.rag_qa_cli
```

명령을 인자 없이 실행하면 질문을 입력받아 **BM25 + Chroma Dense + RRF Hybrid QA**를
실행한다. 빈 입력 후 Enter를 누르면 검증용 예시 질문을 무작위로 실행한다. 검색·답변
생성 중에는 터미널에 spinner가 표시된다.

```bash
python3 -m src.services.rag_qa_cli --query "SSH를 활성화하려면?" --trace
```

## 제품 추천 통합 실행

제품 추천은 QA CLI와 별도 흐름이다. `sLLM LoRA 조건 JSON → catalog 후보 필터·점수화
→ 후보의 공식 문서만 Hybrid RAG → Qwen 인용 답변` 순서로 실행한다. 모델은 후보·제품 URL·
이미지·출처를 새로 만들 수 없으며, 서버가 catalog와 manifest metadata로 조합한다.

`DOCUMENT_MANIFEST`를 v3 manifest로 설정하고, `PRODUCT_CATALOG`와 LoRA adapter를
RunPod volume에 둔 뒤 먼저 색인한다.

```bash
python3 -m src.services.rag_qa_cli --action index --reset
ANSWER_GENERATOR=huggingface CONDITION_EXTRACTOR=lora \
python3 -m src.services.recommendation_rag_cli \
  --query "작은 스마트팜을 만들고 싶은데 어떤 모델이 좋을까?" --trace
```

추천 후보의 `document_ids`는 BM25의 로컬 후보 필터와 Chroma `where`의 `document_id`
조건에 모두 적용된다. 선택된 후보를 뒷받침할 청크가 없으면 Qwen을 호출하지 않고
`insufficient_evidence`로 보류한다.

### v3 공식 corpus 생성·색인

제품 추천용 v3 registry는 v2의 15개 공식 문서를 유지하고, Pi 5 멀티카메라·열 관리·
초기 하드웨어 설정 문서 3개를 추가한다. 제품 페이지는 이미지·URL 카드용
`reference_only`이므로 RAG 본문에 색인하지 않는다.

```bash
# registry 계약 검증: 총 26개 중 include 18개, reference_only 8개
python3 document_pipeline/ingestion/validate_foundation.py \
  --source-registry document_pipeline/data/source_registry_v3.csv

# 동일 commit의 원문·정제본·canonical manifest를 재현한다.
python3 -m document_pipeline.ingestion.run_pipeline \
  --commit 75331a79fbf32d2403b7547729ddccf553873b09 \
  --source-registry document_pipeline/data/source_registry_v3.csv \
  --raw-root document_pipeline/data/raw_v3 \
  --processed-root document_pipeline/data/processed_v3 \
  --manifest-path document_pipeline/data/manifest_v3.json

# .env의 DOCUMENT_MANIFEST/CHROMA_PATH를 v3 경로로 설정한 후 실행한다.
python3 -m src.services.rag_qa_cli --action index --reset
```

`raw_v3`, `processed_v3`, `manifest_v3.json`, `chroma_official_v3` 및 실제
`data/products/catalog.json`은 재생성·내부 공유 데이터이므로 Git에 커밋하지 않는다.
Manifest는 **1.1.0만** 지원한다. 현재 고정 commit 기준 v3 manifest는 18개 문서·270개
승인 청크이며, corpus 또는 처리 설정이 바뀌면 manifest를 재생성하고 `--reset`으로 Chroma를
다시 색인한다.

## Retriever 단위 점검: 실행 위치와 명령어

`demo.py`는 답변 생성 전 Retriever 결과만 확인하는 선택적 단위 점검 도구다. `demo.py`와
`indexer.py`는 상대 import를 사용하는 패키지 모듈이므로, `src/rag` 폴더에서
`python demo.py`처럼 직접 실행하지 않는다.

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

## QA CLI 상세 옵션

RAG 검색 결과를 기존 근거 기반 프롬프트·안전 검증과 연결한 QA CLI는 아래처럼
실행한다. Streamlit, 제품 catalog, Qwen 조건 추출은 이 1차 범위에 포함하지 않는다.

인자 없이 실행하면 최종 사용자용 Hybrid QA가 실행된다. BM25 단독 검색과 Chroma 색인은
성능 비교·운영을 위한 명시적 옵션이며 일반 질의 흐름에는 포함하지 않는다.

```bash
# 최종 사용자용 대화형 Hybrid QA
python3 -m src.services.rag_qa_cli

# Hybrid를 자동화·테스트에서 직접 실행한다.
HF_HUB_OFFLINE=1 python3 -m src.services.rag_qa_cli \
  --query "SSH를 활성화하려면?"

# Chroma 없이 BM25만 확인한다.
python3 -m src.services.rag_qa_cli \
  --mode bm25 \
  --query "microSD에 Raspberry Pi OS를 설치하려면?"

# 이후 Streamlit·통합 테스트가 읽을 공통 응답 JSON을 확인한다.
python3 -m src.services.rag_qa_cli --mode bm25 --query "SSH를 활성화하려면?" --json

# corpus 변경 후 Chroma 색인을 생성·갱신한다.
python3 -m src.services.rag_qa_cli --action index
# 기존 collection을 명시적으로 삭제하고 전체 재색인한다.
python3 -m src.services.rag_qa_cli --action index --reset
```

### 명령별 역할

| 명령·옵션 | 역할 | 사용할 시점 |
| --- | --- | --- |
| `python3 -m src.services.rag_qa_cli --action index --reset` | `manifest.json` 청크를 E5 임베딩으로 변환해 Chroma DB에 전체 색인한다. 기존 collection은 삭제 후 새로 만든다. | 최초 실행, corpus·metadata 변경 후 |
| `--mode bm25` | 문서와 질문의 단어 일치를 기준으로 BM25만 검색한 뒤 QA 응답을 만든다. Chroma와 E5 모델이 없어도 된다. | 빠른 기본 검색 확인, Chroma 색인 전 |
| 기본 실행 또는 `--mode hybrid` | BM25 키워드 검색과 Chroma Dense 의미 검색을 RRF로 결합한 뒤 QA 응답을 만든다. | 실제 시연과 기본 QA 실행 |
| `--json` | 검색 방식은 바꾸지 않고, 콘솔용 출력 대신 공통 `ChatResponse` JSON을 출력한다. | Streamlit 연결, 자동 테스트, API 응답 확인 |

예를 들어 `SSH`처럼 문서와 같은 키워드가 있는 질문은 BM25도 잘 찾는다. 반면
`모니터 없이 처음 설정하고 싶어`처럼 문서 표현과 다른 자연어 질문은 Dense 검색이
의미를 보완하므로 Hybrid 방식이 더 적합하다.

로컬 기본값은 `ANSWER_GENERATOR=template`이며, 한국어 안내와 검색된 영문 공식 근거를
`[C1]` 인용과 함께 출력한다. RunPod Pod에서 Qwen3-4B Base Instruct를 직접 쓸 때는
`ANSWER_GENERATOR=huggingface`와 `--trace`를 지정한다. 원문 URL은 답변 모델이 만들지
않고 출처 카드에서 표시한다. 자세한 Pod 실행 절차는 [RunPod QA 안내](../../runpod/README.md)를
참고한다.

문서 파이프라인의 canonical manifest 1.1은 `collected_at`, `quality_status`,
`embedding_checksum`, 최상위 `processing` metadata를 사용한다. `src.rag.adapters`가
기존 RAG 모델의 `retrieved_at`으로만 호환 변환하며, `quality_status=approved`가 아닌
청크는 색인·검색·인용 대상에서 제외한다. 실제 검색 결과의 출처 카드에는 제목·절·공식 URL·
수집일·라이선스·문서 버전 metadata를 유지한다.

> [!IMPORTANT]
> 현재 이 패키지는 검색 동작을 검증하기 위한 프로토타입입니다. 필드명과 반환 형식의 기준은 기존 `RagResult` 구현이 아니라 `src/contracts/models.py`와 `docs/schemas/search-response.schema.json`입니다. 프로토타입을 서비스에 연결할 때는 공통 계약을 만족하도록 교체하거나 adapter를 구현해야 합니다.

이 패키지는 문서 수집·청킹, sLLM 조건 추출, 챗봇 UI에 의존하지 않는다. 문서·데이터 담당이 검수한 `manifest.json`을 입력으로 받아 E5/Chroma Dense 검색, BM25, RRF, metadata filter와 Hit@k·MRR 평가를 제공한다. 현재 추천 MVP corpus는 설치·원격 접속·카메라·GPIO·전원·NVMe·외장 저장장치·키보드형 컴퓨터 비교를 다룬다. 가격·재고·A/S·리콜은 corpus 범위 밖이므로 근거 부족으로 보류하며, 후속 공식 웹 검색 단계에서 처리한다.

## Manifest 1.1 입력 계약

RAG는 `schema_version: "1.1.0"`의 canonical manifest만 받는다. 최상위에는
`generated_at`, `source_registry`, `processing`, `chunks`가 있어야 하며, 청크는
`source_anchor`, `collected_at`, `embedding_checksum`, `quality_status`를 포함한
`docs/schemas/search-response.schema.json`의 정적 metadata 계약을 따라야 한다.

`official_verified=true`이고 `quality_status=approved`인 청크만 Chroma·BM25·인용 근거로
사용한다. 이전 1.0 manifest나 그로부터 만든 Chroma DB는 호환 대상으로 취급하지 않으며,
manifest 재생성 후 `--reset` 색인을 수행한다.

## Retriever 구현 단위 사용 방법

### `.env` 설정과 로컬 실행

프로젝트 최상위 `.env`에 아래 RAG 설정이 필요하다. 로컬 `PersistentClient`를
사용하므로 Chroma API 키는 필요 없다.

```env
DOCUMENT_MANIFEST=document_pipeline/data/manifest_v3.json
CHROMA_PATH=data/indexed/chroma_official_v3
CHROMA_COLLECTION_NAME=rpi_official
E5_MODEL_NAME=intfloat/multilingual-e5-base
TOP_K=5
# 현재 테스트 corpus 기준 초기값이며, 실제 Dev qrels로 재조정한다.
DENSE_MAX_DISTANCE=0.48
```

LLM까지 로컬에서 실행할 때는 공통 `INFERENCE_DEVICE`로 PyTorch 장치를 고른다.
`auto`는 CUDA → Apple Silicon MPS → CPU 순으로 선택하며, `cuda`, `mps`, `cpu`를
명시할 수도 있다. 4-bit BitsAndBytes는 CUDA 전용이므로 MPS·CPU에서는 자동 해제된다.
따라서 Mac에서는 아래처럼 설정하면 된다. Qwen3-4B 전체 모델을 MPS/CPU에 올리는 것은
가능하지만 CUDA 4-bit Pod보다 메모리를 더 쓰고 느릴 수 있다.

```env
INFERENCE_DEVICE=mps
ANSWER_GENERATOR=huggingface
ANSWER_LOAD_IN_4BIT=false
CONDITION_LOAD_IN_4BIT=false
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

retriever = HybridRetriever.from_manifest(
    "document_pipeline/data/manifest_v3.json",
    chroma_path="data/indexed/chroma_official_v3",
)
results = retriever.search(
    "모니터 없이 카메라를 연결하고 싶어요",
    RagFilters(
        product_models=("Raspberry Pi 5",),
        use_cases=("camera",),
        document_ids=("rpi-doc-camera-install",),
    ),
    top_k=5,
)

decision = retriever.search_with_decision("스마트팜을 작게 구현하고 싶어요")
if decision.status == "insufficient_evidence":
    print(decision.reason)
```

현재 반환값은 테스트용 `list[RagResult]`다. 실제 챗봇 연결 전에는 `SearchResponse` 계약으로 변환하고, 서버가 `citation_id`와 출처 metadata를 조합해야 한다.

Chroma 색인에는 `product_models`, `use_cases`, `os_versions`를 tag별 boolean metadata로
저장하고, `document_id`도 scalar metadata로 저장한다. Dense 검색은 해당 metadata와
선택적인 `document_ids`를 Chroma `where`에 먼저 적용하고, 반환 전에는 동일 조건을 다시
검사한다.

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
