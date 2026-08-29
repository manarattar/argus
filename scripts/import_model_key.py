"""Copy a model API key from another local project's .env into ARGUS's .env.

Convenience for local development only. It reads a key from a source ``.env``
you already have and writes it into this repository's ``.env``, which is
git-ignored. It prints nothing but the variable names it moved - never a value.

Usage:
    python -m scripts.import_model_key --from ../some-project/backend/.env
    python -m scripts.import_model_key --from ../some-project/.env --var ANTHROPIC_API_KEY
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPO_ROOT / ".env"
TEMPLATE = REPO_ROOT / ".env.example"

ASSIGNMENT = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = ASSIGNMENT.match(line)
        if match:
            values[match.group(1)] = match.group(2).strip().strip("'\"")
    return values


def upsert(path: Path, updates: dict[str, str]) -> None:
    """Set each variable in ``path``, preserving comments and ordering."""
    if not path.exists():
        path.write_text(
            TEMPLATE.read_text(encoding="utf-8") if TEMPLATE.exists() else "",
            encoding="utf-8",
        )

    lines = path.read_text(encoding="utf-8").splitlines()
    remaining = dict(updates)

    for index, line in enumerate(lines):
        match = ASSIGNMENT.match(line.strip())
        if match and match.group(1) in remaining:
            key = match.group(1)
            lines[index] = f"{key}={remaining.pop(key)}"

    for key, value in remaining.items():
        lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from",
        dest="source",
        required=True,
        help="path to the .env file to read the key from",
    )
    parser.add_argument(
        "--var",
        action="append",
        default=None,
        help="variable to copy (repeatable). Defaults to the usual model keys.",
    )
    args = parser.parse_args()

    wanted = args.var or [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_BASE_URL",
        "MODEL_NAME",
    ]

    source = Path(args.source).expanduser().resolve()
    values = read_env(source)
    if not values:
        print(f"No readable variables found in {source}")
        return 1

    updates = {k: values[k] for k in wanted if values.get(k)}
    if not updates:
        print(f"None of {', '.join(wanted)} were set in {source}")
        return 1

    upsert(TARGET, updates)
    print(f"Wrote {', '.join(sorted(updates))} into {TARGET}")
    print("Values were not printed. Verify with: python -m scripts.doctor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
