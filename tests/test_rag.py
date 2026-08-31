import json
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
    RetrievalDecision,
    build_chroma_index,
    evaluate_rankings,
    rrf_fuse,
)
from src.rag.chroma_metadata import chroma_where, chunk_to_chroma_metadata, tag_flag_key
from src.rag import demo
from src.rag.demo import DEMO_QUERIES, create_parser, prompt_for_query, select_query


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
    )


def test_rrf_rewards_a_chunk_returned_by_both_rankers() -> None:
    assert rrf_fuse([["a", "b"], ["b", "c"]])[0] == "b"


def test_metadata_filter_is_applied_before_bm25_ranking() -> None:
    retriever = HybridRetriever(
        [
            make_chunk("camera", "camera cable connector", ("camera",)),
            make_chunk("learn", "learning coding", ("learning",)),
            make_chunk("server", "server storage", ("server",)),
        ]
    )
    results = retriever.search("camera", RagFilters(use_cases=("camera",)))
    assert [result.chunk_id for result in results] == ["camera"]
    assert results[0].source_url.startswith("https://www.raspberrypi.com/")


def test_document_id_filter_limits_bm25_candidates_to_catalog_evidence() -> None:
    first = make_chunk("pi5", "server storage setup", ("server",))
    second = DocumentChunk(**{**first.__dict__, "chunk_id": "zero", "document_id": "doc-zero"})
    second = DocumentChunk(**{**second.__dict__, "content": "camera connector setup", "use_cases": ("camera",)})
    first = DocumentChunk(**{**first.__dict__, "document_id": "doc-pi5"})
    third = DocumentChunk(**{**first.__dict__, "chunk_id": "four", "document_id": "doc-pi4"})
    retriever = HybridRetriever([first, second, third])

    results = retriever.search("camera", RagFilters(document_ids=("doc-zero",)))

    assert [result.chunk_id for result in results] == ["zero"]


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
    assert settings.dense_max_distance == 0.48


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


def test_settings_rejects_invalid_dense_distance(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"chunks": []}', encoding="utf-8")
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "DOCUMENT_MANIFEST=manifest.json",
                "CHROMA_PATH=data/chroma",
                "CHROMA_COLLECTION_NAME=test_collection",
                "E5_MODEL_NAME=intfloat/multilingual-e5-base",
                "TOP_K=3",
                "DENSE_MAX_DISTANCE=2",
            ]
        ),
        encoding="utf-8",
    )
    for name in (
        "DOCUMENT_MANIFEST",
        "CHROMA_PATH",
        "CHROMA_COLLECTION_NAME",
        "E5_MODEL_NAME",
        "TOP_K",
        "DENSE_MAX_DISTANCE",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RagSettingsError, match="DENSE_MAX_DISTANCE"):
        RagSettings.from_env(tmp_path)


def test_bm25_all_zero_returns_insufficient_evidence_and_search_stays_compatible() -> None:
    retriever = HybridRetriever([make_chunk("camera", "camera setup", ("camera",))])

    decision = retriever.search_with_decision("스마트팜을 만들고 싶어요")

    assert isinstance(decision, RetrievalDecision)
    assert decision.status == "insufficient_evidence"
    assert decision.reason == "bm25_all_zero"
    assert decision.results == ()
    assert retriever.search("스마트팜을 만들고 싶어요") == []


def _mock_dense_response(monkeypatch, response: dict[str, list[list[object]]]) -> None:
    class FakeCollection:
        def query(self, **kwargs: object) -> dict[str, list[list[object]]]:
            return response

    class FakeClient:
        def get_collection(self, name: str) -> FakeCollection:
            assert name == "rpi_official"
            return FakeCollection()

    class FakeSentenceTransformer:
        def __init__(self, name: str) -> None:
            assert name == "test-e5"

        def encode(self, texts: list[str], normalize_embeddings: bool) -> list[list[float]]:
            assert normalize_embeddings is True
            return [[0.1, 0.2]]

    monkeypatch.setitem(sys.modules, "chromadb", types.SimpleNamespace(PersistentClient=lambda path: FakeClient()))
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    )


def test_dense_distance_over_threshold_returns_insufficient_evidence(monkeypatch) -> None:
    _mock_dense_response(monkeypatch, {"ids": [["camera"]], "distances": [[0.49]]})
    retriever = HybridRetriever(
        [make_chunk("camera", "camera setup", ("camera",))],
        chroma_path="test-chroma",
        embedding_model_name="test-e5",
        dense_max_distance=0.48,
    )

    decision = retriever.search_with_decision("스마트팜을 만들고 싶어요")

    assert decision.status == "insufficient_evidence"
    assert decision.reason == "bm25_all_zero_and_dense_below_threshold"


def test_hybrid_returns_dense_result_when_bm25_is_zero(monkeypatch) -> None:
    _mock_dense_response(monkeypatch, {"ids": [["camera"]], "distances": [[0.20]]})
    retriever = HybridRetriever(
        [make_chunk("camera", "camera setup", ("camera",))],
        chroma_path="test-chroma",
        embedding_model_name="test-e5",
    )

    decision = retriever.search_with_decision("카메라를 연결하고 싶어요")

    assert decision.status == "retrieved"
    assert [result.chunk_id for result in decision.results] == ["camera"]


def test_hybrid_keeps_bm25_result_when_dense_is_below_threshold(monkeypatch) -> None:
    _mock_dense_response(monkeypatch, {"ids": [["camera"]], "distances": [[0.90]]})
    retriever = HybridRetriever(
        [
            make_chunk("camera", "camera setup", ("camera",)),
            make_chunk("learn", "learning coding", ("learning",)),
            make_chunk("server", "server storage", ("server",)),
        ],
        chroma_path="test-chroma",
        embedding_model_name="test-e5",
    )

    decision = retriever.search_with_decision("camera")

    assert decision.status == "retrieved"
    assert [result.chunk_id for result in decision.results] == ["camera"]


def test_demo_parser_has_no_fixed_filter_and_accepts_optional_use_case() -> None:
    default_args = create_parser().parse_args([])
    filtered_args = create_parser().parse_args(["--query", "카메라", "--use-case", "camera"])

    assert default_args.use_cases is None
    assert filtered_args.query == "카메라"
    assert filtered_args.use_cases == ["camera"]


def test_demo_uses_a_random_example_query_only_when_no_query_is_provided(monkeypatch) -> None:
    monkeypatch.setattr(demo.random, "choice", lambda values: values[-1])

    assert select_query(None) == DEMO_QUERIES[-1]
    assert select_query("직접 입력한 질문") == "직접 입력한 질문"


def test_demo_console_input_returns_text_or_none_for_empty_input(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "  SSH를 활성화하려면?  ")
    assert prompt_for_query() == "SSH를 활성화하려면?"

    monkeypatch.setattr("builtins.input", lambda _: "   ")
    assert prompt_for_query() is None


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
    assert {tag_flag_key("product_models", "Raspberry Pi 5"): True} in where["$and"][1]["$or"]
    assert {tag_flag_key("use_cases", "camera"): True} in where["$and"][2]["$or"]

    document_where = chroma_where(RagFilters(document_ids=("doc-pi5", "doc-zero")))
    assert document_where == {
        "$and": [
            {"official_verified": True},
            {"document_id": {"$in": ["doc-pi5", "doc-zero"]}},
        ]
    }


def test_dense_configuration_error_is_not_silently_hidden(monkeypatch) -> None:
    retriever = HybridRetriever([make_chunk("camera", "camera", ("camera",))], chroma_path="missing-chroma")
    # Chroma import 자체가 실패한 상황을 흉내 내어 BM25 fallback이 아닌 명시적 오류를 확인한다.
    monkeypatch.setitem(sys.modules, "chromadb", None)

    with pytest.raises(DenseRetrievalError, match="Dense retrieval failed"):
        retriever.search("camera")


def test_indexer_reset_deletes_existing_collection_and_writes_scalar_metadata(tmp_path, monkeypatch) -> None:
    manifest_path = tmp_path / "manifest.json"
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
                        "retrieved_at": "2026-08-28",
                        "document_version": None,
                        "license": "CC BY-SA 4.0",
                        "product_models": ["Raspberry Pi 5"],
                        "use_cases": ["camera"],
                        "os_versions": ["Raspberry Pi OS"],
                        "official_verified": True,
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
            assert texts == ["passage: camera setup"]
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
    assert (tmp_path / "chroma" / "picare-index.json").is_file()
