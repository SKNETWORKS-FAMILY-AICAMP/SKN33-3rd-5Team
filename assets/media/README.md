# 공식 미디어 자산

PiCare의 제품 추천 카드와 사용 지원 답변에 표시할 Raspberry Pi 공식 문서 이미지 모음입니다.

## 수집 범위

- 제품 대표 이미지 5개: Raspberry Pi 5, Raspberry Pi 4 Model B, Raspberry Pi 500, Raspberry Pi 400, Raspberry Pi Zero 2 W
- 사용 지원 이미지 14개: Raspberry Pi Imager, 전원, Wi-Fi, SSH, GPIO, 부팅 진단, Camera Module 3, Raspberry Pi Connect
- 공식 사용 지원 영상 4개: Imager, 초기 설정, M.2 HAT+, High Quality Camera
- 이미지 총 19개, 영상 링크 총 4개
- 수집일: 2026-08-28
- 원본 저장소: <https://github.com/raspberrypi/documentation>
- 원본 커밋: `75331a79fbf32d2403b7547729ddccf553873b09`

각 파일의 원본 경로, 문서 URL, SHA-256, 크기, 대체 텍스트는 [`manifest.json`](manifest.json)에 기록했습니다. 공식 사용법 영상 4개는 파일을 내려받지 않고 [`video_manifest.json`](video_manifest.json)에 공식 YouTube URL과 연결 문서를 기록했습니다.

## 디렉터리

```text
assets/media/
├── images/
│   ├── products/   # 제품 추천·비교 카드
│   └── guides/     # 설치·설정·문제 해결 답변
├── manifest.json   # 출처·라이선스·무결성 대장
├── video_manifest.json # 공식 영상 링크·임베드·문서 연결 대장
└── README.md
```

## 사용 원칙

1. 서버는 `manifest.json`을 읽어 제품 모델 또는 답변 주제와 일치하는 이미지만 선택합니다.
2. 챗봇의 사용 지원 이미지는 검색된 공식 문서의 citation과 주제가 일치할 때만 표시합니다.
3. 화면에는 이미지와 함께 `Raspberry Pi Ltd`, 원문 링크, `CC BY-SA 4.0`을 표시합니다.
4. 현재 파일은 원본 이미지 바이트를 변경하지 않고 파일명만 바꿨습니다.
5. 이후 자르기·색상 변경·주석 추가 등 편집을 하면 manifest의 `modified`와 `changes`를 갱신하고 결과물에도 CC BY-SA 4.0을 적용합니다.
6. Raspberry Pi 상표나 로고를 프로젝트가 공식 승인받았다는 의미로 사용하지 않습니다.
7. 영상은 공식 YouTube player로만 임베드하며 다운로드·재업로드하지 않습니다. 절차가 영상과 문서에서 다르면 최신 공식 문서를 우선합니다.

권장 화면 표기:

```text
이미지: © Raspberry Pi Ltd
출처: Raspberry Pi Documentation (<원문 URL>)
라이선스: CC BY-SA 4.0
변경: 없음(파일명만 변경)
```

## 제품 이미지

| 제품 | 파일 |
| --- | --- |
| Raspberry Pi 5 | `images/products/raspberry-pi-5.jpg` |
| Raspberry Pi 4 Model B | `images/products/raspberry-pi-4-model-b.jpg` |
| Raspberry Pi 500 | `images/products/raspberry-pi-500.png` |
| Raspberry Pi 400 | `images/products/raspberry-pi-400.jpg` |
| Raspberry Pi Zero 2 W | `images/products/raspberry-pi-zero-2-w.jpg` |

## 사용 지원 이미지

| 주제 | 파일 |
| --- | --- |
| Imager 기기 선택 | `images/guides/imager-device-tab.png` |
| OS 선택 | `images/guides/imager-os-tab.png` |
| 저장장치 선택 | `images/guides/imager-storage-tab.png` |
| 이미지 기록 | `images/guides/imager-write.png` |
| Imager Wi-Fi 설정 | `images/guides/imager-wifi-subtab.png` |
| Imager SSH 설정 | `images/guides/imager-ssh-subtab.png` |
| 전원 연결 | `images/guides/connect-power.png` |
| Raspberry Pi OS Wi-Fi 설정 | `images/guides/wifi-configuration.jpg` |
| 부트로더 진단 화면 | `images/guides/bootloader-diagnostics.png` |
| 40핀 GPIO 핀 배열 | `images/guides/gpio-pinout.png` |
| Camera Module 3 | `images/guides/camera-module-3.jpg` |
| 원격 접속 설정 화면 | `images/guides/remote-access-configuration.png` |
| Raspberry Pi Connect 활성화 | `images/guides/connect-enable.png` |
| Raspberry Pi Connect 화면 공유 | `images/guides/connect-screen-sharing.png` |

## 사용 지원 영상

| 주제 | 공식 영상 |
| --- | --- |
| Raspberry Pi Imager | [How to use Raspberry Pi Imager](https://www.youtube.com/watch?v=O4IQE2E8oOw) |
| Raspberry Pi 초기 설정 | [How to set up a Raspberry Pi](https://www.youtube.com/watch?v=CQtliTJ41ZE) |
| Raspberry Pi M.2 HAT+ | [How to fit the Raspberry Pi M.2 HAT+](https://www.youtube.com/shorts/EMe2DOM8viQ) |
| High Quality Camera | [HOW TO USE the Raspberry Pi High Quality Camera](https://www.youtube.com/watch?v=sAXDgByhcJU) |

영상 자체를 RAG 근거로 사용하지 않습니다. 챗봇은 `source_document_url`과 `source_section`이 일치하는 문서 청크를 먼저 인용한 경우에만 해당 영상을 보조 자료로 표시합니다.

## 문서 청크 연결

v3 문서 corpus와의 연결 파일은 다음 명령으로 생성합니다.

```bash
python -m src.media.linker \
  --document-manifest document_pipeline/data/manifest_v3.json \
  --image-manifest assets/media/manifest.json \
  --video-manifest assets/media/video_manifest.json \
  --output document_pipeline/data/media_chunk_map_v3.json \
  --repository-root .
```

2026-08-31 검증 결과 사용 지원 미디어 18개 중 13개가 현재 corpus에 연결됐습니다. 아래 5개는 관련 세부 섹션이 수집되지 않아 표시 대상에서 제외됩니다.

- `rpi-guide-0009`: Boot diagnostics
- `rpi-guide-0011`: Camera Module 3
- `rpi-guide-0012`: Enable remote access
- `rpi-guide-0013`: Install and enable Connect
- `rpi-guide-0014`: Screen sharing

문서를 추가 수집한 뒤 linker를 다시 실행하면 연결 여부가 재평가됩니다. 생성되는 `manifest_v3.json`과 `media_chunk_map_v3.json`은 재현 가능한 산출물이므로 Git에는 올리지 않습니다.

## 라이선스

선별한 파일은 Raspberry Pi 공식 documentation 저장소의 `documentation/` 하위 자료입니다. 저장소는 해당 문서 자료를 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)으로 제공합니다. 개별 파일에 별도 권리 표시가 추가되거나 원본 경로가 바뀌면 재수집 전에 다시 검토합니다.

- 공식 라이선스 안내: <https://www.raspberrypi.com/licensing/>
- 저장소 라이선스: <https://github.com/raspberrypi/documentation/blob/master/LICENSE.md>
- 상표 정책: <https://www.raspberrypi.com/trademark-rules/>

