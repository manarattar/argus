"""Deterministic grounding checks for model-produced citations.

This module is the reason ARGUS can claim its evidence is not fabricated. Rather
than asking a second model "is this quote real?", every quote an extractor
returns is re-matched against the stored source chunk with plain string
algorithms. A quote that cannot be located scores low and is dropped before it
can influence any downstream agent.

Matching tolerates the small, harmless deviations a model reliably makes
(whitespace collapse, smart quotes, an added ellipsis) while still failing on
the deviation that matters: text that is not in the document.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

# Quotes at or above this score are accepted as grounded. Chosen so that
# formatting drift passes and paraphrase does not; see
# tests/unit/test_grounding.py for the cases that pin this boundary.
GROUNDING_THRESHOLD = 0.82

_WHITESPACE = re.compile(r"\s+")
# The ambiguous-character warnings ruff would raise here are the whole point of
# the table: these are exactly the glyphs a model substitutes when it "quotes".
# ruff: noqa: RUF001
_PUNCT_LOOKALIKES = {
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
    "…": "...",
    " ": " ",
}


def normalise(text: str) -> str:
    """Fold away differences that carry no evidential meaning.

    Case, Unicode punctuation variants and whitespace runs are all normalised,
    because a model that reproduces a sentence with a straight apostrophe has
    still quoted the document faithfully.
    """
    text = unicodedata.normalize("NFKC", text)
    for src, dst in _PUNCT_LOOKALIKES.items():
        text = text.replace(src, dst)
    text = _WHITESPACE.sub(" ", text)
    return text.strip().lower()


@dataclass(frozen=True)
class GroundingResult:
    """Outcome of checking one quote against one source chunk."""

    score: float
    is_grounded: bool
    method: str
    matched_span: str = ""

    @property
    def explanation(self) -> str:
        if self.method == "exact":
            return "Quote found verbatim in the cited source chunk."
        if self.method == "windowed":
            return (
                f"Quote matched the cited chunk at {self.score:.0%} similarity "
                "after whitespace and punctuation normalisation."
            )
        if self.method == "fragment":
            return (
                f"Only {self.score:.0%} of the quote could be located in the cited "
                "chunk; the citation is treated as unreliable."
            )
        return "Quote could not be located in the cited source chunk."


def score_quote_grounding(quote: str, chunk_text: str) -> GroundingResult:
    """Score how faithfully ``quote`` reproduces a span of ``chunk_text``.

    Args:
        quote: The span the model claims to have copied.
        chunk_text: The stored text of the chunk the model cited.

    Returns:
        A :class:`GroundingResult`. ``is_grounded`` is the gate the pipeline
        actually enforces.
    """
    if not quote.strip() or not chunk_text.strip():
        return GroundingResult(score=0.0, is_grounded=False, method="empty")

    norm_quote = normalise(quote)
    norm_chunk = normalise(chunk_text)

    if norm_quote in norm_chunk:
        return GroundingResult(
            score=1.0, is_grounded=True, method="exact", matched_span=quote.strip()
        )

    # Slide a window the length of the quote across the chunk and keep the best
    # alignment. Bounded by the chunk size, so cost stays linear in practice.
    best_score, best_span = _best_window_match(norm_quote, norm_chunk)
    if best_score >= GROUNDING_THRESHOLD:
        return GroundingResult(
            score=round(best_score, 3),
            is_grounded=True,
            method="windowed",
            matched_span=best_span,
        )

    return GroundingResult(
        score=round(best_score, 3),
        is_grounded=False,
        method="fragment" if best_score > 0.4 else "absent",
        matched_span=best_span,
    )


def _best_window_match(needle: str, haystack: str) -> tuple[float, str]:
    """Best similarity between ``needle`` and any same-length window of ``haystack``."""
    n = len(needle)
    if n == 0 or len(haystack) < n // 2:
        return 0.0, ""

    # Step in proportion to the quote length: fine enough not to miss a match,
    # coarse enough to stay cheap on long documents.
    step = max(1, n // 8)
    window = min(len(haystack), int(n * 1.25))
    best_score = 0.0
    best_span = ""

    for start in range(0, max(1, len(haystack) - window + 1), step):
        candidate = haystack[start : start + window]
        score = SequenceMatcher(None, needle, candidate).ratio()
        if score > best_score:
            best_score, best_span = score, candidate
        if best_score >= 0.99:
            break

    return best_score, best_span


def find_best_chunk(quote: str, chunks: dict[str, str]) -> tuple[str | None, GroundingResult]:
    """Locate which chunk a quote actually came from.

    Used when a model cites a plausible chunk id but copied text from a
    neighbouring one - a recoverable mistake that should correct the citation
    rather than discard real evidence.

    Args:
        quote: The quoted span.
        chunks: Mapping of chunk id to chunk text for the case.

    Returns:
        The best-matching chunk id (or ``None``) and its grounding result.
    """
    best_id: str | None = None
    best = GroundingResult(score=0.0, is_grounded=False, method="absent")
    for chunk_id, text in chunks.items():
        result = score_quote_grounding(quote, text)
        if result.score > best.score:
            best_id, best = chunk_id, result
        if result.method == "exact":
            break
    return best_id, best
