# 제품 추천 카탈로그

`catalog.json`은 팀이 공식 문서 근거와 추천 정책을 검수한 실행용 사실 데이터다.
원문 corpus가 아니므로 Git에 커밋하며, 제품 추천 서비스는 이 파일을 임의 보완하지 않고
`src/recommendation/schema.py`로 검증해 읽는다.

계약, 생성 순서와 검증 명령은
[`docs/data-contracts/product-catalog.md`](../../docs/data-contracts/product-catalog.md),
현재 corpus 품질 수치는
[`docs/document-cards/raspberry-pi-official-v3.md`](../../docs/document-cards/raspberry-pi-official-v3.md)를
참조한다.
