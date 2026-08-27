"""검수된 manifest를 E5 벡터로 변환해 로컬 Chroma DB에 저장한다.

이 파일은 한 번의 색인 작업을 담당한다. 실제 질의 검색은 ``retriever.py``가
담당하며, 문서 수집·정제·청킹은 문서·데이터 담당의 범위다.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import DocumentChunk


def build_chroma_index(
    manifest_path: str | Path,
    chroma_path: str | Path,
    collection_name: str = "rpi_official",
    embedding_model_name: str = "intfloat/multilingual-e5-base",
) -> int:
    """공식 검증 청크만 Chroma에 upsert하고, 색인한 청크 수를 반환한다.

    ``passage:`` 접두어는 multilingual-e5 모델에서 문서 본문 임베딩임을
    알려 주는 규약이다. 검색 질의에는 retriever에서 ``query:``를 붙인다.
    """
    import chromadb
    from sentence_transformers import SentenceTransformer

    # 문서 담당자가 제공한 하나의 manifest에서 모든 청크를 읽는다.
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    chunks = [DocumentChunk.from_dict(value) for value in payload["chunks"]]
    # 미검수 문서는 검색 근거와 Chroma DB 모두에서 제외한다.
    approved = [chunk for chunk in chunks if chunk.official_verified]
    if not approved:
        raise ValueError("No official_verified chunks found. Do not index unreviewed documents.")
    # normalize_embeddings=True: 코사인 유사도 검색에 맞춘 단위 벡터를 저장한다.
    model = SentenceTransformer(embedding_model_name)
    vectors = model.encode([f"passage: {chunk.content}" for chunk in approved], normalize_embeddings=True).tolist()
    # PersistentClient이므로 생성된 벡터 DB는 chroma_path에 남아 재사용할 수 있다.
    collection = chromadb.PersistentClient(path=str(chroma_path)).get_or_create_collection(collection_name)
    collection.upsert(
        ids=[chunk.chunk_id for chunk in approved],
        documents=[chunk.content for chunk in approved],
        embeddings=vectors,
        # Chroma의 1차 필터와 추적에 필요한 최소 metadata를 함께 저장한다.
        metadatas=[
            {
                "document_id": chunk.document_id,
                "official_verified": chunk.official_verified,
                "source_type": chunk.source_type,
            }
            for chunk in approved
        ],
    )
    return len(approved)
