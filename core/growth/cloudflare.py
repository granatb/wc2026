"""Cloudflare zone analytics: requests by path and by referrer host.

Reads the edge logs Cloudflare already keeps for every request to evmax.ai,
through their GraphQL Analytics API. Nothing here touches a visitor's browser,
so /privacy/'s "no cookies, no analytics or trackers, no third-party requests"
stays true -- see core/growth/__init__.py.

Dataset is `httpRequestsAdaptiveGroups`, the only zone dataset that can break
requests down by URL path: the older `httpRequests1dGroups` / `httpRequests1hGroups`
aggregates carry country, colo and status but no path and no referrer, which is
exactly the split a growth report needs (which article, from which source).
Dimension names verified against Cloudflare's current schema, 2026-08:
`clientRequestPath`, `clientRefererHost`, `count`, filtered on `datetime_geq` /
`datetime_leq` with `orderBy: [count_DESC]`.

Two failure modes matter and both return None:

  * Cloudflare answers HTTP 200 with a top-level `errors` key for a rejected
    query -- a bad dimension, or a dataset the zone's plan cannot read. A status
    check alone would read that as success, so `parse` inspects the body.
  * Anything network-shaped (`OSError`, which covers urllib's HTTPError and
    URLError) or a body that is not JSON.

The message behind a None is kept in `last_error()` so the report can say WHY a
section is unavailable. It holds Cloudflare's own error text and never a
credential; the token exists only inside `_post`'s request header.
"""
from __future__ import annotations

import json
import os
import urllib.request

ENDPOINT = "https://api.cloudflare.com/client/v4/graphql"
TOKEN_ENV = "CLOUDFLARE_API_TOKEN"
ZONE_ENV = "CLOUDFLARE_ZONE_ID"

DATASET = "httpRequestsAdaptiveGroups"

# Cloudflare caps `limit` at 10000. 5000 path x referrer pairs is far more than
# a site with eight articles a gameweek can produce, and keeps the reply small.
ROW_LIMIT = 5000

USER_AGENT = "wc2026-engine/1.0"
TIMEOUT = 40

# A blank dimension is a real value at the edge, not missing data. An empty
# referrer host means the visitor arrived without one (typed the URL, opened a
# bookmark, followed a link from an app that strips it) -- a report with an empty
# string sitting in its traffic-source column is unreadable, so name it.
DIRECT = "direct"
UNKNOWN_PATH = "(unknown)"

QUERY = """
query GrowthTraffic($zoneTag: String!, $since: Time!, $until: Time!, $limit: Int!) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      %(dataset)s(
        filter: {datetime_geq: $since, datetime_leq: $until}
        limit: $limit
        orderBy: [count_DESC]
      ) {
        count
        dimensions {
          clientRequestPath
          clientRefererHost
        }
      }
    }
  }
}
""" % {"dataset": DATASET}

_last_error: str | None = None


def last_error() -> str | None:
    """Why the most recent fetch returned None, or None if it succeeded.

    Cloudflare's own error text plus our own "not configured" message. Never
    contains a credential -- the token is only ever read inside `_post`.
    """
    return _last_error


# --- configuration -----------------------------------------------------------

def configured() -> bool:
    """True when both the API token and the zone id are in the environment.

    Zone analytics are queried by ZONE, not by account, so CLOUDFLARE_ZONE_ID is
    the id that matters here; an account id would make `zones(filter: {zoneTag:})`
    match nothing and return an empty zone list.
    """
    return bool(os.environ.get(TOKEN_ENV) and os.environ.get(ZONE_ENV))


def missing_env() -> list[str]:
    """The environment variables that would enable this source, in report order."""
    return [name for name in (TOKEN_ENV, ZONE_ENV) if not os.environ.get(name)]


# --- network -----------------------------------------------------------------

def _post(query: str, variables: dict) -> object:
    """POST a GraphQL document and return the decoded body.

    Isolated from `fetch` so tests can patch the network out entirely. Raises;
    `fetch` is the layer that swallows.
    """
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Authorization": "Bearer %s" % os.environ.get(TOKEN_ENV, ""),
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _as_time(value: str, end_of_day: bool = False) -> str:
    """Coerce a YYYY-MM-DD date (or a full timestamp) to the GraphQL Time scalar.

    A bare `until` date means the whole of that day; taking it as midnight would
    silently drop the last day of every window.
    """
    text = str(value).strip()
    if "T" in text:
        return text if text.endswith("Z") or "+" in text else text + "Z"
    return text + ("T23:59:59Z" if end_of_day else "T00:00:00Z")


def fetch(since: str, until: str) -> dict | None:
    """Requests by path and referrer for the window, or None.

    Returns None -- never raises -- when the credentials are absent, when
    Cloudflare rejects the query, or when the network is unreachable.
    """
    global _last_error
    _last_error = None
    if not configured():
        _last_error = "not configured: set %s" % " and ".join(missing_env())
        return None

    variables = {
        "zoneTag": os.environ[ZONE_ENV],
        "since": _as_time(since),
        "until": _as_time(until, end_of_day=True),
        "limit": ROW_LIMIT,
    }
    try:
        response = _post(QUERY, variables)
    except (OSError, ValueError) as exc:
        # OSError covers urllib's HTTPError and URLError; ValueError covers a
        # body that is not JSON (an HTML error page from a proxy, say).
        _last_error = "%s: %s" % (type(exc).__name__, exc)
        return None

    out = parse(response)
    if out is None:
        _last_error = _error_message(response) or "unreadable response"
        return None
    out["since"], out["until"] = variables["since"], variables["until"]
    return out


# --- pure parsing ------------------------------------------------------------

def _error_message(response) -> str | None:
    """Join Cloudflare's GraphQL error messages, for the report's why-line."""
    if not isinstance(response, dict):
        return None
    messages = []
    for err in response.get("errors") or []:
        if isinstance(err, dict) and err.get("message"):
            messages.append(str(err["message"]))
    return "; ".join(messages) or None


def _by_count(counts: dict) -> dict:
    """Biggest first, ties broken by key so a report diff is stable."""
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def parse(response) -> dict | None:
    """{'total', 'by_path', 'by_referrer'} from a GraphQL reply, or None.

    None means "this source produced nothing readable": a GraphQL `errors` body
    (which arrives with HTTP 200) or a shape that is not the one we asked for. An
    empty zone list is NOT that -- it is a real, readable zero.
    """
    if not isinstance(response, dict) or response.get("errors"):
        return None
    data = response.get("data")
    if not isinstance(data, dict):
        return None
    viewer = data.get("viewer")
    if not isinstance(viewer, dict):
        return None
    zones = viewer.get("zones")
    if not isinstance(zones, list):
        return None

    total = 0
    by_path: dict = {}
    by_referrer: dict = {}
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        for group in zone.get(DATASET) or []:
            if not isinstance(group, dict):
                continue
            count = group.get("count")
            if not isinstance(count, (int, float)) or isinstance(count, bool):
                continue
            dimensions = group.get("dimensions")
            if not isinstance(dimensions, dict):
                dimensions = {}
            path = dimensions.get("clientRequestPath") or UNKNOWN_PATH
            referrer = dimensions.get("clientRefererHost") or DIRECT
            total += count
            by_path[path] = by_path.get(path, 0) + count
            by_referrer[referrer] = by_referrer.get(referrer, 0) + count

    return {"total": total,
            "by_path": _by_count(by_path),
            "by_referrer": _by_count(by_referrer)}
