"""Report how ARGUS is currently configured, without revealing secrets.

Answers the question a reviewer asks first: is this thing running a real model
or serving recordings, and which retrieval backend is behind the numbers?

    python -m scripts.doctor
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "apps" / "api")]

from argus_api.core.settings import get_settings  # noqa: E402
from argus_api.services.runtime import runtime_status  # noqa: E402


def mask(value: str) -> str:
    """Confirm a credential is present without disclosing it."""
    if not value:
        return "not set"
    return f"set ({len(value)} chars, ends {value[-4:]})"


def main() -> int:
    settings = get_settings()
    status = runtime_status(settings)

    print("ARGUS configuration")
    print("=" * 58)
    print(f"  environment          {settings.environment}")
    print(f"  database             {status['database']}")
    print(f"  model backend        {settings.model_backend}")
    print(f"  OPENAI_API_KEY       {mask(settings.openai_api_key)}")
    print(f"  ANTHROPIC_API_KEY    {mask(settings.anthropic_api_key)}")
    print()
    print(f"  mode                 {status['mode'].upper()}")
    print(f"  {status['headline']}")
    print(f"  {status['explanation']}")
    print()
    print(f"  embeddings           {status['embedding']['description']}")
    if status["embedding"]["caveat"]:
        print(f"    note: {status['embedding']['caveat']}")
    print()

    recordings = settings.recordings_dir
    count = len(list(recordings.glob("*.json"))) if recordings.exists() else 0
    print(f"  recordings           {count} file(s) in {recordings}")
    if status["mode"] == "demo" and count == 0:
        print()
        print("  WARNING: Demo Mode is active but there are no recordings.")
        print("  Agent steps will fail with a clear error rather than produce")
        print("  content. Either configure a model key in .env, or restore the")
        print("  recordings with: python -m scripts.record_demo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
