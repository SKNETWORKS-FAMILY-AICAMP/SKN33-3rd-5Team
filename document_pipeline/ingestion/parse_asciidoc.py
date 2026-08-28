"""Parse the approved AsciiDoc corpus into citation-safe semantic blocks."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal


HEADING = re.compile(r"^(?P<level>={1,6})\s+(?P<title>.+?)\s*$")
ATTRIBUTE = re.compile(r"^:[A-Za-z0-9_-]+!?:")
EXPLICIT_ANCHOR = re.compile(r"^\[\[(?P<anchor>[^\]]+)\]\]$")
BLOCK_ATTRIBUTE = re.compile(r"^\[(?P<value>[^\]]+)\]$")
LIST_ITEM = re.compile(r"^(?P<marker>\*+|\.+)\s+(?P<text>.+)$")
IMAGE = re.compile(r"^image::(?P<target>[^\[]+)\[(?P<attributes>.*)\]$")
ADMONITION_INLINE = re.compile(r"^(?P<kind>NOTE|TIP|IMPORTANT|WARNING|CAUTION):\s*(?P<text>.+)$")
TABLE_DELIMITER = re.compile(r"^\|={3,}$")
TABLE_CELL = re.compile(r"^(?:[.\^<>]*a)?\|(?P<value>.*)$")
COMMENT_DELIMITER = "////"
CODE_DELIMITERS = {"----", "....", "++++"}
ADMONITIONS = {"NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION"}


@dataclass(frozen=True)
class ListItem:
    level: int
    text: str


@dataclass(frozen=True)
class ParsedBlock:
    """A semantic unit that must not be flattened before chunking."""

    kind: Literal["paragraph", "list", "code", "admonition", "table", "image"]
    text: str = ""
    ordered: bool | None = None
    items: tuple[ListItem, ...] = ()
    language: str | None = None
    severity: str | None = None
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    target: str | None = None
    alt_text: str | None = None


@dataclass(frozen=True)
class ParsedSection:
    title: str
    level: int
    heading_path: tuple[str, ...]
    source_anchor: str | None
    blocks: tuple[ParsedBlock, ...]


def section_to_dict(section: ParsedSection) -> dict[str, object]:
    """Serialize the intermediate representation for local inspection."""
    return asdict(section)


def _clean_inline(value: str) -> str:
    """Remove display markup without removing visible source text or code content."""
    value = re.sub(r"<<[^,>]+,\s*([^>]+)>>", r"\1", value)
    value = re.sub(r"<<([^>]+)>>", r"\1", value)
    value = re.sub(r"(?:xref|link):[^\[]+\[([^\]]+)\]", r"\1", value)
    value = re.sub(r"https?://[^\[]+\[([^\]]+)\]", r"\1", value)
    value = re.sub(r"<([^>]+)>", r"\1", value)
    return value.replace("**", "").replace("__", "").strip()


def _parse_source_attribute(value: str) -> str | None:
    parts = [part.strip() for part in value.split(",")]
    if not parts or parts[0] != "source":
        return None
    if len(parts) < 2:
        return "text"
    return parts[1].split("?", 1)[0] or "text"


def _parse_image_attribute(attributes: str) -> str | None:
    match = re.search(r'(?:^|,)\s*alt="(?P<alt>[^"]+)"', attributes)
    if match:
        return match.group("alt")
    first = attributes.split(",", 1)[0].strip()
    return first or None


def _read_delimited(lines: list[str], start: int, delimiter: str) -> tuple[list[str], int]:
    body: list[str] = []
    index = start + 1
    while index < len(lines) and lines[index].strip() != delimiter:
        body.append(lines[index].rstrip("\n"))
        index += 1
    if index == len(lines):
        raise ValueError(f"unclosed AsciiDoc block delimiter: {delimiter}")
    return body, index + 1


def _read_table(lines: list[str], start: int) -> tuple[ParsedBlock, int]:
    """Keep column order for the pipe tables used by Raspberry Pi docs."""
    cells: list[str] = []
    first_row_width: int | None = None
    index = start + 1
    while index < len(lines) and not TABLE_DELIMITER.match(lines[index].strip()):
        raw = lines[index].rstrip()
        image = IMAGE.match(raw)
        if image and cells:
            alt = _parse_image_attribute(image.group("attributes"))
            if alt:
                cells[-1] = "\n".join(part for part in (cells[-1], f"Image: {alt}") if part)
            index += 1
            continue
        marker = TABLE_CELL.match(raw)
        if marker:
            values = marker.group("value").split("|")
            cleaned_values = [_clean_inline(value) for value in values]
            if first_row_width is None:
                first_row_width = len(cleaned_values)
            cells.extend(cleaned_values)
        elif cells and raw.strip() and not BLOCK_ATTRIBUTE.match(raw.strip()):
            continuation = LIST_ITEM.match(raw)
            if continuation:
                marker_text = "-" if continuation.group("marker").startswith("*") else "1."
                text = f"{marker_text} {_clean_inline(continuation.group('text'))}"
            else:
                text = _clean_inline(raw)
            if text:
                cells[-1] = "\n".join(part for part in (cells[-1], text) if part)
        index += 1
    if index == len(lines):
        raise ValueError("unclosed AsciiDoc table")
    width = first_row_width or 1
    rows = [tuple(cells[offset : offset + width]) for offset in range(0, len(cells), width)]
    headers = rows[0] if rows else ()
    return ParsedBlock(kind="table", headers=headers, rows=tuple(rows[1:])), index + 1


def parse_asciidoc(text: str, *, fallback_title: str) -> list[ParsedSection]:
    """Read headings, anchors and block boundaries without losing their meaning."""
    lines = text.splitlines()
    sections: list[ParsedSection] = []
    heading_stack: list[tuple[int, str]] = []
    current_title = fallback_title
    current_level = 0
    current_anchor: str | None = None
    current_blocks: list[ParsedBlock] = []
    paragraph_lines: list[str] = []
    list_items: list[ListItem] = []
    list_ordered: bool | None = None
    pending_anchor: str | None = None
    pending_attribute: str | None = None
    in_comment = False

    def flush_paragraph() -> None:
        if paragraph_lines:
            current_blocks.append(ParsedBlock(kind="paragraph", text="\n".join(paragraph_lines)))
            paragraph_lines.clear()

    def flush_list() -> None:
        nonlocal list_ordered
        if list_items:
            current_blocks.append(ParsedBlock(kind="list", ordered=list_ordered, items=tuple(list_items)))
            list_items.clear()
        list_ordered = None

    def flush_pending() -> None:
        flush_paragraph()
        flush_list()

    def flush_section() -> None:
        flush_pending()
        if not current_blocks:
            return
        path = tuple(title for _, title in heading_stack) or (current_title,)
        sections.append(
            ParsedSection(
                title=current_title,
                level=current_level,
                heading_path=path,
                source_anchor=current_anchor,
                blocks=tuple(current_blocks),
            )
        )
        current_blocks.clear()

    index = 0
    while index < len(lines):
        raw = lines[index].rstrip()
        stripped = raw.strip()
        if stripped == COMMENT_DELIMITER:
            in_comment = not in_comment
            index += 1
            continue
        if in_comment:
            index += 1
            continue
        anchor = EXPLICIT_ANCHOR.match(stripped)
        if anchor:
            pending_anchor = anchor.group("anchor")
            index += 1
            continue
        heading = HEADING.match(raw)
        if heading:
            flush_section()
            current_level = len(heading.group("level"))
            current_title = _clean_inline(heading.group("title"))
            heading_stack[:] = [(level, title) for level, title in heading_stack if level < current_level]
            heading_stack.append((current_level, current_title))
            current_anchor, pending_anchor = pending_anchor, None
            index += 1
            continue
        if ATTRIBUTE.match(raw):
            index += 1
            continue
        if not stripped:
            flush_pending()
            index += 1
            continue
        if TABLE_DELIMITER.match(stripped):
            flush_pending()
            table, index = _read_table(lines, index)
            current_blocks.append(table)
            pending_attribute = None
            continue
        attribute = BLOCK_ATTRIBUTE.match(stripped)
        if attribute:
            pending_attribute = attribute.group("value")
            index += 1
            continue
        image = IMAGE.match(raw)
        if image:
            flush_pending()
            current_blocks.append(
                ParsedBlock(
                    kind="image",
                    target=image.group("target").strip(),
                    alt_text=_parse_image_attribute(image.group("attributes")),
                )
            )
            pending_attribute = None
            index += 1
            continue
        if stripped in CODE_DELIMITERS:
            flush_pending()
            body, index = _read_delimited(lines, index, stripped)
            language = _parse_source_attribute(pending_attribute or "")
            current_blocks.append(ParsedBlock(kind="code", text="\n".join(body), language=language))
            pending_attribute = None
            continue
        if stripped in {"====", "____"} and pending_attribute in ADMONITIONS:
            flush_pending()
            body, index = _read_delimited(lines, index, stripped)
            current_blocks.append(
                ParsedBlock(kind="admonition", severity=pending_attribute, text="\n".join(body).strip())
            )
            pending_attribute = None
            continue
        if stripped in {"====", "======"} and pending_attribute == "tabs":
            # Tabs are presentation-only; their labelled content remains as ordinary blocks.
            pending_attribute = None
            index += 1
            continue
        inline_admonition = ADMONITION_INLINE.match(raw)
        if inline_admonition:
            flush_pending()
            current_blocks.append(
                ParsedBlock(
                    kind="admonition",
                    severity=inline_admonition.group("kind"),
                    text=_clean_inline(inline_admonition.group("text")),
                )
            )
            pending_attribute = None
            index += 1
            continue
        item = LIST_ITEM.match(raw)
        if item:
            flush_paragraph()
            ordered = item.group("marker").startswith(".")
            if list_items and list_ordered != ordered:
                flush_list()
            list_ordered = ordered
            list_items.append(ListItem(level=len(item.group("marker")), text=_clean_inline(item.group("text"))))
            pending_attribute = None
            index += 1
            continue
        if pending_attribute and pending_attribute.startswith("source"):
            # A malformed source attribute must not leak into RAG text.
            pending_attribute = None
        flush_list()
        paragraph_lines.append(_clean_inline(raw))
        index += 1
    flush_section()
    if not sections:
        raise ValueError(f"no readable sections found in AsciiDoc document: {fallback_title}")
    return sections


def render_block(block: ParsedBlock) -> str:
    """Render a semantic block to retrieval text while retaining its structure."""
    if block.kind == "paragraph":
        return block.text
    if block.kind == "list":
        prefix = "1." if block.ordered else "-"
        return "\n".join(f"{'  ' * (item.level - 1)}{prefix} {item.text}" for item in block.items)
    if block.kind == "code":
        language = block.language or "text"
        return f"```{language}\n{block.text}\n```"
    if block.kind == "admonition":
        return f"[{block.severity}]\n{block.text}"
    if block.kind == "table":
        rows = [block.headers, *block.rows]
        return "\n".join(" | ".join(cell for cell in row) for row in rows if row)
    if block.kind == "image":
        return f"[IMAGE] {block.alt_text or block.target or ''}".strip()
    raise ValueError(f"unsupported parsed block: {block.kind}")
