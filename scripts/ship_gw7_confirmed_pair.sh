#!/usr/bin/env bash
# Dated editorial-only follow-up; run in the existing authorized Mac terminal.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="/Users/bartlomiej.granat/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
export PYTHONDONTWRITEBYTECODE=1
export PATH="$(dirname "$PYTHON_BIN"):$PATH"
command -v npx >/dev/null || { echo 'npx unavailable: no commit, push or deployment performed.'; exit 1; }
test "$(git branch --show-current)" = 'chore/gw6-thursday'
test "$(git rev-parse HEAD)" = '5e581006e0eee1d49007cfdb2c1b8feca7b1a83d' || { echo 'HEAD changed; review this dated release before continuing.'; exit 1; }
git diff --cached --quiet || { echo 'Staged work already exists; review before releasing.'; exit 1; }
"$PYTHON_BIN" -B -c 'from datetime import datetime,timezone; assert datetime.now(timezone.utc) < datetime(2026,10,17,10,tzinfo=timezone.utc), "GW7 deadline passed; review this advisory before publication"'
"$PYTHON_BIN" -B scripts/publish_gw7_confirmed_pair.py --out dist
git add -- HANDOFF.md docs/reviews/2026-09-07-fix-plan.md \
  docs/reviews/2026-10-16-gw7-confirmed-pair.md \
  evmax/assets/editorial/fpl-gw7/confirmed-pair.html \
  scripts/publish_gw7_confirmed_pair.py scripts/ship_gw7_confirmed_pair.sh
git diff --cached --check
git commit -m "Record confirmed GW7 pair and conditional lineup"
git push origin HEAD
bash scripts/deploy.sh
"$PYTHON_BIN" -B scripts/publish_gw7_confirmed_pair.py --out dist --base-url https://evmax.ai
git rev-parse HEAD
