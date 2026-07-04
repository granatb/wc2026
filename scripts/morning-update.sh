#!/usr/bin/env bash
# The daily operating loop during a tournament: refresh data (results + odds +
# player props + FIFA ownership/points), rebuild the site (live mode activates
# automatically mid-round; prose regenerates for changed articles), deploy +
# ping IndexNow. Usage: scripts/morning-update.sh <round>
set -euo pipefail
ROUND="${1:?usage: scripts/morning-update.sh <round>}"
cd "$(dirname "${BASH_SOURCE[0]}")/.."
set -a; [ -f .env ] && . ./.env; set +a
echo "==> Refreshing ESPN odds/schedule + props (round $ROUND)"
python3 manage.py fifa --round "$ROUND" --refresh --props >/dev/null
echo "==> Refreshing FIFA feed (results, ownership, round points)"
python3 -c "from core import fifa_api; fifa_api.refresh()"
echo "==> Building site"
python3 -m evmax.build --round "$ROUND" --sims 50000 --out dist
echo "==> Deploying"
bash scripts/deploy.sh
