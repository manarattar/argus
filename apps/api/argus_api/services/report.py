"""Assessment report generation.

The report is assembled from stored rows, not from a model call. By the time a
report is produced every judgement it contains has already been made, reviewed
and recorded; re-generating prose here would risk the report saying something
the assessment does not.

Two renderings share one builder: Markdown for the UI and the API, and PDF via
ReportLab for the artefact an analyst would actually file. The PDF import is
lazy so the dependency is not required to run the rest of the application.

Sections that would normally be quietly omitted are printed with an explicit
"none recorded" instead. A report that silently drops its limitations section is
worse than one that states there were none.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from argus_api.db.models import (
    Case,
    ChallengeRow,
    Evidence,
    Investigation,
    Override,
    PolicyMatchRow,
    Review,
    VerificationRow,
)

DISCLAIMER = (
    "This assessment was prepared with AI decision support. Every finding was "
    "reviewed by the named analyst, who is accountable for its conclusions. The "
    "provisional rating was computed by a deterministic scoring engine from the "
    "findings, policy triggers, verification outcomes and evidence coverage "
    "recorded below; it was not generated as free text by a language model. "
    "All source material in this demonstration is synthetic."
)


@dataclass
class ReportBundle:
    """A rendered report plus the metadata the UI shows alongside it."""

    markdown: str
    title: str
    reference: str
    generated_at: datetime
    sections: list[str]


def _title(text: str, level: int = 2) -> str:
    return f"\n{'#' * level} {text}\n"


def _bullets(items: list[str], empty: str) -> str:
    if not items:
        return f"_{empty}_\n"
    return "\n".join(f"- {item}" for item in items) + "\n"


def build_report(session: Session, investigation: Investigation) -> ReportBundle:
    """Assemble the full assessment report in Markdown."""
    case = session.get(Case, investigation.case_id)
    if case is None:
        raise ValueError("Investigation has no associated case.")

    evidence = {
        e.evidence_id: e
        for e in session.execute(
            select(Evidence).where(Evidence.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    }
    policy_matches = (
        session.execute(
            select(PolicyMatchRow).where(PolicyMatchRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    )
    challenges = (
        session.execute(
            select(ChallengeRow).where(ChallengeRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    )
    verifications = {
        v.risk_id: v
        for v in session.execute(
            select(VerificationRow).where(VerificationRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    }
    overrides = (
        session.execute(select(Override).where(Override.investigation_id == investigation.id))
        .scalars()
        .all()
    )
    review = session.execute(
        select(Review)
        .where(Review.investigation_id == investigation.id)
        .order_by(Review.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    narrative = investigation.narrative or {}
    generated_at = datetime.now(UTC)
    parts: list[str] = []
    sections: list[str] = []

    # -- header ------------------------------------------------------------
    parts.append(f"# Risk Assessment — {case.organisation}\n")
    parts.append(
        f"**Case reference:** {case.reference}  \n"
        f"**Review type:** {case.review_type}  \n"
        f"**Analyst:** {case.analyst}  \n"
        f"**Generated:** {generated_at.strftime('%d %B %Y %H:%M UTC')}  \n"
        f"**Investigation:** {investigation.id}  \n"
        f"**Model:** {investigation.model_name} "
        f"({'recorded responses' if investigation.demo_mode else 'live inference'})\n"
    )

    # -- 1 executive summary -----------------------------------------------
    sections.append("Executive Summary")
    parts.append(_title("1. Executive Summary"))
    summary = narrative.get("executive_summary")
    if summary:
        parts.append(f"{summary}\n")
    else:
        parts.append(
            "_The synthesis step did not complete, so no narrative summary is "
            "available. The rating below was still computed deterministically "
            "from the findings and is unaffected._\n"
        )

    # -- 2 scope -----------------------------------------------------------
    sections.append("Scope")
    parts.append(_title("2. Scope"))
    parts.append(
        f"{case.background}\n\n"
        f"**Sector:** {case.sector or 'not recorded'}  \n"
        f"**Jurisdiction:** {case.jurisdiction or 'not recorded'}  \n"
        f"**Documents examined:** {len({e.document_name for e in evidence.values()})}  \n"
        f"**Grounded evidence items:** {len(evidence)}\n"
    )

    # -- 3 overall assessment ----------------------------------------------
    sections.append("Overall Assessment")
    parts.append(_title("3. Overall Risk Assessment"))
    parts.append(
        f"**Provisional rating: {(investigation.overall_level or 'not rated').title()}** "
        f"({investigation.overall_score:.0f}/100)  \n"
        f"**Evidence strength:** "
        f"{(investigation.evidence_strength or 'unknown').replace('_', ' ').title()}\n"
    )
    parts.append("\n**Factors contributing to this rating**\n")
    parts.append("| Factor | Contribution | Detail |\n|---|---:|---|")
    for factor in investigation.score_factors or []:
        parts.append(
            f"| {factor.get('label')} | {factor.get('contribution'):+.1f} | "
            f"{factor.get('detail')} |"
        )
    parts.append("")

    if investigation.category_levels:
        parts.append("\n**Rating by category**\n")
        for category, level in sorted(investigation.category_levels.items()):
            parts.append(f"- {category.replace('_', ' ').title()}: **{level.title()}**")
        parts.append("")

    key_judgements = narrative.get("key_judgements") or []
    if key_judgements:
        parts.append("\n**Key judgements**\n")
        parts.append(_bullets(key_judgements, "none recorded"))

    # -- 4 material risks ---------------------------------------------------
    sections.append("Material Risks")
    parts.append(_title("4. Material Risks"))
    active = [r for r in investigation.risks if not r.is_false_positive]
    ranked = sorted(active, key=lambda r: r.adjusted_score, reverse=True)
    if not ranked:
        parts.append("_No findings were recorded for this investigation._\n")
    for index, risk in enumerate(ranked, start=1):
        parts.append(_title(f"4.{index} {risk.title}", level=3))
        parts.append(
            f"**Category:** {risk.category.replace('_', ' ').title()}  \n"
            f"**Severity:** {risk.severity.title()} "
            f"{'(analyst adjusted from ' + risk.ai_severity.title() + ')' if risk.severity != risk.ai_severity else ''}  \n"
            f"**Likelihood:** {risk.likelihood.title()}  \n"
            f"**Evidence strength:** "
            f"{risk.evidence_strength.replace('_', ' ').title()} — {risk.strength_rationale}\n"
        )
        parts.append(f"\n{risk.description}\n")

        if risk.supporting_evidence_ids:
            parts.append("\n**Supporting evidence**\n")
            for eid in risk.supporting_evidence_ids:
                item = evidence.get(eid)
                if item:
                    parts.append(
                        f"- `{eid}` {item.statement}  \n"
                        f"  _{item.document_name}, {item.section_reference}_"
                    )
            parts.append("")

        if risk.contradicting_evidence_ids:
            parts.append("\n**Contradicting evidence**\n")
            for eid in risk.contradicting_evidence_ids:
                item = evidence.get(eid)
                if item:
                    parts.append(
                        f"- `{eid}` {item.statement}  \n"
                        f"  _{item.document_name}, {item.section_reference}_"
                    )
            parts.append("")

        verification = verifications.get(risk.risk_id)
        if verification:
            parts.append(
                f"\n**Verification:** {verification.status.replace('_', ' ').title()} — "
                f"{verification.reasoning}\n"
            )

        if risk.mitigating_factors:
            parts.append("\n**Mitigating factors**\n")
            parts.append(_bullets(list(risk.mitigating_factors), "none"))

        if risk.mind_changer_increase or risk.mind_changer_decrease:
            parts.append("\n**What would change this assessment**\n")
            if risk.mind_changer_increase:
                parts.append(f"- Would raise it: {risk.mind_changer_increase}")
            if risk.mind_changer_decrease:
                parts.append(f"- Would lower it: {risk.mind_changer_decrease}")
            parts.append("")

        if risk.analyst_note:
            parts.append(f"\n**Analyst note:** {risk.analyst_note}\n")

    false_positives = [r for r in investigation.risks if r.is_false_positive]
    if false_positives:
        parts.append(_title("4.x Findings marked as false positives", level=3))
        parts.append("_Retained for the record. These were excluded from the rating._\n")
        parts.append(_bullets([f"{r.title} ({r.category})" for r in false_positives], ""))

    # -- 5 policy -----------------------------------------------------------
    sections.append("Policy Considerations")
    parts.append(_title("5. Relevant Policy Considerations"))
    if not policy_matches:
        parts.append("_No policy clauses were matched to the findings._\n")
    else:
        parts.append("| Clause | Title | Relationship | Finding |\n|---|---|---|---|")
        for match in policy_matches:
            parts.append(
                f"| {match.clause_reference} | {match.clause_title} | "
                f"{match.trigger_type.replace('_', ' ')} | {match.risk_id} |"
            )
        parts.append("")
        for match in policy_matches:
            parts.append(f"\n**{match.clause_reference} — {match.clause_title}**\n")
            parts.append(f"{match.relevance}\n")
            if match.threshold_assessment:
                parts.append(f"\n_Threshold:_ {match.threshold_assessment}\n")
            if match.sufficiency_caveat:
                parts.append(f"\n_Evidential caveat:_ {match.sufficiency_caveat}\n")

    # -- 6 challenges -------------------------------------------------------
    sections.append("Contradictory Evidence and Challenges")
    parts.append(_title("6. Challenges and Contradictory Evidence"))
    if not challenges:
        parts.append("_No challenges were raised against these findings._\n")
    for challenge in challenges:
        status = "unresolved" if challenge.unresolved else "considered"
        parts.append(
            f"\n**{challenge.challenge_type.replace('_', ' ').title()}** "
            f"against `{challenge.risk_id}` ({status})\n"
        )
        parts.append(f"{challenge.argument}\n")
        if challenge.suggested_revision:
            parts.append(f"\n_Suggested revision:_ {challenge.suggested_revision}\n")

    # -- 7 open questions and gaps -----------------------------------------
    sections.append("Open Questions")
    parts.append(_title("7. Open Questions and Evidence Gaps"))
    open_questions = [q for r in active for q in r.open_questions]
    parts.append(_bullets(open_questions, "no open questions recorded"))

    coverage = investigation.coverage or []
    incomplete = [c for c in coverage if c["status"] != "complete"]
    parts.append("\n**Investigation completeness**\n")
    if not coverage:
        parts.append("_Coverage was not assessed._\n")
    else:
        parts.append("| Expected evidence | Status | Note |\n|---|---|---|")
        for entry in coverage:
            parts.append(
                f"| {entry.get('category_label', entry['category'])} | "
                f"{entry['status'].title()} | {entry.get('note', '')} |"
            )
        parts.append("")
        if incomplete:
            parts.append(
                f"\n{len(incomplete)} of {len(coverage)} expected evidence "
                "categories are partial or missing. Unknowns were scored "
                "conservatively rather than treated as reassurance.\n"
            )

    # -- 8 analyst adjustments ---------------------------------------------
    sections.append("Analyst Adjustments")
    parts.append(_title("8. Analyst Adjustments"))
    if not overrides:
        parts.append("_The analyst made no adjustments to the AI recommendations._\n")
    else:
        parts.append(
            "| Finding | Field | AI recommended | Analyst decided | Rationale |"
            "\n|---|---|---|---|---|"
        )
        for override in overrides:
            parts.append(
                f"| {override.risk_id} | {override.field} | {override.ai_value} | "
                f"{override.human_value} | {override.rationale} |"
            )
        parts.append("")

    # -- 9 limitations ------------------------------------------------------
    sections.append("Limitations")
    parts.append(_title("9. Limitations"))
    limitations = list(narrative.get("limitations") or [])
    if investigation.demo_mode:
        limitations.append(
            "This investigation ran in Demo Mode, serving model responses "
            "recorded previously against these exact prompts."
        )
    if investigation.errors:
        limitations.append(
            f"{len(investigation.errors)} step(s) failed during the "
            "investigation; see the execution trace."
        )
    integrity = investigation.integrity or {}
    if integrity.get("summary") and "All citations resolved" not in integrity["summary"]:
        limitations.append(f"Citation integrity: {integrity['summary']}")
    parts.append(_bullets(limitations, "none recorded"))

    # -- 10 follow-up -------------------------------------------------------
    sections.append("Recommended Follow-up")
    parts.append(_title("10. Recommended Follow-up"))
    parts.append(_bullets(list(narrative.get("recommended_followup") or []), "none recorded"))

    if investigation.escalation_reasons:
        parts.append("\n**Mandatory escalations triggered**\n")
        parts.append(_bullets(list(investigation.escalation_reasons), ""))

    # -- 11 audit metadata --------------------------------------------------
    sections.append("Audit Metadata")
    parts.append(_title("11. Audit Metadata"))
    parts.append(
        f"| Field | Value |\n|---|---|\n"
        f"| Investigation id | {investigation.id} |\n"
        f"| Started | {investigation.started_at.isoformat()} |\n"
        f"| Completed | "
        f"{investigation.completed_at.isoformat() if investigation.completed_at else '—'} |\n"
        f"| Duration | {investigation.duration_ms / 1000:.1f}s |\n"
        f"| Model backend | {investigation.model_backend} |\n"
        f"| Model | {investigation.model_name} |\n"
        f"| Embedding model | {investigation.embedding_model} |\n"
        f"| Retrieval quality | {investigation.retrieval_quality:.2f} |\n"
        f"| Input tokens | {investigation.total_input_tokens:,} |\n"
        f"| Output tokens | {investigation.total_output_tokens:,} |\n"
        f"| Estimated cost | ${investigation.total_cost_usd:.4f} |\n"
        f"| Evidence rejected by grounding check | "
        f"{len(investigation.rejected_evidence or [])} |\n"
        f"| Review decision | {review.decision if review else 'not yet reviewed'} |\n"
        f"| Reviewer | {review.actor if review else '—'} |\n"
    )

    parts.append(_title("Disclaimer"))
    parts.append(f"_{DISCLAIMER}_\n")

    return ReportBundle(
        markdown="\n".join(parts),
        title=f"Risk Assessment — {case.organisation}",
        reference=case.reference,
        generated_at=generated_at,
        sections=sections,
    )


def render_pdf(bundle: ReportBundle) -> bytes:
    """Render the report as a PDF.

    A deliberately simple Markdown subset is handled - headings, bullets, tables
    and bold runs - because the report's structure is known and fixed. Pulling
    in a full Markdown-to-PDF stack for one document shape would be more
    dependency than the problem needs.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=bundle.title,
    )

    base = getSampleStyleSheet()
    styles = {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=17, spaceAfter=10, leading=21),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6
        ),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"], fontSize=11, spaceBefore=10, spaceAfter=4
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontSize=9.5,
            leading=13.5,
            alignment=TA_LEFT,
            spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base["BodyText"], fontSize=9.5, leading=13, leftIndent=10
        ),
    }

    def inline(text: str) -> str:
        """Convert the inline Markdown the report uses into ReportLab markup."""
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        while "**" in text:
            text = text.replace("**", "<b>", 1).replace("**", "</b>", 1)
        while text.count("`") >= 2:
            text = text.replace("`", "<font face='Courier'>", 1).replace("`", "</font>", 1)
        while text.count("_") >= 2:
            text = text.replace("_", "<i>", 1).replace("_", "</i>", 1)
        return text

    flow: list[Any] = []
    table_buffer: list[list[str]] = []

    def flush_table() -> None:
        if not table_buffer:
            return
        data = [[Paragraph(inline(cell), styles["body"]) for cell in row] for row in table_buffer]
        table = Table(data, repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8DEE7")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF1F6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        flow.append(table)
        flow.append(Spacer(1, 8))
        table_buffer.clear()

    for raw in bundle.markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue  # separator row
            table_buffer.append(cells)
            continue
        flush_table()

        if not stripped:
            continue
        if stripped.startswith("# "):
            flow.append(Paragraph(inline(stripped[2:]), styles["h1"]))
        elif stripped.startswith("## "):
            flow.append(Paragraph(inline(stripped[3:]), styles["h2"]))
        elif stripped.startswith("### "):
            flow.append(Paragraph(inline(stripped[4:]), styles["h3"]))
        elif stripped.startswith("- "):
            flow.append(Paragraph(f"• {inline(stripped[2:])}", styles["bullet"]))
        else:
            flow.append(Paragraph(inline(stripped), styles["body"]))

    flush_table()
    if not flow:
        flow.append(Paragraph("The report is empty.", styles["body"]))
        flow.append(PageBreak())

    document.build(flow)
    return buffer.getvalue()
