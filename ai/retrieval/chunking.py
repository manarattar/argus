"""Structure-aware chunking for policy and evidence documents.

Naive fixed-width chunking would defeat two of ARGUS's requirements at once:
citations must name a section a human can look up, and policy clauses must be
retrievable by their numbering. So the splitter is driven by the document's own
headings, and every chunk carries the section path it came from.

The corpus is authored as Markdown-flavoured plain text with numbered headings
(``## 4. Customer Concentration``, ``### 4.2 Single-name limits``), which makes
``CRF 4.2`` a deterministic citation key rather than something a model invents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Headings: markdown hashes, optionally followed by a dotted clause number.
_HEADING = re.compile(r"^(#{1,4})\s+(?:([0-9]+(?:\.[0-9]+)*)\.?\s+)?(.+?)\s*$", re.MULTILINE)
_PAGE_MARK = re.compile(r"^\s*<!--\s*page:\s*(\d+)\s*-->\s*$", re.MULTILINE)

# Chunk sizing, in characters. Large enough to hold a complete clause with its
# context, small enough that a retrieved chunk is still readable in a citation
# popover. Overlap preserves sentences that straddle a boundary.
TARGET_CHUNK_CHARS = 1100
MAX_CHUNK_CHARS = 1600
OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 120


@dataclass
class Chunk:
    """A retrievable unit of a document, with everything needed to cite it."""

    chunk_id: str
    document_id: str
    text: str
    ordinal: int
    section_number: str = ""
    section_title: str = ""
    page: int | None = None
    heading_path: list[str] = field(default_factory=list)

    @property
    def citation_key(self) -> str:
        """Stable, human-checkable locator used in evidence and policy citations."""
        parts: list[str] = []
        if self.page is not None:
            parts.append(f"p. {self.page}")
        if self.section_number:
            parts.append(f"§{self.section_number}")
        elif self.section_title:
            parts.append(self.section_title)
        return ", ".join(parts) or f"chunk {self.ordinal + 1}"

    @property
    def display_heading(self) -> str:
        if self.section_number and self.section_title:
            return f"{self.section_number} {self.section_title}"
        return self.section_title or f"Part {self.ordinal + 1}"


@dataclass(frozen=True)
class _Section:
    level: int
    number: str
    title: str
    body: str
    start: int
    path: list[str]


def _page_at(offset: int, page_marks: list[tuple[int, int]]) -> int | None:
    """Page number in force at a character offset, if the document is paginated."""
    current: int | None = None
    for pos, page in page_marks:
        if pos <= offset:
            current = page
        else:
            break
    return current


def _split_sections(text: str) -> list[_Section]:
    """Split on headings, tracking the heading path down the hierarchy."""
    matches = list(_HEADING.finditer(text))
    if not matches:
        return [_Section(level=1, number="", title="", body=text, start=0, path=[])]

    sections: list[_Section] = []
    preamble = text[: matches[0].start()].strip()
    if len(preamble) >= MIN_CHUNK_CHARS:
        sections.append(_Section(1, "", "Preamble", preamble, 0, []))

    stack: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        level = len(match.group(1))
        number = match.group(2) or ""
        title = match.group(3).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()

        while stack and stack[-1][0] >= level:
            stack.pop()
        path = [label for _, label in stack]
        stack.append((level, f"{number} {title}".strip()))

        if body:
            sections.append(_Section(level, number, title, body, match.start(), path))
    return sections


def _pack_paragraphs(body: str) -> list[str]:
    """Group paragraphs into chunks near the target size, splitting only if forced."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks: list[str] = []
    buffer = ""

    for para in paragraphs:
        if len(para) > MAX_CHUNK_CHARS:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_split_long_paragraph(para))
            continue
        candidate = f"{buffer}\n\n{para}".strip() if buffer else para
        if len(candidate) > TARGET_CHUNK_CHARS and buffer:
            chunks.append(buffer)
            tail = buffer[-OVERLAP_CHARS:] if len(buffer) > OVERLAP_CHARS else ""
            buffer = f"{tail}\n\n{para}".strip() if tail else para
        else:
            buffer = candidate

    if buffer:
        chunks.append(buffer)
    return chunks


def _split_long_paragraph(para: str) -> list[str]:
    """Last resort: break an oversized paragraph on sentence boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", para)
    out: list[str] = []
    buffer = ""
    for sentence in sentences:
        candidate = f"{buffer} {sentence}".strip()
        if len(candidate) > TARGET_CHUNK_CHARS and buffer:
            out.append(buffer)
            buffer = sentence
        else:
            buffer = candidate
    if buffer:
        out.append(buffer)
    return out


def chunk_document(document_id: str, text: str) -> list[Chunk]:
    """Split a document into citable chunks.

    Args:
        document_id: Identifier the chunks will be attributed to.
        text: Full document text, optionally carrying ``<!-- page: N -->``
            markers to support page-level citation.

    Returns:
        Chunks in reading order, each with a deterministic id of the form
        ``{document_id}::c{ordinal}``.
    """
    page_marks = [(m.start(), int(m.group(1))) for m in _PAGE_MARK.finditer(text)]
    clean = _PAGE_MARK.sub("", text)
    # Re-measure page offsets against the cleaned text so citations stay accurate.
    if page_marks:
        page_marks = _reindex_page_marks(text, page_marks)

    chunks: list[Chunk] = []
    ordinal = 0
    for section in _split_sections(clean):
        for body in _pack_paragraphs(section.body):
            if len(body) < MIN_CHUNK_CHARS and chunks:
                # Absorb a stub into the previous chunk rather than emit a
                # fragment that cannot stand as a citation on its own.
                chunks[-1].text = f"{chunks[-1].text}\n\n{body}"
                continue
            heading_line = f"{section.number} {section.title}".strip()
            chunks.append(
                Chunk(
                    chunk_id=f"{document_id}::c{ordinal}",
                    document_id=document_id,
                    text=(f"{heading_line}\n\n{body}" if heading_line else body),
                    ordinal=ordinal,
                    section_number=section.number,
                    section_title=section.title,
                    page=_page_at(section.start, page_marks),
                    heading_path=section.path,
                )
            )
            ordinal += 1
    return chunks


def _reindex_page_marks(original: str, marks: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Translate page-marker offsets from the raw text to the stripped text."""
    reindexed: list[tuple[int, int]] = []
    removed = 0
    for match, (pos, page) in zip(_PAGE_MARK.finditer(original), marks, strict=True):
        reindexed.append((pos - removed, page))
        removed += match.end() - match.start()
    return reindexed
