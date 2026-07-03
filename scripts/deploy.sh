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
HOST="evmax.ai"
KEY_FILE="evmax/assets/indexnow_key.txt"
KEY="$(cat "$KEY_FILE" | tr -d '[:space:]')"
KEY_LOCATION="https://${HOST}/${KEY}.txt"
SITEMAP="dist/sitemap.xml"

if [[ ! -f "$SITEMAP" ]]; then
  echo "==> No $SITEMAP found; skipping IndexNow ping."
  exit 0
fi

echo "==> Parsing URLs from $SITEMAP"
URL_LIST_JSON="$(python3 -c "
import json, re, sys

with open('$SITEMAP', encoding='utf-8') as fh:
    xml = fh.read()

urls = re.findall(r'<loc>(.*?)</loc>', xml)
print(json.dumps(urls))
")"

echo "==> Submitting $(python3 -c "import json,sys; print(len(json.loads(sys.argv[1])))" "$URL_LIST_JSON") URLs to IndexNow"

BODY="$(python3 -c "
import json, sys

urls = json.loads(sys.argv[1])
payload = {
    'host': '$HOST',
    'key': '$KEY',
    'keyLocation': '$KEY_LOCATION',
    'urlList': urls,
}
print(json.dumps(payload))
" "$URL_LIST_JSON")"

HTTP_STATUS="$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "https://api.indexnow.org/indexnow" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "$BODY")"

echo "==> IndexNow response: HTTP $HTTP_STATUS"
