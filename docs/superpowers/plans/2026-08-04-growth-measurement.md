# Growth Measurement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Know whether the machine is working. Per-gameweek: search position, indexing coverage, IndexNow acceptance, traffic by path and referrer, LLM citation presence, and Reddit outcomes — graded peak-over-peak, not minute-to-minute.

**Architecture:** A `core/growth/` package with one thin client per source, each reading its credential from the environment and **degrading to "not configured" rather than failing**, so sources light up as credentials arrive instead of blocking each other. `scripts/growth_report.py` aggregates them into a dated markdown report under `data/growth/`. Snapshots are committed so peak-over-peak deltas survive.

**Tech Stack:** Python 3.9 stdlib only (`urllib.request`, `json`) — matching `core/odds.py` and `core/fpl_api.py`, which are stdlib HTTP clients already. No new dependencies.

**Strategy grounding:** `docs/STRATEGY.md` §1 (event-ratchet model), §5 (GEO playbook, items 2 and 7), §8 (Reddit playbook).

---

## Why this shape

**§1's event-ratchet model decides the cadence.** The strategy explicitly optimises for event peaks and expects quiet valleys: "Each peak deposits permanent residue (backlinks, brand searches, citations, email signups) that raises the floor for the next peak." So the question a report must answer is **did this peak raise the floor**, which is a peak-over-peak comparison, not a live dashboard. Snapshots get committed for exactly that reason.

**The zero-tracking posture is a published promise, not a preference.** `/privacy/` states in reader-facing text: "no cookies, no analytics or trackers, no third-party requests." §5's 07-04 decision was "no analytics until a cookieless one is chosen." Every source in this plan is therefore **server-side or API-side only** — nothing executes in a visitor's browser, nothing sets a cookie, and the promise stands unedited.

Owner floated adding cookies (2026-08-04). Deferred, not rejected: the questions being asked — did the peak raise the floor, is IndexNow working, are we ranking, did Reddit convert — are all answerable from referrer, path and timestamp, which the Cloudflare edge already logs. Cookies buy stitched sessions and funnels, which none of those questions need. The asymmetry is that cookies can be added in a week, whereas un-publishing a removed privacy promise is not possible. Revisit once there is a question the edge logs genuinely cannot answer.

**There is a real baseline to measure against.** `docs/research/2026-07-03-competitor-landscape.md` recorded **zero retrieval presence across 15 target queries**, and noted the "evmax" entity collides with EV-charger brands. That document holds the query list — the implementer must read it and use those exact queries, not invent new ones, or the baseline is worthless.

**Reddit is deliberately manual.** Spec D7 established Reddit is unreachable from this toolchain (UA-blocked on direct fetch, refused by WebFetch and WebSearch, blocked by browser policy), and §8's rule is **never covert automation** — "failure mode is brand-fatal for a transparency brand." So the owner records what happened; this builds the log and the grading. Same division as the lineup notes: build the ingestion path, not the acquisition path.

---

## File structure

| File | Responsibility |
|---|---|
| `core/growth/__init__.py` (create) | Package marker. |
| `core/growth/cloudflare.py` (create) | Zone analytics via the GraphQL API. Requests by path and referrer. |
| `core/growth/bing.py` (create) | Bing Webmaster: query stats, indexed count, IndexNow submission status. |
| `core/growth/gsc.py` (create) | Google Search Console: position/impressions/clicks per query and page, plus URL inspection. |
| `core/growth/citations.py` (create) | The §5 item 7 loop: log which engines cite us for the 15 target queries. |
| `core/growth/reddit_log.py` (create) | Parse and grade the owner's hand-written post log. |
| `core/growth/snapshot.py` (create) | Read/write dated snapshots; compute peak-over-peak deltas. |
| `scripts/growth_report.py` (create) | CLI: gather every configured source, emit a dated markdown report. |
| `tests/test_growth_*.py` (create) | Per-source parse tests against saved fixtures, offline. |

`data/growth/` holds raw pulls (gitignored, like the rest of `data/`). **Snapshots are the exception** — they go in `evmax/assets/growth/` and are committed, because a peak-over-peak delta needs the previous peak to still exist. Mirrors how `evmax/assets/projections/` holds the frozen projection record.

---

## Task 1: The report skeleton and one working source

Build the frame and Cloudflare together, because a frame with no source cannot be verified and Cloudflare is the credential the owner can get fastest (an API token, no OAuth).

**Files:** Create `core/growth/__init__.py`, `core/growth/cloudflare.py`, `core/growth/snapshot.py`, `scripts/growth_report.py`; Test `tests/test_growth_cloudflare.py`, `tests/test_growth_snapshot.py`

### The contract every source must satisfy

```python
def configured() -> bool:
    """True when this source's credentials are present in the environment."""

def fetch(since: str, until: str) -> dict | None:
    """Raw pull for the window, or None when not configured.

    NEVER raises on a missing credential, an auth failure or a network error.
    A growth report is diagnostics: one dead source must degrade its own section
    to "unavailable" and leave every other section intact. Returning None and
    letting the report say so is the contract.
    """
```

That contract is the load-bearing design decision. Three sources with three different auth stories will not all be configured at once, and a report that dies because Google's OAuth is not set up yet is useless for reading Cloudflare.

- [ ] **Step 1: Write the failing tests**

Parse tests against a saved fixture, no network:

```python
class TestCloudflareParse(unittest.TestCase):
    RESPONSE = {  # shape of the GraphQL zone analytics response
        "data": {"viewer": {"zones": [{"httpRequestsAdaptiveGroups": [
            {"dimensions": {"clientRequestPath": "/fpl/gw1/captains/",
                            "clientRefererHost": "www.reddit.com"},
             "count": 412},
            {"dimensions": {"clientRequestPath": "/fpl/gw1/captains/",
                            "clientRefererHost": "www.google.com"},
             "count": 190},
            {"dimensions": {"clientRequestPath": "/", "clientRefererHost": ""},
             "count": 88},
        ]}]}}
    }

    def test_requests_by_path(self):
        out = cloudflare.parse(self.RESPONSE)
        self.assertEqual(out["by_path"]["/fpl/gw1/captains/"], 602)
        self.assertEqual(out["by_path"]["/"], 88)

    def test_requests_by_referrer(self):
        out = cloudflare.parse(self.RESPONSE)
        self.assertEqual(out["by_referrer"]["www.reddit.com"], 412)

    def test_empty_referrer_is_direct_not_a_blank_key(self):
        """A blank referrer host is direct traffic, and a report that prints an
        empty string as a source name is unreadable."""
        self.assertEqual(cloudflare.parse(self.RESPONSE)["by_referrer"]["direct"], 88)

    def test_total(self):
        self.assertEqual(cloudflare.parse(self.RESPONSE)["total"], 690)

    def test_a_graphql_error_response_parses_as_none(self):
        """Cloudflare returns HTTP 200 with an `errors` key on a bad query."""
        self.assertIsNone(cloudflare.parse({"errors": [{"message": "nope"}]}))

    def test_an_empty_zone_list_is_not_a_crash(self):
        out = cloudflare.parse({"data": {"viewer": {"zones": []}}})
        self.assertEqual(out["total"], 0)


class TestConfigured(unittest.TestCase):
    def test_not_configured_without_a_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(cloudflare.configured())

    def test_configured_with_both_values(self):
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "t",
                                          "CLOUDFLARE_ACCOUNT_ID": "a"}):
            self.assertTrue(cloudflare.configured())

    def test_fetch_returns_none_when_unconfigured(self):
        """The contract: never raise on a missing credential."""
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(cloudflare.fetch("2026-08-01", "2026-08-04"))
```

Snapshot tests:

```python
class TestSnapshot(unittest.TestCase):
    def test_round_trips(self): ...
    def test_delta_against_the_previous_snapshot(self): ...
    def test_delta_with_no_previous_snapshot_is_none_not_zero(self):
        """First run has no baseline. Reporting 0% growth would be a lie; the
        report must say 'no previous peak' instead."""
    def test_snapshots_are_ordered_by_gameweek_not_filename(self): ...
```

Write these out properly.

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement.** Use `urllib.request` following `core/fpl_api.py`'s conventions. The Cloudflare GraphQL endpoint is `https://api.cloudflare.com/client/v4/graphql`; query `httpRequestsAdaptiveGroups` with `clientRequestPath` and `clientRefererHost` dimensions. **Look up the current schema rather than trusting this plan** — Cloudflare's analytics datasets have been renamed before, and a plan written today can be stale. If the dataset name differs, use the real one and note it.

- [ ] **Step 4: `scripts/growth_report.py`** — `--gw N` for labelling, `--since` / `--until` for the window, defaulting to since-the-last-snapshot. Emits markdown to `data/growth/gw{N}-{date}.md` and writes the snapshot to `evmax/assets/growth/`. Every unconfigured source gets a line saying which environment variable would enable it — a report that silently omits a source is worse than one that says "GSC: not configured, set GSC_CLIENT_ID".

- [ ] **Step 5: Verify.** Full suite green. Then run the report with no credentials at all and confirm it produces a readable document saying every source is unconfigured rather than crashing. That is the degradation path and it is the one most likely to be exercised.

- [ ] **Step 6: Commit.**

---

## Task 2: Bing Webmaster and IndexNow status

**Files:** Create `core/growth/bing.py`; Test `tests/test_growth_bing.py`

API-key auth, so this is the second-easiest credential. Bing matters disproportionately: §5 notes Perplexity and Copilot retrieve from Bing's index and competition there is near-zero.

Three things to pull: query stats (impressions, clicks, average position), indexed page count, and **IndexNow submission status** — which is the only way to learn whether our deploy-time pings are being accepted. `scripts/deploy.sh` submits and reads the HTTP code, but a 200 means "accepted for processing", not "indexed".

- [ ] Same `configured()` / `fetch()` / `parse()` contract.
- [ ] Tests against a saved fixture. Include a test that an HTTP 401 (bad key) returns `None` rather than raising — a rotated key must not break the whole report.
- [ ] Report section: indexed count, top queries by impressions, and IndexNow acceptance.
- [ ] Commit.

---

## Task 3: Google Search Console

**Files:** Create `core/growth/gsc.py`; Test `tests/test_growth_gsc.py`

The authoritative position data, and the only real answer on Google indexing coverage. OAuth makes it the most setup, hence last.

- [ ] Search Analytics query: impressions, clicks, CTR, average position, by query and by page, for the window.
- [ ] URL Inspection for the current gameweek's eight article URLs — the direct answer to "did Google index what we just published", which is the IndexNow question restated.
- [ ] **Token handling:** a refresh token in `.env`, exchanged for an access token per run. **Never log or print a token**, and never write one into `data/growth/` — those files are diagnostics that could end up pasted into a report. Add a test that the fetch path does not include the token in any returned structure.
- [ ] Same contract; an expired refresh token degrades to `None` with a clear "re-authorise" line in the report.
- [ ] Commit.

---

## Task 4: The citation loop (§5 item 7)

**Files:** Create `core/growth/citations.py`; Test `tests/test_growth_citations.py`

§5 item 7: "ask ChatGPT/Claude/Perplexity the target queries, log who gets cited, tune." The baseline is **zero presence across 15 target queries** as of 07-03.

**Read `docs/research/2026-07-03-competitor-landscape.md` and use its exact 15 queries.** Inventing new ones discards the only baseline that exists. If the list is ambiguous, report what you found rather than guessing.

Two honest constraints:
- We can ask **Claude** directly (`ANTHROPIC_API_KEY` is already in `.env` and `evmax/writer.py` already calls it). Whether Claude cites a source depends on its search tooling being enabled for that call — check what is actually available rather than assuming, and report what the call can and cannot see.
- ChatGPT and Perplexity need their own API keys, which the owner does not have. **Do not build a scraper for them.** Support them behind `configured()` so they light up if keys arrive, and until then record them as unmeasured. §5 item 8 already sets the expectation that citation rates are low (~3%); a partial measurement honestly labelled beats a fabricated one.

- [ ] Log per query per engine: cited or not, and the competing sources named. Snapshot it so presence over time is visible.
- [ ] Report section: N of 15 queries citing us, and the delta against the July zero baseline.
- [ ] Commit.

---

## Task 5: The Reddit log

**Files:** Create `core/growth/reddit_log.py`; Test `tests/test_growth_reddit.py`

**No Reddit API, no scraping, no browser automation.** The owner posts and records the outcome; this parses and grades it.

A shorthand log the owner appends to, following `scripts/fpl_notes.py`'s precedent so the muscle memory transfers:

```
gw1 r/FantasyPL 2026-08-19  upvotes 47 comments 12  # captains post
gw1 r/FantasyWC 2026-08-19  upvotes 8 comments 3    # rate-my-team reply
```

- [ ] `parse(text)` — reject unrecognised lines rather than dropping them, same discipline as `fpl_notes.parse`.
- [ ] **Grade against traffic**: cross-reference the Cloudflare referrer data for `reddit.com` in the window against what was posted. That correlation is the actual question — did the post send anyone — and it is only answerable because both halves exist.
- [ ] Report section: posts made, engagement, and referred traffic per post.
- [ ] Commit.

---

## Task 6: Wire together, document, schedule

- [ ] Full suite green.
- [ ] Run the complete report with whatever credentials exist and include the output in the report-back. **State plainly which sources were live and which were unconfigured** — a growth report that looks complete while measuring one source is the failure mode to avoid.
- [ ] `docs/STRATEGY.md`: tick §5 item 7, and record the cookies deferral with its reasoning so the decision is not silently revisited.
- [ ] `README.md`: the report command and the environment variables each source needs.
- [ ] `CHANGELOG.md` entry.
- [ ] Consider whether this belongs in `scripts/morning-update.sh` (which already exists) or as a `/loop`-style scheduled run. **Recommend, do not wire up a schedule unprompted** — a cron that burns API quota is the owner's call.
- [ ] Commit, push.

---

## Self-Review

- **Cadence matches the strategy:** §1's event-ratchet model wants peak-over-peak, so snapshots are committed and deltas are the headline. A live dashboard would answer a question the strategy does not ask.
- **The privacy promise survives:** every source is server-side or API-side. Nothing runs in a browser, nothing sets a cookie, `/privacy/` needs no edit. The cookies question is recorded as deferred with its reasoning, not dropped.
- **Degradation is the primary design constraint**, because three sources with three auth stories will never all be configured at once. Every source returns `None` rather than raising, and Task 1 Step 5 explicitly tests the all-unconfigured path.
- **The baseline is preserved:** Task 4 uses the existing 15 queries rather than new ones, so the July zero-presence measurement remains comparable.
- **Reddit stays manual**, per D7's technical reality and §8's never-covert-automation rule. Build the ingestion path, not the acquisition path.
- **No secret ever lands in a file under `data/growth/`** — those are diagnostics that get read and pasted, and Task 3 has an explicit test.
