# 공식 영상–청크 재검수 (2026-09-01)

## 결과

검수 범위는 기존 후보 연결 46개다. OS 설치 20개, 초기 설정의 데스크톱 절차 11개,
NVMe 8개, 카메라 7개를 대상으로 했다. `direct`는 영상이 실제 UI/물리 절차를
보여 주는 청크만 뜻한다. `supporting`은 문서 근거로는 유효하지만 영상의 실제 절차와
일치하지 않아 런타임 영상 연결에서 제외한 청크다. `remove`는 영상과 무관하거나
오래된/다른 절차여서 완전히 제거한 청크다.

| 공식 영상 | 후보 | direct | supporting | remove | 런타임 연결 |
| --- | ---: | ---: | ---: | ---: | --- |
| Raspberry Pi Imager | 20 | 2 | 10 | 8 | `...install-005`, `...install-016` |
| 초기 설정 | 11 | 3 | 3 | 5 | `...setting-up-022`–`024` |
| M.2 HAT+ | 8 | 1 | 1 | 6 | `...boot-nvme-001` |
| High Quality Camera | 7 | 2 | 4 | 1 | `...camera-install-004`, `...camera-install-005` |
| 합계 | 46 | 8 | 18 | 20 | 8개 |

따라서 과잉 매핑 38개(`supporting` 18개와 `remove` 20개)를 런타임 영상 연결에서
제거했다. 상세 분류·근거와 경계 검수는
[`video_chunk_audit_v1.json`](../../assets/media/video_chunk_audit_v1.json)에 있다.

## 영상 기준

- Imager 영상은 Device/OS/Storage 선택과 Write/verify를 보여 준다. OS별 설치 명령,
  Exclude system drives 경고, Connect 인증키, Network Install은 영상 연결 대상이 아니다.
- 초기 설정 영상은 부팅 미디어, 데스크톱 주변기기, 마지막 전원 연결 순서를 보여 준다.
  Wi-Fi/유선 네트워크의 세부 절차와 headless SSH 절차는 제외한다.
- M.2 HAT+ 영상은 Raspberry Pi 5의 HAT/SSD 물리 장착 보조 자료다. `apt` 업데이트,
  `raspi-config`, EEPROM `BOOT_ORDER`, UART/`lsblk` 진단은 제외한다.
- HQ Camera 영상은 리본 케이블의 양 끝 연결을 보여 준다. 영상의 구형 Camera enable 및
  `raspistill` 화면은 현재 `rpicam-apps` 소프트웨어 절차의 근거로 쓰지 않는다.

## 청크 경계

중요 단계·명령어·경고·제품 조건은 청크에서 유실되지 않았다. 다만 다음 항목은 답변에서
동반 검색해야 하는 인접 청크다.

| 문서 | 동반 검색 | 이유 |
| --- | --- | --- |
| OS 설치 | `...install-013` + `014` | Raspberry Pi Connect 인증키 전달 절차가 이어짐 |
| 초기 설정 | `...setting-up-035` + `036` | `openssl passwd -6`와 macOS LibreSSL 주의가 분리됨 |
| NVMe | `...boot-nvme-005` + `006` | `lsblk` 해석 지시와 예시 출력이 이어짐 |
| 카메라 | `...camera-install-001` + `003` + `004` | 케이블 조건·모델별 위치·플랩 작업을 함께 확인해야 함 |

OS 설치의 저장장치 삭제 경고는 `...install-005`와 `006`에, Connect 브라우저 확인 문장은
`...install-013`과 `014`에 중복되어 있어 경계만으로 안전 경고가 사라지지 않는다.

## 평가 라벨

영상별 두 문제씩 총 8개를
[`media_questions_v1.jsonl`](../../eval/media_questions_v1.jsonl)에 추가했다. 모든 사례는
`expected_chunk_ids`, `expected_media_ids`, `media_required: true`를 갖는다. 카메라
모델 조건 질문은 직접 영상 청크(`...-004`)뿐 아니라 동반 문서 청크(`...-001`, `...-003`)도
기대 청크로 표기해 제품 조건이 누락되지 않게 했다.

## 재현 검증

```text
pytest tests/test_media_linker.py -q  ->  2 passed
src.media.linker canonical run         ->  4 videos / direct chunks 2, 3, 1, 2
```
