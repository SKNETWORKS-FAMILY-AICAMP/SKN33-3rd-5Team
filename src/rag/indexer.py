"""Build the local E5/Chroma index from a document-team approved manifest."""
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
    import chromadb
    from sentence_transformers import SentenceTransformer

    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    chunks = [DocumentChunk.from_dict(value) for value in payload["chunks"]]
    approved = [chunk for chunk in chunks if chunk.official_verified]
    if not approved:
        raise ValueError("No official_verified chunks found. Do not index unreviewed documents.")
    model = SentenceTransformer(embedding_model_name)
    vectors = model.encode([f"passage: {chunk.content}" for chunk in approved], normalize_embeddings=True).tolist()
    collection = chromadb.PersistentClient(path=str(chroma_path)).get_or_create_collection(collection_name)
    collection.upsert(
        ids=[chunk.chunk_id for chunk in approved],
        documents=[chunk.content for chunk in approved],
        embeddings=vectors,
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
