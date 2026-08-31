# 제품 추천 카탈로그 계약

[`data/products/catalog.json`](../../data/products/catalog.json)은 공식 문서의 제품 사실과
팀이 승인한 추천 정책을 묶은 실행용 카탈로그다. 원문 corpus와 달리 팀이 만든 정규화
사실 데이터이므로 Git에 커밋한다. 생성된 `manifest_v3.json`, 원문, 정제본과 Chroma
색인은 재현 가능한 산출물이므로 Git에서 제외한다. 기존 제품 ID와 근거 문서 ID를
유지하며 검수·수정하고, 학습 JSONL은 별도 공유한다.

## 작업 순서

1. `source_registry_v3.csv`에서 안정적인 `document_id`, 공식 URL, 라이선스,
   수집 여부와 제품 태그를 먼저 확정한다.
2. registry로 원문을 수집·파싱하고 품질 게이트, 정확 중복 제거와 근접 중복 검사를
   거쳐 `manifest_v3.json`을 생성한다.
3. 검수자가 공식 사양과 서비스 범위를 제품별 catalog v1.2에 기록한다. 모든 사실과
   추천 기준에는 registry와 manifest에 존재하는 `document_id`를 필드별로 연결한다.
4. catalog–manifest 교차 검증을 통과시킨 뒤 E5/Chroma를 재색인한다.
5. 실제 추천 시 서버가 후보를 먼저 확정하고, 후보의 `document_ids` 및 엄격한 제품
   태그로 Hybrid RAG 범위를 제한한다.

즉 메타데이터의 식별자와 출처 대장을 먼저 안정화해야 하지만, catalog를 만들기 위해
전체 임베딩까지 기다릴 필요는 없다. 최종 배포 조건은 생성된 manifest와 catalog의
자동 교차 검증 통과다.

## v1.2 핵심 계약

- `schema_version`: `1.2.0`
- `recommendation_policy`: 추천 등급·용도 기준의 검수 ID, 승인일, 상태와 범위
- `capabilities`: Wi-Fi, Ethernet, GPIO 헤더 상태, 카메라·디스플레이 커넥터 수,
  내장 키보드 여부
- `recommendation_profile`: 상대 성능 등급, 입문자 친화성, 승인 추천 용도·작업
- `required_accessories`: 사용 목적과 무관하게 기본 동작에 필요한 준비물
- `conditional_accessories`: 냉각·GPIO 납땜처럼 특정 조건에서만 필요한 준비물
- `evidence_by_field`: 사양뿐 아니라 `performance_tier`, `beginner_friendly`,
  `recommended_use_cases`, `recommended_tasks` 각각의 공식 근거 `document_id`
- `document_ids`: `evidence_by_field` 전체의 정렬된 중복 제거 합집합

`performance_tier`와 추천 태그는 공식 문서의 문장을 그대로 옮긴 값이 아니다. 공식
CPU·메모리·연결 사양을 근거로 서비스 범위 안에서 비교하도록 사람이 승인한 정책값이다.
따라서 `recommendation_policy.review_status=approved`가 아니면 v1.2 catalog는 로드되지
않는다. 가격·재고·제3자 액세서리 호환성은 현재 범위에 포함하지 않는다.

## 자동 검증

```bash
python -m src.recommendation.validate_catalog \
  --catalog data/products/catalog.json \
  --manifest document_pipeline/data/manifest_v3.json
```

검증기는 다음 오류를 배포 전에 차단한다.

- 제품 ID·공식명·별칭 충돌과 목록 중복
- 필수 사양·추천 기준의 필드별 근거 누락
- `document_ids` 합집합 불일치 또는 알 수 없는 문서 참조
- catalog와 manifest의 제목·URL·라이선스·수집일 불일치
- 비공식·미승인 또는 임베딩 checksum이 없는 근거 청크
- 해당 제품 태그가 하나도 없는 근거 문서

2026-08-31 검증 기준은 제품 5종, catalog source 8개, manifest 공식 문서 18개,
승인 청크 270개다. 자세한 처리·품질·제품별 근거량은
[`Raspberry Pi 공식 문서 v3 Document Card`](../document-cards/raspberry-pi-official-v3.md)에
기록한다.

## 공식 출처가 여러 개인 이유

하드웨어 소개 문서만으로 CPU·메모리·네트워크·포트 비교는 가능하지만, 추천에는
카메라 케이블 차이, 전원 요구량, 키보드 컴퓨터 구성, GPIO 헤더 상태와 냉각 조건도
필요하다. 그래서 제품 사양, 카메라 설치, 전원, 시작하기, 주파수·냉각 문서를 함께
사용하며 각 제품은 실제 사용한 근거만 `document_ids`로 제한한다.

## 변경 규칙

- 사양 또는 추천 정책 변경 시 `catalog_version`과 `generated_at`을 갱신한다.
- 추천 등급·용도를 바꾸면 `recommendation_policy`도 다시 검수한다.
- registry의 `document_id`를 바꾸면 manifest와 catalog를 같은 변경에서 재생성·검증한다.
- corpus 변경 후에는 Chroma를 재색인하고 `picare-index.json`의 manifest checksum과
  색인 청크 수를 확인한다.

실행 환경에서는 catalog와 manifest를 같은 검수 버전으로 배치하고, catalog의 필드 근거
문서만 `document_ids` 검색 필터로 전달한다. 파일별 전달 방법은
[팀 데이터 인수인계](team-handoff.md)를 참고한다.
