# 라이선스 및 수집 정책 검토

- 검토일: 2026-08-28
- 검토 범위: Raspberry Pi 공식 온라인 documentation, 공식 documentation GitHub 저장소, 제품 페이지, 제품 PDF, 이미지·영상
- 주의: 이 문서는 프로젝트의 보수적인 운영 기준이며 법률 자문이 아니다.

## 공식 근거

1. [Raspberry Pi Licensing](https://www.raspberrypi.com/licensing/)
   - 공식 온라인 documentation은 CC BY-SA 4.0이다.
   - 일부 eLinux 유래 콘텐츠는 CC BY-SA 3.0 Unported다.
   - 가공물에는 Raspberry Pi Ltd 표시, 원문 링크, 변경 여부 표시와 ShareAlike 조건이 필요하다.
   - 다수의 제품 PDF는 CC BY-ND 4.0이며 수정물을 배포할 수 없다.
   - 그 밖의 문서는 Raspberry Pi Ltd 또는 제3자에게 권리가 있고 별도 허가가 없을 수 있다.
2. [raspberrypi/documentation README](https://github.com/raspberrypi/documentation/blob/master/README.md)
   - `documentation/` 아래 문서 원문은 CC BY-SA 4.0이다.
   - documentation 도구는 BSD 3-Clause다.
3. [Raspberry Pi Terms and conditions](https://www.raspberrypi.com/terms-and-conditions/)
   - 2026-06-02 개정본을 검토했다.
   - 사이트에 대한 자동 웹 스크래핑 및 텍스트·데이터 마이닝 금지 조항이 있다.
   - Creative Commons로 명시된 자료에는 해당 CC 조건이 적용되지만, 자동 수집 방식은 별도 약관 위험이 있으므로 보수적으로 제한한다.

## 프로젝트 적용 결정

| 자료 유형 | 결정 | 이유 |
|---|---|---|
| 공식 GitHub 저장소의 `documentation/**/*.adoc` | 포함 | 문서 라이선스와 변경 이력을 확인하고 commit SHA로 고정할 수 있음 |
| `raspberrypi.com/documentation` HTML | 탐색·원문 링크 표시만 | 자동 스크래핑 대신 동일 콘텐츠의 공식 GitHub 원문 사용 |
| Raspberry Pi 제품 페이지 본문 | 참고 전용 | documentation과 같은 CC 라이선스로 가정할 수 없고 사이트 자동 수집을 허용하지 않음 |
| 제품 PDF·데이터시트 | 기본 제외 | 다수가 CC BY-ND이므로 청킹·정규화한 파생물을 공개 배포하지 않음 |
| `documentation/` 안의 제품 사진 | 포함 | 저장소 README가 `documentation/` 전체를 CC BY-SA 4.0으로 명시하며, commit SHA와 파일 경로를 고정함 |
| 제품 페이지의 CDN 사진 | 기본 제외 | 제품 페이지 자산은 documentation 저장소의 CC 라이선스로 자동 전환되지 않음 |
| 제품 영상·로고 | 기본 제외 | 문서 텍스트 라이선스가 미디어·상표 권리까지 자동으로 포함하지 않음 |
| eLinux 유래 문단 | 개별 provenance 확인 | 해당 부분은 CC BY-SA 3.0 조건과 원저작자 표시가 필요할 수 있음 |

## 허용된 수집 방식

1. `source_registry.csv`에서 `collection_decision=include`인 행만 처리한다.
2. `collection_method=git_raw`인 공식 GitHub 원문만 자동 수집한다.
3. 실제 수집 시 `master` 대신 확인한 commit SHA로 URL과 `document_version`을 고정한다.
4. `reference_only`, `blocked`, `pending` 자료는 본문을 다운로드·청킹하지 않는다.
5. 원문은 로컬 작업 공간에만 두고 저장소에는 source registry, checksum, 처리 코드와 검토 문서만 커밋한다.

## 제품 사진 표시 정책

`data/product_media_registry.json`에는 제품 페이지 CDN 사진이 아니라, 공식 GitHub 저장소의 `documentation/` 아래에서 확인한 이미지 5개만 등록한다. 각 URL은 `master`가 아니라 확인한 commit SHA `75331a79fbf32d2403b7547729ddccf553873b09`로 고정했다.

이 이미지들은 CC BY-SA 4.0 조건으로 로컬 저장, Git 커밋, 공개 배포와 수정이 가능하다. 다만 아래 조건은 반드시 지킨다.

1. 카드 또는 별도 출처 화면에 저작자, 원문 파일 URL, `CC BY-SA 4.0`, 변경 여부를 표시한다.
2. 이미지를 수정하거나 UI에 맞게 편집해 배포하면, 그 이미지의 수정본도 CC BY-SA 4.0으로 제공한다.
3. `Raspberry Pi` 이름은 실제 제품 설명에만 쓰고, 프로젝트가 공식·후원 서비스처럼 보이게 하지 않는다.
4. Raspberry Pi 로고는 서비스의 로고, 아이콘, 파비콘 또는 배너에 사용하지 않는다.
5. 문서 저장소 밖의 제품 페이지 CDN 사진·영상에는 이 허용 범위를 적용하지 않는다.

즉, 이 프로젝트는 등록된 5개 문서 저장소 이미지를 제품 카드에 사용할 수 있다. 화면에는 `PiCare is an unofficial educational project and is not endorsed by Raspberry Pi Ltd.`를 함께 표시한다.

## Attribution 형식

```text
Source: Raspberry Pi Ltd, <문서 제목>, <원문 URL>
Retrieved: YYYY-MM-DD
Licence: CC BY-SA 4.0 또는 확인된 개별 라이선스
Changes: AsciiDoc 파싱, 반복 UI 제거, 섹션 기반 청킹
```

eLinux 유래 콘텐츠가 확인되면 원저작자와 CC BY-SA 3.0 정보를 추가한다.

## 재검토 조건

- 공식 이용약관 또는 라이선스 페이지 변경
- 새로운 도메인·PDF·제품 페이지 추가
- 이미지나 영상을 로컬 저장 또는 UI에 표시
- corpus 또는 파생 청크를 외부에 배포
- 상업적 이용으로 프로젝트 범위 변경
