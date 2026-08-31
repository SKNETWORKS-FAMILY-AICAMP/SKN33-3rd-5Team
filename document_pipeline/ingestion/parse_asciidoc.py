"""Parse the approved AsciiDoc corpus into citation-safe semantic blocks."""
from __future__ import annotations

import html
import re
import unicodedata
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
TABLE_CELL_DELIMITER = re.compile(r"(?:^|(?<=\s))(?P<style>[.\^<>]*a?)\|")
TABLE_COLUMNS = re.compile(r'(?:^|,)\s*cols="(?P<cols>[^"]+)"')
BLOCK_TITLE = re.compile(r"^\.(?P<title>[^.\s].*)$")
DESCRIPTION_TERM = re.compile(r"^(?P<label>\S.*?)::$")
COMMENT_DELIMITER = "////"
CODE_DELIMITERS = {"----", "....", "++++"}
ADMONITIONS = {"NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION"}
ATTRIBUTE_SUBSTITUTIONS = {"cpp": "C++"}


@dataclass(frozen=True)
class ListItem:
    level: int
    text: str


@dataclass(frozen=True)
class ParsedBlock:
    """A semantic unit that must not be flattened before chunking."""

    kind: Literal["paragraph", "list", "code", "admonition", "table", "image", "tab"]
    text: str = ""
    ordered: bool | None = None
    items: tuple[ListItem, ...] = ()
    language: str | None = None
    severity: str | None = None
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    target: str | None = None
    alt_text: str | None = None
    caption: str | None = None
    label: str | None = None
    blocks: tuple["ParsedBlock", ...] = ()
    issues: tuple[str, ...] = ()


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
    for name, replacement in ATTRIBUTE_SUBSTITUTIONS.items():
        value = value.replace(f"{{{name}}}", replacement)
    value = re.sub(r"<<[^,>]+,\s*([^>]+)>>", r"\1", value)
    value = re.sub(r"<<([^>]+)>>", r"\1", value)
    value = re.sub(r"(?:xref|link):[^\[]+\[([^\]]+)\]", r"\1", value)
    value = re.sub(r"https?://[^\[]+\[([^\]]+)\]", r"\1", value)
    value = re.sub(r"<([^>]+)>", r"\1", value)
    value = html.unescape(value).replace("**", "").replace("__", "")
    value = unicodedata.normalize("NFC", value)
    return re.sub(r"[\t\u2002\u2003]+", " ", value).strip()


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


def _table_column_count(attribute: str | None) -> int | None:
    if not attribute:
        return None
    match = TABLE_COLUMNS.search(attribute)
    if not match:
        return None
    columns = [column.strip() for column in match.group("cols").split(",") if column.strip()]
    return len(columns) or None


def _append_cell_text(cells: list[str], value: str) -> None:
    cleaned = _clean_inline(value)
    if not cleaned:
        return
    if not cells:
        cells.append(cleaned)
        return
    cells[-1] = "\n".join(part for part in (cells[-1], cleaned) if part)


def _read_table(
    lines: list[str],
    start: int,
    *,
    attribute: str | None,
    caption: str | None,
) -> tuple[ParsedBlock, int]:
    """Keep logical rows even when AsciiDoc writes one cell per physical line."""
    cells: list[str] = []
    declared_width = _table_column_count(attribute)
    inferred_width: int | None = None
    last_cell_caption: str | None = None
    index = start + 1
    while index < len(lines) and not TABLE_DELIMITER.match(lines[index].strip()):
        raw = lines[index].rstrip()
        stripped = raw.strip()
        if not stripped:
            index += 1
            continue
        block_title = BLOCK_TITLE.match(stripped)
        if block_title and cells:
            last_cell_caption = _clean_inline(block_title.group("title"))
            _append_cell_text(cells, last_cell_caption)
            index += 1
            continue
        image = IMAGE.match(raw)
        if image and cells:
            alt = _parse_image_attribute(image.group("attributes"))
            cleaned_alt = _clean_inline(alt) if alt else None
            if cleaned_alt and cleaned_alt != last_cell_caption and cleaned_alt not in cells[-1].splitlines():
                _append_cell_text(cells, f"Image: {cleaned_alt}")
            index += 1
            continue
        delimiters = list(TABLE_CELL_DELIMITER.finditer(raw))
        if delimiters:
            leading = raw[: delimiters[0].start()]
            if leading.strip():
                _append_cell_text(cells, leading)
            values = [
                raw[match.end() : delimiters[offset + 1].start() if offset + 1 < len(delimiters) else len(raw)]
                for offset, match in enumerate(delimiters)
            ]
            cells.extend(_clean_inline(value) for value in values)
            if inferred_width is None and delimiters[0].start() == 0 and len(values) > 1:
                inferred_width = len(values)
            last_cell_caption = None
        elif cells and not BLOCK_ATTRIBUTE.match(stripped):
            continuation = LIST_ITEM.match(raw)
            if continuation:
                marker_text = "-" if continuation.group("marker").startswith("*") else "1."
                text = f"{marker_text} {_clean_inline(continuation.group('text'))}"
            else:
                text = _clean_inline(raw)
            if text:
                _append_cell_text(cells, text)
        index += 1
    if index == len(lines):
        raise ValueError("unclosed AsciiDoc table")
    width = declared_width or inferred_width or 1
    issues: list[str] = []
    if len(cells) % width:
        issues.append(f"table_cell_count_not_divisible_by_columns:{len(cells)}:{width}")
        cells.extend("" for _ in range(width - len(cells) % width))
    rows = [tuple(cells[offset : offset + width]) for offset in range(0, len(cells), width)]
    headers = rows[0] if rows else ()
    return (
        ParsedBlock(
            kind="table",
            headers=headers,
            rows=tuple(rows[1:]),
            caption=caption,
            issues=tuple(issues),
        ),
        index + 1,
    )


def _parse_tabs(lines: list[str]) -> tuple[ParsedBlock, ...]:
    branches: list[tuple[str, list[str]]] = []
    current_label: str | None = None
    current_lines: list[str] = []
    for raw in lines:
        term = DESCRIPTION_TERM.match(raw.strip())
        if term:
            if current_label is not None:
                branches.append((current_label, current_lines))
            current_label = _clean_inline(term.group("label"))
            current_lines = []
            continue
        if current_label is None and raw.strip() and raw.strip() != "+":
            current_lines.append(raw)
            continue
        current_lines.append(raw)
    if current_label is not None:
        branches.append((current_label, current_lines))
    if not branches:
        text = "\n".join(line for line in lines if line.strip() != "+").strip()
        return (
            ParsedBlock(
                kind="tab",
                label="Unlabelled tab",
                text=text,
                issues=("tab_has_no_description_labels",),
            ),
        )

    parsed: list[ParsedBlock] = []
    for label, branch_lines in branches:
        branch_text = "\n".join(branch_lines)
        sections = parse_asciidoc(branch_text, fallback_title=label)
        branch_blocks = tuple(block for section in sections for block in section.blocks)
        parsed.append(ParsedBlock(kind="tab", label=label, blocks=branch_blocks))
    return tuple(parsed)


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
    pending_caption: str | None = None
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
            pending_caption = None
            index += 1
            continue
        if ATTRIBUTE.match(raw):
            index += 1
            continue
        if not stripped:
            flush_pending()
            index += 1
            continue
        if stripped == "+":
            # AsciiDoc continuation markers connect blocks but carry no searchable text.
            index += 1
            continue
        block_title = BLOCK_TITLE.match(stripped)
        if block_title:
            flush_pending()
            pending_caption = _clean_inline(block_title.group("title"))
            index += 1
            continue
        if TABLE_DELIMITER.match(stripped):
            flush_pending()
            table, index = _read_table(
                lines,
                index,
                attribute=pending_attribute,
                caption=pending_caption,
            )
            current_blocks.append(table)
            pending_attribute = None
            pending_caption = None
            continue
        attribute = BLOCK_ATTRIBUTE.match(stripped)
        if attribute:
            pending_attribute = attribute.group("value")
            index += 1
            continue
        image = IMAGE.match(raw)
        if image:
            flush_pending()
            alt_text = _parse_image_attribute(image.group("attributes"))
            current_blocks.append(
                ParsedBlock(
                    kind="image",
                    target=image.group("target").strip(),
                    alt_text=_clean_inline(alt_text) if alt_text else None,
                    caption=pending_caption,
                )
            )
            pending_attribute = None
            pending_caption = None
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
        if stripped == "======" and pending_attribute == "tabs":
            flush_pending()
            body, index = _read_delimited(lines, index, stripped)
            current_blocks.extend(_parse_tabs(body))
            pending_attribute = None
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
        if pending_caption:
            paragraph_lines.append(pending_caption)
            pending_caption = None
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
        rendered = "\n".join(" | ".join(cell for cell in row) for row in rows if row)
        return "\n".join(part for part in (block.caption, rendered) if part)
    if block.kind == "image":
        description = block.alt_text or block.target or ""
        if block.caption and block.caption != description:
            description = f"{block.caption}: {description}"
        return f"[IMAGE] {description}".strip()
    if block.kind == "tab":
        body = "\n\n".join(render_block(child) for child in block.blocks)
        if not body and block.text:
            body = block.text
        return f"[{block.label or 'Tab'}]\n{body}".strip()
    raise ValueError(f"unsupported parsed block: {block.kind}")
