"""Canonical text passed to the multilingual E5 document encoder."""

from __future__ import annotations


def build_retrieval_text(*, title: str, section: str, content: str) -> str:
    """Add document context without changing the citation-safe source text."""

    return f"Title: {title}\nSection: {section}\n\n{content}"


def build_e5_passage(*, title: str, section: str, content: str) -> str:
    """Return the exact string expected by an E5 document embedding model."""

    return f"passage: {build_retrieval_text(title=title, section=section, content=content)}"
