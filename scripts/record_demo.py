"""Capture live model responses so Demo Mode can replay them.

Runs the demonstration investigation against a live backend with recording
enabled, then runs the model-dependent evaluation cases so those can execute in
Demo Mode too.

    python -m scripts.record_demo

Requires a model key in ``.env``. Recordings are written to ``data/recordings``,
keyed by a hash of the exact prompt, and contain genuine model output together
with the model name, token counts and original latency.

Re-record whenever a prompt version changes: the fingerprint includes the prompt
text, so a stale recording is simply never matched rather than silently
misrepresenting the current prompt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "apps" / "api")]

from argus_api.core.settings import get_settings  # noqa: E402
from argus_api.db.models import Case  # noqa: E402
from argus_api.db.session import init_db, session_scope  # noqa: E402
from argus_api.services.evaluation import run_evaluation  # noqa: E402
from argus_api.services.investigation import run_investigation  # noqa: E402
from argus_api.services.runtime import get_embedder  # noqa: E402
from sqlalchemy import select  # noqa: E402

from ai.providers.registry import ProviderConfig, build_provider  # noqa: E402
from ai.providers.replay import RecordingStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="record the investigation only, not the evaluation cases",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.has_live_model:
        print("No live model backend is configured.")
        print()
        print("Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env, then re-run.")
        print("Check the resolved configuration with: python -m scripts.doctor")
        return 1

    # Force recording on regardless of the RECORD_LLM_CALLS setting: capturing
    # fixtures is the entire purpose of this script.
    provider = build_provider(
        ProviderConfig(
            backend=settings.model_backend,
            openai_token=settings.openai_api_key,
            openai_base_url=settings.openai_base_url,
            anthropic_token=settings.anthropic_api_key,
            anthropic_base_url=settings.anthropic_base_url,
            model_name=settings.model_name,
            recordings_dir=settings.recordings_dir,
            record=True,
        )
    )
    store = RecordingStore(settings.recordings_dir)
    before = store.stats()["count"]

    print(f"Recording against {provider.model} into {settings.recordings_dir}")
    print(f"  {before} recording(s) already present")
    print()

    init_db()
    embedder = get_embedder()

    with session_scope() as session:
        case = session.execute(select(Case).limit(1)).scalar_one_or_none()
        if case is None:
            print("No case found. Run `make seed` first.")
            return 1

        print(f"Running investigation for {case.organisation}...")
        investigation = run_investigation(
            session,
            case=case,
            provider=provider,
            embedder=embedder,
            actor="record",
            max_attempts=settings.model_max_attempts,
            max_tokens=settings.model_max_tokens,
            temperature=settings.model_temperature,
        )
        print(f"  status          {investigation.status}")
        print(
            f"  rating          {investigation.overall_level or '-'} "
            f"({investigation.overall_score:.0f}/100)"
        )
        print(f"  findings        {len(investigation.risks)}")
        print(f"  evidence        {len(investigation.evidence)}")
        print(f"  estimated cost  ${investigation.total_cost_usd:.4f}")
        for error in investigation.errors:
            print(f"  ERROR  {error}")

    if not args.skip_eval:
        print()
        print("Running model-dependent evaluation cases...")
        with session_scope() as session:
            report, _ = run_evaluation(
                session,
                dataset=settings.eval_data_dir / "cases.jsonl",
                provider=provider,
                embedder=embedder,
                recordings_dir=settings.recordings_dir,
                persist=False,
            )
            metrics = report.metrics()
            print(f"  executed {metrics['executed']} of {metrics['total_cases']} case(s)")
            print(f"  passed   {metrics['passed']}")
            print(f"  failed   {metrics['failed']}")

    store.invalidate()
    after = store.stats()["count"]
    print()
    print(f"Captured {after - before} new recording(s); {after} total.")
    print()
    print("Demo Mode will now serve these. Verify by unsetting the model key and")
    print("running: python -m scripts.doctor && python -m scripts.evaluate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
