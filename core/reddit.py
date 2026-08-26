"""Read-only Reddit client — the official API, app-only OAuth, no password.

WHY THIS EXISTS: Reddit is where this project's best corrections have come from
(the double-keeper trick, Maguire's and Isak's real minutes, the Watkins recency
catch), and every one of them reached the model by the owner pasting a thread.
This is the sanctioned way to read the same material systematically: Reddit's
documented API, authenticated app-only (grant_type=client_credentials), rate
limited, with a descriptive User-Agent as their rules require.

WHAT IT WILL NEVER DO: post, vote, comment, message, or authenticate as a human.
Standing owner policy is that outbound Reddit activity is his, disclosed, and
manual (STRATEGY §8, "never covert automation"). This module has no write path,
by construction — there is no code here that can POST to a subreddit.

Credentials come from the environment (REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET,
set by the owner in the gitignored .env). Following core/growth's source
contract: when they are absent the module degrades to "not configured" and
returns None rather than raising, so a runbook step can skip it cleanly.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"
USER_AGENT = "python:evmax-research:v1.0 (read-only; +https://evmax.ai)"
DEFAULT_SUBREDDIT = "FantasyPL"
# Reddit allows ~100 queries/minute per client id. We are nowhere near that, but
# a floor between calls keeps us politely under it even in a tight loop.
MIN_INTERVAL = 1.1

_token_cache: dict = {}
_last_call = [0.0]


def configured() -> bool:
    """True when both credentials are present in the environment."""
    return bool(os.environ.get("REDDIT_CLIENT_ID")
                and os.environ.get("REDDIT_CLIENT_SECRET"))


def _throttle() -> None:
    gap = time.time() - _last_call[0]
    if gap < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - gap)
    _last_call[0] = time.time()


def _post_token(opener=urllib.request.urlopen) -> dict:
    cid = os.environ["REDDIT_CLIENT_ID"]
    secret = os.environ["REDDIT_CLIENT_SECRET"]
    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, headers={
        "Authorization": f"Basic {basic}", "User-Agent": USER_AGENT})
    with opener(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def token(opener=urllib.request.urlopen, now=None) -> str | None:
    """A cached app-only bearer token, or None when unconfigured.

    Cached until 60s before expiry — a token refresh costs a request, and the
    default lifetime is an hour.
    """
    if not configured():
        return None
    now = now if now is not None else time.time()
    if _token_cache.get("value") and _token_cache.get("expires", 0) > now + 60:
        return _token_cache["value"]
    payload = _post_token(opener=opener)
    _token_cache["value"] = payload.get("access_token")
    _token_cache["expires"] = now + float(payload.get("expires_in", 3600))
    return _token_cache["value"]


def _get(path: str, params: dict, opener=urllib.request.urlopen) -> dict | None:
    bearer = token(opener=opener)
    if not bearer:
        return None
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"bearer {bearer}", "User-Agent": USER_AGENT})
    _throttle()
    try:
        with opener(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:      # 401/403/429 — say so, don't raise
        print(f"  [reddit] HTTP {exc.code} on {path} — skipping")
        return None
    except OSError as exc:
        print(f"  [reddit] network error on {path} ({exc}) — skipping")
        return None


# --- pure parsers ---------------------------------------------------------

def parse_listing(payload: dict) -> list:
    """A Reddit listing -> [{id, title, author, score, num_comments, created_utc,
    permalink, selftext, subreddit}]. Pure; unknown shapes yield []."""
    out = []
    for child in ((payload or {}).get("data") or {}).get("children") or []:
        d = child.get("data") or {}
        out.append({
            "id": d.get("id"), "title": d.get("title") or "",
            "author": d.get("author"), "score": d.get("score", 0),
            "num_comments": d.get("num_comments", 0),
            "created_utc": d.get("created_utc"),
            "permalink": f"https://reddit.com{d.get('permalink', '')}",
            "selftext": (d.get("selftext") or "")[:4000],
            "subreddit": d.get("subreddit"),
        })
    return out


def parse_comments(payload: list) -> list:
    """The comments half of a post response -> flat [{author, score, body}].

    Reddit nests replies arbitrarily deep; this flattens breadth-first and drops
    the 'more comments' stubs, which carry no text.
    """
    out = []
    if not isinstance(payload, list) or len(payload) < 2:
        return out
    queue = list(((payload[1] or {}).get("data") or {}).get("children") or [])
    while queue:
        child = queue.pop(0)
        if child.get("kind") == "more":
            continue
        d = child.get("data") or {}
        if d.get("body"):
            out.append({"author": d.get("author"), "score": d.get("score", 0),
                        "body": d["body"][:4000]})
        replies = d.get("replies")
        if isinstance(replies, dict):
            queue.extend(((replies.get("data") or {}).get("children") or []))
    return out


# --- read paths -----------------------------------------------------------

def search(query: str, subreddit: str = DEFAULT_SUBREDDIT, sort: str = "new",
           limit: int = 25, opener=urllib.request.urlopen) -> list | None:
    """Search one subreddit. None when unconfigured, [] when nothing matched."""
    payload = _get(f"/r/{subreddit}/search",
                   {"q": query, "restrict_sr": 1, "sort": sort,
                    "limit": min(limit, 100), "raw_json": 1}, opener=opener)
    return None if payload is None else parse_listing(payload)


def hot(subreddit: str = DEFAULT_SUBREDDIT, limit: int = 25,
        opener=urllib.request.urlopen) -> list | None:
    payload = _get(f"/r/{subreddit}/hot",
                   {"limit": min(limit, 100), "raw_json": 1}, opener=opener)
    return None if payload is None else parse_listing(payload)


def post_comments(post_id: str, subreddit: str = DEFAULT_SUBREDDIT,
                  limit: int = 100, opener=urllib.request.urlopen) -> list | None:
    payload = _get(f"/r/{subreddit}/comments/{post_id}",
                   {"limit": min(limit, 500), "raw_json": 1}, opener=opener)
    return None if payload is None else parse_comments(payload)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Read-only Reddit search (official API)")
    ap.add_argument("--search", help="query to run against the subreddit")
    ap.add_argument("--hot", action="store_true", help="list hot posts instead")
    ap.add_argument("--comments", help="post id to read comments for")
    ap.add_argument("--subreddit", default=DEFAULT_SUBREDDIT)
    ap.add_argument("--limit", type=int, default=15)
    args = ap.parse_args(argv)
    if not configured():
        print("reddit: not configured — set REDDIT_CLIENT_ID and "
              "REDDIT_CLIENT_SECRET in .env (see docs/runbooks).")
        return 2
    if args.comments:
        rows = post_comments(args.comments, args.subreddit, args.limit) or []
        for c in rows:
            print(f"[{c['score']:>4}] {c['author']}: {c['body'][:300]}")
        return 0
    rows = (hot(args.subreddit, args.limit) if args.hot
            else search(args.search or "", args.subreddit, limit=args.limit)) or []
    for p in rows:
        print(f"[{p['score']:>4} · {p['num_comments']:>3}c] {p['title'][:110]}")
        print(f"       {p['permalink']}")
    print(f"({len(rows)} result(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
