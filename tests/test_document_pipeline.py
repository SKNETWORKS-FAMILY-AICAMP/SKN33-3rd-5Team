from __future__ import annotations

from document_pipeline.ingestion.build_manifest import chunk_section
from document_pipeline.ingestion.fetch import REGISTRY_PATH, included_sources
from document_pipeline.ingestion.parse_asciidoc import parse_asciidoc
from document_pipeline.ingestion.validate_foundation import validate_source_registry
from src.rag.adapters import manifest_chunk_to_document_chunk


class FakeE5Tokenizer:
    """Deterministic tokenizer substitute for boundary tests without model downloads."""

    def encode(self, text: str, *, add_special_tokens: bool = True) -> list[int]:
        return list(range(len(text.split()) + (2 if add_special_tokens else 0)))


def test_parser_preserves_anchor_lists_code_admonitions_and_table() -> None:
    source = """[[networking]]
== Networking

[WARNING]
====
Use a secured network.
====

. Open the terminal.
.. Run the command below.

[source,console]
----
$ nmcli dev wifi list
  --rescan yes
----

|===
| Model | Memory
| Raspberry Pi 5 | 8 GB
|===
"""

    section = parse_asciidoc(source, fallback_title="fallback")[0]

    assert section.source_anchor == "networking"
    assert section.heading_path == ("Networking",)
    assert [block.kind for block in section.blocks] == ["admonition", "list", "code", "table"]
    assert section.blocks[0].severity == "WARNING"
    assert section.blocks[1].items[1].level == 2
    assert section.blocks[2].language == "console"
    assert "  --rescan yes" in section.blocks[2].text
    assert section.blocks[3].headers == ("Model", "Memory")
    assert section.blocks[3].rows == (("Raspberry Pi 5", "8 GB"),)


def test_chunking_uses_whole_semantic_blocks_for_overlap() -> None:
    source = """[[ssh]]
== SSH

Use SSH for remote access.

[source,console]
----
$ nmcli dev wifi list
----

Use a secured password.
"""
    section = parse_asciidoc(source, fallback_title="fallback")[0]

    chunks = chunk_section(section, tokenizer=FakeE5Tokenizer(), target_tokens=8, max_tokens=14, overlap_tokens=6)

    assert chunks
    assert all(not chunk.startswith("cli") for chunk in chunks)
    assert any("```console\n$ nmcli dev wifi list\n```" in chunk for chunk in chunks)


def test_manifest_adapter_maps_collected_at_without_dropping_manifest_contract() -> None:
    chunk = manifest_chunk_to_document_chunk(
        {
            "document_id": "rpi-doc-ssh",
            "chunk_id": "rpi-doc-ssh-000",
            "chunk_index": 0,
            "title": "SSH",
            "publisher": "Raspberry Pi Ltd",
            "section": "SSH",
            "content": "Use SSH.",
            "source_url": "https://www.raspberrypi.com/documentation/computers/remote-access.html#ssh",
            "source_anchor": "ssh",
            "language": "en",
            "source_type": "documentation",
            "published_at": None,
            "updated_at": None,
            "collected_at": "2026-08-28",
            "document_version": "a" * 40,
            "license": "CC-BY-SA-4.0",
            "product_models": [],
            "use_cases": ["headless_remote_management"],
            "tasks": ["remote_access"],
            "categories": ["ssh"],
            "os_versions": ["Raspberry Pi OS"],
            "document_checksum": "sha256:" + "a" * 64,
            "chunk_checksum": "sha256:" + "b" * 64,
            "parser_version": "asciidoc-semantic-2.0.0",
            "official_verified": True,
            "image_url": None,
            "video_url": None,
        }
    )

    assert chunk.retrieved_at == "2026-08-28"
    assert chunk.use_cases == ("headless_remote_management",)
    assert chunk.official_verified is True


V2_REGISTRY_PATH = REGISTRY_PATH.with_name("source_registry_v2.csv")


def test_original_registry_remains_the_nine_document_baseline() -> None:
    assert validate_source_registry() == (17, 9, 8)


def test_recommendation_mvp_v2_registry_has_15_approved_official_documents() -> None:
    total, included, reference_only = validate_source_registry(V2_REGISTRY_PATH)
    sources = {source.source_id: source for source in included_sources(V2_REGISTRY_PATH)}
    original_sources = {source.source_id: source for source in included_sources()}

    assert (total, included, reference_only) == (23, 15, 8)
    assert set(original_sources).issubset(sources)
    assert all(sources[source_id] == source for source_id, source in original_sources.items())
    assert {
        "rpi-doc-power-supplies",
        "rpi-doc-boot-nvme",
        "rpi-doc-external-storage",
        "rpi-doc-keyboard-computers",
        "rpi-doc-raspberry-pi-connect",
        "rpi-doc-interfaces",
    }.issubset(sources)
    assert sources["rpi-doc-boot-nvme"].product_models == ["Raspberry Pi 5"]
    assert sources["rpi-doc-keyboard-computers"].product_models == [
        "Raspberry Pi 500",
        "Raspberry Pi 400",
    ]
    assert sources["rpi-doc-raspberry-pi-connect"].official_verified is True
