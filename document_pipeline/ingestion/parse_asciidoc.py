"""Small, dependency-free AsciiDoc parser for the approved documentation corpus."""
from __future__ import annotations

import re
from dataclasses import dataclass


HEADING = re.compile(r"^(?P<level>={1,6})\s+(?P<title>.+?)\s*$")
ATTRIBUTE = re.compile(r"^:[A-Za-z0-9_-]+!?:")
DIRECTIVE = re.compile(r"^(?:include|image|video|link):")
BLOCK_DELIMITER = re.compile(r"^(?:-{4,}|\.{4,}|_{4,}|\*{4,}|\+{4,}|={4,})$")
HTML_TAG = re.compile(r"<[^>]+>")
NON_SLUG = re.compile(r"[^a-z0-9]+")
EXPLICIT_ANCHOR = re.compile(r"^\[\[[^\]]+\]\]$")
BRACKETED_BLOCK = re.compile(r"^\[[A-Za-z0-9_-]+(?:=[^\]]+)?\]$")
XREF_WITH_LABEL = re.compile(r"(?:xref:[^\[]+|link:[^\[]+)\[([^\]]+)\]")
ANGLE_XREF_WITH_LABEL = re.compile(r"<<[^,>]+,\s*([^>]+)>>")
ANGLE_XREF = re.compile(r"<<([^>]+)>>")
TABLE_MARKUP = re.compile(r"^(?:[.\^<>]*a)?\|$")
TABLE_DELIMITER = re.compile(r"^\|={3,}$")


@dataclass(frozen=True)
class ParsedSection:
    title: str
    level: int
    body: str


def anchor_for(title: str) -> str:
    """Produce a predictable AsciiDoc-style anchor for citation metadata."""
    normalized = NON_SLUG.sub("-", title.lower()).strip("-")
    return normalized or "document"


def _clean_line(line: str) -> str:
    line = ANGLE_XREF_WITH_LABEL.sub(r"\1", line)
    line = ANGLE_XREF.sub(r"\1", line)
    line = XREF_WITH_LABEL.sub(r"\1", line)
    line = HTML_TAG.sub("", line).strip()
    line = line.replace("**", "").replace("__", "")
    line = re.sub(r"^(?:[.\^<>]*a)?\|\s*", "", line)
    line = re.sub(r"\s+\|\s*", " | ", line)
    line = re.sub(r"^\.(?=[A-Z0-9])", "", line)
    if line.endswith("::"):
        line = line[:-1]
    line = re.sub(r"^(?:\*\s+|\.\s+|\d+\.\s+)", "", line)
    return re.sub(r"\s+", " ", line)


def parse_asciidoc(text: str, *, fallback_title: str) -> list[ParsedSection]:
    """Extract readable prose by section while excluding directives and metadata.

    Code blocks are preserved: Raspberry Pi commands are useful retrieval evidence.
    """
    current_title = fallback_title
    current_level = 0
    buffer: list[str] = []
    sections: list[ParsedSection] = []
    in_comment = False

    def flush() -> None:
        content = "\n".join(buffer).strip()
        if content:
            sections.append(ParsedSection(title=current_title, level=current_level, body=content))
        buffer.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.strip() == "////":
            in_comment = not in_comment
            continue
        if (
            in_comment
            or not line.strip()
            or ATTRIBUTE.match(line)
            or DIRECTIVE.match(line)
            or EXPLICIT_ANCHOR.match(line.strip())
            or BRACKETED_BLOCK.match(line.strip())
            or TABLE_MARKUP.match(line.strip())
            or TABLE_DELIMITER.match(line.strip())
            or line.strip() == "+"
        ):
            continue
        heading = HEADING.match(line)
        if heading:
            flush()
            current_level = len(heading.group("level"))
            current_title = _clean_line(heading.group("title"))
            continue
        if BLOCK_DELIMITER.match(line.strip()):
            continue
        cleaned = _clean_line(line)
        if cleaned:
            buffer.append(cleaned)
    flush()

    if not sections:
        raise ValueError(f"no readable sections found in AsciiDoc document: {fallback_title}")

    return sections
