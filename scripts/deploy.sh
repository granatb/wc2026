#!/usr/bin/env bash
# Deploy dist/ to Cloudflare Pages, then ping IndexNow so search engines pick up
# every URL immediately instead of waiting for the next crawl.
#
# Usage: scripts/deploy.sh
# Run from the repo root, after `python3 -m evmax.build --round N ...` has
# populated dist/.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Deploying dist/ to Cloudflare Pages (project: evmax)"
npx wrangler@latest pages deploy dist --project-name evmax --branch main --commit-dirty=true

# --- IndexNow ping -----------------------------------------------------------
# Delegated to the tested script (stdlib, injectable, offline-tested in
# tests/test_indexnow.py). Non-fatal on purpose: the deploy above already
# succeeded, and a failed ping is re-runnable by hand.
python3 scripts/indexnow_ping.py --out dist \
  || echo "==> IndexNow ping FAILED (non-fatal) — re-run: python3 scripts/indexnow_ping.py --out dist"
