# 받게 되는 파일: 제품 추천 카탈로그

`data/products/catalog.json`은 문서·데이터 담당이 Raspberry Pi 공식 자료에서 수집·정규화하고 팀이 추천 메타데이터를 검수한 뒤 전달한다. `data/`는 저장소 정책상 Git에서 제외되므로 실제 파일은 팀 내부 저장소나 RunPod volume로 공유한다. 이 브랜치는 크롤러나 전처리 결과를 만들지 않고 파일을 읽고 검증한다.

## 왜 `raspberry-pi.html` 한 페이지만으로 부족한가

컴퓨터 하드웨어 문서는 제품 계열, 메모리, 포트, GPIO, 네트워크를 비교하는 핵심 출발점이다. 그러나 실제 추천에는 아래 공식 페이지의 정보도 필요하다.

- 개별 제품 페이지: 현재 판매 변형, 메모리 선택지, 공식 구성품과 제품별 주의사항
- Getting started: 데스크톱·헤드리스 구성에 필요한 준비물
- Camera 문서: 보드별 커넥터와 케이블 차이
- 전원·USB 문서: 전원 요구량과 주변기기 전력 제한
- Compute Module 문서: 일반 사용자가 아니라 커스텀 baseboard를 쓰는 임베디드 용도 구분
- 라이선스 페이지: 온라인 문서, 제품 brief/PDF, 이미지의 서로 다른 이용 조건

MVP 범위에서는 다른 회사의 블로그나 쇼핑몰이 꼭 필요한 것은 아니다. 가격·실시간 재고·제3자 액세서리 호환성까지 추천하려면 별도 출처와 갱신 정책이 필요하지만, 현재 README는 이 범위를 명시적으로 제외한다.

## 최소 JSON 계약

```json
{
  "schema_version": "1.0.0",
  "catalog_version": "YYYY-MM-DD-or-commit",
  "generated_at": "2026-08-27T12:00:00+09:00",
  "sources": [
    {
      "document_id": "official-doc-001",
      "title": "Official source title",
      "source_url": "https://www.raspberrypi.com/documentation/...",
      "retrieved_at": "2026-08-27",
      "license": "CC BY-SA 4.0"
    }
  ],
  "products": [
    {
      "product_id": "stable-team-product-id",
      "name": "Official product name",
      "aliases": ["팀이 검수한 다른 표기"],
      "family": "flagship",
      "is_current": true,
      "memory_options_gb": [4, 8],
      "capabilities": {
        "wireless": true,
        "ethernet": true,
        "gpio_header": "populated",
        "camera_connector_count": 1,
        "display_output_count": 2,
        "built_in_keyboard": false
      },
      "display": {
        "cpu": "팀이 공식 문서에서 확인한 CPU 요약",
        "memory": "4 GB / 8 GB",
        "wireless": "Wi-Fi 지원",
        "dimensions": "공식 크기"
      },
      "recommendation_profile": {
        "performance_tier": "medium",
        "beginner_friendly": true,
        "recommended_use_cases": ["education_coding", "desktop_computing"],
        "recommended_tasks": ["desktop_programming", "os_installation"]
      },
      "required_accessories": ["팀이 공식 근거로 확인한 필수 구성품"],
      "caveats": ["팀이 공식 근거로 확인한 주의사항"],
      "document_ids": ["official-doc-001"],
      "product_url": "https://www.raspberrypi.com/products/example/",
      "image_url": null
    }
  ]
}
```

`performance_tier`, `recommended_use_cases`, `recommended_tasks`는 LLM 생성값이 아니라 팀이 공식 근거와 서비스 범위를 기준으로 검수한 추천 기준표다. 실시간 가격은 다루지 않는다.

## 전달 전 확인

- 모든 `document_id`가 `sources`에 존재하고 RAG metadata의 `document_id`와 같다.
- `retrieved_at`, `catalog_version`과 라이선스가 기록됐다.
- 단종 제품은 `is_current=false`다.
- `required_accessories`, `caveats`, 추천 태그에 검수 근거가 있다.
- 제품 이미지 URL은 온라인 문서와 같은 라이선스라고 가정하지 않고 UI용 별도 메타데이터에서 관리한다.
