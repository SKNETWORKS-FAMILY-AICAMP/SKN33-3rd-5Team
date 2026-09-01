# LLM 담당자 전달 문서: RAG QA 답변 생성 연결

## 1. 목적과 현재 상태

이 문서는 공식 Raspberry Pi 문서를 검색한 뒤 Qwen이 근거 기반 한국어 답변을 생성하도록
LLM 담당자와 RAG 담당자가 연결하는 기준이다.

```text
사용자 질문
  → Hybrid RAG 검색 (BM25 + Chroma Dense + RRF)
  → 공식 문서 근거 청크
  → Qwen 답변 생성
  → [C1] 인용 검증 (실패 시 형식 수정 1회)
  → Media Resolver(chunk_id ↔ media_id)
  → ChatResponse + 출처 카드 + 관련 이미지·영상
```

RAG 검색, 근거 부족 보류, 인용 검증, CLI는 구현되어 있다. 현재 로컬 기본값은 실제
모델 대신 `EvidenceTemplateGenerator`를 사용하며, RunPod Pod에서는 Qwen3-4B Base
Instruct를 직접 실행하도록 준비되어 있다.

## 2. 역할 분리

| 영역 | 담당 | 역할 |
| --- | --- | --- |
| `src/rag` | RAG 담당 | 공식 문서 Hybrid 검색, Chroma, BM25, RRF, 근거 부족 보류 |
| `src/rag_to_llm` | RAG·LLM 연결 | 검색 근거를 생성 모델에 전달하고 실행 정보를 반환 |
| `src/services/rag_qa_service.py` | 통합 계층 | 검색 → 생성 → 인용 검증·형식 수정 1회 → `ChatResponse` 조합 |
| `src/media/resolver.py` | 미디어 계층 | 최종 citation의 `chunk_id`에 연결된 공식 미디어만 조합 |
| 조건 JSON QLoRA | LLM 담당 | 제품 추천용 사용자 조건 추출 |
| Qwen Base Instruct | LLM 담당 | 공식 근거 기반 한국어 QA 답변 생성 |

조건 JSON 추출용 QLoRA Adapter는 QA 답변 생성에 사용하지 않는다. 해당 adapter는 JSON
출력에 최적화되어 있으므로, QA에는 `Qwen/Qwen3-4B-Instruct-2507` Base Instruct를 쓴다.

## 3. 생성기 인터페이스

LLM 생성기는 아래 계약을 구현한다.

```python
generate(messages, evidence) -> GenerationResult
```

반환 형식은 다음과 같다.

```python
GenerationResult(
    text="한국어 답변입니다. [C1]",
    provider="huggingface",
    model_id="Qwen/Qwen3-4B-Instruct-2507",
    elapsed_ms=1234.5,
)
```

`messages`에는 기존 안전 프롬프트와 사용자 질문, `[C1]` 형식의 공식 근거가 포함된다.
답변 본문에는 허용된 인용 ID만 사용해야 하며 URL, 별도 출처 목록, 추측을 넣으면 안 된다.
URL과 출처 카드는 모델이 아니라 서버가 RAG metadata로 조합한다.

Hugging Face Qwen의 첫 출력이 인용 검증에만 실패하면, 서버는 첫 출력을 비신뢰 데이터로
감싸고 같은 공식 근거·허용 citation ID만 제공하는 형식 수정 프롬프트를 **한 번** 호출한다.
수정 출력도 URL·가짜 인용·인용 없는 문단 검증을 통과해야 한다. 두 번째 실패 시 template
fallback이나 실패 원문 노출 없이 `error`로 보류한다.

현재 Qwen 구현 위치는 아래다.

- `src/rag_to_llm/answer_generator.py`: `HuggingFaceAnswerGenerator`
- `src/rag_to_llm/settings.py`: 환경 변수 설정
- `src/services/rag_qa_service.py`: 생성 결과·인용 검증 연결

Qwen 모델은 생성 요청 시점에만 lazy loading한다. 따라서 가격·재고·프롬프트 인젝션
차단과 `insufficient_evidence` 보류 상황에서는 GPU 모델을 로드하거나 호출하지 않는다.

## 4. RunPod Pod 실행

vLLM이나 HTTP endpoint는 사용하지 않는다. RunPod Pod 안에서 RAG와 Qwen을 같은
Python 프로세스로 실행한다. CUDA PyTorch가 포함된 이미지와 24GB 이상 GPU를 사용한다.

프로젝트, 실제 corpus/manifest, Chroma DB는 `/workspace` 영속 볼륨에 둔다. `data/`는
Git에 포함되지 않을 수 있으므로 팀 공유 저장소나 volume에서 별도로 준비한다.

```bash
cd /workspace/skn_33_3rd_5team
pip install -r requirements-gpu.txt
export HF_HOME=/workspace/.cache/huggingface
```

Pod의 프로젝트 최상위 `.env`에 다음 값을 설정한다.

```env
ANSWER_GENERATOR=huggingface
ANSWER_MODEL_ID=Qwen/Qwen3-4B-Instruct-2507
ANSWER_MODEL_REVISION=main
ANSWER_LOAD_IN_4BIT=true
ANSWER_MAX_NEW_TOKENS=512
```

모델 접근 권한이 필요한 경우 `HF_TOKEN`은 Pod의 비밀 환경변수로만 설정한다. RunPod
API Key, token, corpus 원문은 Git이나 `.env.example`에 저장하지 않는다.

실행 순서는 다음과 같다.

```bash
python3 -m src.rag.indexer --reset
python3 -m src.services.rag_qa_cli --mode hybrid --query "SSH를 활성화하려면?" --trace
```

## 5. 검증 기준

정상 QA 응답은 한국어 답변, 최소 하나의 `[C1]` 인용, 해당 `ChatCitation` 출처 카드를
가져야 한다. `--trace` 실행 시 아래 정보가 출력돼야 한다.

```text
trace.evidence_chunks=...
trace.generator=huggingface
trace.model_id=Qwen/Qwen3-4B-Instruct-2507
trace.generation_elapsed_ms=...
trace.generation_attempts=1
trace.citation_repair=not_needed
trace.citation_validation=passed
```

아래 상황은 Qwen을 호출하지 않거나 답변을 차단해야 한다.

| 입력 상황 | 기대 상태 |
| --- | --- |
| corpus에 근거가 없는 스마트팜 배선 질문 | `insufficient_evidence` |
| 실시간 가격·재고 질문 | `out_of_scope` |
| 프롬프트 인젝션 요청 | `safety_blocked` |
| URL·가짜 인용·인용 없는 문단이 포함된 모델 답변 | 형식 수정 1회 후에도 실패하면 `error` |
| CUDA·모델 로드 실패 | `error`, 템플릿 자동 대체 없음 |

## 6. LLM 담당자 확인 항목

1. RunPod CUDA Pod에서 Qwen3-4B Base Instruct가 4-bit로 로드되는지 확인한다.
2. SSH·OS 설치 같은 공식 문서 질문에 한국어 답변과 `[C1]` 인용이 생성되는지 확인한다.
3. `--trace`의 모델명·생성 시간·인용 검증 결과를 공유한다.
4. 모델 출력이 인용 검증에 실패한 경우, 출력 예시와 오류 원인을 RAG 담당자에게 공유한다.
5. [LLM 답변 품질 평가](llm-answer-evaluation.md)에 따라 Faithfulness, Answer Relevancy,
   Citation Precision, 근거 부족 보류 정확도, 한국어·명령어 원문 보존을 평가한다.
   인용 형식 통과를 의미상 Citation Precision 통과로 보고하지 않는다.

검색 결과가 있어도 모델이 `[INSUFFICIENT_EVIDENCE]` 한 줄만 반환하면 서비스가 정상 보류 상태로 변환한다.
한국어 설명이 전혀 없는 QA·추천 생성 결과는 차단하며, 자연스러운 한국어와 의미 정확성은 별도 검수한다.

로컬에서는 `ANSWER_GENERATOR=template`을 사용한다. 실제 Qwen 생성은 CUDA GPU가 있는
RunPod Pod에서만 실행한다.
