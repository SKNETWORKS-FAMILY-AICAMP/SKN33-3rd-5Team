# Raspberry Pi 공식 문서 v3 Document Card

## 개요

| 항목 | 값 |
| --- | --- |
| 용도 | Raspberry Pi 제품 추천과 공식 문서 QA의 검색 근거 |
| 기준일 | 2026-08-31 |
| source registry | `document_pipeline/data/source_registry_v3.csv` |
| 원문 버전 | raspberrypi/documentation commit `75331a79fbf32d2403b7547729ddccf553873b09` |
| 수집 대상 | include 18개, 제품 카드용 reference_only 8개 |
| 최종 manifest | 공식·승인 청크 270개, 문서 18개 |
| tokenizer | `intfloat/multilingual-e5-base` |
| 청킹 | 목표 360, 최대 460, overlap 60 tokens |
| pipeline | `document-pipeline-3.1.0`, `asciidoc-semantic-3.1.0` |
| guide media | 이미지 70개, 영상 1개; 72회 등장, 49개 청크 연결 |

## 출처와 권리

Raspberry Pi 공식 documentation 저장소와 공식 웹 문서만 본문 corpus에 포함한다.
registry에 공식 URL, 원문 경로, 라이선스와 수집 결정을 기록한다. 제품 페이지 8개는
최신 공식 URL 확인용 `reference_only`이며 본문을 복제·색인하지 않는다. 개인정보,
API key, 내부 문서와 사용자 대화는 포함하지 않는다.

## 처리와 품질 게이트

원문 checksum을 기록한 뒤 AsciiDoc 구조, 제목·목록·코드·표와 anchor를 보존해 파싱한다.
E5에 실제 전달되는 `passage: title + section + content`를 기준으로 청크 크기와
`embedding_checksum`을 계산한다. 정확 중복은 manifest 생성 전에 제거하고, 근접 중복은
0.90 기준으로 보고한다. `official_verified=true`, `quality_status=approved`인 청크만
manifest와 Chroma에 들어간다.

이미지·영상은 검색 청크와 임베딩에서 제외한다. 같은 수집 원문에서 별도 Media Linker가
문서·섹션 기준으로 `chunk_id ↔ media_id`를 연결한다. 이미지 70개는 모두 위 commit에
고정된 공식 documentation 저장소 URL이고, 영상 1개는 공식 문서에 선언된 YouTube 링크다.
AsciiDoc 주석과 TODO 안의 영상은 제외했으며, 두 섹션에서 반복된 이미지 1건은 동일
`media_id`로 중복 제거했다. 모든 미디어에는 license·attribution과 원문 commit이 있다.

2차 검증 결과는 다음과 같다.

- 승인 청크: 270개, 정확 중복: 0개, 근접 중복 쌍: 0개
- E5 입력 길이: 최소 40, 중앙값 202, p95 370, 최대 458 tokens; 460 초과 0개
- 검토 제외: 2개. Raspberry Pi 500+ 고급 키보드 명령 표에서 열 수가 맞지 않아
  `needs_review`로 분리했으며 MVP 5종의 핵심 사양·추천 근거에는 사용하지 않는다.
- catalog–manifest 제목·URL·라이선스·수집일 및 제품 태그 정합성: 통과
- 실제 E5 CPU 임베딩과 Chroma 색인: 승인 청크 270개 모두 완료
- media manifest JSON Schema, document manifest checksum, URL host/provider,
  chunk/document/section 참조 정합성: 통과
- BM25 → template 답변 → citation 검증 → Media Resolver → `ChatResponse.media`
  실제 통합: 인용된 Imager 청크의 공식 이미지 4개만 반환, 미인용 미디어 0개

## 제품 추천 근거 커버리지

| 제품 | 근거 필드 | 근거 문서 | 제품 태그 근거 청크 |
| --- | ---: | ---: | ---: |
| Raspberry Pi 5 | 16 | 7 | 81 |
| Raspberry Pi 4 Model B | 14 | 4 | 56 |
| Raspberry Pi 500 | 16 | 3 | 88 |
| Raspberry Pi 400 | 16 | 4 | 99 |
| Raspberry Pi Zero 2 W | 16 | 4 | 56 |

필드 수 차이는 값 누락이 아니라 `conditional_accessories`, `dimensions`, `caveats`처럼
제품에 따라 존재하지 않는 선택 필드 차이다. Wi-Fi, 카메라 커넥터 수, GPIO 헤더,
성능 등급, 추천 용도·작업은 전 제품에 필드별 근거가 있다.

## 검색·모델 연결 검증

`multilingual-e5-base`와 Chroma 1.x로 270개 청크를 색인했다. 제품별
`document_ids + product_models` 엄격 필터를 적용한 Hybrid 검색에서 5개 제품 모두
공식 근거를 반환했다. 일반 QA는 제품 태그가 없는 공통 문서를 허용하지만, 제품 추천은
선택 제품 태그가 없는 청크를 차단해 다른 제품 섹션이 섞이지 않게 한다.

실제 catalog → 추천 엔진 → E5/Chroma Hybrid 검색 → 인용 검증 → template 응답 통합은
로컬에서 `answered`까지 확인했다. Qwen3 답변 생성과 조건 추출 LoRA는 이 로컬 환경에
CUDA 및 학습 adapter가 없어 실제 가중치 추론을 실행하지 않았고, provider 계약·오류
처리·무단 제품 추가 차단은 자동 테스트로 검증했다. 배포 전 RunPod에서는
[`docs/guides/runpod-pod-setup.md`](../guides/runpod-pod-setup.md)의 LoRA·Qwen smoke test가 별도 승인 게이트다.

추천 시나리오 회귀 결과:

- 고성능 홈 서버: Raspberry Pi 5 → Raspberry Pi 4 Model B
- 카메라 모니터링: Raspberry Pi 5 → Raspberry Pi 4 Model B → Zero 2 W
- 저성능 우선 GPIO·IoT: Zero 2 W → Raspberry Pi 4 Model B → Raspberry Pi 5
- 입문자 데스크톱: Raspberry Pi 4 Model B와 Raspberry Pi 400이 공동 최고점

## 한계와 갱신

- 5개 MVP 제품만 다루며 Compute Module, Pico, Raspberry Pi 500+는 추천 대상이 아니다.
- 성능 등급과 추천 용도는 benchmark가 아니라 승인된 상대 정책이다.
- 가격, 지역별 재고, 실시간 판매 상태, 제3자 액세서리 호환성은 제공하지 않는다.
- 원문 commit, registry, 청킹 설정 또는 catalog 추천 정책이 바뀌면 manifest 생성,
  catalog 교차 검증, Chroma 재색인과 이 카드의 수치를 함께 갱신한다.

## 재현 명령

```bash
python -m document_pipeline.ingestion.run_pipeline \
  --commit 75331a79fbf32d2403b7547729ddccf553873b09 \
  --source-registry document_pipeline/data/source_registry_v3.csv \
  --raw-root document_pipeline/data/raw_v3 \
  --processed-root document_pipeline/data/processed_v3 \
  --manifest-path document_pipeline/data/manifest_v3.json \
  --media-manifest-path document_pipeline/data/media_manifest_v3.json

python -m src.recommendation.validate_catalog \
  --catalog data/products/catalog.json \
  --manifest document_pipeline/data/manifest_v3.json

python -m src.services.rag_qa_cli --action index --reset
```
