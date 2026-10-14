#!/usr/bin/env bash
# Run from a normal, authorized Mac terminal. Does not change permissions/settings.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="/Users/bartlomiej.granat/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
export PYTHONDONTWRITEBYTECODE=1
export PATH="$(dirname "$PYTHON_BIN"):$PATH"
command -v npx >/dev/null || { echo 'Node/npm npx is unavailable in this terminal; no Git or deployment action performed.'; exit 1; }
test "$(git branch --show-current)" = 'chore/gw6-thursday'
test "$(git rev-parse --short=7 HEAD)" = '0ddb44b' || { echo 'HEAD changed; review the release before continuing.'; exit 1; }
git diff --cached --quiet || { echo 'Index already contains staged changes; review them before releasing.'; exit 1; }
"$PYTHON_BIN" -B -c 'import json,pathlib; from core.forecast_archive import require_fresh; root=pathlib.Path("data/releases/2026-10-14-gw7/inputs"); [(require_fresh(json.loads((root/f"{n}.json").read_text()),json.loads((root/f"{n}.meta.json").read_text()))) for n in ("bootstrap","fixtures")]'
"$PYTHON_BIN" -B scripts/verify_gw7_release.py --out dist --receipt data/releases/2026-10-14-gw7/predeploy-check.json
git diff --check
git add -- \
  HANDOFF.md \
  docs/reviews/2026-09-07-fix-plan.md \
  docs/reviews/2026-10-12-gw6-provisional-review.md \
  docs/reviews/2026-10-14-gw7-provisional-recommendation.md \
  docs/reviews/2026-10-14-provisional-release-plan.md \
  docs/reviews/2026-10-14-provisional-release-status.md \
  evmax/assets/accuracy/gw6.json \
  evmax/assets/editorial/fpl-gw7 \
  evmax/assets/forecasts/gw7 \
  evmax/assets/projections/fpl-gw7 \
  games/fpl/decisions/gw7/553cfb64f468b6b339b882189fb06e552ee15f323232e31bd5b774a961074907.json \
  research/experts/gw7.json \
  scripts/publish_gw7_provisional.py \
  scripts/verify_gw7_release.py \
  scripts/ship_gw7_provisional.sh
git diff --cached --check
git commit -m "Publish final GW6 results and provisional GW7 research"
git push origin HEAD
bash scripts/deploy.sh
"$PYTHON_BIN" -B scripts/verify_gw7_release.py --out dist --base-url https://evmax.ai --receipt data/releases/2026-10-14-gw7/live-check.json
git rev-parse HEAD
echo 'Release verified live: https://evmax.ai/'
