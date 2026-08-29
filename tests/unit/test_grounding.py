"""Tests for the grounding control.

The negative cases matter more than the positive ones. A checker that accepts
everything passes every "real quote" test and provides no protection at all, so
each fabrication mode gets its own case.

The ambiguous-character warnings ruff would raise here are the subject of the
tests: smart quotes and dashes are exactly what a model substitutes when it
"quotes" a document, and the normaliser has to fold them.
"""
# ruff: noqa: RUF001

from __future__ import annotations

import pytest

from ai.graphs.integrity import IntegrityReport, filter_grounded_evidence
from ai.tools.grounding import (
    GROUNDING_THRESHOLD,
    find_best_chunk,
    normalise,
    score_quote_grounding,
)
from tests.conftest import make_evidence

SOURCE = (
    "In 2025, the two largest customers together accounted for 62% of consolidated "
    "revenue (2024: 58%; 2023: 51%). The largest single customer accounted for 39% "
    "of revenue. The agreement with the second-largest customer expires in June 2026 "
    "and is currently under renegotiation."
)


class TestAcceptsFaithfulQuotes:
    def test_verbatim_quote(self) -> None:
        result = score_quote_grounding(
            "the two largest customers together accounted for 62% of consolidated revenue",
            SOURCE,
        )
        assert result.is_grounded
        assert result.score == 1.0
        assert result.method == "exact"

    def test_tolerates_whitespace_and_case(self) -> None:
        result = score_quote_grounding(
            "The  TWO largest customers   together accounted for 62%\nof consolidated revenue",
            SOURCE,
        )
        assert result.is_grounded

    def test_tolerates_smart_punctuation(self) -> None:
        source = "The company’s principal facility is a EUR 55.0 million term loan."
        result = score_quote_grounding(
            "The company's principal facility is a EUR 55.0 million term loan.", source
        )
        assert result.is_grounded


class TestRejectsFabrication:
    def test_rejects_altered_figure(self) -> None:
        """The most dangerous failure mode: a real sentence with a wrong number."""
        result = score_quote_grounding(
            "the two largest customers together accounted for 81% of consolidated revenue "
            "which is unsustainable",
            SOURCE,
        )
        assert not result.is_grounded

    def test_rejects_paraphrase(self) -> None:
        result = score_quote_grounding(
            "Customer concentration is very high and threatens the business model",
            SOURCE,
        )
        assert not result.is_grounded

    def test_rejects_unrelated_text(self) -> None:
        result = score_quote_grounding(
            "The company completed its first independent cybersecurity assessment",
            SOURCE,
        )
        assert not result.is_grounded

    def test_rejects_real_quote_with_appended_invention(self) -> None:
        result = score_quote_grounding(
            "The largest single customer accounted for 39% of revenue and the board "
            "expects this to double during 2026",
            SOURCE,
        )
        assert not result.is_grounded

    @pytest.mark.parametrize("quote", ["", "   ", "\n"])
    def test_rejects_empty_quote(self, quote: str) -> None:
        assert not score_quote_grounding(quote, SOURCE).is_grounded

    def test_rejects_against_empty_source(self) -> None:
        assert not score_quote_grounding("anything at all", "").is_grounded


class TestNormalisation:
    def test_collapses_whitespace_and_case(self) -> None:
        assert normalise("  The   QUICK\n brown  ") == "the quick brown"

    def test_folds_unicode_punctuation(self) -> None:
        assert normalise("“quoted” – dash") == '"quoted" - dash'


class TestChunkRecovery:
    def test_locates_the_chunk_a_quote_really_came_from(self) -> None:
        chunks = {
            "doc::c0": "Unrelated introductory material about the company history.",
            "doc::c1": SOURCE,
        }
        chunk_id, result = find_best_chunk(
            "The largest single customer accounted for 39% of revenue", chunks
        )
        assert chunk_id == "doc::c1"
        assert result.is_grounded

    def test_returns_no_chunk_for_invented_text(self) -> None:
        chunks = {"doc::c0": SOURCE}
        _, result = find_best_chunk("The company entered administration in March 2026", chunks)
        assert not result.is_grounded


class TestEvidenceFiltering:
    def test_keeps_grounded_evidence(self) -> None:
        report = IntegrityReport()
        item = make_evidence(
            "E1",
            quote="The largest single customer accounted for 39% of revenue",
        )
        kept = filter_grounded_evidence([item], {"doc-1::c0": SOURCE}, report)
        assert len(kept) == 1
        assert kept[0].is_grounded
        assert kept[0].grounding_score > 0
        assert not report.dropped_evidence

    def test_drops_ungrounded_evidence_and_records_why(self) -> None:
        report = IntegrityReport()
        item = make_evidence("E1", quote="The company entered administration in March 2026")
        kept = filter_grounded_evidence([item], {"doc-1::c0": SOURCE}, report)
        assert kept == []
        assert len(report.dropped_evidence) == 1
        assert report.dropped_evidence[0][0] == "E1"

    def test_repairs_a_wrong_chunk_reference_rather_than_discarding(self) -> None:
        """Real evidence with a wrong pointer is corrected, not thrown away."""
        report = IntegrityReport()
        item = make_evidence(
            "E1",
            quote="The largest single customer accounted for 39% of revenue",
        )
        chunks = {
            "doc-1::c0": "Some other section entirely.",
            "doc-1::c7": SOURCE,
        }
        kept = filter_grounded_evidence([item], chunks, report)
        assert len(kept) == 1
        assert kept[0].chunk_id == "doc-1::c7"
        assert report.repaired_chunk_refs

    def test_drops_evidence_citing_a_nonexistent_chunk(self) -> None:
        report = IntegrityReport()
        item = make_evidence("E1", quote="Entirely invented content not in any document")
        kept = filter_grounded_evidence([item], {"other::c0": SOURCE}, report)
        assert kept == []
        assert report.dropped_evidence


def test_threshold_is_within_a_sensible_range() -> None:
    """Guards against someone 'fixing' a failing test by lowering the bar."""
    assert 0.7 <= GROUNDING_THRESHOLD <= 0.95
