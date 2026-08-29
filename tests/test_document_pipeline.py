from __future__ import annotations

from pathlib import Path

from document_pipeline.ingestion.build_manifest import (
    _near_duplicate_pairs,
    _remove_exact_duplicates,
    block_quality_issues,
    build_manifest,
    chunk_section,
    chunk_section_drafts,
    product_models_for,
)
from document_pipeline.ingestion.parse_asciidoc import ParsedBlock, parse_asciidoc, render_block
from src.contracts.retrieval_text import build_e5_passage
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


def test_parser_uses_declared_columns_for_multiline_led_table() -> None:
    """Regression fixture from rpi-doc-led-warning-codes.adoc."""
    source = """== LED behaviour

.Power and activity LEDs by Raspberry Pi model
[cols="1,1,1,1",options="header"]
|===
| Models
| LED count
| LED colours
| MicroSD card activity indication

| Raspberry Pi 1, 2, 3, and 4
| 2 (1 power LED and 1 activity LED)
| Red and green
| Green LED flashes during activity
|===
"""

    table = parse_asciidoc(source, fallback_title="fallback")[0].blocks[0]

    assert table.kind == "table"
    assert table.caption == "Power and activity LEDs by Raspberry Pi model"
    assert table.headers == (
        "Models",
        "LED count",
        "LED colours",
        "MicroSD card activity indication",
    )
    assert table.rows == (
        (
            "Raspberry Pi 1, 2, 3, and 4",
            "2 (1 power LED and 1 activity LED)",
            "Red and green",
            "Green LED flashes during activity",
        ),
    )


def test_parser_keeps_hardware_model_caption_inside_its_table_cell() -> None:
    """Regression fixture from rpi-doc-hardware-introduction.adoc."""
    source = """== Introduction

[cols="3a,1,1,1,2"]
|===
| Model | SoC | Memory | GPIO | Wireless Connectivity

^.^a|
.Raspberry Pi Zero W
image::images/zero-w.jpg[alt="Raspberry Pi Zero W"]
| BCM2835 | 512 MB | 40-pin GPIO header (unpopulated)
a|
* 2.4 GHz single-band 802.11n Wi-Fi
* Bluetooth 4.0
|===
"""

    table = parse_asciidoc(source, fallback_title="fallback")[0].blocks[0]

    assert table.headers == ("Model", "SoC", "Memory", "GPIO", "Wireless Connectivity")
    assert table.rows == (
        (
            "Raspberry Pi Zero W",
            "BCM2835",
            "512 MB",
            "40-pin GPIO header (unpopulated)",
            "- 2.4 GHz single-band 802.11n Wi-Fi\n- Bluetooth 4.0",
        ),
    )
    assert not table.issues


def test_parser_preserves_tabs_and_removes_asciidoc_continuations() -> None:
    """Regression fixture from rpi-doc-networking.adoc."""
    source = """[[find-networks]]
== Find networks

[tabs]
======
Desktop::
Select the wireless icon.
+
.Wireless Manager menu
image::images/wifi2.jpg[wifi2]
+
CLI::
Run the following command:
+
[source,console]
----
$ nmcli dev wifi list
----
======
"""

    section = parse_asciidoc(source, fallback_title="fallback")[0]

    assert [block.kind for block in section.blocks] == ["tab", "tab"]
    assert [block.label for block in section.blocks] == ["Desktop", "CLI"]
    rendered = "\n\n".join(render_block(block) for block in section.blocks)
    assert "[Desktop]" in rendered
    assert "Wireless Manager menu" in rendered
    assert "[CLI]" in rendered
    assert "$ nmcli dev wifi list" in rendered
    assert "\n+\n" not in rendered
    assert "======" not in rendered
    assert "Desktop::" not in rendered


def test_attribute_substitution_is_block_aware() -> None:
    source = """== Camera

The library provides a {cpp} API.

[source,cpp]
----
std::map<std::string, {literal}> values;
----
"""

    section = parse_asciidoc(source, fallback_title="fallback")[0]

    assert section.blocks[0].text == "The library provides a C++ API."
    assert "{literal}" in section.blocks[1].text


def test_quality_gate_ignores_code_literals_but_flags_narrative_residue() -> None:
    assert block_quality_issues(ParsedBlock(kind="code", text="echo {literal}")) == ()
    assert block_quality_issues(ParsedBlock(kind="paragraph", text="Unknown {literal} value")) == (
        "unresolved_asciidoc_attribute",
    )


def test_malformed_table_is_preserved_for_review() -> None:
    source = """== Broken table

[cols="1,1"]
|===
| Key | Value
| incomplete
|===
"""
    section = parse_asciidoc(source, fallback_title="fallback")[0]
    table = section.blocks[0]

    assert table.kind == "table"
    assert table.issues == ("table_cell_count_not_divisible_by_columns:3:2",)
    drafts = chunk_section_drafts(section, tokenizer=FakeE5Tokenizer(), target_tokens=80, max_tokens=100)
    assert drafts[0].quality_issues == table.issues


def test_chunk_limit_counts_title_section_and_passage_prefix() -> None:
    source = """== Very descriptive network section

One two three four five six seven eight. Nine ten eleven twelve thirteen fourteen fifteen sixteen.
"""
    section = parse_asciidoc(source, fallback_title="fallback")[0]
    tokenizer = FakeE5Tokenizer()
    drafts = chunk_section_drafts(
        section,
        tokenizer=tokenizer,
        document_title="Long official Raspberry Pi document title",
        target_tokens=20,
        max_tokens=24,
        overlap_tokens=0,
    )

    assert len(drafts) == 2
    for draft in drafts:
        passage = build_e5_passage(
            title="Long official Raspberry Pi document title",
            section="Very descriptive network section",
            content=draft.content,
        )
        assert len(tokenizer.encode(passage)) <= 24


def test_exact_duplicates_are_removed_and_near_duplicates_are_review_only() -> None:
    repeated = " ".join(f"word{index}" for index in range(30))
    duplicate = {
        "document_id": "doc",
        "chunk_id": "doc-000",
        "chunk_index": 0,
        "title": "Title",
        "section": "Section",
        "content": repeated,
        "source_url": "https://example.com",
        "source_anchor": None,
        "chunk_checksum": "same",
    }
    chunks = [
        duplicate,
        {**duplicate, "chunk_id": "doc-001", "chunk_index": 1},
        {
            **duplicate,
            "chunk_id": "doc-002",
            "chunk_index": 2,
            "content": repeated + " extra",
            "chunk_checksum": "near",
        },
    ]

    unique, rejected = _remove_exact_duplicates(chunks)

    assert [chunk["chunk_id"] for chunk in unique] == ["doc-000", "doc-002"]
    assert rejected[0]["quality_status"] == "rejected"
    near_pairs = _near_duplicate_pairs(unique, threshold=0.8)
    assert near_pairs == [
        {
            "left_chunk_id": "doc-000",
            "right_chunk_id": "doc-002",
            "jaccard_similarity": near_pairs[0]["jaccard_similarity"],
            "quality_status": "needs_review",
        }
    ]


def test_product_model_tags_use_curated_exact_names() -> None:
    assert product_models_for("Raspberry Pi 500 keyboard computer") == ["Raspberry Pi 500"]
    assert product_models_for("Raspberry Pi 5 single-board computer") == ["Raspberry Pi 5"]
    assert product_models_for("A generic Raspberry Pi board") == []


def test_manifest_chunks_are_deterministic_for_the_same_input(tmp_path) -> None:
    raw_root = Path(__file__).resolve().parents[1] / "document_pipeline" / "data" / "raw"
    first = build_manifest(
        raw_root=raw_root,
        output_path=tmp_path / "first.json",
        processed_root=tmp_path / "first-processed",
        tokenizer=FakeE5Tokenizer(),
        tokenizer_name="fake-e5",
        tokenizer_revision="fake-revision",
    )
    second = build_manifest(
        raw_root=raw_root,
        output_path=tmp_path / "second.json",
        processed_root=tmp_path / "second-processed",
        tokenizer=FakeE5Tokenizer(),
        tokenizer_name="fake-e5",
        tokenizer_revision="fake-revision",
    )

    assert first["processing"] == second["processing"]
    assert [
        (chunk["chunk_id"], chunk["chunk_checksum"], chunk["embedding_checksum"])
        for chunk in first["chunks"]
    ] == [
        (chunk["chunk_id"], chunk["chunk_checksum"], chunk["embedding_checksum"])
        for chunk in second["chunks"]
    ]


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
            "embedding_checksum": "sha256:" + "c" * 64,
            "parser_version": "asciidoc-semantic-3.0.0",
            "official_verified": True,
            "quality_status": "approved",
            "image_url": None,
            "video_url": None,
        }
    )

    assert chunk.retrieved_at == "2026-08-28"
    assert chunk.use_cases == ("headless_remote_management",)
    assert chunk.official_verified is True
    assert chunk.quality_status == "approved"
    assert chunk.source_anchor == "ssh"
