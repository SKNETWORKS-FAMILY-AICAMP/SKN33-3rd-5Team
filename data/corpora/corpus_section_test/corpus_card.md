# corpus_section_test

RAG 연결과 검색 로직을 확인하기 위한 최소 **legacy fixture**다. 최종 성능 비교,
서비스 배포, 서비스 색인에 사용하지 않는다.

> [!WARNING]
> 이 manifest는 schema `1.1.0` 이전 형식이며 `tasks`, `categories`, canonical 처리
> metadata가 없다. 서비스의 `HybridRetriever.from_manifest()`는 이 파일을 입력으로
> 받으면 schema version 오류로 거부해야 한다. 활성 corpus는
> `document_pipeline/data/manifest_v3.json`뿐이다.

## 생성 조건

- 원본: `document/documentation-master/documentation/asciidoc/`
- 포함 범위: Raspberry Pi OS 설치, 헤드리스·SSH 원격 접속, 카메라 소프트웨어
- 청킹 방식: AsciiDoc 제목·소제목을 기준으로 의미가 완결되는 구간을 직접 분리
- 총 청크 수: 4개
- 수집일: 2026-08-28
- 라이선스: CC BY-SA 4.0

## 원본 파일

- `computers/getting-started/install.adoc`
- `computers/remote-access/ssh.adoc`
- `computers/camera/camera_usage.adoc`

## 사용 규칙

- `.env`의 `DOCUMENT_MANIFEST`, 서비스 Chroma 색인, Dev/Holdout 성능평가에 사용하지
  않는다.
- legacy schema 거부와 검색 단위 테스트를 위한 로컬 fixture로만 유지한다.
- 서비스 실행·색인·평가는 [`src/rag/README.md`](../../../src/rag/README.md)의 v3
  절차를 사용한다.
