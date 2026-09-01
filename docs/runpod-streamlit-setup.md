# RunPod 설치부터 Streamlit 실행까지

이 문서는 PiCare를 **새 RunPod GPU Pod**에서 처음 설치하고, QLoRA 어댑터·RAG 인덱스를 준비한 뒤 로컬 브라우저에서 Streamlit을 확인하는 표준 절차다.

기준 브랜치는 `fix/dev`이며, 예시는 A40 + CUDA 12.8 드라이버와 Qwen3 4B를 사용한다. Pod의 IP 주소와 SSH 포트는 Pod를 다시 만들면 달라질 수 있으므로 RunPod 콘솔의 값으로 바꾼다.

## 전체 흐름

```text
Mac 로컬
  ├─ SSH로 RunPod 접속
  ├─ 학습 JSONL 전송(scp)
  └─ SSH 터널로 Streamlit 접속

RunPod Pod
  ├─ Git clone / fix/dev checkout
  ├─ Python venv + CUDA 12.8 의존성 설치
  ├─ 300/40/20 데이터 검사 → QLoRA 학습·평가
  ├─ (선택) LoRA 어댑터를 Hugging Face Hub에 업로드
  ├─ 공식 문서·미디어·Chroma를 run_pipeline으로 재생성
  └─ Streamlit 실행
```

> **터미널 구분이 중요하다.** `choejiheum@... %` 프롬프트는 Mac 로컬 터미널이고, `root@...:/#` 또는 `root@...:/workspace/...#`는 RunPod 터미널이다. `/workspace/...` 경로와 GPU 명령은 RunPod에서만 실행한다. `scp`의 원본 파일 경로는 Mac에서만 쓸 수 있다.

## 1. RunPod 접속과 프로젝트 준비

Mac 로컬 터미널에서 RunPod의 SSH 정보를 사용해 접속한다.

```bash
ssh -p <RUNPOD_SSH_PORT> root@<RUNPOD_IP>
```

RunPod 프롬프트가 나오면 프로젝트를 준비한다. 이미 clone한 Pod라면 `git clone`은 생략하고 `git pull`부터 실행한다.

```bash
cd /workspace
git clone https://github.com/skn-33-Raspberry-Pi-Assistant/skn_33_3rd_5team.git
cd /workspace/skn_33_3rd_5team
git checkout fix/dev
git pull
```

현재 위치와 브랜치는 항상 확인한다.

```bash
pwd
git branch --show-current
git status --short --branch
```

`git pull`은 반드시 저장소 안에서만 실행한다. `/`처럼 Git 저장소 밖에서 실행하면 실패한다.

## 2. 가상환경과 RunPod 의존성 설치

RunPod 전용 가상환경은 프로젝트 밖의 지속 경로에 만든다.

```bash
python3 -m venv /workspace/venvs/skn_33_3rd_5team
source /workspace/venvs/skn_33_3rd_5team/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements-training.txt
```

`python -m pip`은 활성화된 가상환경의 pip를 명시적으로 사용한다. `-r`은 requirements 파일을 읽는 옵션이며, 이미 설치되어 버전 조건을 만족하는 패키지는 재설치하지 않는다.

CUDA 빌드를 바꿨거나 설치가 깨졌을 때만 다음 강제 재설치를 사용한다. PyTorch와 CUDA 관련 대용량 파일을 다시 받으므로 평소에는 사용하지 않는다.

```bash
python -m pip install --force-reinstall -r requirements-training.txt
```

설치가 끝나면 아래 네 가지를 확인한다.

```bash
which python
python --version
python -m pip check
nvidia-smi

python -c "import torch; print('torch:', torch.__version__); print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else '없음')"
```

정상 기준은 `pip check`가 `No broken requirements found.`, `CUDA: True`, 그리고 GPU 이름(예: `NVIDIA A40`)이 출력되는 것이다.

## 3. 환경 변수와 Hugging Face 캐시 설정

프로젝트에 `.env`가 없다면 예시 파일에서 만든다. `.env`는 Git에 올리지 않는다.

```bash
cd /workspace/skn_33_3rd_5team
cp .env.example .env

grep -E '^(CHROMA_PATH|DOCUMENT_MANIFEST|MEDIA_MANIFEST|MEDIA_CHUNK_MAP)=' .env
```

v3 RAG 산출물은 다음과 같아야 한다.

```env
CHROMA_PATH=data/indexed/chroma_official_v3
DOCUMENT_MANIFEST=document_pipeline/data/manifest_v3.json
MEDIA_MANIFEST=document_pipeline/data/media_manifest_v3.json
MEDIA_CHUNK_MAP=document_pipeline/data/media_chunk_map_v3.json
```

모델 캐시가 Pod 디스크에 남도록 현재 셸에서 설정한다. 새 SSH 세션을 열면 다시 설정한다.

```bash
export HF_HOME=/workspace/.cache/huggingface
export HF_HUB_ENABLE_HF_TRANSFER=1
```

## 4. 파인튜닝 데이터 전달과 검사

학습 데이터는 `train.jsonl`, `dev.jsonl`, `holdout.jsonl` 세 파일이며, **Mac 로컬 터미널**에서 RunPod로 전송한다.

```bash
scp -P <RUNPOD_SSH_PORT> \
  /절대경로/train.jsonl \
  /절대경로/dev.jsonl \
  /절대경로/holdout.jsonl \
  root@<RUNPOD_IP>:/workspace/skn_33_3rd_5team/data/finetuning/
```

RunPod에서 수신 수량과 스키마·토큰 길이를 검사한다.

```bash
cd /workspace/skn_33_3rd_5team
source /workspace/venvs/skn_33_3rd_5team/bin/activate

wc -l data/finetuning/train.jsonl data/finetuning/dev.jsonl data/finetuning/holdout.jsonl
python training/train_qlora.py --validate-only --check-token-lengths
```

이번 검수 데이터의 기준 수량은 `300 / 40 / 20`이다. Holdout은 품질 비교만을 위해 보관하며 학습 파라미터 조정에 사용하지 않는다.

## 5. QLoRA 학습과 평가

학습은 RunPod GPU에서만 실행한다.

```bash
cd /workspace/skn_33_3rd_5team
source /workspace/venvs/skn_33_3rd_5team/bin/activate
export HF_HOME=/workspace/.cache/huggingface
export HF_HUB_ENABLE_HF_TRANSFER=1

python training/train_qlora.py --config training/configs/qwen3_4b_qlora.yaml
```

학습 완료 후 어댑터 위치와 실행 정보를 확인한다.

```bash
ls -lah /workspace/models/picare-qwen3-4b-qlora
python -c "import json; from pathlib import Path; m=json.loads(Path('/workspace/models/picare-qwen3-4b-qlora/run_manifest.json').read_text()); print(m['dataset_sizes']); print(m['train_metrics']); print(m['eval_metrics'])"
```

같은 Holdout으로 Base와 LoRA를 각각 평가한다.

```bash
python -m src.evaluation.extractor_eval \
  --mode baseline \
  --data data/finetuning/holdout.jsonl \
  --catalog data/products/catalog.json \
  --output artifacts/evaluation/baseline-300-40-20.json

python -m src.evaluation.extractor_eval \
  --mode lora \
  --adapter-path /workspace/models/picare-qwen3-4b-qlora \
  --data data/finetuning/holdout.jsonl \
  --catalog data/products/catalog.json \
  --output artifacts/evaluation/qlora-300-40-20.json
```

검증 기록: 300/40/20 Holdout에서 Base의 전체 Macro F1은 약 `0.7933`, LoRA는 약 `0.8627`이었다. 데이터가 20건이므로 수치를 과대해석하지 말고, 재현 가능한 고정 Holdout 비교 결과로 기록한다.

## 6. LoRA 어댑터를 Hugging Face Hub에서 사용하기

`/workspace/models/picare-qwen3-4b-qlora`에는 전체 Qwen 모델이 아닌 LoRA 차분 가중치와 토크나이저가 있다. 다른 환경에서는 **베이스 Qwen 모델 + Hub 어댑터**를 결합해 실행한다.

먼저 업로드 파일을 확인한다.

```bash
python training/publish_adapter.py \
  --adapter-path /workspace/models/picare-qwen3-4b-qlora \
  --repo-id ajjarago/picare-qwen3-4b-qlora \
  --public \
  --dry-run
```

인증 계정을 확인하고 실제 업로드한다. 공개 저장소는 추론 환경에서 인증이 필요 없다.

```bash
hf auth whoami

python training/publish_adapter.py \
  --adapter-path /workspace/models/picare-qwen3-4b-qlora \
  --repo-id ajjarago/picare-qwen3-4b-qlora \
  --public
```

실행 환경의 `.env`에서는 로컬 경로 대신 Hub ID를 사용한다.

```env
CONDITION_EXTRACTOR=lora
CONDITION_MODEL_ID=Qwen/Qwen3-4B-Instruct-2507
LORA_ADAPTER_PATH=ajjarago/picare-qwen3-4b-qlora
CONDITION_LOAD_IN_4BIT=true
```

첫 제품 추천 요청 시 베이스 Qwen과 어댑터가 캐시에 없으면 다운로드된다. 이후에는 `HF_HOME`의 캐시를 재사용한다. 이 LoRA는 **제품 추천 조건 추출기**용이며, RAG QA 답변 모델을 대체하지 않는다.

## 7. v3 RAG·미디어·Chroma 통합 파이프라인

`run_pipeline` 한 번으로 문서 수집·청킹, 미디어 manifest, 미디어-청크 연결, Chroma 전체 재색인을 수행한다. 별도로 `media.linker`나 `rag_qa_cli --action index`를 실행할 필요가 없다.

```bash
cd /workspace/skn_33_3rd_5team
source /workspace/venvs/skn_33_3rd_5team/bin/activate
export HF_HOME=/workspace/.cache/huggingface
export HF_HUB_ENABLE_HF_TRANSFER=1

python -m document_pipeline.ingestion.run_pipeline
```

성공 출력에는 아래 정보가 포함된다.

```text
documents: <문서 수>
chunks: <청크 수>
media: <미디어 수>
media links: <연결 수>
unmatched media: <미연결 수>
media chunk map: .../media_chunk_map_v3.json
indexed chunks: <색인 청크 수>
```

이번 실행 예시는 `documents: 18`, `chunks: 270`, `media: 71`, `media links: 13`, `unmatched media: 5`, `indexed chunks: 270`이었다. `unmatched media`가 0이 아니어도 파이프라인 실패는 아니며, 검수 대상 미디어가 실제 인용 청크에 연결되지 않았다는 뜻이다.

## 8. Streamlit 실행과 Mac SSH 터널

### RunPod: 앱 서버 실행

RunPod 터미널 하나에서 앱을 실행하고 **이 터미널은 유지**한다. SSH 터널을 쓸 때는 외부에 포트를 공개할 필요 없이 `127.0.0.1`에만 바인딩한다.

```bash
cd /workspace/skn_33_3rd_5team
source /workspace/venvs/skn_33_3rd_5team/bin/activate
export HF_HOME=/workspace/.cache/huggingface
export HF_HUB_ENABLE_HF_TRANSFER=1

python -m streamlit run streamlit_app/app.py \
  --server.address 127.0.0.1 \
  --server.port 8501
```

`Uvicorn server started on 127.0.0.1:8501`과 `URL: http://127.0.0.1:8501`가 나오면 정상이다.

### Mac: 터널 열기

별도의 **Mac 로컬 터미널**에서 아래를 실행하고, 이 터미널도 열어 둔다.

```bash
ssh -N -L 8501:127.0.0.1:8501 -p <RUNPOD_SSH_PORT> root@<RUNPOD_IP>
```

`-N`은 원격 셸을 열지 않고 포트 연결만 만든다. 따라서 아무 출력 없이 멈춘 것처럼 보이는 것이 정상이다. 브라우저에서는 다음 주소로 접속한다.

```text
http://127.0.0.1:8501
```

### 화면 수용 테스트

1. QA 탭에서 `SSH를 활성화하려면?`을 입력한다.
2. 답변, 공식 출처, 인용 기반 미디어 카드가 표시되는지 확인한다.
3. 추천 탭에서 `모니터 없이 홈 서버로 사용하고 싶어요`를 입력한다.
4. 조건 추출, 제품 후보, 공식 인용이 표시되는지 확인한다.

처음 추천 요청은 베이스 모델·LoRA 로드로 시간이 걸릴 수 있다. 같은 Streamlit 프로세스에서의 다음 요청은 캐시를 사용한다.

## 9. 오류 대응표

| 증상 | 원인 | 대응 |
| --- | --- | --- |
| `zsh: command not found: pip` | Mac 로컬 셸이거나 가상환경 미활성화 | RunPod에서 venv를 활성화한 뒤 `python -m pip ...` 사용 |
| `/workspace/.../python: no such file or directory` | `/workspace`는 Mac에 없는 RunPod 경로 | SSH로 RunPod에 접속해 실행 |
| `fatal: not a git repository` | `/` 등 저장소 밖에서 `git pull` 실행 | `cd /workspace/skn_33_3rd_5team` 후 재시도 |
| CUDA 초기화 경고, `CUDA: False` | 드라이버보다 새 CUDA wheel(예: cu130)을 설치 | venv에서 `requirements-training.txt`의 cu128 wheel로 설치 후 CUDA 재확인 |
| `pip check`가 `fsspec` 또는 `transformers` 충돌을 보고 | 개별 최신 버전 설치로 상한 조건 위반 | `python -m pip install -r requirements-training.txt` 후 `python -m pip check` 실행 |
| `HF_HUB_ENABLE_HF_TRANSFER=1`인데 `No module named hf_transfer` | 고속 다운로드 옵션의 선택 의존성이 없음 | `python -m pip install hf_transfer` 또는 환경 변수를 해제 |
| `받게 되는 학습 파일이 없습니다` | `data/finetuning/`에 JSONL이 없음 | Mac 로컬에서 `scp`로 세 파일을 전송하고 `ls -lah data/finetuning` 확인 |
| `schema_version`이 `1.0.0`, 기대값은 `1.1.0` | 전달 데이터 계약과 코드 계약이 다름 | 먼저 팀 계약·데이터 버전을 확인한다. 계약상 1.1.0이 맞고 백업을 만든 경우에만 세 파일을 변경한 뒤 다시 검증한다. 임의로 1.2.0으로 올리지 않는다. |
| `rg: command not found` | 최소 RunPod 이미지에 ripgrep이 없음 | `grep -RIn` 또는 `grep -n` 사용 |
| Qwen 파일이 다시 다운로드됨 | Pod의 `HF_HOME` 캐시가 비었거나 새 Pod/새 경로를 사용 | `export HF_HOME=/workspace/.cache/huggingface`를 설정하고 첫 다운로드가 끝날 때까지 기다림 |
| Hub에 올린 LoRA가 있는데도 Qwen 4B를 다운로드함 | Hub 저장소는 66MB 어댑터이고 베이스 모델은 별도 | 정상 동작이다. 베이스 Qwen과 LoRA 둘 다 한 번은 필요하며 이후 캐시 재사용 |
| `channel 2: open failed: connect failed: Connection refused` | SSH 터널은 열렸지만 RunPod 8501에 Streamlit이 없음 | RunPod에서 Streamlit 실행 터미널이 살아 있는지 확인하고 재실행 |
| 브라우저에서 RunPod 외부 IP `:8501`이 timeout | Pod 외부 포트가 공개되지 않았거나 방화벽이 차단 | 외부 IP 대신 SSH 터널 후 `http://127.0.0.1:8501` 사용 |
| 터널 뒤에도 `ERR_CONNECTION_RESET` | 원격 Streamlit 프로세스가 종료됐거나 다른 네임스페이스에서 실행 | Mac에서 `ssh -p <PORT> root@<IP> 'curl -I http://127.0.0.1:8501'`로 확인. 실패하면 RunPod에서 Streamlit 재실행 |
| `.env: No such file or directory` | 새 clone에는 비밀 환경 파일이 포함되지 않음 | `cp .env.example .env` 후 경로·설정값 검토 |
| Hub 어댑터를 로드하지 못함 | `LORA_ADAPTER_PATH`가 로컬 경로이거나 잘못된 Hub ID | `LORA_ADAPTER_PATH=ajjarago/picare-qwen3-4b-qlora`로 설정하고 Streamlit 재시작 |

## 10. 종료 전 체크리스트

- [ ] `python -m pip check`가 통과한다.
- [ ] `torch.cuda.is_available()`가 `True`다.
- [ ] 300/40/20 데이터 검증과 토큰 길이 검사가 통과한다.
- [ ] QLoRA 어댑터와 `run_manifest.json`이 `/workspace/models/picare-qwen3-4b-qlora`에 있다.
- [ ] Base·LoRA Holdout 평가 결과가 `artifacts/evaluation/`에 저장됐다.
- [ ] 필요 시 Hub 어댑터 `ajjarago/picare-qwen3-4b-qlora`가 접근 가능하다.
- [ ] `run_pipeline`이 v3 manifest·media map·Chroma 청크를 생성했다.
- [ ] Streamlit QA와 추천 화면이 SSH 터널을 통해 정상 표시된다.
- [ ] Pod를 중지하거나 삭제하기 전에 Hub 업로드·Git push·필요한 산출물 백업을 확인했다.

