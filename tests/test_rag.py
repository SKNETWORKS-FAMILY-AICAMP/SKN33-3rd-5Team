import json
import hashlib
import sys
import types

import pytest

from src.rag import (
    DenseRetrievalError,
    DocumentChunk,
    HybridRetriever,
    RagFilters,
    RagSettings,
    RagSettingsError,
    build_chroma_index,
    evaluate_rankings,
    rrf_fuse,
)
from src.rag.chroma_metadata import chroma_where, chunk_to_chroma_metadata, tag_flag_key
from src.contracts.retrieval_text import build_e5_passage


def make_chunk(chunk_id: str, content: str, use_cases: tuple[str, ...]) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        title="Official Raspberry Pi documentation",
        section="Test section",
        content=content,
        source_url="https://www.raspberrypi.com/documentation/",
        retrieved_at="2026-08-27",
        document_version="test",
        license="CC BY-SA 4.0",
        use_cases=use_cases,
        official_verified=True,
        quality_status="approved",
    )


def test_rrf_rewards_a_chunk_returned_by_both_rankers() -> None:
    assert rrf_fuse([["a", "b"], ["b", "c"]])[0] == "b"


def test_metadata_filter_is_applied_before_bm25_ranking() -> None:
    retriever = HybridRetriever(
        [make_chunk("camera", "camera cable connector", ("camera",)), make_chunk("learn", "camera coding", ("learning",))]
    )
    results = retriever.search("camera", RagFilters(use_cases=("camera",)))
    assert [result.chunk_id for result in results] == ["camera"]
    assert results[0].source_url.startswith("https://www.raspberrypi.com/")


def test_evaluation_reports_hit_and_mrr() -> None:
    report = evaluate_rankings({"q1": ["x", "a"]}, {"q1": {"a"}}, k=2)
    assert report.hit_at_k == 1.0
    assert report.mrr == 0.5


def test_settings_reads_dotenv_and_resolves_project_relative_paths(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "data" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text('{"chunks": []}', encoding="utf-8")
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "DOCUMENT_MANIFEST=data/manifest.json",
                "CHROMA_PATH=data/indexed/chroma",
                "CHROMA_COLLECTION_NAME=test_collection",
                "E5_MODEL_NAME=intfloat/multilingual-e5-base",
                "TOP_K=3",
            ]
        ),
        encoding="utf-8",
    )
    for name in ("DOCUMENT_MANIFEST", "CHROMA_PATH", "CHROMA_COLLECTION_NAME", "E5_MODEL_NAME", "TOP_K"):
        monkeypatch.delenv(name, raising=False)

    settings = RagSettings.from_env(tmp_path)

    assert settings.manifest_path == manifest
    assert settings.chroma_path == tmp_path / "data" / "indexed" / "chroma"
    assert settings.chroma_collection_name == "test_collection"
    assert settings.top_k == 3


def test_settings_rejects_invalid_top_k(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"chunks": []}', encoding="utf-8")
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "DOCUMENT_MANIFEST=manifest.json",
                "CHROMA_PATH=data/chroma",
                "CHROMA_COLLECTION_NAME=test_collection",
                "E5_MODEL_NAME=intfloat/multilingual-e5-base",
                "TOP_K=0",
            ]
        ),
        encoding="utf-8",
    )
    for name in ("DOCUMENT_MANIFEST", "CHROMA_PATH", "CHROMA_COLLECTION_NAME", "E5_MODEL_NAME", "TOP_K"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RagSettingsError, match="TOP_K"):
        RagSettings.from_env(tmp_path)


def test_chroma_metadata_and_where_include_tag_filters() -> None:
    chunk = make_chunk("pi5-camera", "camera setup", ("camera",))
    chunk = DocumentChunk(
        **{**chunk.__dict__, "product_models": ("Raspberry Pi 5",), "os_versions": ("Raspberry Pi OS",)}
    )
    metadata = chunk_to_chroma_metadata(chunk)

    assert metadata[tag_flag_key("product_models", "Raspberry Pi 5")] is True
    assert metadata[tag_flag_key("use_cases", "camera")] is True
    assert metadata[tag_flag_key("os_versions", "Raspberry Pi OS")] is True
    assert metadata["filter_all_product_models"] is False

    where = chroma_where(
        RagFilters(product_models=("Raspberry Pi 5",), use_cases=("camera",), os_versions=("Raspberry Pi OS",))
    )
    assert where is not None
    assert where["$and"][0] == {"official_verified": True}
    assert where["$and"][1] == {"quality_status": "approved"}
    assert {tag_flag_key("product_models", "Raspberry Pi 5"): True} in where["$and"][2]["$or"]
    assert {tag_flag_key("use_cases", "camera"): True} in where["$and"][3]["$or"]


def test_dense_configuration_error_is_not_silently_hidden(monkeypatch) -> None:
    retriever = HybridRetriever([make_chunk("camera", "camera", ("camera",))], chroma_path="missing-chroma")
    # Chroma import 자체가 실패한 상황을 흉내 내어 BM25 fallback이 아닌 명시적 오류를 확인한다.
    monkeypatch.setitem(sys.modules, "chromadb", None)

    with pytest.raises(DenseRetrievalError, match="Dense retrieval failed"):
        retriever.search("camera")


def test_indexer_reset_deletes_existing_collection_and_writes_scalar_metadata(tmp_path, monkeypatch) -> None:
    manifest_path = tmp_path / "manifest.json"
    passage = build_e5_passage(title="Camera", section="Setup", content="camera setup")
    embedding_checksum = f"sha256:{hashlib.sha256(passage.encode('utf-8')).hexdigest()}"
    manifest_path.write_text(
        json.dumps(
            {
                "chunks": [
                    {
                        "chunk_id": "camera",
                        "document_id": "doc-1",
                        "title": "Camera",
                        "section": "Setup",
                        "content": "camera setup",
                        "source_url": "https://www.raspberrypi.com/documentation/",
                        "source_anchor": "setup",
                        "retrieved_at": "2026-08-28",
                        "document_version": None,
                        "license": "CC BY-SA 4.0",
                        "product_models": ["Raspberry Pi 5"],
                        "use_cases": ["camera"],
                        "os_versions": ["Raspberry Pi OS"],
                        "official_verified": True,
                        "quality_status": "approved",
                        "embedding_checksum": embedding_checksum,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class FakeCollection:
        def __init__(self) -> None:
            self.upserted: dict[str, object] | None = None

        def upsert(self, **kwargs: object) -> None:
            self.upserted = kwargs

        def get(self) -> dict[str, list[str]]:
            return {"ids": []}

        def delete(self, *, ids: list[str]) -> None:
            raise AssertionError(f"reset collection should not contain stale ids: {ids}")

    class FakeClient:
        def __init__(self) -> None:
            self.collection = FakeCollection()
            self.deleted: list[str] = []

        def list_collections(self) -> list[str]:
            return ["rpi_official"]

        def delete_collection(self, name: str) -> None:
            self.deleted.append(name)

        def get_or_create_collection(self, name: str) -> FakeCollection:
            assert name == "rpi_official"
            return self.collection

    class FakeSentenceTransformer:
        def __init__(self, name: str) -> None:
            assert name == "test-e5"

        def encode(self, texts: list[str], normalize_embeddings: bool) -> list[list[float]]:
            assert texts == [passage]
            assert normalize_embeddings is True
            return [[0.1, 0.2]]

    client = FakeClient()
    monkeypatch.setitem(sys.modules, "chromadb", types.SimpleNamespace(PersistentClient=lambda path: client))
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    )

    count = build_chroma_index(manifest_path, tmp_path / "chroma", embedding_model_name="test-e5", reset=True)

    assert count == 1
    assert client.deleted == ["rpi_official"]
    assert client.collection.upserted is not None
    metadata = client.collection.upserted["metadatas"][0]
    assert metadata[tag_flag_key("product_models", "Raspberry Pi 5")] is True
    assert metadata["quality_status"] == "approved"


def test_indexer_removes_stale_chunk_ids_without_full_reset(tmp_path, monkeypatch) -> None:
    manifest_path = tmp_path / "manifest.json"
    passage = build_e5_passage(title="Camera", section="Setup", content="camera setup")
    checksum = f"sha256:{hashlib.sha256(passage.encode('utf-8')).hexdigest()}"
    manifest_path.write_text(
        json.dumps(
            {
                "chunks": [
                    {
                        "chunk_id": "camera",
                        "document_id": "doc-1",
                        "title": "Camera",
                        "section": "Setup",
                        "content": "camera setup",
                        "source_url": "https://www.raspberrypi.com/documentation/",
                        "source_anchor": "setup",
                        "retrieved_at": "2026-08-28",
                        "document_version": None,
                        "license": "CC BY-SA 4.0",
                        "product_models": [],
                        "use_cases": [],
                        "os_versions": [],
                        "official_verified": True,
                        "quality_status": "approved",
                        "embedding_checksum": checksum,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class FakeCollection:
        def __init__(self) -> None:
            self.deleted_ids: list[str] = []

        def get(self) -> dict[str, list[str]]:
            return {"ids": ["camera", "removed-old-chunk"]}

        def delete(self, *, ids: list[str]) -> None:
            self.deleted_ids.extend(ids)

        def upsert(self, **kwargs: object) -> None:
            pass

    collection = FakeCollection()
    fake_client = types.SimpleNamespace(
        list_collections=lambda: ["rpi_official"],
        delete_collection=lambda name: None,
        get_or_create_collection=lambda name: collection,
    )

    class FakeSentenceTransformer:
        def __init__(self, name: str) -> None:
            pass

        def encode(self, texts: list[str], normalize_embeddings: bool) -> list[list[float]]:
            return [[0.1, 0.2]]

    monkeypatch.setitem(sys.modules, "chromadb", types.SimpleNamespace(PersistentClient=lambda path: fake_client))
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    )

    build_chroma_index(manifest_path, tmp_path / "chroma", embedding_model_name="test-e5")

    assert collection.deleted_ids == ["removed-old-chunk"]
