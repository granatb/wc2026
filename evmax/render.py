"""Pure emitters for the evmax static site (HTML/SVG/JSON/text). No I/O."""

import html as _html
import json as _json

SITE_URL = "https://evmax.pages.dev"
METHODOLOGY = ("Market odds (de-vigged) → Dixon-Coles scorelines → 50k Monte-Carlo "
               "simulations, scored on the official FIFA World Cup Fantasy points table.")


def article_json(competition, fantasy_round, article, title, generated_at, sims, entries):
    return {
        "competition": competition,
        "round": fantasy_round,
        "article": article,
        "title": title,
        "generated_at": generated_at,
        "sims": sims,
        "methodology": METHODOLOGY,
        "entries": entries,
        "source": SITE_URL,
        "license": "Attribution requested: evmax",
    }


def summary_sentence(article, entries):
    if not entries:
        return "No qualifying players this round."
    top = entries[0]
    name, team = top["name"], top.get("team", "")
    if article == "captains":
        return (f"Captain {name} ({team}): {top['captain_ev']:.1f} expected points — "
                f"the highest captain EV in this round.")
    if article == "differentials":
        return (f"{name} ({team}) is the standout differential: {top['x_points']:.1f} xPts "
                f"at just {top['ownership_pct']:.1f}% ownership.")
    if article == "best-value-xi":
        return (f"{name} ({team}) leads on value: {top['x_points']:.1f} xPts for "
                f"{top['price']:.1f}m.")
    if article == "high-ceiling-xi":
        return (f"{name} ({team}) has the highest ceiling: up to {top['ceiling']:.1f} points.")
    if article == "blowout-transfers":
        return (f"{name} ({team}) is the top attacker in this round's most lopsided fixtures "
                f"at {top['x_points']:.1f} xPts.")
    return f"{name} ({team}) tops the list at {top['x_points']:.1f} expected points."


def svg_bar_chart(pairs, unit, width=520, row_h=34):
    """Horizontal bar chart as a standalone inline SVG (no JS). pairs = [(label, value)]."""
    pairs = list(pairs)
    height = max(row_h * len(pairs) + 10, 40)
    if not pairs:
        return f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg"></svg>'
    vmax = max(v for _, v in pairs) or 1.0
    label_w, pad = 150, 8
    bar_max = width - label_w - 60
    rows = []
    for i, (label, value) in enumerate(pairs):
        y = i * row_h + pad
        bw = max(2, bar_max * (value / vmax))
        lbl = _html.escape(str(label))
        rows.append(
            f'<text x="0" y="{y + 16}" font-size="13" fill="#cbd5e1">{lbl}</text>'
            f'<rect x="{label_w}" y="{y + 4}" width="{bw:.1f}" height="18" rx="3" '
            f'fill="#22d3ee"/>'
            f'<text x="{label_w + bw + 6:.1f}" y="{y + 17}" font-size="12" '
            f'fill="#e2e8f0">{value:.1f}</text>')
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="{_html.escape(unit)} chart">' + "".join(rows) + "</svg>")


_COL_LABEL = {"x_points": "xPts", "captain_ev": "Captain EV", "ceiling": "Ceiling",
              "value": "Value", "price": "Price", "ownership_pct": "Owned %"}


def _fmt(col, row):
    v = row.get(col)
    if v is None:
        return "—"
    if col == "ownership_pct":
        return f"{v:.1f}%"
    if col == "price":
        return f"{v:.1f}"
    return f"{v:.2f}" if isinstance(v, float) else str(v)


def _table(entries, columns):
    head = "".join(f"<th>{_COL_LABEL.get(c, c)}</th>" for c in columns)
    body = []
    for r in entries:
        cells = (f'<td class="name">{_html.escape(r["name"])}</td>'
                 f'<td>{_html.escape(r.get("team") or "")}</td>'
                 f'<td>{_html.escape(r.get("position") or "")}</td>')
        cells += "".join(f"<td>{_fmt(c, r)}</td>" for c in columns)
        body.append(f"<tr><td>{r.get('rank','')}</td>{cells}</tr>")
    return (f'<table><thead><tr><th>#</th><th>Player</th><th>Team</th><th>Pos</th>'
            f'{head}</tr></thead><tbody>{"".join(body)}</tbody></table>')


_STYLE = ("body{margin:0;background:#0b1120;color:#e2e8f0;font:16px/1.5 system-ui,sans-serif}"
          "main{max-width:880px;margin:0 auto;padding:24px}"
          "h1{font-size:1.6rem;line-height:1.2}a{color:#22d3ee}"
          ".lede{font-size:1.15rem;color:#f8fafc;margin:12px 0 20px}"
          "nav a{display:inline-block;margin:0 12px 8px 0}"
          "table{width:100%;border-collapse:collapse;margin:16px 0}"
          "th,td{padding:6px 8px;text-align:left;border-bottom:1px solid #1e293b;font-size:14px}"
          ".name{font-weight:600}.method{color:#94a3b8;font-size:13px;margin-top:24px}")


def _nav_html(nav, round_no):
    return "<nav>" + "".join(
        f'<a href="/round/{round_no}/{slug}/">{_html.escape(title)}</a>'
        for slug, title in nav) + "</nav>"


def article_page(round_no, article, title, entries, columns, nav, json_url):
    chart_pairs = [(r["name"], r.get(columns[0]) or 0.0) for r in entries[:6]]
    jsonld = _json.dumps({
        "@context": "https://schema.org", "@type": "Dataset", "name": title,
        "description": METHODOLOGY, "url": f"{SITE_URL}{json_url}",
        "creator": {"@type": "Organization", "name": "evmax"},
        "variableMeasured": [_COL_LABEL.get(c, c) for c in columns],
    })
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(title)} | evmax</title>
<meta name="description" content="{_html.escape(summary_sentence(article, entries))}">
<link rel="alternate" type="application/json" href="{json_url}">
<style>{_STYLE}</style>
<script type="application/ld+json">{jsonld}</script>
</head><body><main>
<h1>{_html.escape(title)}</h1>
<p class="lede">{_html.escape(summary_sentence(article, entries))}</p>
{svg_bar_chart(chart_pairs, _COL_LABEL.get(columns[0], columns[0]))}
{_table(entries, columns)}
<p class="method"><strong>Method:</strong> {METHODOLOGY} Data: free market odds + our simulation. Backtested results coming.</p>
<p class="method">Machine-readable: <a href="{json_url}">{json_url}</a></p>
<h2 style="font-size:1.1rem">More Round {round_no} picks</h2>
{_nav_html(nav, round_no)}
</main></body></html>"""


def hub_page(round_no, nav, highlights):
    cards = []
    for slug, title in nav:
        hl = _html.escape(highlights.get(slug, ""))
        cards.append(f'<p><a href="/round/{round_no}/{slug}/"><strong>{_html.escape(title)}</strong></a><br>'
                     f'<span class="method">{hl}</span></p>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>World Cup Fantasy Round {round_no} — picks, captains, differentials | evmax</title>
<meta name="description" content="Simulation-based World Cup Fantasy picks for Round {round_no}: best XI, captains, differentials, value and blowout-fixture transfers from 50k Monte-Carlo runs.">
<style>{_STYLE}</style>
</head><body><main>
<h1>World Cup Fantasy — Round {round_no}</h1>
<p class="lede">Simulation-based picks from 50,000 Monte-Carlo runs on market odds. Pick a list:</p>
{"".join(cards)}
<p class="method"><strong>Method:</strong> {METHODOLOGY}</p>
</main></body></html>"""
