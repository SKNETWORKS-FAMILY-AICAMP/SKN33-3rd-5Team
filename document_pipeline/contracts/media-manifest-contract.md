# Citation-linked media manifest 계약

- 계약 버전: `1.0.0`
- 생성 코드: `python -m document_pipeline.ingestion.build_media_manifest`
- 기계 검증 스키마: `media-manifest.schema.json`

이미지와 영상은 검색 문장이 아니므로 별도 청크를 만들거나 임베딩하지 않는다. 공식
AsciiDoc의 `image::`·`video::` 매크로를 읽어 고정된 원문 URL로 해석하고, 같은 문서와
섹션의 승인된 `chunk_id`에 결정적인 `media_id`를 연결한다.

```text
공식 AsciiDoc + document manifest
  → Media Linker
  → media_manifest_vN.json (items + chunk_id/media_id links)
  → 실제 답변에 남은 citation의 chunk_id만 Media Resolver에 전달
  → ChatResponse.media
```

## 분리 원칙

1. 문서 이미지·영상 본문은 RAG 청크에 넣지 않는다. 텍스트 청크의 `image_url`,
   `video_url`은 호환성 때문에 유지하되 `null`이다.
2. 제품 카드 이미지는 `data/products/catalog.json`의 `image_url`로 표시한다. 문서
   가이드 미디어인 `ChatResponse.media`와 섞지 않는다.
3. `media_id`는 `media_type + URL`의 SHA-256으로 결정하므로 재생성해도 같다.
4. 미디어는 같은 `document_id + section`에 속한 승인 청크에만 연결한다. 연결할 청크가
   없거나 URL·원문 checksum·source registry가 맞지 않으면 생성 자체를 실패시킨다.
5. 이미지 URL은 공식 Raspberry Pi 호스트 또는 수집 commit에 고정된 공식 문서 저장소만
   허용한다. YouTube 영상은 공식 문서의 명시적 `video::... [youtube]`만 링크하며 파일을
   복제하거나 라이선스를 CC로 추정하지 않는다.
6. 런타임은 모델이 언급한 모든 후보가 아니라 인용 검증 후 실제 응답에 남은 citation의
   `chunk_id`만 해석한다. 동일 미디어가 여러 인용에 연결되면 첫 인용 기준으로 한 번만 낸다.

## 2차 검증 기준

- document manifest checksum과 media manifest 기준 checksum 일치
- 모든 `chunk_id`와 `media_id`가 존재하며 중복 없음
- 모든 미디어가 최소 한 개 승인 청크에 연결됨
- URL은 HTTPS이고 유형별 허용 호스트·provider 규칙 통과
- `official_verified=true`, 라이선스·attribution 비어 있지 않음
- `ChatResponse.media[*].source_citation_id`가 최종 `citations`에 존재
