"""검수된 manifest를 E5 벡터로 변환해 로컬 Chroma DB에 저장한다.

이 파일은 한 번의 색인 작업을 담당한다. 실제 질의 검색은 ``retriever.py``가
담당하며, 문서 수집·정제·청킹은 문서·데이터 담당의 범위다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src.contracts.retrieval_text import build_e5_passage

from .adapters import manifest_to_document_chunks
from .chroma_metadata import chunk_to_chroma_metadata
from .index_metadata import write_index_metadata
from .settings import RagSettings, RagSettingsError


def build_chroma_index(
    manifest_path: str | Path,
    chroma_path: str | Path,
    collection_name: str = "rpi_official",
    embedding_model_name: str = "intfloat/multilingual-e5-base",
    *,
    reset: bool = False,
) -> int:
    """공식 검증 청크만 Chroma에 upsert하고, 색인한 청크 수를 반환한다.

    ``passage:`` 접두어는 multilingual-e5 모델에서 문서 본문 임베딩임을
    알려 주는 규약이다. 검색 질의에는 retriever에서 ``query:``를 붙인다.
    """
    import chromadb
    from sentence_transformers import SentenceTransformer

    # 문서 담당자가 제공한 하나의 manifest에서 모든 청크를 읽는다.
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    chunks = manifest_to_document_chunks(payload)
    # 미검수 문서는 검색 근거와 Chroma DB 모두에서 제외한다.
    approved = [
        chunk
        for chunk in chunks
        if chunk.official_verified and chunk.quality_status == "approved"
    ]
    if not approved:
        raise ValueError("No official_verified chunks found. Do not index unreviewed documents.")
    # normalize_embeddings=True: 코사인 유사도 검색에 맞춘 단위 벡터를 저장한다.
    model = SentenceTransformer(embedding_model_name)
    passages = [
        build_e5_passage(title=chunk.title, section=chunk.section, content=chunk.content)
        for chunk in approved
    ]
    for chunk, passage in zip(approved, passages, strict=True):
        checksum = f"sha256:{hashlib.sha256(passage.encode('utf-8')).hexdigest()}"
        if chunk.embedding_checksum and chunk.embedding_checksum != checksum:
            raise ValueError(f"Embedding input checksum mismatch: {chunk.chunk_id}")
    encoded_vectors = model.encode(passages, normalize_embeddings=True)
    # sentence-transformers 기본값은 NumPy 배열이지만, 테스트·대체 구현은 list를 반환할 수도 있다.
    vectors = encoded_vectors.tolist() if hasattr(encoded_vectors, "tolist") else list(encoded_vectors)
    # PersistentClient이므로 생성된 벡터 DB는 chroma_path에 남아 재사용할 수 있다.
    client = chromadb.PersistentClient(path=str(chroma_path))
    if reset:
        # reset은 명시적으로 요청했을 때만 수행한다. 평소 upsert는 같은 ID만 갱신한다.
        existing = client.list_collections()

        existing_names = {item.name if hasattr(item, "name") else str(item) for item in existing}
        if collection_name in existing_names:
            client.delete_collection(collection_name)
    collection = client.get_or_create_collection(collection_name)
    existing_payload = collection.get()
    existing_ids = set(existing_payload.get("ids", []))
    approved_ids = {chunk.chunk_id for chunk in approved}
    stale_ids = sorted(existing_ids - approved_ids)
    if stale_ids:
        collection.delete(ids=stale_ids)
    collection.upsert(
        ids=[chunk.chunk_id for chunk in approved],
        documents=[chunk.content for chunk in approved],
        embeddings=vectors,
        # 다중 tag는 scalar boolean flag로 저장해 Chroma ``where`` 조건에서 검색한다.
        metadatas=[chunk_to_chroma_metadata(chunk) for chunk in approved],
    )
    write_index_metadata(
        chroma_path=chroma_path,
        collection_name=collection_name,
        embedding_model_name=embedding_model_name,
        manifest_path=manifest_path,
        indexed_chunk_count=len(approved),
    )
    return len(approved)


def main() -> None:
    """`.env` 설정으로 Chroma 색인을 만들고, 필요 시 전체 재색인한다."""
    parser = argparse.ArgumentParser(description="Build the local Raspberry Pi Chroma index.")
    parser.add_argument("--reset", action="store_true", help="Delete the existing collection before indexing.")
    args = parser.parse_args()
    try:
        settings = RagSettings.from_env()
    except RagSettingsError as exc:
        raise SystemExit(f"RAG settings error: {exc}") from exc
    count = build_chroma_index(
        manifest_path=settings.manifest_path,
        chroma_path=settings.chroma_path,
        collection_name=settings.chroma_collection_name,
        embedding_model_name=settings.e5_model_name,
        reset=args.reset,
    )
    action = "reset and indexed" if args.reset else "indexed"
    print(f"{action} {count} official chunks in '{settings.chroma_collection_name}'.")


if __name__ == "__main__":
    main()
