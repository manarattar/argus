#!/bin/sh
# Container start-up for the API.
#
# Three steps, in order, each safe to repeat:
#   1. apply migrations, so a fresh volume gets the current schema and an
#      existing one is upgraded in place;
#   2. seed the demonstration corpus if the database is empty;
#   3. serve.
#
# Step 2 exists because the public demo runs on an ephemeral disk. Rather than
# treat that as a problem to work around, the container simply rebuilds the
# demonstration state on boot - which takes seconds in Demo Mode, since model
# responses are replayed rather than generated.
#
# Seeding is skipped when a case already exists, so a deployment with a real
# volume is never overwritten.

set -e

echo "[argus] applying migrations"
alembic upgrade head

if [ "${SEED_ON_BOOT:-true}" = "true" ]; then
  # Ask the application whether there is anything here already. Any failure is
  # treated as "empty", because seeding is idempotent and an empty demo is a
  # worse outcome than a redundant seed.
  CASE_COUNT=$(python - <<'PY' 2>/dev/null || echo 0
import sys
sys.path[:0] = ["/app", "/app/apps/api"]
try:
    from argus_api.db.models import Case
    from argus_api.db.session import session_scope

    with session_scope() as session:
        print(session.query(Case).count())
except Exception:
    print(0)
PY
)

  if [ "$CASE_COUNT" = "0" ]; then
    echo "[argus] empty database, seeding demonstration corpus"
    # --investigate replays the recorded run, so the demo lands on a populated
    # case rather than an empty one. Failure here must not stop the server:
    # the UI has honest empty states, and a running app that says it has no
    # investigation is better than no app at all.
    python -m scripts.seed --investigate || echo "[argus] seed failed; serving empty"
  else
    echo "[argus] database already has $CASE_COUNT case(s), skipping seed"
  fi
fi

# PORT is the convention on the host stack; API_PORT is this application's own
# name for the same thing. Accept either, preferring PORT so the platform wins.
LISTEN_PORT="${PORT:-${API_PORT:-8000}}"

echo "[argus] starting API on ${LISTEN_PORT}"
exec uvicorn argus_api.main:app \
  --app-dir apps/api \
  --host "${API_HOST:-0.0.0.0}" \
  --port "${LISTEN_PORT}"
