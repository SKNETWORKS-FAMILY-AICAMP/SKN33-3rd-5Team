# RunPod Pod: Qwen3-4B RAG QA 실행

이 문서는 HTTP endpoint나 vLLM 없이 RunPod Pod 안에서 RAG와 Qwen3-4B Base
Instruct를 같은 Python 프로세스로 실행하는 절차다. 조건 JSON 추출용 LoRA adapter는
QA 답변 생성에 사용하지 않는다.

## Pod 준비

1. CUDA PyTorch가 포함된 RunPod Pod와 24GB 이상 GPU를 선택한다.
2. 프로젝트와 실제 corpus/manifest를 `/workspace/skn_33_3rd_5team`에 둔다.
   `data/`는 Git에 포함되지 않을 수 있으므로 volume 또는 팀 공유 저장소에서 별도로
   복사한다.
3. Hugging Face 모델 cache는 Pod 종료 후에도 유지되도록 `/workspace`에 둔다.

```bash
cd /workspace/skn_33_3rd_5team
pip install -r requirements.txt -r runpod/requirements.txt
export HF_HOME=/workspace/.cache/huggingface
```

모델 접근 권한이 필요한 경우에만 `HF_TOKEN`을 Pod의 비밀 환경변수로 설정한다. API
Key, token, corpus 원문은 Git과 프로젝트 `.env.example`에 넣지 않는다.

## 설정과 실행

Pod의 프로젝트 최상위 `.env`에는 RAG 경로와 아래 생성기 설정을 둔다.

```env
ANSWER_GENERATOR=huggingface
ANSWER_MODEL_ID=Qwen/Qwen3-4B-Instruct-2507
ANSWER_MODEL_REVISION=main
ANSWER_LOAD_IN_4BIT=true
ANSWER_MAX_NEW_TOKENS=512
```

실제 corpus가 준비된 뒤 Chroma를 색인하고 QA를 실행한다.

```bash
python3 -m src.services.rag_qa_cli --action index --reset
python3 -m src.services.rag_qa_cli \
  --query "SSH를 활성화하려면?" \
  --trace
```

`--trace` 출력에는 검색 근거 수, `huggingface` provider, Qwen 모델명, 생성 시간,
인용 검증 결과가 표시된다. 근거 부족·가격·재고·프롬프트 인젝션 요청은 Qwen을 로드하거나
호출하지 않고 기존 보류·차단 정책을 따른다.
