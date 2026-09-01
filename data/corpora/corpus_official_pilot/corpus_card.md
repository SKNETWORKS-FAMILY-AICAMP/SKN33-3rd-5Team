# corpus_official_pilot

공식 Raspberry Pi 문서 Git checkout과 공개 웹 문서를 대조해 만든, 제품 추천·사용법
RAG 연결용 **legacy fixture**다. 원문을 대량 수집한 최종 corpus가 아니라, 이전
prototype의 청킹·metadata·검색 흐름을 검증하기 위한 12개 청크다.

> [!WARNING]
> 이 corpus는 서비스·배포·성능평가에 사용하지 않는다. 현재 서비스의 유일한 입력은
> schema `1.1.0`의 `document_pipeline/data/manifest_v3.json`이다. 이 fixture manifest는
> `tasks`, `categories`, canonical 처리 metadata가 없으므로 서비스 RAG가 명시적으로
> 거부해야 한다.

## 원본과 추적 정보

- 공식 문서 저장소: `raspberrypi/documentation` (전체 사본은 저장소에 두지 않는다)
- checkout commit: `3e614e3`
- 사용자 출처 URL: `https://www.raspberrypi.com/documentation/`
- 수집일: 2026-08-28
- 라이선스: CC BY-SA 4.0 (`documentation-master/LICENSE.md` 확인)
- 포함 문서: 컴퓨터 하드웨어, 키보드 컴퓨터, Getting started, SSH, 카메라
  소프트웨어, GPIO Python, AI Camera, AI HATs

Git checkout은 청킹·재현을 위한 원본이고, `source_url`은 사용자가 열 수 있는 공식
웹 문서다. 문서가 갱신되면 새 commit과 수집일로 재생성하고, 내용 변경 청크만
갱신한다.

## 범위와 한계

- 포함: Raspberry Pi 5, Pi 4 Model B, Pi 500, Pi 400, Zero 2 W의 공식 사양,
  OS 설치, 헤드리스·SSH, 카메라, GPIO, AI Camera/AI HAT+ 호환성 사실.
- 제외: 가격·재고, 비공식 액세서리, 센서·워터펌프 배선, 제품 리콜, 실제 프로젝트
  설계의 안전성 판단.
- `use_cases`는 검색 라우팅용 태그다. 예를 들어 `smart_farm_monitoring`은 GPIO
  관련 문서를 찾기 위한 태그이지, 공식 문서가 특정 모델을 스마트팜용으로 추천했다는
  의미가 아니다.
- 제품 추천의 최종 결론은 이 corpus의 공식 사실과 별도 검수 제품 카탈로그의
  `recommendation_profile`을 함께 사용해 만든다.

## 권장 확인 질문

| 질문 | 필터 예시 | 기대 근거 청크 |
| --- | --- | --- |
| Pi 4와 Pi 5의 포트·전원 차이는? | 제품: Pi 4 Model B, Pi 5 | `computers-raspberry-pi-4-spec-001`, `computers-raspberry-pi-5-spec-001` |
| 모니터 없이 SSH를 켜려면? | 목적: `headless_remote_management` | `computers-getting-started-headless-001`, `computers-remote-access-ssh-enable-001` |
| Zero 2 W에 AI Camera를 연결할 수 있나? | 제품: Zero 2 W / 목적: `camera_monitoring` | `accessories-ai-camera-compatibility-001`, `computers-raspberry-pi-zero-2-w-spec-001` |
| GPIO를 Python에서 제어하려면? | 목적: `gpio_iot` | `computers-os-gpiozero-001` |
| Pi 5에서 AI HAT+를 쓰려면? | 제품: Pi 5 / 목적: `camera_monitoring` | `accessories-ai-hat-plus-pi5-001` |

## 사용 규칙

- `.env`의 `DOCUMENT_MANIFEST`나 Chroma 색인 입력으로 설정하지 않는다.
- legacy 거부와 이전 검색 흐름을 확인하는 로컬 fixture로만 보관한다.
- 서비스 실행·색인·평가는 [`src/rag/README.md`](../../../src/rag/README.md)의 v3
  절차를 사용한다.
