"""Seed the demonstration corpus.

Run with ``make seed`` or ``python -m scripts.seed``.

Creates the schema, ingests the Northstar case documents and the policy
library, and registers the demo case. With ``--investigate`` it also runs the
full investigation graph so the application is populated on first launch.

The seed is idempotent: documents are replaced by id, and ``--reset`` drops the
schema first for a genuinely clean start.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "apps" / "api")]

from argus_api.core.settings import get_settings  # noqa: E402
from argus_api.db.models import Case  # noqa: E402
from argus_api.db.session import init_db, reset_db, session_scope  # noqa: E402
from argus_api.services import audit  # noqa: E402
from argus_api.services.corpus import ingest_directory  # noqa: E402
from argus_api.services.investigation import run_investigation  # noqa: E402
from argus_api.services.runtime import get_embedder, get_llm_provider  # noqa: E402
from sqlalchemy import select  # noqa: E402

DEMO_CASE = {
    "id": "case_northstar_2026",
    "reference": "CR-2026-0417",
    "organisation": "Northstar Manufacturing B.V.",
    "review_type": "Annual Counterparty Review",
    "domain_key": "counterparty_review",
    "analyst": "T. Okonkwo",
    "sector": "Industrial manufacturing - thermal management components",
    "jurisdiction": "Netherlands",
    "background": (
        "Client since 2016. Working capital facility, cash management and FX "
        "hedging. Annual review falling due following FY2025 results, in which "
        "the counterparty materially increased borrowings to fund a capacity "
        "expansion. Not a borrower under the March 2025 senior facility."
    ),
}


def seed(*, reset: bool, investigate: bool) -> int:
    settings = get_settings()
    embedder = get_embedder()

    if reset:
        print("Dropping and recreating schema...")
        reset_db()
    else:
        init_db()

    with session_scope() as session:
        case = session.get(Case, DEMO_CASE["id"])
        if case is None:
            case = Case(**DEMO_CASE, status="draft")
            session.add(case)
            session.flush()
            audit.record(
                session,
                case_id=case.id,
                actor="seed",
                actor_type="system",
                action=audit.CASE_CREATED,
                summary=f"Demonstration case created for {case.organisation}.",
                entity_type="case",
                entity_id=case.id,
            )
            print(f"Created case {case.reference} - {case.organisation}")
        else:
            print(f"Case {case.reference} already exists; refreshing documents.")

        print(f"Embedding backend: {embedder.description}")

        case_dir = settings.demo_data_dir / "northstar"
        results = ingest_directory(
            session,
            case_dir,
            embedder=embedder,
            doc_kind="case",
            case_id=case.id,
            id_prefix="northstar-",
        )
        for result in results:
            print(f"  case doc  {result.document_id:<44} {result.chunks:>3} chunks")
            audit.record(
                session,
                case_id=case.id,
                actor="seed",
                actor_type="system",
                action=audit.DOCUMENT_INGESTED,
                summary=f"Ingested {result.name} ({result.chunks} chunks).",
                entity_type="document",
                entity_id=result.document_id,
            )

        policy_results = ingest_directory(
            session,
            settings.policy_data_dir,
            embedder=embedder,
            doc_kind="policy",
            case_id=None,
            id_prefix="policy-",
        )
        for result in policy_results:
            print(f"  policy    {result.document_id:<44} {result.chunks:>3} chunks")

        total_chunks = sum(r.chunks for r in results) + sum(r.chunks for r in policy_results)
        print(
            f"\nIngested {len(results)} case document(s) and "
            f"{len(policy_results)} policy document(s); {total_chunks} chunks total."
        )

    if not investigate:
        print("\nSeed complete. Run with --investigate to also run the graph.")
        return 0

    provider = get_llm_provider()
    print(
        f"\nRunning investigation using "
        f"{'recorded responses' if not provider.live else provider.model}..."
    )
    started = time.perf_counter()

    with session_scope() as session:
        case = session.execute(select(Case).where(Case.id == DEMO_CASE["id"])).scalar_one()
        investigation = run_investigation(
            session,
            case=case,
            provider=provider,
            embedder=get_embedder(),
            actor="seed",
            max_attempts=settings.model_max_attempts,
            max_tokens=settings.model_max_tokens,
            temperature=settings.model_temperature,
        )
        elapsed = time.perf_counter() - started
        print(f"\nInvestigation {investigation.id} -> {investigation.status}")
        print(
            f"  rating          {investigation.overall_level or '-'} "
            f"({investigation.overall_score:.0f}/100)"
        )
        print(f"  findings        {len(investigation.risks)}")
        print(f"  evidence        {len(investigation.evidence)}")
        print(f"  duration        {elapsed:.1f}s")
        print(f"  estimated cost  ${investigation.total_cost_usd:.4f}")
        if investigation.errors:
            print("  errors:")
            for error in investigation.errors:
                print(f"    - {error}")
        return 0 if investigation.status != "failed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the ARGUS demo corpus.")
    parser.add_argument("--reset", action="store_true", help="drop and recreate the schema first")
    parser.add_argument(
        "--investigate",
        action="store_true",
        help="also run the investigation graph for the demo case",
    )
    args = parser.parse_args()
    return seed(reset=args.reset, investigate=args.investigate)


if __name__ == "__main__":
    raise SystemExit(main())
