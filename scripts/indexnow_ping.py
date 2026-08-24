#!/usr/bin/env python3
"""Tell the engines about every deployed URL — the post-deploy IndexNow ping.

IndexNow (indexnow.org) is keyless-account instant indexing for Bing, Yandex
and Seznam — and Bing powers Copilot and Perplexity grounding, which is where
an FPL answer engine gets cited. The site serves /{key}.txt (written by
evmax.build.write_site_chrome on every build, key committed at
evmax/assets/indexnow_key.txt — it is not a secret, it proves domain control
by being served), and this script POSTs the freshly deployed sitemap's URL
list to the shared endpoint. Google does NOT consume IndexNow — Google needs
the one-time Search Console setup (owner action, in his browser; see the
Thursday runbook's first-time appendix).

Usage (right after a deploy):
    python3 scripts/indexnow_ping.py --out dist

Exit 0 on HTTP 200/202, nonzero otherwise — and it NEVER raises on a network
failure: a failed ping must not break a deploy (scripts/deploy.sh treats a
nonzero exit as a warning). Re-run it by hand any time; IndexNow deduplicates.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENDPOINT = "https://api.indexnow.org/indexnow"
KEY_PATH = os.path.join(_HERE, "evmax", "assets", "indexnow_key.txt")
MAX_URLS = 10_000        # the protocol's per-POST ceiling
TIMEOUT = 30


def load_key() -> str:
    with open(KEY_PATH, encoding="utf-8") as fh:
        return fh.read().strip()


def urls_from_sitemap(xml_text: str) -> list:
    """Every <loc> in document order. A regex on purpose: the sitemap is our
    own generator's output (evmax.render.sitemap_xml), and a namespace-blind
    match keeps this immune to urlset attribute changes."""
    return re.findall(r"<loc>(.*?)</loc>", xml_text)


def build_payload(urls: list, key: str) -> dict:
    host = urllib.parse.urlparse(urls[0]).netloc
    return {
        "host": host,
        "key": key,
        "keyLocation": f"https://{host}/{key}.txt",
        "urlList": urls[:MAX_URLS],
    }


def ping(payload: dict, opener=None) -> int:
    """POST the payload; return the HTTP status code."""
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": "wc2026-engine/1.0"},
        method="POST",
    )
    with opener(request, timeout=TIMEOUT) as response:
        return getattr(response, "status", None) or response.getcode()


def main(argv=None, opener=None) -> int:
    ap = argparse.ArgumentParser(
        description="POST the deployed sitemap's URLs to IndexNow")
    ap.add_argument("--out", default="dist",
                    help="the deployed tree (holding sitemap.xml)")
    args = ap.parse_args(argv)

    sitemap_path = os.path.join(args.out, "sitemap.xml")
    if not os.path.exists(sitemap_path):
        print(f"indexnow: no sitemap at {sitemap_path} — build first "
              f"(python3 -m evmax.build ...)")
        return 1
    with open(sitemap_path, encoding="utf-8") as fh:
        urls = urls_from_sitemap(fh.read())
    if not urls:
        print(f"indexnow: {sitemap_path} carries no <loc> entries")
        return 1

    payload = build_payload(urls, load_key())
    try:
        status = ping(payload, opener=opener)
    except Exception as exc:  # noqa: BLE001 — a failed ping must not break a deploy
        print(f"indexnow: ping FAILED ({exc}) — deploy is unaffected; re-run "
              f"scripts/indexnow_ping.py --out {args.out} when the network "
              f"is back")
        return 1

    print(f"indexnow: submitted {len(payload['urlList'])} URL(s) for "
          f"{payload['host']} — HTTP {status}")
    if status in (200, 202):
        return 0
    print("indexnow: non-success status; check key file deployment "
          f"(https://{payload['host']}/{payload['key']}.txt) and retry")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
