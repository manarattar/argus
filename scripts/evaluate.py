"""Run the ARGUS evaluation suite from the command line.

    python -m scripts.evaluate                 # full suite
    python -m scripts.evaluate --category retrieval
    python -m scripts.evaluate --case gnd-003 --verbose
    python -m scripts.evaluate --json report.json

Exits non-zero when any executed case fails, so the suite can gate CI. Skipped
cases do not fail the run - they are reported, and the coverage figure makes
clear how much of the suite actually executed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "apps" / "api")]

from argus_api.core.settings import get_settings  # noqa: E402
from argus_api.db.session import init_db, session_scope  # noqa: E402
from argus_api.services.evaluation import run_evaluation  # noqa: E402
from argus_api.services.runtime import get_embedder, get_llm_provider  # noqa: E402

STATUS_MARK = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP", "error": "ERR "}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the ARGUS evaluation suite.")
    parser.add_argument("--suite", default=None, help="run only this suite")
    parser.add_argument("--case", default=None, help="run only this case id")
    parser.add_argument("--category", default=None, help="filter results to a category")
    parser.add_argument("--json", dest="json_path", default=None, help="write the report to a file")
    parser.add_argument("--verbose", action="store_true", help="show detail for every case")
    parser.add_argument("--no-persist", action="store_true", help="do not store the run")
    args = parser.parse_args()

    settings = get_settings()
    init_db()
    provider = get_llm_provider()
    embedder = get_embedder()

    print("ARGUS evaluation suite")
    print("=" * 74)
    print(f"  model backend    {provider.name} ({provider.model})")
    print(f"  mode             {'DEMO (replayed)' if not provider.live else 'LIVE'}")
    print(f"  embeddings       {embedder.description}")
    print()

    with session_scope() as session:
        try:
            report, _ = run_evaluation(
                session,
                dataset=settings.eval_data_dir / "cases.jsonl",
                provider=provider,
                embedder=embedder,
                recordings_dir=settings.recordings_dir,
                suite=args.suite,
                case_id=args.case,
                persist=not args.no_persist,
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}")
            return 2

        results = report.results
        if args.category:
            results = [r for r in results if r.case.category == args.category]

        current = ""
        for result in sorted(results, key=lambda r: (r.case.category, r.case.id)):
            if result.case.category != current:
                current = result.case.category
                print(f"\n{current.replace('_', ' ').upper()}")
                print("-" * 74)
            mark = STATUS_MARK[result.status]
            print(f"  [{mark}] {result.case.id:<10} {result.case.description[:52]}")
            if args.verbose or result.status in {"failed", "error"}:
                print(f"         expected: {json.dumps(result.case.expected)[:100]}")
                print(f"         actual:   {result.outcome.actual[:100]}")
                if result.outcome.error:
                    print(f"         error:    {result.outcome.error[:100]}")
                if result.outcome.skipped and result.outcome.detail.get("reason"):
                    print(f"         reason:   {result.outcome.detail['reason'][:100]}")

        metrics = report.metrics()
        print()
        print("=" * 74)
        print("SUMMARY")
        print("-" * 74)
        for category, bucket in sorted(metrics["by_category"].items()):
            rate = bucket["pass_rate"]
            rate_text = f"{rate:.0%}" if rate is not None else "  n/a"
            print(
                f"  {category:<22} {bucket['passed']:>2}/{bucket['passed'] + bucket['failed']:<2} "
                f"pass  {rate_text:>6}   "
                f"({bucket['skipped']} skipped)"
            )
        print("-" * 74)
        pass_rate = metrics["pass_rate"]
        print(
            f"  {'TOTAL':<22} {metrics['passed']:>2}/{metrics['executed']:<2} pass  "
            f"{(f'{pass_rate:.0%}' if pass_rate is not None else 'n/a'):>6}   "
            f"({metrics['skipped']} skipped, {metrics['errored']} errored)"
        )
        print(f"  suite coverage         {metrics['coverage']:.0%} of cases executed")
        print(f"  duration               {metrics['duration_ms'] / 1000:.2f}s")

        if metrics["skipped"]:
            print()
            print(
                "  Note: skipped cases require a model backend. Configure a key in\n"
                "  .env, or restore the demo recordings, to execute them."
            )

        if args.json_path:
            Path(args.json_path).write_text(
                json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"\n  report written to {args.json_path}")

        return 1 if (report.failed or report.errored) else 0


if __name__ == "__main__":
    raise SystemExit(main())
