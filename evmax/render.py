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
          'family=Hanken+Grotesk:wght@400;500;600;700;800&'
          'family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap" rel="stylesheet">')

_STYLE = (
    ":root{"
    "--bg:#fbfaf7;--surf:#fff;--ink:#15140f;--ink2:#5d564a;--ink3:#8a8275;"
    "--line:#e7e2d6;--green:#0f7a45;--greend:#0a4f2d;--acc:#e8482b;--chipbg:#f1efe7;"
    "--sans:'Hanken Grotesk',system-ui,sans-serif;--serif:'Newsreader',Georgia,serif;"
    "}"
    "*{box-sizing:border-box;margin:0;padding:0}"
    "body{background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.5;"
    "-webkit-font-smoothing:antialiased}"
    "a{color:inherit;text-decoration:none}"
    ".wrap{max-width:1000px;margin:0 auto;padding:0 28px}"
    "header{display:flex;align-items:center;gap:20px;height:62px;border-bottom:1px solid var(--line);"
    "position:sticky;top:0;background:rgba(251,250,247,.92);backdrop-filter:blur(8px);z-index:10}"
    ".logo{font-weight:800;font-size:22px;letter-spacing:-.5px}.logo b{color:var(--green)}"
    "nav{margin-left:auto;display:flex;gap:4px;align-items:center}"
    "nav a{font-size:14px;font-weight:600;color:var(--ink2);padding:8px 14px;border-radius:8px}"
    "nav a.on{color:var(--green);background:#eaf5ee}"
    "nav a:hover:not(.on){color:var(--ink)}"
    "nav a.soon{color:var(--ink3)}"
    "nav a.soon::after{content:'soon';font-size:9px;font-weight:700;text-transform:uppercase;"
    "letter-spacing:.5px;background:var(--chipbg);color:var(--ink3);padding:2px 5px;"
    "border-radius:5px;margin-left:6px;vertical-align:1px}"
    ".pagelabel{font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;"
    "color:var(--ink3);margin:34px 0 18px;display:flex;align-items:center;gap:12px}"
    ".pagelabel::after{content:'';flex:1;border-top:1px solid var(--line)}"
    ".feat{display:grid;grid-template-columns:1.1fr .9fr;gap:34px;align-items:center;padding:6px 0 8px}"
    ".kick{font-size:12.5px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;"
    "color:var(--acc);margin-bottom:12px}"
    ".feat h1{font-size:clamp(30px,4.2vw,46px);font-weight:800;line-height:1.04;letter-spacing:-1px}"
    ".feat .stand{font-family:var(--serif);font-size:19px;line-height:1.45;color:var(--ink2);margin-top:14px}"
    ".byline{display:flex;align-items:center;gap:10px;margin-top:18px;font-size:13px;color:var(--ink3)}"
    ".byline .av{width:26px;height:26px;border-radius:50%;background:var(--green);color:#fff;"
    "font-weight:800;font-size:12px;display:flex;align-items:center;justify-content:center}"
    ".feat .viz{background:var(--surf);border:1px solid var(--line);border-radius:16px;padding:16px}"
    ".vcap{font-size:12px;color:var(--ink3);text-align:center;margin-top:8px}.vcap b{color:var(--green)}"
    ".feed{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;margin-top:8px}"
    ".card{background:var(--surf);border:1px solid var(--line);border-radius:14px;padding:20px 22px;"
    "transition:border-color .12s,transform .12s;display:flex;flex-direction:column;gap:8px}"
    ".card:hover{border-color:var(--green);transform:translateY(-2px)}"
    ".card .ck{font-size:11px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:var(--green)}"
    ".card h3{font-size:21px;font-weight:700;line-height:1.1;letter-spacing:-.3px}"
    ".card p{font-family:var(--serif);font-size:15.5px;color:var(--ink2);line-height:1.45}"
    ".card .stat{margin-top:auto;display:flex;align-items:baseline;gap:8px;padding-top:10px;"
    "border-top:1px solid var(--line)}"
    ".card .stat b{font-size:22px;font-weight:800;color:var(--ink)}"
    ".card .stat span{font-size:12px;color:var(--ink3);text-transform:uppercase;letter-spacing:.5px}"
    ".divider{margin:60px 0;border:0;border-top:2px dashed var(--line)}"
    ".art{max-width:720px;margin:0 auto}"
    ".art .kick{margin-bottom:14px}"
    ".art h1{font-size:clamp(30px,5vw,44px);font-weight:800;line-height:1.05;letter-spacing:-1px}"
    ".art .stand{font-family:var(--serif);font-size:20px;color:var(--ink2);line-height:1.45;margin-top:14px}"
    ".art .meta{display:flex;align-items:center;gap:12px;margin:18px 0 26px;padding-bottom:20px;"
    "border-bottom:1px solid var(--line);font-size:13px;color:var(--ink3)}"
    ".art .meta .av{width:28px;height:28px;border-radius:50%;background:var(--green);color:#fff;"
    "font-weight:800;font-size:12px;display:flex;align-items:center;justify-content:center}"
    ".artviz{background:var(--surf);border:1px solid var(--line);border-radius:16px;padding:18px;"
    "margin:6px 0 26px;display:grid;grid-template-columns:auto 1fr;gap:22px;align-items:center}"
    ".prose p{font-family:var(--serif);font-size:18px;line-height:1.66;color:#23201a;margin-bottom:18px}"
    ".prose p b{color:var(--ink)}"
    ".prose h2{font-size:15px;font-weight:700;letter-spacing:1px;text-transform:uppercase;"
    "color:var(--green);margin:30px 0 10px}"
    ".pull{font-family:var(--serif);font-style:italic;font-size:23px;line-height:1.4;"
    "color:var(--greend);border-left:3px solid var(--green);padding:4px 0 4px 20px;margin:26px 0}"
    "table.rank{width:100%;border-collapse:collapse;margin:8px 0 6px;font-family:var(--sans)}"
    "table.rank th{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;"
    "color:var(--ink3);text-align:right;padding:10px 10px;border-bottom:2px solid var(--ink)}"
    "table.rank th:first-child,table.rank td:first-child,table.rank th.l{text-align:left}"
    "table.rank td{padding:12px 10px;border-bottom:1px solid var(--line);text-align:right;"
    "font-size:15px;font-variant-numeric:tabular-nums}"
    "table.rank .nm{font-weight:700}table.rank .tm{color:var(--ink3);font-size:12px}"
    "table.rank .big{font-weight:800;color:var(--green)}"
    ".tag{display:inline-block;font-size:10.5px;font-weight:700;text-transform:uppercase;"
    "letter-spacing:.5px;color:var(--acc);background:#fdeee9;border-radius:6px;padding:2px 7px;margin-left:6px}"
    ".method{font-size:13.5px;color:var(--ink3);line-height:1.7;border-top:1px solid var(--line);"
    "margin-top:34px;padding-top:18px}"
    ".method b{color:var(--green)}"
    ".pitch-mini{width:200px}"
    "@media(max-width:760px){"
    ".feat{grid-template-columns:1fr;gap:20px}"
    ".feed{grid-template-columns:1fr}"
    ".artviz{grid-template-columns:1fr}"
    ".pitch-mini{width:100%;max-width:240px;margin:0 auto}"
    "}"
)


def _nav_html(nav, round_no, active=None):
    items = [
        '<a class="soon">Build a team</a>',
        '<a class="soon">Analyse a sub</a>',
    ]
    for slug, title in nav:
        if slug == active:
            items.append(
                f'<a class="on" href="/round/{round_no}/{slug}/">{_html.escape(title)}</a>')
        else:
            items.append(
                f'<a href="/round/{round_no}/{slug}/">{_html.escape(title)}</a>')
    return "<nav>" + "".join(items) + "</nav>"


def pitch_svg(xi_entries):
    """SVG football pitch placing an XI by position lines. Captain (rank 1) is flagged."""
    from evmax.articles import formation_of  # lazy to avoid circular at module level
    xi = list(xi_entries)
    # group by position
    gks = [e for e in xi if e.get("position") == "GK"]
    defs = [e for e in xi if e.get("position") == "DEF"]
    mids = [e for e in xi if e.get("position") == "MID"]
    fwds = [e for e in xi if e.get("position") == "FWD"]
    # fallback: any not matching a standard position goes to mid
    placed = set(id(e) for e in gks + defs + mids + fwds)
    for e in xi:
        if id(e) not in placed:
            mids.append(e)

    # pitch dimensions
    W, H = 200, 280
    # y positions for rows (top = fwd, bottom = gk to match typical pitch view)
    row_y = {"FWD": 50, "MID": 120, "DEF": 190, "GK": 250}

    def _row_nodes(players, y):
        if not players:
            return ""
        n = len(players)
        nodes = []
        for i, p in enumerate(players):
            x = W * (i + 1) / (n + 1)
            surname = _html.escape(p["name"].split()[-1])
            xpts = p.get("x_points", 0.0)
            is_captain = (p.get("rank") == 1) or (xi and p is xi[0])
            # node circle
            fill = "#0f7a45" if is_captain else "#fff"
            stroke = "#0f7a45"
            text_fill = "#fff" if is_captain else "#15140f"
            cap_badge = ""
            if is_captain:
                cap_badge = (f'<circle cx="{x+10:.1f}" cy="{y-12}" r="6" fill="#e8482b"/>'
                             f'<text x="{x+10:.1f}" y="{y-9}" text-anchor="middle" '
                             f'font-size="7" font-weight="700" fill="#fff">C</text>')
            nodes.append(
                f'<circle cx="{x:.1f}" cy="{y}" r="16" fill="{fill}" '
                f'stroke="{stroke}" stroke-width="1.5"/>'
                f'<text x="{x:.1f}" y="{y-3}" text-anchor="middle" '
                f'font-size="8.5" font-weight="700" fill="{text_fill}">{surname}</text>'
                f'<text x="{x:.1f}" y="{y+8}" text-anchor="middle" '
                f'font-size="8" fill="{text_fill}">{xpts:.1f}</text>'
                + cap_badge
            )
        return "".join(nodes)

    # pitch grass
    pitch_bg = (
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#1a7a3c" rx="4"/>'
        f'<rect x="8" y="8" width="{W-16}" height="{H-16}" fill="none" stroke="#fff" '
        f'stroke-width=".8" opacity=".4" rx="2"/>'
        # centre line
        f'<line x1="8" y1="{H//2}" x2="{W-8}" y2="{H//2}" '
        f'stroke="#fff" stroke-width=".6" opacity=".3"/>'
        # centre circle
        f'<circle cx="{W//2}" cy="{H//2}" r="20" fill="none" stroke="#fff" '
        f'stroke-width=".6" opacity=".3"/>'
    )

    nodes_svg = (
        _row_nodes(fwds, row_y["FWD"])
        + _row_nodes(mids, row_y["MID"])
        + _row_nodes(defs, row_y["DEF"])
        + _row_nodes(gks, row_y["GK"])
    )

    formation = formation_of(xi)
    formation_label = (
        f'<text x="{W//2}" y="{H-4}" text-anchor="middle" '
        f'font-size="9" font-weight="600" fill="#fff" opacity=".7">{formation}</text>'
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="XI pitch">'
        f'<g font-family="\'Hanken Grotesk\',sans-serif">'
        f'{pitch_bg}{nodes_svg}{formation_label}'
        f'</g></svg>'
    )


def ev_bar(entries, metric, width=360, row_h=30):
    """Horizontal bar viz (v2-styled). Top entry green, differentials red, others muted."""
    entries = list(entries)
    if not entries:
        return f'<svg viewBox="0 0 {width} 40" xmlns="http://www.w3.org/2000/svg"></svg>'
    vmax = max((e.get(metric) or 0.0) for e in entries) or 1.0
    label_w, pad = 90, 6
    bar_max = width - label_w - 50
    height = row_h * len(entries) + 10
    rows = []
    for i, e in enumerate(entries):
        y = i * row_h + pad
        val = e.get(metric) or 0.0
        bw = max(2, bar_max * (val / vmax))
        label = _html.escape(e["name"].split()[-1] if "name" in e else str(i + 1))
        own = e.get("ownership_pct")
        is_top = (i == 0)
        is_diff = (own is not None and own < 10.0) and not is_top
        bar_fill = "#0f7a45" if is_top else ("#e8482b" if is_diff else "#cdc6b6")
        val_fill = "#0a4f2d" if is_top else ("#a8331c" if is_diff else "#5d564a")
        nm_fill = "#15140f"
        rows.append(
            f'<text x="0" y="{y + 18}" font-size="13" font-weight="700" '
            f'fill="{nm_fill}">{label}</text>'
            f'<rect x="{label_w}" y="{y + 7}" width="{bw:.1f}" height="15" rx="3" '
            f'fill="{bar_fill}"/>'
            f'<text x="{label_w + bw + 6:.1f}" y="{y + 19}" font-size="12" '
            f'font-weight="700" fill="{val_fill}">{val:.2f}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="{_html.escape(metric)} chart">'
        f'<g font-family="\'Hanken Grotesk\',sans-serif">'
        + "".join(rows) +
        f'</g></svg>'
    )


def _rank_table_html(entries, columns):
    """v2 table.rank — rank, player+team+chips, then metric columns."""
    col_headers = "".join(
        f'<th>{_html.escape(_COL_LABEL.get(c, c))}</th>' for c in columns)
    rows = []
    for r in entries:
        own = r.get("ownership_pct")
        diff_tag = (f'<span class="tag">Differential</span>'
                    if own is not None and own < 10.0 else "")
        player_cell = (
            f'<td class="l"><span class="nm">{_html.escape(r["name"])}</span> '
            f'<span class="tm">{_html.escape(r.get("team") or "")}</span>'
            f'{diff_tag}</td>'
        )
        col_vals = "".join(
            f'<td class="big">{_fmt(c, r)}</td>' for c in columns)
        rows.append(
            f'<tr><td>{r.get("rank", "")}</td>{player_cell}{col_vals}</tr>')
    th_row = (f'<tr><th class="l">#</th><th class="l">Player</th>'
              f'{col_headers}</tr>')
    return (f'<table class="rank"><thead>{th_row}</thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def article_page(round_no, article, title, prose, entries, columns, nav, json_url, viz_html):
    """v2 editorial article page.

    prose: dict {headline, standfirst, body_html, bottom_line, source}
    viz_html: already-safe HTML string (pitch SVG or ev_bar)
    """
    summary = summary_sentence(article, entries)
    dataset_ld = _json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": _html.escape(title),
        "description": METHODOLOGY,
        "url": f"{SITE_URL}{json_url}",
        "creator": {"@type": "Organization", "name": "evmax"},
        "variableMeasured": [_COL_LABEL.get(c, c) for c in columns],
    })
    article_ld = _json.dumps({
        "@context": "https://schema.org", "@type": "Article",
        "headline": _html.escape(prose["headline"]),
        "author": {"@type": "Organization", "name": "evmax"},
        "publisher": {"@type": "Organization", "name": "evmax"},
        "description": _html.escape(prose["standfirst"]),
    })
    kicker_label = _html.escape(
        _COL_LABEL.get(article, article.replace("-", " ").title()) + f" · Round {round_no}")
    table_html = _rank_table_html(entries, columns)
    bottom_line = _html.escape(prose.get("bottom_line", ""))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(title)} | evmax</title>
<meta name="description" content="{_html.escape(summary)}">
<link rel="alternate" type="application/json" href="{json_url}">
{_FONTS}
<style>{_STYLE}</style>
<script type="application/ld+json">{dataset_ld}</script>
<script type="application/ld+json">{article_ld}</script>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html(nav, round_no, active=article)}
</div></header>
<div class="wrap">
<article class="art">
<div class="kick">{kicker_label}</div>
<h1>{_html.escape(prose["headline"])}</h1>
<p class="stand">{_html.escape(prose["standfirst"])}</p>
<div class="meta"><span class="av">e</span><span>By the evmax model</span></div>
<div class="artviz">{viz_html}</div>
<div class="prose">{prose["body_html"]}
<h2>The data</h2>
{table_html}
<h2>Bottom line</h2>
<p>{bottom_line}</p>
<p class="method"><b>How we get these numbers.</b> {METHODOLOGY}
Every figure here is machine-readable at <a href="{json_url}" style="color:var(--greend)">{json_url}</a>.</p>
</div>
</article>
</div></body></html>"""


def hub_page(round_no, nav, highlights):
    """Legacy hub page (kept for back-compat). Prefer landing_page for v2 builds."""
    cards = []
    for slug, title in nav:
        hl = _html.escape(highlights.get(slug, ""))
        cards.append(f'<a href="/round/{round_no}/{slug}/" class="card">'
                     f'<span class="ck">{_html.escape(title)}</span>'
                     f'<h3>{_html.escape(title)}</h3>'
                     f'<p>{hl}</p></a>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>World Cup Fantasy Round {round_no} — picks, captains, differentials | evmax</title>
<meta name="description" content="Simulation-based World Cup Fantasy picks for Round {round_no}: best XI, captains, differentials, value and blowout-fixture transfers from 50,000 Monte-Carlo runs.">
{_FONTS}
<style>{_STYLE}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html(nav, round_no)}
</div></header>
<div class="wrap">
<div class="pagelabel">World Cup Fantasy · Round {round_no}</div>
<div class="feed">{"".join(cards)}</div>
<p class="method"><b>Method.</b> {METHODOLOGY}</p>
</div></body></html>"""


def feed_card(slug, round_no, headline, teaser, stat_value, stat_label):
    """A single v2 feed card linking to /round/{round_no}/{slug}/."""
    kicker = _html.escape(slug.replace("-", " ").title())
    return (
        f'<a class="card" href="/round/{round_no}/{slug}/">'
        f'<span class="ck">{kicker}</span>'
        f'<h3>{_html.escape(headline)}</h3>'
        f'<p>{_html.escape(teaser)}</p>'
        f'<div class="stat"><b>{_html.escape(str(stat_value))}</b>'
        f'<span>{_html.escape(stat_label)}</span></div>'
        f'</a>'
    )


def landing_page(round_no, featured, feed, nav):
    """v2 landing page — featured block + feed grid.

    featured: {slug, prose: {headline, standfirst, ...}, viz_html}
    feed: list of {slug, headline, teaser, stat_value, stat_label}
    """
    feat_slug = featured["slug"]
    feat_prose = featured["prose"]
    feat_viz = featured.get("viz_html", "")
    feat_kicker = "Featured · " + _html.escape(
        feat_slug.replace("-", " ").title())
    feat_url = f"/round/{round_no}/{feat_slug}/"

    feed_cards = "".join(
        feed_card(
            f["slug"], round_no, f["headline"], f["teaser"],
            f["stat_value"], f["stat_label"])
        for f in feed)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>World Cup Fantasy Round {round_no} — picks, captains, differentials | evmax</title>
<meta name="description" content="Simulation-based World Cup Fantasy analysis for Round {round_no} from 50,000 Monte-Carlo runs.">
{_FONTS}
<style>{_STYLE}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html(nav, round_no)}
</div></header>
<div class="wrap">
<div class="pagelabel">World Cup Fantasy · Round {round_no}</div>
<section class="feat">
<div>
  <div class="kick">{feat_kicker}</div>
  <h1>{_html.escape(feat_prose["headline"])}</h1>
  <p class="stand">{_html.escape(feat_prose["standfirst"])}</p>
  <div class="byline"><span class="av">e</span><span>By the evmax model</span></div>
  <p style="margin-top:16px"><a href="{feat_url}" style="color:var(--green);font-weight:600;font-size:14px">Read the full analysis →</a></p>
</div>
<div class="viz">{feat_viz}</div>
</section>
<div class="pagelabel">Latest analysis</div>
<div class="feed">{feed_cards}</div>
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
