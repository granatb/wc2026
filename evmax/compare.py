"""The comparison page: how evmax differs from the other public FPL models.

WHAT THIS PAGE DELIBERATELY DOES NOT DO: compare accuracy numbers between
sites. Every model grades itself over a different sample, a different set of
gameweeks and a different player pool, so "our MAE beats theirs" is not a
claim anyone can check — it is exactly the unverifiable marketing this project
exists to be the alternative to. The only accuracy comparison we publish is
against FPL's own `ep_next` on the identical player set, on our own ledger.

What this page compares instead is CHECKABLE: is the method published, is the
data licensed for reuse, is there a public graded record, is it free, can a
machine read it. Every cell carries a source and the date it was checked, and
the page states where evmax is behind — a comparison that only flatters the
author is an advert.

Facts sourced from docs/research/2026-08-24-fpl-competitor-landscape.md
(fetched + verified 2026-08-24) and re-stated here with their links.
"""

from __future__ import annotations

import html as _html

from evmax import render

CHECKED = "24 August 2026"
COMPARE_PATH = "/fpl/compare/"

# (label, url) or None when there is nothing to link.
_ROWS = [
    {
        "name": "evmax", "url": "https://evmax.ai", "us": True,
        "method": ("Published", "/about/"),
        "data": ("CC BY 4.0, per gameweek", "/data/"),
        "record": ("Public ledger, every gameweek", "/fpl/accuracy/"),
        "free": ("Free, no ads, no sign-up", None),
        "machine": ("JSON API, MCP server, llms.txt", "/data/"),
    },
    {
        "name": "Onside Arena", "url": "https://onsidearena.com",
        "method": ("Private — “the exact recipe stays private”",
                   "https://onsidearena.com"),
        "data": ("Projections in a public git repo; no reuse licence stated",
                 "https://onsidearena.com"),
        "record": ("Public rolling ledger vs ep_next",
                   "https://onsidearena.com"),
        "free": ("Free core, paid tiers", "https://onsidearena.com"),
        "machine": ("API, llms.txt, MCP (v0.2.0, unchanged since 5 Jun 2026)",
                    "https://www.npmjs.com/package/onside-football-mcp"),
    },
    {
        "name": "Solio Analytics", "url": "https://solioanalytics.com",
        "method": ("Partly described, model not published",
                   "https://solioanalytics.com"),
        "data": ("Agent endpoint, refreshed 4-hourly; licence not stated",
                 "https://fpl.solioanalytics.com"),
        "record": ("No public graded ledger", None),
        "free": ("Free tier, membership gating", "https://solioanalytics.com"),
        "machine": ("No-auth data endpoint", "https://fpl.solioanalytics.com"),
    },
    {
        "name": "FPL Review", "url": "https://fplreview.com",
        "method": ("Private", "https://fplreview.com"),
        "data": ("No open dataset", None),
        "record": ("Occasional articles (“Ultimate Truth”)",
                   "https://fplreview.com/ultimate-truth-how-fpl-models-perform-relative-to-a-perfect-model/"),
        "free": ("Free lite model; solver paid (Patreon from €3.90/mo)",
                 "https://www.patreon.com/fplreview"),
        "machine": ("Blocks AI crawlers", None),
    },
    {
        "name": "Fantasy Football Hub", "url": "https://www.fantasyfootballhub.co.uk",
        "method": ("Private", None),
        "data": ("No open dataset", None),
        "record": ("Marketing claims, no public ledger", None),
        "free": ("Paid (Starter £11.99/mo)",
                 "https://www.fantasyfootballhub.co.uk"),
        "machine": ("No public API", None),
    },
    {
        "name": "Fantasy Football Scout", "url": "https://www.fantasyfootballscout.co.uk",
        "method": ("Private", None),
        "data": ("No open dataset", None),
        "record": ("Marketing claims, no public ledger", None),
        "free": ("Paid membership", "https://www.fantasyfootballscout.co.uk"),
        "machine": ("No public API", None),
    },
]

_COLS = [("method", "Method published"), ("data", "Data reusable"),
         ("record", "Public graded record"), ("free", "Free to use"),
         ("machine", "Machine-readable")]

_CSS = (
    ".cmp-table .cmp-n{color:var(--ink3);font-size:11px;margin-left:6px}"
    ".cmp-table tr.cmp-best td{font-weight:800;color:var(--greend)}"
    ".cmp-table tr.cmp-best td:first-child::after{content:' \\2190 best';"
    "font-size:10.5px;color:var(--green);font-weight:700;margin-left:6px}"

    ".cmp-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;"
    "background:var(--surf);margin:18px 0}"
    ".cmp{border-collapse:collapse;width:100%;min-width:840px;font-size:14px}"
    ".cmp th{font-family:var(--mono);font-size:10.5px;letter-spacing:.8px;"
    "text-transform:uppercase;color:var(--ink3);text-align:left;padding:12px 14px;"
    "border-bottom:2px solid var(--line);vertical-align:bottom}"
    ".cmp td{padding:11px 14px;border-bottom:1px solid var(--line);"
    "color:var(--ink2);vertical-align:top;line-height:1.45}"
    ".cmp tr:last-child td{border-bottom:0}"
    ".cmp td.who{color:var(--ink);font-weight:700;white-space:nowrap}"
    ".cmp tr.us td{background:#f2f7f3}"
    ".cmp tr.us td.who{color:var(--greend)}"
    ".cmp a{color:var(--greend);text-decoration:underline;text-underline-offset:2px}"
    ".cmp-note{font-size:13px;color:var(--ink3);margin-top:-4px}"
    ".cmp-behind{background:var(--surf);border-left:4px solid var(--acc);"
    "border-radius:0 12px 12px 0;padding:16px 20px;margin:22px 0}"
    ".cmp-behind h2{margin-top:0}"
)


def _cell(value) -> str:
    text, url = value
    text = _html.escape(text)
    if not url:
        return text
    return f'<a href="{_html.escape(url)}">{text}</a>'


def _table() -> str:
    head = "".join(f"<th>{label}</th>" for _key, label in _COLS)
    body = ""
    for row in _ROWS:
        cls = ' class="us"' if row.get("us") else ""
        name = _html.escape(row["name"])
        who = (f'<a href="{_html.escape(row["url"])}">{name}</a>'
               if not row.get("us") else name)
        cells = "".join(f"<td>{_cell(row[key])}</td>" for key, _label in _COLS)
        body += f'<tr{cls}><td class="who">{who}</td>{cells}</tr>'
    return (f'<div class="cmp-wrap"><table class="cmp">'
            f'<tr><th>Site</th>{head}</tr>{body}</table></div>')


_BENCH_SOURCE_LABEL = {
    "evmax": "evmax",
    "ffiq": '<a href="https://fantasyfootballiq.app">Fantasy Football IQ</a>',
    "ep_next": "FPL ep_next (official)",
    "baseline_ppg": "baseline: season pts/appearance",
    "baseline_form4": "baseline: last-4 mean",
}
# The table's row order: models first, the reference, then the bar the models
# must clear to be worth anything.
_BENCH_ORDER = ("evmax", "ffiq", "ep_next", "baseline_ppg", "baseline_form4")


def _bench_data():
    """Graded benchmark rows + pending snapshots, from the banked assets."""
    import glob
    import json as _json
    import os as _os
    here = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    graded, pending = [], []
    for path in sorted(glob.glob(_os.path.join(
            here, "evmax", "assets", "accuracy", "gw*.json"))):
        with open(path, encoding="utf-8") as fh:
            acc = _json.load(fh)
        if acc.get("benchmark"):
            graded.append(acc)
    for path in sorted(glob.glob(_os.path.join(
            here, "evmax", "assets", "bench", "gw*.json"))):
        with open(path, encoding="utf-8") as fh:
            snap = _json.load(fh)
        if not any(a["gameweek"] == snap["gameweek"] for a in graded):
            pending.append(snap)
    return graded, pending


def benchmark_section() -> str:
    """The same-sample benchmark: graded tables per gameweek, pending
    snapshots named with their freeze time. Derived metrics only — nobody's
    projections appear here."""
    graded, pending = _bench_data()
    blocks = ['<h2 id="benchmark">The benchmark — same sample, same yardstick'
              '</h2>',
              "<p>Self-reported accuracy numbers are not comparable, so we "
              "grade every column ourselves: each source's projections are "
              "frozen in a public git commit <b>before the deadline</b> and "
              "scored after the gameweek on the same players with the same "
              "error definition. Mean absolute error, lower is better; "
              "<i>n</i> is each source's own coverage. A model earns its keep "
              "only by beating the naive baselines at the bottom.</p>"]
    for acc in graded:
        rows = []
        scores = acc["benchmark"]["scores"]
        best = min((v["mae_60plus"] for v in scores.values()
                    if v.get("mae_60plus") is not None), default=None)
        for key in _BENCH_ORDER:
            v = scores.get(key)
            if not v:
                continue
            mark = " class=\"cmp-best\"" if v.get("mae_60plus") == best else ""
            rows.append(
                f'<tr{mark}><td>{_BENCH_SOURCE_LABEL.get(key, key)}</td>'
                f'<td>{v.get("mae_60plus") if v.get("mae_60plus") is not None else "—"}'
                f'<span class="cmp-n">n={v.get("n_60plus")}</span></td>'
                f'<td>{v.get("rmse_60plus") if v.get("rmse_60plus") is not None else "—"}</td>'
                f'<td>{v.get("mae_all") if v.get("mae_all") is not None else "—"}'
                f'<span class="cmp-n">n={v.get("n_all")}</span></td></tr>')
        blocks.append(
            f'<h3>Gameweek {acc["gameweek"]}</h3>'
            f'<table class="cmp-table"><thead><tr><th>Source</th>'
            f'<th>MAE, 60+ min</th><th>RMSE, 60+ min</th>'
            f'<th>MAE, everyone</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')
    for snap in pending:
        taken = _html.escape((snap.get("taken_at") or "")[:16].replace("T", " "))
        blocks.append(
            f'<p class="cmp-note"><b>Gameweek {snap["gameweek"]}: frozen, '
            f'not yet graded.</b> Every column snapshotted {taken} UTC, '
            f'before the deadline, in a public commit. Grades land once the '
            f'gameweek finishes.</p>')
    if not graded:
        blocks.append(
            '<p class="cmp-note">Until the first frozen gameweek is graded, '
            'the only cross-source history is ours against FPL\'s own '
            'ep_next, in <a href="/fpl/accuracy/">the ledger</a>.</p>')
    blocks.append(
        '<p class="cmp-note">Fantasy Football IQ projections are used under '
        'their published licence (free to use with attribution — '
        '<a href="https://fantasyfootballiq.app">fantasyfootballiq.app</a>). '
        'Only derived metrics appear here; nobody\'s projections are '
        'republished. Sources with restrictive terms are invited in writing '
        'instead — the invitation and the answer both get published.</p>')
    return "".join(blocks)


def compare_page() -> str:
    """`/fpl/compare/` — the checkable differences, including ours."""
    title = "How evmax compares"
    description = ("A factual comparison of the public FPL projection models: "
                   "whose method is published, whose data is reusable, who "
                   "publishes a graded record, who is free and who machines "
                   "can read. No accuracy claims across sites.")
    body = f"""
<p class="pagelabel">Comparison</p>
<h1>How we compare</h1>
<p class="stand">{_html.escape(description)}</p>

{benchmark_section()}

<h2>Why the table above never quotes anyone's self-reported number</h2>
<p>Every model grades itself over a different sample: different gameweeks, a
different set of players, sometimes a different definition of error. Side by
side, those numbers would look authoritative and prove nothing. The benchmark
above exists precisely so the comparison can be made honestly: one sample,
one yardstick, frozen in public before kickoff.</p>

<h2>What can actually be checked</h2>
<p class="cmp-note">Every cell links to its source. Checked {CHECKED}. If a row
is wrong or out of date, tell us and we will correct it here.</p>
{_table()}

<div class="cmp-behind">
<h2>Where we are behind</h2>
<p><b>Onside Arena has far more graded history than we do.</b> They have been
publishing a rolling ledger with tens of thousands of graded predictions; ours
starts at gameweek 1 of this season and currently holds a single gameweek. A
record of one week proves nothing yet, and we would rather say so than let the
table imply otherwise.</p>
<p><b>Their infrastructure is ahead in places</b> — a calibration page and a
resolved entity on Wikidata, both of which we lack. <b>Solio's model comes from
the person who built the solver toolkit the community runs on.</b> We are the
newer, smaller project.</p>
<p>What we do claim is narrower and checkable: nobody else publishes the method,
the licensed data, the graded record and free access at once.</p>
</div>

<h2>How to check any of this</h2>
<p>Our method is written out on <a href="/about/">the About page</a> and the
numbers behind every claim are downloadable from <a href="/data/">the data
page</a> under CC BY 4.0. Projections are frozen before each deadline and
graded afterwards in <a href="/fpl/accuracy/">the ledger</a>, with the raw
grading files linked per gameweek. Machines can read all of it through the
JSON API and the MCP server.</p>
"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | {render.TITLE_BRAND}</title>
<meta name="description" content="{_html.escape(description)}">
{render._og_meta(title, description, COMPARE_PATH, og_type="website")}
{render.GSC_META_TAG}
{render._HEAD_COMMON}
{render._FONTS}
<style>{render._STYLE}{_CSS}{render._NAV_SCROLL_CSS}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{render._nav_html(active="track-record")}
</div></header>
<div class="wrap">
{body}
</div>
{render._footer_html()}
</body></html>"""
