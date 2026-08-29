"""Hybrid retrieval over case documents and the policy library.

Two retrievers with complementary failure modes are fused rather than choosing
one:

* **BM25** is exact. It reliably finds "62%", "CRF 4.2" and "Stichting" - the
  literal tokens that carry most of the weight in a risk document. It fails when
  the analyst's wording differs from the document's.
* **Vector similarity** is tolerant. It bridges phrasing differences. It fails by
  returning topically adjacent but useless text, and - with the key-less lexical
  fallback - by being only as good as term overlap allows.

Fusion uses Reciprocal Rank Fusion, which combines *rankings* rather than raw
scores. That matters here because the two retrievers' scores are not on a
comparable scale, and RRF needs no per-corpus normalisation constant to tune.

Retrieval quality is reported alongside the hits (:attr:`SearchResponse.quality`)
because the uncertainty model treats "we searched and found little" differently
from "we searched and found strong matches".
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from ai.retrieval.embeddings import EmbeddingProvider, cosine_similarity

_TOKEN = re.compile(r"[a-z0-9]+")

# Standard BM25 parameters; k1 controls term-frequency saturation and b controls
# length normalisation.
BM25_K1 = 1.5
BM25_B = 0.75

# RRF damping. 60 is the value from the original formulation and behaves well
# when neither retriever should dominate.
RRF_K = 60

_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its of on or that the
    to was were will with this these those which such may can""".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


@dataclass
class IndexedChunk:
    """A chunk with everything retrieval and citation need."""

    chunk_id: str
    document_id: str
    document_name: str
    text: str
    citation_key: str
    section_number: str = ""
    section_title: str = ""
    page: int | None = None
    doc_kind: str = "case"
    vector: list[float] = field(default_factory=list)


@dataclass
class SearchHit:
    """One retrieved chunk with the provenance of how it was found."""

    chunk: IndexedChunk
    score: float
    bm25_rank: int | None = None
    vector_rank: int | None = None
    bm25_score: float = 0.0
    vector_score: float = 0.0

    @property
    def retrieved_by(self) -> str:
        if self.bm25_rank is not None and self.vector_rank is not None:
            return "hybrid"
        if self.bm25_rank is not None:
            return "keyword"
        return "semantic"


@dataclass
class SearchResponse:
    """Hits plus an interpretable quality signal for the uncertainty model."""

    hits: list[SearchHit]
    query: str
    quality: float
    strategy: str

    @property
    def quality_label(self) -> str:
        if self.quality >= 0.7:
            return "strong"
        if self.quality >= 0.45:
            return "adequate"
        if self.quality >= 0.2:
            return "weak"
        return "poor"


class HybridIndex:
    """In-memory hybrid index over one case's chunks plus the policy library.

    The corpus for a single review is a few hundred chunks, so an in-memory
    index is the right size of solution: no external service, exact results,
    and trivial to reason about. :class:`argus_api.services.retrieval` persists
    the same vectors to Postgres/pgvector when that backend is configured, and
    the interface here is what the rest of the system codes against.
    """

    def __init__(self, chunks: list[IndexedChunk], embedder: EmbeddingProvider) -> None:
        self.chunks = chunks
        self.embedder = embedder
        self._tokens: list[list[str]] = [tokenize(c.text) for c in chunks]
        self._lengths = np.array([len(t) for t in self._tokens], dtype=np.float32)
        self._avg_length = float(self._lengths.mean()) if len(chunks) else 0.0
        self._doc_freq = self._compute_document_frequencies()
        self._matrix = self._build_matrix()

    # -- construction ----------------------------------------------------

    def _compute_document_frequencies(self) -> Counter[str]:
        df: Counter[str] = Counter()
        for tokens in self._tokens:
            df.update(set(tokens))
        return df

    def _build_matrix(self) -> np.ndarray:
        vectors = [c.vector for c in self.chunks if c.vector]
        if len(vectors) != len(self.chunks) or not vectors:
            return np.zeros((0, 0), dtype=np.float32)
        return np.array(vectors, dtype=np.float32)

    @classmethod
    def build(cls, chunks: list[IndexedChunk], embedder: EmbeddingProvider) -> HybridIndex:
        """Embed any chunks lacking vectors, then construct the index."""
        pending = [c for c in chunks if not c.vector]
        if pending:
            result = embedder.embed([c.text for c in pending])
            for chunk, vector in zip(pending, result.vectors, strict=True):
                chunk.vector = vector
        return cls(chunks, embedder)

    # -- retrieval -------------------------------------------------------

    def _bm25_scores(self, query_tokens: list[str]) -> np.ndarray:
        n = len(self.chunks)
        scores = np.zeros(n, dtype=np.float32)
        if not n or not query_tokens:
            return scores
        for term in set(query_tokens):
            df = self._doc_freq.get(term, 0)
            if df == 0:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for i, tokens in enumerate(self._tokens):
                tf = tokens.count(term)
                if not tf:
                    continue
                norm = 1 - BM25_B + BM25_B * (self._lengths[i] / (self._avg_length or 1))
                scores[i] += idf * (tf * (BM25_K1 + 1)) / (tf + BM25_K1 * norm)
        return scores

    def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        doc_kind: str | None = None,
        document_ids: list[str] | None = None,
    ) -> SearchResponse:
        """Retrieve the ``top_k`` chunks most relevant to ``query``.

        Args:
            query: Natural-language query or clause text.
            top_k: Number of chunks to return.
            doc_kind: Restrict to ``case`` or ``policy`` chunks.
            document_ids: Restrict to specific documents.

        Returns:
            Ranked hits and a retrieval-quality score in ``[0, 1]``.
        """
        if not self.chunks:
            return SearchResponse(hits=[], query=query, quality=0.0, strategy="empty")

        allowed = self._allowed_indices(doc_kind, document_ids)
        if not allowed:
            return SearchResponse(hits=[], query=query, quality=0.0, strategy="filtered-empty")

        query_tokens = tokenize(query)
        bm25 = self._bm25_scores(query_tokens)

        vector_scores = np.zeros(len(self.chunks), dtype=np.float32)
        strategy = "bm25-only"
        if self._matrix.size:
            query_vector = np.array(self.embedder.embed_one(query), dtype=np.float32)
            if query_vector.shape[0] == self._matrix.shape[1]:
                vector_scores = cosine_similarity(query_vector, self._matrix)
                strategy = "hybrid-rrf"

        bm25_order = self._rank(bm25, allowed)
        vector_order = self._rank(vector_scores, allowed)

        fused: dict[int, float] = {}
        for rank, idx in enumerate(bm25_order):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, idx in enumerate(vector_order):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)

        bm25_rank_of = {idx: r for r, idx in enumerate(bm25_order[: top_k * 3])}
        vector_rank_of = {idx: r for r, idx in enumerate(vector_order[: top_k * 3])}

        ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        hits = [
            SearchHit(
                chunk=self.chunks[idx],
                score=round(score, 6),
                bm25_rank=bm25_rank_of.get(idx),
                vector_rank=vector_rank_of.get(idx),
                bm25_score=round(float(bm25[idx]), 4),
                vector_score=round(float(vector_scores[idx]), 4),
            )
            for idx, score in ordered
        ]

        return SearchResponse(
            hits=hits,
            query=query,
            quality=self._quality(hits, bm25, vector_scores),
            strategy=strategy,
        )

    def _allowed_indices(self, doc_kind: str | None, document_ids: list[str] | None) -> list[int]:
        wanted = set(document_ids) if document_ids else None
        return [
            i
            for i, c in enumerate(self.chunks)
            if (doc_kind is None or c.doc_kind == doc_kind)
            and (wanted is None or c.document_id in wanted)
        ]

    @staticmethod
    def _rank(scores: np.ndarray, allowed: list[int]) -> list[int]:
        """Indices of ``allowed`` ordered by score, dropping zero-score entries."""
        scored = [(i, float(scores[i])) for i in allowed if scores[i] > 0]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return [i for i, _ in scored]

    @staticmethod
    def _quality(hits: list[SearchHit], bm25: np.ndarray, vector_scores: np.ndarray) -> float:
        """How much to trust that retrieval actually found the right material.

        Blends absolute match strength with agreement between the two
        retrievers: when keyword and vector search independently surface the
        same chunk, that is a much stronger signal than either alone.
        """
        if not hits:
            return 0.0
        top = hits[0]
        bm25_ceiling = float(bm25.max()) if bm25.size else 0.0
        lexical = min(top.bm25_score / bm25_ceiling, 1.0) if bm25_ceiling > 0 else 0.0
        semantic = max(0.0, min(float(top.vector_score), 1.0)) if vector_scores.size else 0.0
        agreement = sum(1 for h in hits[:5] if h.retrieved_by == "hybrid") / min(len(hits), 5)
        quality = 0.4 * lexical + 0.35 * semantic + 0.25 * agreement
        return round(min(1.0, quality), 3)
