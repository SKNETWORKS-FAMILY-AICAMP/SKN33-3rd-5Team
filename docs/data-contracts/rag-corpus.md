# 받게 되는 파일: 공식 문서 RAG corpus

> 아래는 초기 프로토타입의 최소 형식을 기록한 문서다. 현재 팀 전달 파일은
> `document_pipeline/data/manifest_v3.json`이며, 반드시
> [canonical manifest 계약](../../document_pipeline/contracts/manifest-contract.md)과
> [기계 검증 스키마](../../document_pipeline/contracts/manifest.schema.json)를 따른다.
> 신규 파일에는 `retrieved_at` 대신 `collected_at`을 사용한다. 현재 청킹 기본값은
> E5 토크나이저 목표 360 / 최대 460 tokens이며, 아래의 250~700 단어 지침을 적용하지 않는다.
> 실제 전달 목록·검증 명령은 [팀 데이터 인수인계](team-handoff.md)에 정리되어 있다.

`data/corpora/<corpus_id>/manifest.json`은 문서·데이터 담당이 공식 원문을
수집·정제·청킹·검수한 뒤 RAG 담당에게 전달하는 파일이다. RAG는 이 파일을
직접 수집하거나 재청킹하지 않고, `official_verified=true`인 청크만 BM25와
Chroma에 색인한다.

`data/`는 저장소 정책상 Git에서 제외한다. 따라서 이 문서는 전달 계약을
고정하고, 실제 corpus는 팀 내부 저장소 또는 RunPod volume에서 공유한다.

## 이전 프로토타입 manifest 계약 — 신규 전달에 사용하지 않음

현재 `src/rag/models.py`의 `DocumentChunk`가 읽는 형식이다. 각 청크는 하나의
제목·소제목 안에서 의미가 완결되어야 하며, 다른 문서의 정보를 임의로 합치지
않는다.

```json
{
  "chunks": [
    {
      "chunk_id": "computers-raspberry-pi-5-spec-001",
      "document_id": "computers-raspberry-pi",
      "title": "Raspberry Pi computer hardware",
      "section": "Raspberry Pi 5",
      "content": "Official-document text for one self-contained fact.",
      "source_url": "https://www.raspberrypi.com/documentation/computers/raspberry-pi.html",
      "retrieved_at": "2026-08-28",
      "document_version": "git:<short-commit>",
      "license": "CC BY-SA 4.0",
      "product_models": ["Raspberry Pi 5"],
      "use_cases": ["home_server", "camera_monitoring"],
      "os_versions": ["Raspberry Pi OS"],
      "source_type": "documentation",
      "official_verified": true
    }
  ]
}
```

## 필드 규칙

| 필드 | 규칙 |
| --- | --- |
| `chunk_id` | corpus 내에서 불변·고유한 ID. 본문 수정 시에도 ID를 유지하면 Chroma upsert가 갱신한다. |
| `document_id` | 동일 원문 문서의 청크가 공유하는 안정 ID. 제품 카탈로그의 `sources[].document_id`와 맞춘다. |
| `title`, `section` | 공식 페이지의 문서 제목과 소제목. UI 출처 카드에도 그대로 노출한다. |
| `content` | 검색과 LLM 근거에 쓰는 정제 원문. 링크·이미지 문법·내비게이션은 제거하되, 명령어·단위·주의사항은 보존한다. |
| `source_url` | 사용자가 열 수 있는 공식 웹 URL. Git raw URL만 넣지 않는다. |
| `retrieved_at`, `document_version` | 수집 날짜와 Git commit 또는 공식 문서 버전. 최신성 확인과 재수집 판단에 사용한다. |
| `license` | 원문에서 확인한 라이선스. 문서·제품 PDF·이미지 라이선스를 하나로 가정하지 않는다. |
| `product_models` | 공식 명칭을 그대로 쓴다. 예: `Raspberry Pi 5`, `Raspberry Pi 4 Model B`. 공통 문서는 빈 배열이다. |
| `use_cases` | 서비스의 검색 라우팅 태그다. `condition.schema.json`의 `use_case` enum과 같은 값만 쓴다. 태그는 추천 결론이 아니라 관련 문서를 좁히기 위한 검수 값이다. |
| `os_versions` | 특정 OS에만 적용될 때만 기록한다. 공통 하드웨어 문서는 빈 배열이다. |
| `source_type` | 현재는 `documentation`, 제품 페이지는 `product_page`, 지원 공지는 `support_notice` 또는 `recall_notice`를 사용한다. |
| `official_verified` | 공식 Raspberry Pi 원문과 URL·라이선스·정제 내용을 검수한 경우에만 `true`다. |

## 이미지·영상 연결

이미지와 영상은 별도 청크로 만들거나 임베딩하지 않는다. 파서가 공식 AsciiDoc의
미디어 매크로를 구조적으로 보존한 뒤 Media Linker가 문서·섹션이 같은 승인 청크에
`media_id`를 연결해 `document_pipeline/data/media_manifest_vN.json`을 생성한다.
런타임 Media Resolver는 LLM 인용 검증 후 최종 citation에 남은 `chunk_id`만 조회한다.
제품 카드 이미지는 이 경로가 아니라 `data/products/catalog.json`의 `image_url`을 쓴다.
세부 계약은 [`media-manifest-contract.md`](../../document_pipeline/contracts/media-manifest-contract.md)를
기준으로 한다.

## 청킹 기준

- 기본 크기는 영어 기준 약 250~700 단어를 목표로 하되, 설치 절차·표 한 행처럼
  의미가 완결되는 단위는 더 짧아도 분리한다.
- 한 청크에는 한 제품 또는 한 설정 주제만 둔다. 예를 들어 Pi 4와 Pi 5의 사양은
  각각 청크를 만들고, 비교 답변은 검색 결과를 조합해 생성한다.
- `WARNING`, 전력 조건, 호환 불가, 단종·리콜은 앞뒤 문맥이 분리되지 않도록
  같은 청크에 보존한다.
- 공식 문서가 특정 용도를 “추천”하지 않았다면 청크 본문에 팀의 추천 문장을
  추가하지 않는다. 추천 기준은 별도 `data/products/catalog.json`의 검수된
  `recommendation_profile`에서 관리한다.

## 서비스 통합 시 보강할 metadata

현재 RAG 프로토타입은 위의 최소 필드만 읽는다. 챗봇 통합 전에는
`docs/schemas/search-response.schema.json`에 맞춰 아래 값을 원문 manifest 또는
adapter에서 추가한다.

- `publisher`: `Raspberry Pi`
- `source_anchor`, `chunk_index`, `language`
- `published_at`, `updated_at`, `collected_at`, `indexed_at`
- 서버가 부여하는 `citation_id`

이 보강은 `DocumentChunk` 최소 계약을 깨지 않도록 adapter에서 수행한다. RAG가
LLM에게 전달하는 `content`와 출처 UI의 URL·라이선스·날짜는 같은 청크 metadata에서
나와야 한다.

## 평가 세트

각 corpus는 선택적으로 `dev_queries.json`을 함께 전달한다. 이는 질문·필터·정답
`chunk_id`를 기록한 평가용 파일이며 색인에는 사용하지 않는다. RAG 담당은 여기서
`query_id -> relevant_chunk_ids`를 추출해 BM25, Dense, Hybrid의 Hit@k와 MRR을 같은
조건에서 비교한다. Holdout 질문은 최종 설정 선택 전까지 보지 않는다.
