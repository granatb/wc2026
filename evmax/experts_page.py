"""`/fpl/gw{N}/experts/` — what the public FPL sources recommended this week,
every cell linked to its source, with our own row beside them.

Owner decision 2026-09-12. Derived-only: the page says WHO each source picked
(captain, transfers, chip) and links to them. It carries none of their
projections and no paywalled content. The data is research/experts/gw{N}.json
(see core.experts); no file, no page.
"""
from __future__ import annotations

import html as _html

from core import experts as _experts

SLUG = "experts"
TITLE = "What the experts say"

_CSS = (
    ".xp-table{width:100%;border-collapse:collapse;background:var(--surf);"
    "border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:13.5px}"
    ".xp-table th{font-size:10.5px;font-weight:800;letter-spacing:1.4px;text-transform:uppercase;"
    "color:var(--ink3);text-align:left;padding:9px 12px 6px;border-bottom:1px solid var(--line)}"
    ".xp-table td{padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}"
    ".xp-table tr:last-child td{border-bottom:0}"
    ".xp-table a{color:var(--greend);font-weight:600}"
    ".xp-ours td{background:#eaf5ee;font-weight:600}"
    ".xp-when{display:block;font-size:11.5px;color:var(--ink3);font-weight:400;margin-top:2px}"
    ".xp-note{font-size:12.5px;color:var(--ink2);margin-top:3px}"
    ".xp-wrap{overflow-x:auto;margin:14px 0 22px}"
    ".xp-sum{margin:6px 0 0;padding-left:18px;font-size:14.5px}"
    ".xp-sum li{margin:4px 0}"
    ".xp-foot{font-size:12.5px;color:var(--ink3);margin-top:18px}"
)


def _when(iso: str) -> str:
    return (iso or "")[:10]


def _names(xs) -> str:
    return ", ".join(_html.escape(x) for x in (xs or [])) or "—"


def _row(s: dict) -> str:
    links = [f'<a href="{_html.escape(s["url"])}" rel="noopener">{_html.escape(s["name"])}</a>']
    for i, u in enumerate(s.get("extra_urls") or [], start=1):
        links.append(f'<a href="{_html.escape(u)}" rel="noopener" style="font-weight:400">(+{i})</a>')
    note = (f'<div class="xp-note">{_html.escape(s["note"])}</div>' if s.get("note") else "")
    return (f'<tr><td>{" ".join(links)}<span class="xp-when">published {_when(s["published"])}</span>{note}</td>'
            f'<td>{_html.escape(s.get("captain") or "—")}'
            + (f'<span class="xp-when">vice {_html.escape(s["vice"])}</span>' if s.get("vice") else "")
            + f'</td><td>{_names(s.get("transfers_in"))}</td>'
            f'<td>{_names(s.get("transfers_out"))}</td>'
            f'<td>{_html.escape(s.get("chip") or "—")}</td></tr>')


def _our_row(our: dict, model: dict, gameweek: int, section) -> str:
    chip = our.get("chip") or {}
    chip_text = {"3xc": "Triple Captain", "bboost": "Bench Boost", "freehit": "Free Hit",
                 "wildcard": "Wildcard"}.get(chip.get("chip"), "—") if chip else "—"
    href = section.article_path(gameweek, "our-squad")
    return (f'<tr class="xp-ours"><td><a href="{href}">evmax — the model squad</a>'
            f'<span class="xp-when">frozen before the deadline · projected '
            f'{our.get("projected_total", 0):.1f}</span></td>'
            f'<td>{_html.escape(our.get("captain") or "—")}'
            + (f'<span class="xp-when">vice {_html.escape(our["vice"])}</span>' if our.get("vice") else "")
            + f'</td><td>{_names(model.get("transfers_in"))}</td>'
            f'<td>{_names(model.get("transfers_out"))}</td><td>{chip_text}</td></tr>')


def summary_items(data: dict, our: dict) -> list:
    """Plain sentences: where the sources agree with us and where they do not."""
    t = _experts.tallies(data)
    c = _experts.compare_with_model(data, our)
    items = []
    if c["top_captain"]:
        votes = dict(t["captains"])[c["top_captain"]]
        if c["captain_agreement"]:
            items.append(f"Captain: {c['top_captain']} leads the sources with {votes} of "
                         f"{t['n_sources']} naming him, and he wears our armband too.")
        else:
            items.append(f"Captain: the sources lean {c['top_captain']} ({votes} of "
                         f"{t['n_sources']}); ours is {our.get('captain')}.")
    if t["transfers_in"]:
        top_in = ", ".join(f"{n} ({k})" for n, k in t["transfers_in"][:4])
        items.append(f"Most recommended buys: {top_in}.")
    if c["they_buy_we_lack"]:
        items.append("Recommended by them, not in our squad: "
                     + ", ".join(c["they_buy_we_lack"][:5]) + ".")
    hold = (data.get("model") or {}).get("hold_against_the_crowd") or []
    if c["they_sell_we_hold"] or hold:
        names = hold or c["they_sell_we_hold"]
        items.append("Being sold elsewhere, held by us: " + ", ".join(names) + ".")
    if t["chips"]:
        items.append("Chips: " + "; ".join(f"{n} — {ch}" for n, ch in t["chips"]) + ".")
    return items


def page_html(data: dict, gameweek: int, our: dict, date_str: str = None,
              section=None) -> str:
    from evmax import render
    section = section or render.FPL
    model = data.get("model") or {}
    rows = "".join(_row(s) for s in data["sources"])
    items = "".join(f"<li>{_html.escape(i)}</li>" for i in summary_items(data, our))
    title = f"{TITLE}: FPL Gameweek {gameweek}"
    description = (f"Captain, transfers and chip calls from {len(data['sources'])} public "
                   f"FPL sources for Gameweek {gameweek}, each linked, next to the "
                   f"evmax model's own squad.")
    path = section.article_path(gameweek, SLUG)
    byline = f" · {_html.escape(date_str)}" if date_str else ""
    body = f"""<article class="art">
<div class="kick">Expert scan · Gameweek {gameweek}</div>
<h1>{_html.escape(TITLE)}</h1>
<p class="stand">{_html.escape(description)}</p>
<div class="meta"><span class="av">e</span><span>Read by evmax{byline} · sources checked {_html.escape(_when(data["checked_at"]))}</span></div>
<div class="xp-wrap"><table class="xp-table"><thead><tr>
<th>Source</th><th>Captain</th><th>Transfers in</th><th>Transfers out</th><th>Chip</th>
</tr></thead><tbody>{rows}{_our_row(our, model, gameweek, section)}</tbody></table></div>
<h2>Where they agree, where they split</h2>
<ul class="xp-sum">{items}</ul>
<p class="xp-foot">Each row is that source's own published call, linked. We record who they
picked and nothing else: no projections, no paywalled text. Fantasy Football Fix's row is the
crowd's transfer counts, not a recommendation. Our row is the squad frozen before the deadline
and graded after it in <a href="/fpl/accuracy/">the ledger</a>.</p>
</article>"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(title)} | {render.TITLE_BRAND}</title>
<meta name="description" content="{_html.escape(description)}">
{render._og_meta(title, description, path, og_type="article")}
{render.GSC_META_TAG}
{render._HEAD_COMMON}
{render._FONTS}
<style>{render._STYLE}{_CSS}{render._NAV_SCROLL_CSS}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{render._nav_html()}
</div></header>
<div class="wrap">
{body}
</div>
{render._footer_html()}
</body></html>"""


def feed_entry(data: dict, our: dict) -> dict:
    """The landing's feed card for the scan."""
    t = _experts.tallies(data)
    c = _experts.compare_with_model(data, our)
    cap = c["top_captain"] or "no consensus"
    teaser = (f"Captain, transfers and chips from {t['n_sources']} public sources, "
              f"each linked, beside our own squad. "
              + ("They and the model agree on the armband." if c["captain_agreement"]
                 else f"The sources lean {cap}; the model captains {our.get('captain')}."))
    return {"slug": SLUG, "headline": f"{TITLE} for gameweek {data['gameweek']}",
            "teaser": teaser, "stat_value": str(t["n_sources"]), "stat_label": "Sources read"}


def public_json(data: dict, our: dict) -> dict:
    """The JSON twin: the scan plus the derived tallies and comparison."""
    t = _experts.tallies(data)
    return {"gameweek": data["gameweek"], "checked_at": data["checked_at"],
            "sources": data["sources"], "model": data.get("model") or {},
            "our_captain": our.get("captain"), "tallies": {
                "captains": t["captains"], "transfers_in": t["transfers_in"],
                "transfers_out": t["transfers_out"]},
            "comparison": _experts.compare_with_model(data, our),
            "policy": "Who each source picked, linked. No projections of theirs are republished."}
