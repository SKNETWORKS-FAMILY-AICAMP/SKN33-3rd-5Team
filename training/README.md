# 파인튜닝 모델 별도 저장

PiCare QLoRA는 원본 모델 전체 대신 **학습한 LoRA 어댑터**를 저장한다.
현재 base는 `Qwen/Qwen3-4B-Instruct-2507`이며 다시 사용할 때도 필요하다.
이는 Hugging Face의 [PEFT 저장 형식](https://huggingface.co/docs/peft/developer_guides/checkpoint)을 따른다.
`picare-qwen3-4b-qlora`새 모델 저장소에 보관한다.


## 학습 결과가 만들어지는 위치

검수된 `data/finetuning/train.jsonl`, `dev.jsonl`, `holdout.jsonl`을 받은 뒤
CUDA GPU에서 `train_qlora.py`를 실행해야 실제 학습 결과가 생긴다.
기본 저장 위치는 설정 파일의 `/workspace/models/picare-qwen3-4b-qlora`다.

- `adapter_model.safetensors`: 학습한 가중치
- `adapter_config.json`: 원본 모델과 LoRA 설정
- `tokenizer.json`, `tokenizer_config.json`, chat template 등: 입력·출력 처리
- `run_manifest.json`: 모델 revision, 학습 설정과 결과

이 폴더를 PC나 별도 저장 장치에 복사해 보관할 수도 있다. RunPod 저장소의 지속 여부는
volume 설정에 따라 달라지므로 Pod를 삭제하기 전에 외부 백업을 확인한다.
아래 Hub 백업은 추론용이며 optimizer·중간 checkpoint는 제외하므로 학습을 정확히
이어서 진행하려면 해당 checkpoint도 별도로 보관해야 한다.

## 이미 학습한 모델을 Hugging Face에 백업

프로젝트 루트에서 실행한다. 업로드 자체에는 GPU나 재학습이 필요 없다.
인증은 `hf auth login` 또는 RunPod 비밀 환경변수 `HF_TOKEN`을 사용한다.
토큰에는 대상 모델 저장소의 쓰기 권한이 필요하며 코드·YAML·Git에 넣지 않는다.

```bash
pip install "huggingface_hub>=0.34,<2"
hf auth login

# 먼저 올릴 파일 확인: 원격 접근이나 저장소 생성 없음
python training/publish_adapter.py \
  --adapter-path /workspace/models/picare-qwen3-4b-qlora \
  --repo-id t91004/picare-qwen3-4b-qlora --dry-run

# 실제 백업: 새 저장소는 비공개로 생성
python training/publish_adapter.py \
  --adapter-path /workspace/models/picare-qwen3-4b-qlora \
  --repo-id t91004/picare-qwen3-4b-qlora
```

완성된 Qwen3 어댑터 파일을 확인한 뒤 지정된 모델·토크나이저·manifest 파일과
`SHA256SUMS.txt`만 업로드한다. 학습 원문, `.env`, 토큰 파일, 로그, 중간 checkpoint는
업로드 대상에서 제외한다. 선택된 JSON·README 파일의 내용도 공유 전에 검토한다.
업로드 실패 시 로컬 파일은 그대로 남으며 같은 명령으로 재시도할 수 있다.

공개 공유가 필요할 때만 `--public`을 추가한다. 기본 모드에서는 이미 공개된 저장소에
업로드하지 않으며, 이 명령은 기존 저장소의 공개/비공개 설정을 변경하지 않는다.
동일 저장소에 다시 올리면 같은 이름의 파일이 새 commit으로 갱신된다. 다른 실험을
따로 보관하려면 저장소 이름을 구분한다. 이전 commit은 출력된 commit 링크로 확인한다.

## 학습이 끝나면 바로 백업

```bash
pip install -r training/requirements.txt
python training/train_qlora.py \
  --config training/configs/qwen3_4b_qlora.yaml \
  --hub-repo-id t91004/picare-qwen3-4b-qlora
```

학습과 로컬 저장에 성공한 뒤에만 비공개 Hub 백업을 실행한다. `--hub-repo-id`를
생략하면 기존처럼 로컬 저장만 한다. 공개 업로드는 `--hub-public`을 추가한다.
업로드만 실패했다면 위의 `publish_adapter.py`로 재시도하고 학습을 다시 돌리지 않는다.

## 다시 불러오기

추론 의존성과 GPU가 준비된 환경에서 로컬 폴더 대신 Hub 저장소 ID를 넘긴다.
비공개 저장소는 읽기 권한이 있는 계정으로 인증해야 한다.

```python
from src.condition_extraction.lora import LoraConditionExtractor

extractor = LoraConditionExtractor("t91004/picare-qwen3-4b-qlora")
```

추천 CLI에서도 `.env`에 `CONDITION_EXTRACTOR=lora`와
`LORA_ADAPTER_PATH=t91004/picare-qwen3-4b-qlora`를 설정할 수 있다.
로컬 폴더는 기존처럼 지정하며, 아직 없는 상대경로를 Hub ID로 해석하지 않으려면
`./models/adapter`처럼 `./`를 붙인다. 원격 모델 존재 여부·접근 권한은 실제 로드 시 확인한다.

이 어댑터는 **제품 추천용 조건 JSON 추출기**에 적용한다. RAG 질의응답 생성기는
별도로 base 모델을 사용하므로 이 어댑터를 연결하지 않는다.
