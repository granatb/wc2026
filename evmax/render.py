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


_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
          '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
          '<link href="https://fonts.googleapis.com/css2?'
          'family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&'
          'family=Archivo:wght@400;500;600;700&display=swap" rel="stylesheet">')

_STYLE = (":root{--bg:#0b1020;--bg2:#121933;--card:#161e3d;--line:#26315c;--ink:#eef2ff;"
          "--mut:#8893bf;--lime:#d4ff3d;--blue:#3d7bff;--pink:#ff4d8d;"
          "--disp:'Bricolage Grotesque',sans-serif;--sans:'Archivo',sans-serif}"
          "*{box-sizing:border-box;margin:0;padding:0}"
          "body{background:radial-gradient(120% 80% at 50% -10%,#16204a 0%,var(--bg) 55%);"
          "color:var(--ink);font-family:var(--sans);line-height:1.5;min-height:100vh;"
          "-webkit-font-smoothing:antialiased}"
          ".wrap{max-width:940px;margin:0 auto;padding:0 22px}"
          "header{display:flex;align-items:center;gap:16px;padding:20px 0;flex-wrap:wrap}"
          ".logo{font-family:var(--disp);font-weight:800;font-size:24px;letter-spacing:-.5px;"
          "color:var(--ink);text-decoration:none}.logo b{color:var(--lime)}"
          "nav{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}"
          "nav a{font-size:12.5px;font-weight:600;color:var(--mut);text-decoration:none;"
          "padding:7px 13px;border-radius:999px;border:1px solid transparent}"
          "nav a.on{color:var(--bg);background:var(--lime)}"
          "nav a:hover:not(.on){color:var(--ink);border-color:var(--line)}"
          ".badge{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:700;"
          "letter-spacing:1.5px;text-transform:uppercase;color:var(--lime);"
          "background:rgba(212,255,61,.08);border:1px solid rgba(212,255,61,.25);"
          "padding:7px 14px;border-radius:999px}"
          ".badge .dot{width:7px;height:7px;border-radius:50%;background:var(--lime)}"
          ".hero{padding:24px 0 28px}"
          "h1{font-family:var(--disp);font-weight:800;font-size:clamp(34px,6vw,68px);"
          "line-height:.94;letter-spacing:-1.5px;margin:16px 0 0;color:var(--ink)}"
          ".sub{font-size:17px;color:var(--mut);max-width:60ch;margin-top:16px}"
          ".sub b{color:var(--ink);font-weight:600}"
          ".hero-card{background:linear-gradient(135deg,var(--lime),#a6e000);color:#0b1020;"
          "border-radius:22px;padding:24px 26px;margin-top:24px;display:flex;align-items:center;"
          "gap:24px;flex-wrap:wrap}"
          ".hero-card .big{font-family:var(--disp);font-weight:800;font-size:62px;line-height:.85;"
          "letter-spacing:-2px}"
          ".hero-card .lbl{font-weight:700;text-transform:uppercase;letter-spacing:1.5px;"
          "font-size:11px;opacity:.7}"
          ".hero-card .who{font-family:var(--disp);font-weight:700;font-size:28px;line-height:1}"
          ".hero-card .det{font-size:13px;font-weight:600;opacity:.8;margin-top:6px}"
          ".seclabel{font-family:var(--disp);font-weight:700;font-size:14px;letter-spacing:2px;"
          "text-transform:uppercase;color:var(--mut);margin:36px 0 14px}"
          ".grid{display:flex;flex-direction:column;gap:10px}"
          ".row{display:grid;grid-template-columns:42px 1fr auto;align-items:center;gap:16px;"
          "background:var(--card);border:1px solid var(--line);border-radius:16px;"
          "padding:15px 20px;transition:transform .12s,border-color .12s}"
          ".row:hover{transform:translateX(4px);border-color:var(--blue)}"
          ".row .rk{font-family:var(--disp);font-weight:800;font-size:28px;color:var(--blue)}"
          ".row.lead .rk{color:var(--lime)}"
          ".nm{font-family:var(--disp);font-weight:700;font-size:20px;line-height:1.05;color:var(--ink)}"
          ".meta{display:flex;align-items:center;gap:8px;margin-top:5px;flex-wrap:wrap}"
          ".tm{font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:var(--mut)}"
          ".chip{font-size:10.5px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;"
          "color:var(--mut);background:transparent;border:1px solid var(--line);"
          "padding:2px 8px;border-radius:999px}"
          ".chip.diff{color:var(--pink);background:rgba(255,77,141,.12);border-color:rgba(255,77,141,.3)}"
          ".ev{text-align:right}"
          ".ev .v{font-family:var(--disp);font-weight:800;font-size:28px;color:var(--lime);"
          "line-height:1;font-variant-numeric:tabular-nums}"
          ".ev .u{font-size:10.5px;font-weight:700;letter-spacing:1px;text-transform:uppercase;"
          "color:var(--mut);margin-top:4px}"
          ".barline{height:6px;border-radius:999px;background:#0e1530;overflow:hidden;"
          "margin-top:12px;grid-column:1/-1}"
          ".barline i{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--lime));"
          "border-radius:999px}"
          ".hubcard{display:block;background:var(--card);border:1px solid var(--line);"
          "border-radius:16px;padding:18px 22px;text-decoration:none;transition:border-color .12s}"
          ".hubcard:hover{border-color:var(--lime)}"
          ".hubcard .t{font-family:var(--disp);font-weight:700;font-size:21px;color:var(--ink)}"
          ".hubcard .h{font-size:14px;color:var(--mut);margin-top:6px}"
          ".method{font-size:13px;color:var(--mut);line-height:1.75;border-top:1px solid var(--line);"
          "margin-top:34px;padding:24px 0 10px}.method b{color:var(--lime);font-weight:700}"
          ".api{display:inline-flex;align-items:center;gap:8px;font-family:var(--sans);"
          "font-weight:700;font-size:13px;color:var(--bg);background:var(--lime);"
          "border-radius:999px;padding:11px 18px;margin:8px 0 56px;text-decoration:none}"
          ".api:hover{background:#fff}")


def _nav_html(nav, round_no, active=None):
    return "<nav>" + "".join(
        f'<a class="on" href="/round/{round_no}/{slug}/">{_html.escape(title)}</a>'
        if slug == active else
        f'<a href="/round/{round_no}/{slug}/">{_html.escape(title)}</a>'
        for slug, title in nav) + "</nav>"


def _row_html(r, columns, lead=False):
    own = r.get("ownership_pct")
    chips = [f'<span class="tm">{_html.escape(r.get("team") or "")}</span>']
    if r.get("position"):
        chips.append(f'<span class="chip">{_html.escape(r["position"])}</span>')
    if own is not None:
        if own < 10.0:
            chips.append(f'<span class="chip diff">Differential · {own:.1f}%</span>')
        else:
            chips.append(f'<span class="chip">{own:.1f}% owned</span>')
    secondary = " · ".join(f"{_fmt(c, r)} {_COL_LABEL.get(c, c).lower()}"
                           for c in columns[1:] if r.get(c) is not None)
    det = f'<div class="meta"><span class="tm">{_html.escape(secondary)}</span></div>' if secondary else ""
    return (f'<div class="row{" lead" if lead else ""}">'
            f'<div class="rk">{r.get("rank", "")}</div>'
            f'<div><div class="nm">{_html.escape(r["name"])}</div>'
            f'<div class="meta">{"".join(chips)}</div>{det}</div>'
            f'<div class="ev"><div class="v">{_fmt(columns[0], r)}</div>'
            f'<div class="u">{_html.escape(_COL_LABEL.get(columns[0], columns[0]))}</div></div>'
            f'<div class="barline"><i style="width:{r.get("_barpct", 0):.1f}%"></i></div></div>')


def _rows_html(entries, columns):
    vmax = max((e.get(columns[0]) or 0.0) for e in entries) or 1.0
    out = []
    for i, e in enumerate(entries):
        e = dict(e)
        e["_barpct"] = max(2.0, 100.0 * (e.get(columns[0]) or 0.0) / vmax)
        out.append(_row_html(e, columns, lead=(i == 0)))
    return '<div class="grid">' + "".join(out) + "</div>"


_BADGE = ('<span class="badge"><span class="dot"></span>'
          'World Cup Fantasy · Round {r} · 50,000 sims</span>')


def article_page(round_no, article, title, entries, columns, nav, json_url):
    summary = summary_sentence(article, entries)
    top = entries[0] if entries else {}
    hero = ""
    if top:
        det = " · ".join([top.get("team", "")] +
                         [f"{_fmt(c, top)} {_COL_LABEL.get(c, c).lower()}"
                          for c in columns[1:] if top.get(c) is not None])
        hero = (f'<div class="hero-card"><div><div class="lbl">'
                f'{_html.escape(_COL_LABEL.get(columns[0], columns[0]))}</div>'
                f'<div class="big">{_fmt(columns[0], top)}</div></div>'
                f'<div><div class="who">{_html.escape(top["name"])}</div>'
                f'<div class="det">{_html.escape(det)}</div></div></div>')
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
<meta name="description" content="{_html.escape(summary)}">
<link rel="alternate" type="application/json" href="{json_url}">
{_FONTS}
<style>{_STYLE}</style>
<script type="application/ld+json">{jsonld}</script>
</head><body><div class="wrap">
<header><a class="logo" href="/">ev<b>max</b></a>{_nav_html(nav, round_no, active=article)}</header>
<section class="hero">{_BADGE.format(r=round_no)}
<h1>{_html.escape(title)}</h1>
<p class="sub">{_html.escape(summary)}</p>
{hero}</section>
<div class="seclabel">{_html.escape(_COL_LABEL.get(columns[0], columns[0]))} — ranked</div>
{_rows_html(entries, columns)}
<p class="method"><b>Method.</b> {METHODOLOGY} Data: free market odds + our simulation. Backtested results coming.</p>
<a class="api" href="{json_url}">Get the raw data →</a>
</div></body></html>"""


def hub_page(round_no, nav, highlights):
    cards = []
    for slug, title in nav:
        hl = _html.escape(highlights.get(slug, ""))
        cards.append(f'<a class="hubcard" href="/round/{round_no}/{slug}/">'
                     f'<div class="t">{_html.escape(title)}</div>'
                     f'<div class="h">{hl}</div></a>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>World Cup Fantasy Round {round_no} — picks, captains, differentials | evmax</title>
<meta name="description" content="Simulation-based World Cup Fantasy picks for Round {round_no}: best XI, captains, differentials, value and blowout-fixture transfers from 50,000 Monte-Carlo runs.">
{_FONTS}
<style>{_STYLE}</style>
</head><body><div class="wrap">
<header><a class="logo" href="/">ev<b>max</b></a>{_nav_html(nav, round_no)}</header>
<section class="hero">{_BADGE.format(r=round_no)}
<h1>Who to pick<br>in Round {round_no}.</h1>
<p class="sub">Simulation-based World Cup Fantasy picks from <b>50,000 Monte-Carlo runs</b> on market odds. Pick a list:</p></section>
<div class="grid">{"".join(cards)}</div>
<p class="method"><b>Method.</b> {METHODOLOGY}</p>
</div></body></html>"""


_AI_BOTS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-Web",
            "PerplexityBot", "Google-Extended", "CCBot", "Applebot-Extended"]


def llms_txt(round_no, nav):
    lines = [
        "# evmax — simulation-based World Cup Fantasy picks",
        "",
        "> Free, transparent fantasy picks from 50,000 Monte-Carlo simulations on "
        "de-vigged market odds, scored on the official FIFA World Cup Fantasy table. "
        "Numbers are machine-readable JSON; attribution to evmax is requested.",
        "",
        f"## Round {round_no} articles",
    ]
    for slug, title in nav:
        lines.append(f"- [{title}]({SITE_URL}/round/{round_no}/{slug}/) — "
                     f"data: {SITE_URL}/api/round/{round_no}/{slug}.json")
    lines += ["", "## API", f"- Article index: {SITE_URL}/api/latest.json"]
    return "\n".join(lines) + "\n"


def robots_txt():
    blocks = [f"User-agent: {b}\nAllow: /" for b in _AI_BOTS]
    blocks.append("User-agent: *\nAllow: /")
    return "\n\n".join(blocks) + f"\n\nSitemap: {SITE_URL}/sitemap.xml\n"


def sitemap_xml(round_no, nav):
    urls = [f"{SITE_URL}/", f"{SITE_URL}/round/{round_no}/"]
    urls += [f"{SITE_URL}/round/{round_no}/{slug}/" for slug, _ in nav]
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f'{items}</urlset>')
