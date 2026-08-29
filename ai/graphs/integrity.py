"""Cross-reference integrity: the controls that do not trust the model.

Schema validation proves an agent returned well-formed output. It says nothing
about whether the ids inside that output refer to anything real. These functions
close that gap with plain set arithmetic, and they run on every investigation.

Three checks, in the order the pipeline applies them:

1. :func:`filter_grounded_evidence` - each extracted quote is re-matched against
   the stored source chunk. Evidence that cannot be located is removed before
   any other agent sees it.
2. :func:`enforce_evidence_references` - findings, challenges and verifications
   may only cite evidence that survived step 1. Unknown ids are stripped and
   recorded.
3. :func:`enforce_risk_references` - policy matches, challenges and
   verifications may only attach to findings that exist.

The design point: none of this asks a model whether it was honest. A citation is
either resolvable against stored text or it is not, and that is decided by code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.schemas.models import Challenge, ClaimVerification, EvidenceItem, PolicyMatch, RiskFinding
from ai.tools.grounding import find_best_chunk, score_quote_grounding


@dataclass
class IntegrityReport:
    """What the controls removed, so it can be surfaced rather than hidden."""

    dropped_evidence: list[tuple[str, str, float]] = field(default_factory=list)
    repaired_chunk_refs: list[tuple[str, str, str]] = field(default_factory=list)
    stripped_evidence_refs: list[tuple[str, str]] = field(default_factory=list)
    dropped_policy_matches: list[tuple[str, str]] = field(default_factory=list)
    dropped_challenges: list[tuple[str, str]] = field(default_factory=list)
    dropped_verifications: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        return (
            len(self.dropped_evidence)
            + len(self.stripped_evidence_refs)
            + len(self.dropped_policy_matches)
            + len(self.dropped_challenges)
            + len(self.dropped_verifications)
        )

    def summary(self) -> str:
        if not self.total_issues and not self.repaired_chunk_refs:
            return "All citations resolved against stored sources."
        parts: list[str] = []
        if self.dropped_evidence:
            parts.append(f"{len(self.dropped_evidence)} ungrounded quote(s) discarded")
        if self.repaired_chunk_refs:
            parts.append(f"{len(self.repaired_chunk_refs)} chunk reference(s) corrected")
        if self.stripped_evidence_refs:
            parts.append(f"{len(self.stripped_evidence_refs)} unresolvable citation(s) stripped")
        dropped = (
            len(self.dropped_policy_matches)
            + len(self.dropped_challenges)
            + len(self.dropped_verifications)
        )
        if dropped:
            parts.append(f"{dropped} orphaned record(s) removed")
        return "; ".join(parts) + "."

    def to_dict(self) -> dict[str, object]:
        return {
            "dropped_evidence": [
                {"evidence_id": eid, "reason": reason, "score": score}
                for eid, reason, score in self.dropped_evidence
            ],
            "repaired_chunk_refs": [
                {"evidence_id": eid, "from": old, "to": new}
                for eid, old, new in self.repaired_chunk_refs
            ],
            "stripped_evidence_refs": [
                {"owner_id": owner, "evidence_id": eid}
                for owner, eid in self.stripped_evidence_refs
            ],
            "orphans_removed": (
                len(self.dropped_policy_matches)
                + len(self.dropped_challenges)
                + len(self.dropped_verifications)
            ),
            "summary": self.summary(),
        }


def filter_grounded_evidence(
    items: list[EvidenceItem],
    chunk_texts: dict[str, str],
    report: IntegrityReport,
) -> list[EvidenceItem]:
    """Keep only evidence whose quote is verifiable against a stored chunk.

    A quote that matches a *different* chunk than the one cited has its
    reference corrected rather than being discarded: the evidence is real, the
    pointer was wrong, and throwing away real evidence would be the worse error.

    Args:
        items: Evidence as returned by the extractor.
        chunk_texts: Chunk id to stored text, for the case being investigated.
        report: Mutated in place with everything that was changed or removed.

    Returns:
        The surviving evidence, annotated with grounding scores.
    """
    kept: list[EvidenceItem] = []

    for item in items:
        cited_text = chunk_texts.get(item.chunk_id)

        if cited_text is not None:
            result = score_quote_grounding(item.quote, cited_text)
            if result.is_grounded:
                kept.append(
                    item.model_copy(
                        update={
                            "grounding_score": result.score,
                            "is_grounded": True,
                        }
                    )
                )
                continue
        # Either the chunk id is unknown, or the quote is not in it. Look for
        # the quote elsewhere in the corpus before discarding it.
        best_chunk, best = find_best_chunk(item.quote, chunk_texts)
        if best_chunk and best.is_grounded:
            report.repaired_chunk_refs.append((item.evidence_id, item.chunk_id, best_chunk))
            kept.append(
                item.model_copy(
                    update={
                        "chunk_id": best_chunk,
                        "grounding_score": best.score,
                        "is_grounded": True,
                    }
                )
            )
            continue

        report.dropped_evidence.append(
            (
                item.evidence_id,
                "Quote could not be located in any source document."
                if cited_text is not None
                else f"Cited chunk {item.chunk_id!r} does not exist.",
                best.score,
            )
        )

    return kept


def enforce_evidence_references(
    *,
    risks: list[RiskFinding],
    challenges: list[Challenge],
    verifications: list[ClaimVerification],
    valid_evidence_ids: set[str],
    report: IntegrityReport,
) -> tuple[list[RiskFinding], list[Challenge], list[ClaimVerification]]:
    """Strip citations that do not resolve to surviving evidence.

    A finding left with no supporting evidence is *kept*, not deleted. It flows
    into the uncertainty model, which bands it as Insufficient Evidence, and the
    reviewer sees a finding that could not be substantiated. That is more useful
    than the finding quietly disappearing.
    """
    clean_risks: list[RiskFinding] = []
    for risk in risks:
        supporting = [e for e in risk.supporting_evidence_ids if e in valid_evidence_ids]
        contradicting = [e for e in risk.contradicting_evidence_ids if e in valid_evidence_ids]
        for missing in set(risk.supporting_evidence_ids) - set(supporting):
            report.stripped_evidence_refs.append((risk.risk_id, missing))
        for missing in set(risk.contradicting_evidence_ids) - set(contradicting):
            report.stripped_evidence_refs.append((risk.risk_id, missing))
        clean_risks.append(
            risk.model_copy(
                update={
                    "supporting_evidence_ids": supporting,
                    "contradicting_evidence_ids": contradicting,
                }
            )
        )

    clean_challenges: list[Challenge] = []
    for challenge in challenges:
        counter = [e for e in challenge.counter_evidence_ids if e in valid_evidence_ids]
        for missing in set(challenge.counter_evidence_ids) - set(counter):
            report.stripped_evidence_refs.append((challenge.challenge_id, missing))
        clean_challenges.append(challenge.model_copy(update={"counter_evidence_ids": counter}))

    clean_verifications: list[ClaimVerification] = []
    for verification in verifications:
        checked = [e for e in verification.citations_checked if e in valid_evidence_ids]
        irrelevant = [e for e in verification.irrelevant_citation_ids if e in valid_evidence_ids]
        for missing in set(verification.citations_checked) - set(checked):
            report.stripped_evidence_refs.append((verification.verification_id, missing))
        clean_verifications.append(
            verification.model_copy(
                update={
                    "citations_checked": checked,
                    "irrelevant_citation_ids": irrelevant,
                }
            )
        )

    return clean_risks, clean_challenges, clean_verifications


def enforce_risk_references(
    *,
    valid_risk_ids: set[str],
    policy_matches: list[PolicyMatch],
    challenges: list[Challenge],
    verifications: list[ClaimVerification],
    report: IntegrityReport,
) -> tuple[list[PolicyMatch], list[Challenge], list[ClaimVerification]]:
    """Drop records attached to findings that do not exist.

    Unlike a stripped citation, an orphan here has nothing to attach to and
    would render as a dangling row in the UI, so it is removed outright.
    """
    kept_matches = []
    for match in policy_matches:
        if match.risk_id in valid_risk_ids:
            kept_matches.append(match)
        else:
            report.dropped_policy_matches.append((match.match_id, match.risk_id))

    kept_challenges = []
    for challenge in challenges:
        if challenge.risk_id in valid_risk_ids:
            kept_challenges.append(challenge)
        else:
            report.dropped_challenges.append((challenge.challenge_id, challenge.risk_id))

    kept_verifications = []
    for verification in verifications:
        if verification.risk_id in valid_risk_ids:
            kept_verifications.append(verification)
        else:
            report.dropped_verifications.append(
                (verification.verification_id, verification.risk_id)
            )

    return kept_matches, kept_challenges, kept_verifications
