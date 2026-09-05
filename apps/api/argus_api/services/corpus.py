"""Document ingestion and index construction.

Ingestion is deliberately a separate concern from investigation. Chunking and
embedding happen once, at ingest; every later investigation and every
evaluation run reads the same stored chunks. That means a citation always
resolves to exactly the text the extractor saw, which is the precondition for
the grounding check being meaningful at all.

The index built here is the in-memory hybrid index from
:mod:`ai.retrieval.search`, hydrated from stored rows. Vectors are computed at
ingest and reused, so building an index for a case is cheap and involves no
model calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.retrieval.chunking import chunk_document
from ai.retrieval.embeddings import EmbeddingProvider
from ai.retrieval.search import HybridIndex, IndexedChunk
from argus_api.db.models import Chunk, Document

# Policy documents declare their citation prefix in the title, e.g.
# "ARGUS Counterparty Risk Framework (CRF)".
_CODE_IN_TITLE = re.compile(r"\(([A-Z]{2,5})\)\s*$")


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    name: str
    chunks: int
    doc_kind: str


def derive_code(title: str) -> str:
    """Extract the short citation code from a policy document title."""
    match = _CODE_IN_TITLE.search(title.strip())
    return match.group(1) if match else ""


def read_title(text: str, fallback: str) -> str:
    """First level-one heading, or the filename if the document has none."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def ingest_document(
    session: Session,
    *,
    document_id: str,
    name: str,
    text: str,
    embedder: EmbeddingProvider,
    doc_kind: str = "case",
    case_id: str | None = None,
    description: str = "",
    code: str = "",
) -> IngestResult:
    """Chunk, embed and persist one document.

    Replaces any existing document with the same id so re-seeding is idempotent.
    """
    existing = session.get(Document, document_id)
    if existing is not None:
        session.delete(existing)
        session.flush()

    document = Document(
        id=document_id,
        case_id=case_id,
        name=name,
        doc_kind=doc_kind,
        code=code or (derive_code(name) if doc_kind == "policy" else ""),
        description=description,
        content=text,
        is_synthetic=True,
    )
    session.add(document)

    chunks = chunk_document(document_id, text)
    vectors = embedder.embed([c.text for c in chunks]).vectors if chunks else []

    for chunk, vector in zip(chunks, vectors, strict=True):
        session.add(
            Chunk(
                id=chunk.chunk_id,
                document_id=document_id,
                ordinal=chunk.ordinal,
                text=chunk.text,
                section_number=chunk.section_number,
                section_title=chunk.section_title,
                citation_key=chunk.citation_key,
                page=chunk.page,
                embedding=vector,
                embedding_model=embedder.name,
            )
        )

    session.flush()
    return IngestResult(document_id=document_id, name=name, chunks=len(chunks), doc_kind=doc_kind)


def ingest_directory(
    session: Session,
    directory: Path,
    *,
    embedder: EmbeddingProvider,
    doc_kind: str,
    case_id: str | None = None,
    id_prefix: str = "",
) -> list[IngestResult]:
    """Ingest every Markdown file in a directory, in filename order."""
    results: list[IngestResult] = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        stem = path.stem
        document_id = f"{id_prefix}{stem}" if id_prefix else stem
        title = read_title(text, stem)
        results.append(
            ingest_document(
                session,
                document_id=document_id,
                name=title,
                text=text,
                embedder=embedder,
                doc_kind=doc_kind,
                case_id=case_id,
            )
        )
    return results


def load_indexed_chunks(
    session: Session, *, case_id: str | None, include_policies: bool = True
) -> list[IndexedChunk]:
    """Hydrate stored chunks into the retrieval layer's representation."""
    statement = select(Chunk, Document).join(Document, Chunk.document_id == Document.id)
    rows = session.execute(statement).all()

    indexed: list[IndexedChunk] = []
    for chunk, document in rows:
        if document.doc_kind == "case":
            if case_id is None or document.case_id != case_id:
                continue
        elif not include_policies:
            continue

        indexed.append(
            IndexedChunk(
                chunk_id=chunk.id,
                document_id=document.id,
                document_name=document.name,
                text=chunk.text,
                citation_key=chunk.citation_key,
                section_number=chunk.section_number,
                section_title=chunk.section_title,
                page=chunk.page,
                doc_kind=document.doc_kind,
                vector=list(chunk.embedding or []),
            )
        )
    return indexed


def build_index(
    session: Session,
    embedder: EmbeddingProvider,
    *,
    case_id: str | None,
    include_policies: bool = True,
) -> HybridIndex:
    """Build a hybrid index over one case's documents plus the policy library.

    Chunks whose stored vector was produced by a different embedding model are
    re-embedded in memory, so switching embedding providers cannot silently
    produce an index of mixed, incomparable vectors.
    """
    chunks = load_indexed_chunks(session, case_id=case_id, include_policies=include_policies)
    expected_dimensions = embedder.dimensions
    for chunk in chunks:
        if len(chunk.vector) != expected_dimensions:
            chunk.vector = []
    return HybridIndex.build(chunks, embedder)


def document_summaries(session: Session, case_id: str) -> list[dict[str, object]]:
    """Document inventory for the case screen."""
    documents = (
        session.execute(select(Document).where(Document.case_id == case_id).order_by(Document.id))
        .scalars()
        .all()
    )
    summaries: list[dict[str, object]] = []
    for document in documents:
        chunk_count = len(document.chunks)
        summaries.append(
            {
                "id": document.id,
                "name": document.name,
                "doc_kind": document.doc_kind,
                "chunks": chunk_count,
                "characters": len(document.content),
                "is_synthetic": document.is_synthetic,
            }
        )
    return summaries
