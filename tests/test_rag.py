from src.rag import DocumentChunk, HybridRetriever, RagFilters, evaluate_rankings, rrf_fuse


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
        [make_chunk("camera", "camera cable connector", ("camera",)), make_chunk("learn", "camera coding", ("learning",))]
    )
    results = retriever.search("camera", RagFilters(use_cases=("camera",)))
    assert [result.chunk_id for result in results] == ["camera"]
    assert results[0].source_url.startswith("https://www.raspberrypi.com/")


def test_evaluation_reports_hit_and_mrr() -> None:
    report = evaluate_rankings({"q1": ["x", "a"]}, {"q1": {"a"}}, k=2)
    assert report.hit_at_k == 1.0
    assert report.mrr == 0.5
