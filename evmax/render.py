"""Pure emitters for the evmax static site (HTML/SVG/JSON/text). No I/O."""

import html as _html
import json as _json

SITE_URL = "https://evmax.ai"
BRAND_SUFFIX = "evmax — fantasy football simulations"
GSC_META_TAG = (
    '<meta name="google-site-verification" '
    'content="TSaQglsr4AcaNMorvb7CgaHcSLkNhdt4xiaawRluLkQ" />')
# Our model outputs are licensed CC BY 4.0: anyone (humans or AI systems) may reuse
# the numbers WITH attribution to evmax — reuse-with-credit is the growth strategy,
# and a formal license both invites it and satisfies schema.org Dataset validation.
DATA_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
DATA_LICENSE_TEXT = ("CC BY 4.0 — free to reuse with attribution to evmax "
                     "(https://evmax.ai)")

# Favicons + mobile theme color, on every page. Google Search shows the favicon next
# to results (SVG supported); the PNG set covers Safari/Apple-touch and old browsers.
_HEAD_COMMON = (
    '<link rel="icon" href="/brand/logo.svg" type="image/svg+xml">'
    '<link rel="alternate icon" href="/brand/icon-32.png" type="image/png">'
    '<link rel="apple-touch-icon" href="/brand/icon-180.png">'
    '<meta name="theme-color" content="#0f7a45">')


def _og_meta(title, description, canonical_path, og_type="article"):
    """Open Graph + Twitter card + canonical — what makes shares (Reddit, X, WhatsApp)
    render a branded preview card instead of a bare link, and tells Google the
    canonical URL for each page."""
    url = f"{SITE_URL}{canonical_path}"
    t = _html.escape(title)
    d = _html.escape(description)
    return (
        f'<link rel="canonical" href="{url}">'
        f'<meta property="og:site_name" content="evmax">'
        f'<meta property="og:type" content="{og_type}">'
        f'<meta property="og:title" content="{t}">'
        f'<meta property="og:description" content="{d}">'
        f'<meta property="og:url" content="{url}">'
        f'<meta property="og:image" content="{SITE_URL}/brand/og-image.png">'
        f'<meta property="og:image:width" content="1200">'
        f'<meta property="og:image:height" content="630">'
        f'<meta name="twitter:card" content="summary_large_image">'
        f'<meta name="twitter:title" content="{t}">'
        f'<meta name="twitter:description" content="{d}">'
        f'<meta name="twitter:image" content="{SITE_URL}/brand/og-image.png">')


METHODOLOGY = ("Market odds (de-vigged) → Dixon-Coles scorelines → 50k Monte-Carlo "
               "simulations, scored on the official FIFA World Cup Fantasy points table.")
# Buttondown chosen for its static-site-friendly no-JS embed form: a plain HTML
# <form> POST, no client-side script, no cookies set by us. The account is
# registered separately from this codebase. This is a user-initiated POST only
# (fires when a visitor deliberately submits the form) — it does not run on page
# load, so it does not violate the site's zero-cookie / zero-JS / zero-third-party-
# on-load compliance posture. Disclosed to visitors in /privacy/.
NEWSLETTER_ACTION = "https://buttondown.com/api/emails/embed-subscribe/evmax"


def article_json(competition, fantasy_round, article, title, generated_at, sims, entries,
                 extra_fields=None):
    """extra_fields: optional dict merged into the envelope as additional top-level
    keys (e.g. wildcard's {"squad": {...}} meta). Never overrides the standard keys."""
    env = {
        "competition": competition,
        "round": fantasy_round,
        "article": article,
        "title": title,
        "generated_at": generated_at,
        "sims": sims,
        "methodology": METHODOLOGY,
        "entries": entries,
        "source": SITE_URL,
        "license": DATA_LICENSE_URL,
        "license_text": DATA_LICENSE_TEXT,
    }
    if extra_fields:
        for k, v in extra_fields.items():
            env.setdefault(k, v)
    return env


def summary_sentence(article, entries):
    if not entries:
        return "No data available this round."
    if article == "matches":
        close = sum(1 for e in entries if e.get("close"))
        return (f"Match predictions for {len(entries)} fixtures this round; "
                f"{close} close game(s) to watch.")
    if article == "wildcard":
        # summary_sentence only receives entries (no meta dict), so derive the
        # squad-level numbers straight from the 15 rows themselves. SQUAD_BUDGET
        # is the article's fixed budget constant (entries carry cost, not budget).
        from evmax.articles import formation_of, SQUAD_BUDGET
        xi = [e for e in entries if e.get("role") == "XI"] or entries[:11]
        total_cost = round(sum(e.get("price") or 0.0 for e in entries), 2)
        xi_xpoints = round(sum(e.get("x_points") or 0.0 for e in xi), 2)
        return (f"A {formation_of(xi)} wildcard squad costing {total_cost}m of the "
                f"{SQUAD_BUDGET}m budget, projecting {xi_xpoints} xPts from the XI.")
    top = entries[0]
    if article == "transfers" and "name" in top:
        return (f"{top['name']} ({top.get('team', '')}) is the top priority transfer: "
                f"{top['vor']:+.2f} value over replacement"
                + (f", {top['p_advance']:.0f}% chance of advancing" if "p_advance" in top
                   and top['p_advance'] < 100 else "") + ".")
    if "name" not in top:
        return f"Round {article} analysis."
    name, team = top["name"], top.get("team", "")
    if article == "captains":
        return (f"Captain {name} ({team}): {top['captain_ev']:.1f} expected points — "
                f"the highest captain EV in this round.")
    if article == "differentials":
        return (f"{name} ({team}) is the standout differential: {top['x_points']:.1f} xPts "
                f"at just {top['ownership_pct']:.1f}% ownership.")
    if article == "efficiency":
        return (f"{name} ({team}) is the best value: {top['x_points']:.2f} xPts "
                f"at just {top['price']:.1f}m.")
    if article in ("high-ceiling-xi", "risky"):
        return (f"{name} ({team}) has the highest ceiling: up to {top['ceiling']:.1f} points.")
    if article == "defenders":
        return (f"{name} ({team}) is the top defensive pick at {top['x_points']:.1f} xPts.")
    if article == "blowout-transfers":
        return (f"{name} ({team}) is the top attacker in this round's most lopsided fixtures "
                f"at {top['x_points']:.1f} xPts.")
    if article == "fixtures":
        return (f"{name} ({team}) has the best clean-sheet odds this round: "
                f"{top['p_clean_sheet'] * 100:.0f}%.")
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
              "value": "Pts/m", "price": "Price", "ownership_pct": "Owned %",
              "priority_score": "Priority", "vor": "VOR", "p_advance": "Advance %",
              "p_clean_sheet": "CS %", "exp_goals_for": "xGF", "exp_goals_against": "xGA",
              "top_def": "Best DEF", "top_gk": "Best GK"}

# Columns whose value is already a display-ready string (not a number to format).
_STRING_COLS = {"top_def", "top_gk"}


def _fmt(col, row):
    v = row.get(col)
    if v is None:
        return "—"
    if col in _STRING_COLS:
        return str(v)
    if col in ("ownership_pct", "p_advance"):
        return f"{v:.1f}%"
    if col == "p_clean_sheet":
        return f"{v * 100:.0f}%"
    if col == "price":
        return f"{v:.1f}"
    return f"{v:.2f}" if isinstance(v, float) else str(v)


# Fonts are SELF-HOSTED (variable woff2 under /fonts/, shipped by build.py from
# evmax/assets/fonts/). Deliberately NOT loaded from fonts.googleapis.com: remote
# Google Fonts transmits visitor IPs to Google, which an EU court (LG München,
# 3 O 17493/20, Jan 2022) held violates the GDPR absent consent. Self-hosting keeps
# the site zero-third-party / zero-cookie, so no consent banner is required.
_FONTS = ("<style>"
          "@font-face{font-family:'Hanken Grotesk';font-style:normal;font-weight:400 800;"
          "font-display:swap;src:url(/fonts/hanken-grotesk-var.woff2) format('woff2')}"
          "@font-face{font-family:'Newsreader';font-style:normal;font-weight:400 600;"
          "font-display:swap;src:url(/fonts/newsreader-var.woff2) format('woff2')}"
          "</style>")

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
    ".live-tag{color:var(--acc);font-size:11px;font-weight:700;letter-spacing:1.5px;"
    "text-transform:uppercase}"
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
    "margin:6px 0 26px;display:flex;flex-direction:column;align-items:center}"
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
    ".tag-floor{display:inline-block;font-size:10.5px;font-weight:700;text-transform:uppercase;"
    "letter-spacing:.5px;color:var(--ink3);background:var(--chipbg);border-radius:6px;"
    "padding:2px 7px;margin-left:6px}"
    ".tag-go{display:inline-block;font-size:10.5px;font-weight:700;text-transform:uppercase;"
    "letter-spacing:.5px;color:var(--green);background:#eaf5ee;border-radius:6px;"
    "padding:2px 7px;margin-left:6px}"
    ".method{font-size:13.5px;color:var(--ink3);line-height:1.7;border-top:1px solid var(--line);"
    "margin-top:34px;padding-top:18px}"
    ".method b{color:var(--green)}"
    ".nl-box{background:var(--surf);border:1px solid var(--line);border-radius:14px;"
    "padding:26px 28px;margin:34px 0}"
    ".nl-box h2{font-size:21px;font-weight:800;letter-spacing:-.3px;margin-bottom:8px}"
    ".nl-box p{font-family:var(--serif);font-size:15.5px;color:var(--ink2);line-height:1.5;"
    "margin-bottom:16px}"
    ".nl-form{display:flex;gap:10px;flex-wrap:wrap}"
    ".nl-form input[type=email]{flex:1;min-width:220px;font-family:var(--sans);font-size:14.5px;"
    "padding:11px 14px;border:1px solid var(--line);border-radius:8px;background:var(--bg);"
    "color:var(--ink)}"
    ".nl-form button{font-family:var(--sans);font-size:14.5px;font-weight:700;color:#fff;"
    "background:var(--green);border:0;border-radius:8px;padding:11px 20px;cursor:pointer}"
    ".nl-form button:hover{background:var(--greend)}"
    ".nl-micro{font-size:12px;color:var(--ink3);margin-top:10px;margin-bottom:0}"
    "@media(max-width:760px){.nl-form{flex-direction:column}.nl-form button{width:100%}}"
    ".sitefoot{border-top:1px solid var(--line);margin-top:56px;padding:26px 0 40px;background:var(--surf)}"
    ".sitefoot p{font-size:12.5px;color:var(--ink3);line-height:1.65;max-width:76ch;margin-bottom:10px}"
    ".sitefoot a{color:var(--greend);text-decoration:underline}"
    ".pitch-mini{width:200px}"
    ".landing-grid{display:grid;grid-template-columns:1fr 300px;gap:40px;align-items:start}"
    ".rail{position:sticky;top:80px;align-self:start;background:var(--surf);"
    "border:1px solid var(--line);border-radius:14px;padding:18px 20px}"
    ".rail .pagelabel{margin:0 0 14px}"
    ".rail-row{padding:12px 0;border-bottom:1px solid var(--line)}"
    ".rail-row:last-of-type{border-bottom:0}"
    ".rail-row-top{display:flex;align-items:baseline;justify-content:space-between;gap:8px;"
    "margin-bottom:8px}"
    ".rail-teams{font-size:14px;font-weight:700;letter-spacing:-.2px}"
    ".rail-ko{font-size:11px;color:var(--ink3);white-space:nowrap;text-align:right}"
    ".rail-score{font-size:18px;font-weight:800;color:var(--ink)}"
    ".rail-link{display:block;margin-top:14px;font-size:13px;font-weight:600;color:var(--green)}"
    "@media(max-width:900px){"
    ".landing-grid{grid-template-columns:1fr}"
    ".landing-grid .rail{position:static;order:2}"
    ".landing-grid .main-col{order:1}"
    "}"
    "@media(max-width:760px){"
    ".feat{grid-template-columns:1fr;gap:20px}"
    ".feed{grid-template-columns:1fr}"
    ".pitch-mini{width:100%;max-width:240px;margin:0 auto}"
    "}"
)


def _nav_html(active=None):
    """Fixed site nav, identical on every page.
    active ∈ {'home','about','track-record',None}."""
    home_cls = ' class="on"' if active == "home" else ""
    track_cls = ' class="on"' if active == "track-record" else ""
    about_cls = ' class="on"' if active == "about" else ""
    items = [
        f'<a href="/"{home_cls}>Home</a>',
        f'<a href="/track-record/"{track_cls}>Track record</a>',
        '<a class="soon">Build a team</a>',
        '<a class="soon">Analyse a sub</a>',
        f'<a href="/about/"{about_cls}>About</a>',
    ]
    return "<nav>" + "".join(items) + "</nav>"



def _footer_html():
    """Site-wide footer: legal disclaimer + privacy/about links, on every page."""
    return (
        '<footer class="sitefoot"><div class="wrap">'
        '<p><b>evmax</b> is an independent statistical-analysis project. It is not '
        'affiliated with, endorsed by, or connected to FIFA, any football federation, '
        'league, club, or fantasy game operator. All player and team names are used in '
        'a purely descriptive, informational context.</p>'
        '<p>All projections are our own model estimates (Monte-Carlo simulations on '
        'publicly available market information) and carry no guarantee of accuracy. '
        'Nothing on this site is betting or financial advice. If you choose to bet, '
        'you must be of legal gambling age in your jurisdiction \u2014 please gamble '
        'responsibly.</p>'
        f'<p>Data license: <a href="{DATA_LICENSE_URL}">CC BY 4.0</a> \u2014 reuse our '
        'numbers freely with attribution to evmax. '
        '<a href="/about/">About</a> \u00b7 <a href="/privacy/">Privacy</a> \u00b7 '
        '<a href="/llms.txt">llms.txt</a></p>'
        '</div></footer>')

def _newsletter_html():
    """Editorial newsletter box: plain HTML form, no JS. The POST only fires when
    a visitor deliberately submits it, so it does not run on page load and does not
    compromise the site's zero-cookie / zero-JS / zero-third-party-on-load posture.
    See NEWSLETTER_ACTION and /privacy/ for the Buttondown disclosure."""
    return (
        '<div class="nl-box">'
        '<h2>Get the next round the moment odds drop</h2>'
        '<p>50,000 simulations per matchday — captains, EV and match predictions '
        'in your inbox before lock.</p>'
        f'<form method="post" action="{NEWSLETTER_ACTION}" class="nl-form">'
        '<input type="email" name="email" required placeholder="you@example.com">'
        '<button type="submit">Subscribe</button>'
        '</form>'
        '<p class="nl-micro">Double opt-in. No spam, no tracking. Unsubscribe anytime.</p>'
        '</div>'
    )


def pitch_svg(xi_entries):
    """SVG football pitch placing an XI by position lines. Captain (rank 1) is flagged."""
    from evmax.articles import formation_of  # lazy to avoid circular at module level
    xi = list(xi_entries)
    if not xi:
        return '<svg viewBox="0 0 200 280" xmlns="http://www.w3.org/2000/svg"/>'
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


def ev_bar(entries, metric, width=360, row_h=30, max_rows=None):
    """Horizontal bar viz (v2-styled). Top entry green, differentials red, others muted.

    max_rows: optional cap on the number of rows drawn (belt & braces alongside
    slicing at the call site) -- keeps a chart from growing unbounded when it's
    fed a long ranked list. None (default) draws every entry."""
    entries = list(entries)
    if max_rows is not None:
        entries = entries[:max_rows]
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
        ceil_ratio = r.get("ceiling_ratio")
        floor_tag = (f'<span class="tag-floor">Safe floor</span>'
                     if ceil_ratio is not None and ceil_ratio < 1.15 else "")
        p_adv = r.get("p_advance")
        risk_tag = (f'<span class="tag">Advance risk</span>'
                    if p_adv is not None and p_adv < 60.0 else "")
        env = r.get("env")
        blowout_tag = f'<span class="tag-go">Blowout</span>' if env == "blowout" else ""
        avoid_tag = (f'<span class="tag-floor">Low-goal — fade forwards</span>'
                    if env == "avoid" else "")
        bench_tag = (f'<span class="tag-floor">Bench</span>'
                    if r.get("role") == "Bench" else "")
        # efficiency() price tier -- a muted chip, same style for all three tiers
        # (Premium deliberately does NOT use the red .tag style: red reads as a
        # warning elsewhere on the site, and a Premium price isn't a warning).
        tier = r.get("tier")
        tier_tag = f'<span class="tag-floor">{_html.escape(tier)}</span>' if tier else ""
        player_cell = (
            f'<td class="l"><span class="nm">{_html.escape(r["name"])}</span> '
            f'<span class="tm">{_html.escape(r.get("team") or "")}</span>'
            f'{tier_tag}{diff_tag}{floor_tag}{risk_tag}{blowout_tag}{avoid_tag}{bench_tag}</td>'
        )
        col_vals = "".join(
            f'<td class="big">{_fmt(c, r)}</td>' for c in columns)
        rows.append(
            f'<tr><td>{r.get("rank", "")}</td>{player_cell}{col_vals}</tr>')
    th_row = (f'<tr><th class="l">#</th><th class="l">Player</th>'
              f'{col_headers}</tr>')
    return (f'<table class="rank"><thead>{th_row}</thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


_MATCH_CSS = (
    ".mx-lead{background:var(--surf);border:1px solid var(--line);border-radius:14px;"
    "padding:16px 20px;margin-bottom:24px}"
    ".mx-lead h3{font-size:15px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;"
    "color:var(--green);margin-bottom:10px}"
    ".mx-close-list{display:flex;flex-wrap:wrap;gap:8px}"
    ".mx-close-tag{background:#fdeee9;color:var(--acc);font-size:13px;font-weight:700;"
    "padding:4px 10px;border-radius:8px}"
    ".mx-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}"
    ".mx-card{background:var(--surf);border:1px solid var(--line);border-radius:14px;"
    "padding:18px 20px;display:flex;flex-direction:column;gap:10px}"
    ".mx-card.mx-close-card{border-color:var(--acc);border-width:2px}"
    ".mx-teams{font-size:18px;font-weight:800;letter-spacing:-.3px}"
    ".mx-score{font-size:32px;font-weight:800;color:var(--green);letter-spacing:1px;"
    "line-height:1}"
    ".mx-xg{font-size:13px;color:var(--ink3);display:flex;align-items:center;gap:6px}"
    ".mx-xg-h{color:var(--green);font-weight:700}"
    ".mx-xg-a{color:var(--ink2);font-weight:700}"
    ".mx-probs{display:flex;gap:0;border:1px solid var(--line);border-radius:8px;overflow:hidden;"
    "font-size:12px;font-weight:700;text-align:center}"
    ".mx-ph{flex:1;background:#eaf5ee;color:var(--greend);padding:5px 2px}"
    ".mx-pd{flex:1;background:var(--chipbg);color:var(--ink2);padding:5px 2px}"
    ".mx-pa{flex:1;background:#f5f0ea;color:var(--ink2);padding:5px 2px}"
    ".mx-ko{font-size:11px;color:var(--ink3);letter-spacing:.5px}"
    ".mx-badge{display:inline-block;font-size:10.5px;font-weight:700;text-transform:uppercase;"
    "letter-spacing:.5px;color:var(--acc);background:#fdeee9;border-radius:6px;"
    "padding:2px 8px;align-self:flex-start}"
    ".mx-badge.final{color:var(--greend);background:#eaf5ee}"
    ".mx-final-score{font-size:32px;font-weight:800;color:var(--ink);letter-spacing:1px;"
    "line-height:1}"
    ".mx-predicted{font-size:12.5px;color:var(--ink3)}"
)


def match_predictions_html(entries: list) -> str:
    """Render fixture prediction cards in v2 editorial style."""
    if not entries:
        return "<p style='color:var(--ink3);text-align:center'>No fixtures found for this round.</p>"

    close_matches = [e for e in entries if e.get("close")]

    # Lead strip
    lead_parts = []
    if close_matches:
        tags = "".join(
            f'<span class="mx-close-tag">{_html.escape(e["match"])}</span>'
            for e in close_matches
        )
        lead_parts.append(
            f'<div class="mx-lead">'
            f'<h3>Games to watch</h3>'
            f'<div class="mx-close-list">{tags}</div>'
            f'</div>'
        )

    # Sort: close games first, then by kickoff
    sorted_entries = sorted(entries, key=lambda e: (not e.get("close"), e.get("kickoff", "")))

    cards = []
    for e in sorted_entries:
        is_close = e.get("close", False)
        is_finished = e.get("finished", False)
        card_cls = "mx-card mx-close-card" if (is_close and not is_finished) else "mx-card"
        home_esc = _html.escape(e.get("home", ""))
        away_esc = _html.escape(e.get("away", ""))
        score = _html.escape(e.get("top_scoreline", "?-?"))
        xgh = e.get("exp_home_goals", 0.0)
        xga = e.get("exp_away_goals", 0.0)
        p_home = e.get("p_home", 0.0)
        p_draw = e.get("p_draw", 0.0)
        p_away = e.get("p_away", 0.0)
        ko = e.get("kickoff", "")
        # Format kickoff: show ISO date+time trimmed
        ko_display = ko[:16].replace("T", " ") + " UTC" if ko else "—"

        if is_finished:
            # Finished fixture: the ACTUAL score is the headline number, with the
            # pre-match prediction demoted to a small caption underneath — a
            # running predicted-vs-actual scoreboard rather than a stale forecast.
            final_score = _html.escape(e.get("final_score", score))
            badge = '<span class="mx-badge final">Final</span>'
            fav_pct = round(max(p_home, p_draw, p_away) * 100)
            fav_label = "Draw" if p_draw >= p_home and p_draw >= p_away else (
                home_esc if p_home >= p_away else away_esc)
            card = (
                f'<div class="{card_cls}">'
                f'<div class="mx-teams">{home_esc} <span style="color:var(--ink3);font-weight:400">vs</span> {away_esc}</div>'
                f'<div class="mx-final-score">{final_score}</div>'
                f'<div class="mx-predicted">predicted {score} · P({fav_label}) {fav_pct}%</div>'
                f'<div class="mx-ko">{_html.escape(ko_display)}</div>'
                f'{badge}'
                f'</div>'
            )
        else:
            badge = '<span class="mx-badge">Close — one to watch</span>' if is_close else ""
            card = (
                f'<div class="{card_cls}">'
                f'<div class="mx-teams">{home_esc} <span style="color:var(--ink3);font-weight:400">vs</span> {away_esc}</div>'
                f'<div class="mx-score">{score}</div>'
                f'<div class="mx-xg">'
                f'<span class="mx-xg-h">{xgh:.2f} xG</span>'
                f'<span style="color:var(--line)">|</span>'
                f'<span class="mx-xg-a">{xga:.2f} xG</span>'
                f'</div>'
                f'<div class="mx-probs">'
                f'<div class="mx-ph">H {p_home*100:.0f}%</div>'
                f'<div class="mx-pd">D {p_draw*100:.0f}%</div>'
                f'<div class="mx-pa">A {p_away*100:.0f}%</div>'
                f'</div>'
                f'<div class="mx-ko">{_html.escape(ko_display)}</div>'
                f'{badge}'
                f'</div>'
            )
        cards.append(card)

    grid = f'<div class="mx-grid">{"".join(cards)}</div>'
    return f'<style>{_MATCH_CSS}</style>' + "".join(lead_parts) + grid


_TRACK_RECORD_CSS = (
    ".tr-badge{display:inline-block;font-size:11px;font-weight:700;text-transform:uppercase;"
    "letter-spacing:.6px;padding:3px 10px;border-radius:20px}"
    ".tr-badge.final{background:#eaf5ee;color:var(--greend)}"
    ".tr-badge.pending{background:var(--chipbg);color:var(--ink3)}"
    ".tag-retro{display:inline-block;font-size:11px;font-weight:700;text-transform:uppercase;"
    "letter-spacing:.6px;padding:3px 10px;border-radius:20px;color:#854f0b;background:#faeeda}"
    ".tr-retro-note{font-family:var(--serif);font-size:14px;color:var(--ink3);"
    "line-height:1.5;margin:-6px 0 16px;font-style:italic}"
    ".tr-card{background:var(--surf);border:1px solid var(--line);border-radius:14px;"
    "padding:24px 26px;margin-bottom:24px}"
    ".tr-card h2{font-size:20px;font-weight:800;letter-spacing:-.3px;margin:0}"
    ".tr-head{display:flex;align-items:center;justify-content:space-between;gap:12px;"
    "flex-wrap:wrap;margin-bottom:14px}"
    ".tr-claim{font-family:var(--serif);font-size:16.5px;color:var(--ink2);line-height:1.55;"
    "margin-bottom:16px}"
    ".tr-claim b{color:var(--ink)}"
    ".tr-table-wrap{overflow-x:auto}"
    "table.tr-metrics{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:4px}"
    "table.tr-metrics th{text-align:right;font-size:10.5px;font-weight:700;letter-spacing:.8px;"
    "text-transform:uppercase;color:var(--ink3);padding:8px 8px;border-bottom:2px solid var(--ink)}"
    "table.tr-metrics th:first-child,table.tr-metrics td:first-child{text-align:left}"
    "table.tr-metrics td{padding:9px 8px;border-bottom:1px solid var(--line);text-align:right;"
    "font-variant-numeric:tabular-nums}"
    "table.tr-metrics td.na{color:var(--ink3)}"
    ".tr-misses{margin-top:16px;border-top:1px dashed var(--line);padding-top:14px}"
    ".tr-misses h3{font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;"
    "color:var(--acc);margin-bottom:8px}"
    ".tr-misses li{font-size:14px;color:var(--ink2);line-height:1.55;margin-bottom:6px;"
    "margin-left:18px}"
    ".tr-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));"
    "gap:14px;margin:18px 0 8px}"
    ".tr-stat{background:var(--surf);border:1px solid var(--line);border-radius:12px;"
    "padding:14px 16px}"
    ".tr-stat b{display:block;font-size:24px;font-weight:800;color:var(--green)}"
    ".tr-stat span{font-size:12px;color:var(--ink3);text-transform:uppercase;letter-spacing:.4px}"
)


def _tr_badge(status: str) -> str:
    """Small badge for the round's completeness status (Final / pending)."""
    label = "Final" if status == "final" else (
        "Results pending" if status == "pending" else "No snapshot")
    cls = status if status in ("final", "pending") else "pending"
    return f'<span class="tr-badge {cls}">{_html.escape(label)}</span>'


def _tr_kind_badge(kind: str) -> str:
    """The provenance badge: distinguishes a published-and-frozen round from a
    retrospective backtest. This is the credibility-critical bit of the page —
    it must never be ambiguous which kind a round is."""
    if kind == "retrospective":
        return '<span class="tag-retro">Retrospective backtest</span>'
    return '<span class="tr-badge final" style="background:#eaf5ee">Published · frozen at lock</span>'


def _tr_metrics_table(grades: dict) -> str:
    rows = []
    for slug in sorted(grades):
        g = grades[slug]
        label = _html.escape(slug.replace("-", " ").title())
        if not g.get("graded"):
            reason = _html.escape(g.get("reason", "not graded"))
            rows.append(
                f'<tr><td>{label}</td><td class="na" colspan="5">{reason}</td></tr>')
            continue
        mae = f'{g["mae"]:.2f}' if g.get("mae") is not None else "—"
        rho = f'{g["spearman"]:.2f}' if g.get("spearman") is not None else "—"
        tp = g.get("top_pick") or {}
        bi = g.get("best_in_list") or {}
        tp_str = (f'{_html.escape(tp.get("name",""))} '
                  f'({tp.get("projected", 0):.1f}→{tp.get("realized", 0):.1f})') if tp else "—"
        bi_str = (f'{_html.escape(bi.get("name",""))} '
                  f'({bi.get("realized", 0):.1f})') if bi else "—"
        matched = f'{g.get("matched", 0)}/{g.get("total", 0)}'
        rows.append(
            f'<tr><td>{label}</td><td>{mae}</td><td>{rho}</td>'
            f'<td>{matched}</td><td>{tp_str}</td><td>{bi_str}</td></tr>')
    return (
        '<div class="tr-table-wrap"><table class="tr-metrics"><thead><tr>'
        '<th>Article</th><th>MAE</th><th>Rank corr.</th><th>Matched</th>'
        '<th>Top pick (proj.→real)</th><th>Best in list (real)</th>'
        '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'
    )


def _tr_headline_claim(round_no: int, grades: dict) -> str:
    """The headline claims-vs-reality line: top captain projected vs realized,
    and best-XI projected vs realized totals, when available."""
    parts = []
    cap = grades.get("captains")
    if cap and cap.get("graded") and cap.get("top_pick"):
        tp = cap["top_pick"]
        parts.append(
            f'Our top captain pick, <b>{_html.escape(tp["name"])}</b>, was projected '
            f'<b>{tp["projected"]:.1f}</b> pts and actually scored '
            f'<b>{tp["realized"]:.1f}</b>.')
    xi = grades.get("best-xi")
    if xi and xi.get("graded") and xi.get("xi_projected_total") is not None:
        parts.append(
            f'The published best XI projected <b>{xi["xi_projected_total"]:.1f}</b> total '
            f'points; it actually scored <b>{xi["xi_realized_total"]:.1f}</b>.')
    if not parts:
        parts.append("No graded headline claims for this round yet.")
    return " ".join(parts)


def _track_record_round_card(round_data: dict) -> str:
    round_no = round_data["round"]
    status = round_data["status"]
    kind = round_data.get("kind", "published")
    badge = _tr_badge(status)
    kind_badge = _tr_kind_badge(kind)
    header = (f'<div class="tr-head"><h2>Round {round_no}</h2>'
             f'<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
             f'{kind_badge}{badge}</div></div>')

    note = round_data.get("note")
    note_html = (f'<p class="tr-retro-note">{_html.escape(note)}</p>' if note else "")

    if status != "final":
        body = ('<p class="tr-claim">This round is still in progress — matches have not '
                'all finished, so we have not graded it yet. The published prediction '
                'snapshot is already frozen and will be graded automatically once the '
                'round completes.</p>')
        return f'<div class="tr-card">{header}{note_html}{body}</div>'

    grades = round_data.get("grades", {})
    claim = _tr_headline_claim(round_no, grades)
    table = _tr_metrics_table(grades)
    coverage = round_data.get("coverage") or {}
    cov_note = ""
    if coverage.get("total"):
        cov_note = (f'<p style="font-size:12px;color:var(--ink3);margin-top:10px">'
                    f'Name-match coverage vs the official FIFA fantasy feed: '
                    f'{coverage.get("matched", 0)}/{coverage.get("total", 0)} players.</p>')

    misses = round_data.get("misses") or []
    misses_html = ""
    if misses:
        items = "".join(f'<li>{_html.escape(m)}</li>' for m in misses)
        misses_html = (f'<div class="tr-misses"><h3>Honest misses</h3>'
                       f'<ul>{items}</ul></div>')

    return (f'<div class="tr-card">{header}{note_html}'
           f'<p class="tr-claim">{claim}</p>{table}{cov_note}{misses_html}</div>')


def track_record_page(record: dict) -> str:
    """/track-record/ — the site's credibility layer. Deterministic text only:
    every number here comes straight from evmax.backtest, no LLM prose, because
    trust requires that this specific page never has room for a model to shade
    the truth."""
    rounds = record.get("rounds", [])
    summary = record.get("summary", {})

    cards = "".join(_track_record_round_card(r) for r in rounds)

    mae = summary.get("mean_captain_mae")
    rho = summary.get("mean_spearman")
    graded_n = summary.get("rounds_graded", 0)
    summary_stats = (
        '<div class="tr-summary">'
        f'<div class="tr-stat"><b>{graded_n}</b><span>Rounds graded</span></div>'
        f'<div class="tr-stat"><b>{f"{mae:.2f}" if mae is not None else "—"}</b>'
        f'<span>Mean captain MAE</span></div>'
        f'<div class="tr-stat"><b>{f"{rho:.2f}" if rho is not None else "—"}</b>'
        f'<span>Mean rank correlation</span></div>'
        '</div>'
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Every prediction, graded | {BRAND_SUFFIX}</title>
<meta name="description" content="evmax grades its own published World Cup Fantasy predictions against official FIFA fantasy points, misses included. No cherry-picking — every round, every article.">
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}{_TRACK_RECORD_CSS}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html(active="track-record")}
</div></header>
<div class="wrap">
<article class="art" style="max-width:820px">
<div class="kick">Accountability</div>
<h1>Every prediction, graded</h1>
<p class="stand">Before every round locks, we publish our picks as a frozen, timestamped
snapshot. Once the round finishes, we grade that exact snapshot against the official FIFA
World Cup Fantasy points — no do-overs, no rebuilding the model after the fact. Misses are
shown alongside hits. Rounds marked retrospective were reconstructed after results were
known — from frozen closing odds — and are shown for context, not credit.</p>
{summary_stats}
<div class="pagelabel" style="margin-top:8px">By round, newest first</div>
{cards}
<p class="method"><b>Method.</b> {METHODOLOGY} Grading: MAE compares our projected
expected points to realized official points across matched entries; rank correlation
(Spearman) checks whether our ordering matched reality, not just our top pick; captain
regret is the gap between the best-scoring player in our own published list and the one we
actually named captain. A round is graded only once every one of its fixtures has finished.</p>
</article>
</div>
{_footer_html()}</body></html>"""


def track_record_json(record: dict) -> dict:
    """/api/track-record.json — machine-readable grading history."""
    return {
        "competition": "fifa_world_cup_fantasy",
        "title": "evmax track record — graded predictions",
        "methodology": METHODOLOGY,
        "grading_methodology": (
            "Predictions are frozen at round lock as point-in-time JSON snapshots. Once "
            "every fixture in a round reaches a final status, each snapshot is graded "
            "against official FIFA World Cup Fantasy points: MAE (projected vs realized), "
            "Spearman rank correlation (our order vs realized order), top-pick vs "
            "best-in-list, and (captains) captain regret. Fixture 1X2 grading for the "
            "matches article is not yet implemented."),
        "rounds": record.get("rounds", []),
        "summary": record.get("summary", {}),
        "source": SITE_URL,
        "license": DATA_LICENSE_URL,
        "license_text": DATA_LICENSE_TEXT,
    }


def article_page(round_no, article, title, prose, entries, columns, json_url, viz_html,
                 generated_at=None, date_str=None, show_table=True):
    """v2 editorial article page.

    Published articles are frozen claims: this page always renders the exact
    pre-lock projection, with no live/in-progress mutation. The one place
    reality shows up post-lock is the matches article's predicted-vs-actual
    panel (see match_predictions_html), which is driven entirely by data on
    each entry (finished/final_score), not by a flag here.

    prose: dict {headline, standfirst, body_html, bottom_line, source}
    viz_html: already-safe HTML string (pitch SVG or ev_bar)
    generated_at: ISO-8601 timestamp string (optional)
    date_str: human-readable date string, e.g. "24 June 2026" (optional)
    """
    summary = summary_sentence(article, entries)
    dataset_ld_raw = _json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": title,
        "description": METHODOLOGY,
        "url": f"{SITE_URL}{json_url}",
        "creator": {"@type": "Organization", "name": "evmax"},
        "variableMeasured": [_COL_LABEL.get(c, c) for c in columns],
        "license": DATA_LICENSE_URL,
        "isAccessibleForFree": True,
    })
    dataset_ld = dataset_ld_raw.replace("</", "<\\/")
    article_ld_obj = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": prose["headline"],
        "author": {"@type": "Organization", "name": "evmax"},
        "publisher": {"@type": "Organization", "name": "evmax"},
        "description": prose["standfirst"],
        "articleBody": prose["standfirst"],
    }
    if generated_at is not None:
        article_ld_obj["datePublished"] = generated_at
    article_ld = _json.dumps(article_ld_obj).replace("</", "<\\/")
    kicker_label = _html.escape(
        _COL_LABEL.get(article, article.replace("-", " ").title()) + f" · Round {round_no}")
    table_html = _rank_table_html(entries, columns) if show_table else ""
    data_section = f"<h2>The data</h2>\n{table_html}" if show_table else ""
    bottom_line = _html.escape(prose.get("bottom_line", ""))
    byline_date = f" · {_html.escape(date_str)}" if date_str else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(title)} | {BRAND_SUFFIX}</title>
<meta name="description" content="{_html.escape(summary)}">
<link rel="alternate" type="application/json" href="{json_url}">
{_og_meta(prose["headline"], summary, f"/round/{round_no}/{article}/", "article")}
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}</style>
<script type="application/ld+json">{dataset_ld}</script>
<script type="application/ld+json">{article_ld}</script>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html()}
</div></header>
<div class="wrap">
<article class="art">
<div class="kick">{kicker_label}</div>
<h1>{_html.escape(prose["headline"])}</h1>
<p class="stand">{_html.escape(prose["standfirst"])}</p>
<div class="meta"><span class="av">e</span><span>By the evmax model{byline_date}</span></div>
<div class="artviz">{viz_html}</div>
<div class="prose">{prose["body_html"]}
{data_section}
<h2>Bottom line</h2>
<p>{bottom_line}</p>
{_newsletter_html()}
<p class="method"><b>How we get these numbers.</b> {METHODOLOGY}
Every figure here is machine-readable at <a href="{json_url}" style="color:var(--greend)">{json_url}</a>.</p>
</div>
</article>
</div>
{_footer_html()}</body></html>"""


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
<title>World Cup Fantasy Round {round_no} — picks, captains, differentials | {BRAND_SUFFIX}</title>
<meta name="description" content="Simulation-based World Cup Fantasy picks for Round {round_no}: best XI, captains, differentials, value and blowout-fixture transfers from 50,000 Monte-Carlo runs.">
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html(active="home")}
</div></header>
<div class="wrap">
<div class="pagelabel">World Cup Fantasy · Round {round_no}</div>
<div class="feed">{"".join(cards)}</div>
<p class="method"><b>Method.</b> {METHODOLOGY}</p>
</div>
{_footer_html()}</body></html>"""


def feed_card(slug, round_no, headline, teaser, stat_value, stat_label, date_str=None):
    """A single v2 feed card linking to /round/{round_no}/{slug}/."""
    kicker = _html.escape(slug.replace("-", " ").title())
    date_html = (f'<span style="font-size:11px;color:var(--ink3);margin-top:-4px">'
                 f'{_html.escape(date_str)}</span>' if date_str else "")
    return (
        f'<a class="card" href="/round/{round_no}/{slug}/">'
        f'<span class="ck">{kicker}</span>'
        f'<h3>{_html.escape(headline)}</h3>'
        f'{date_html}'
        f'<p>{_html.escape(teaser)}</p>'
        f'<div class="stat"><b>{_html.escape(str(stat_value))}</b>'
        f'<span>{_html.escape(stat_label)}</span></div>'
        f'</a>'
    )


def _fixtures_rail_row(m: dict) -> str:
    """One compact fixture row for the landing page's odds rail. Reuses the
    .mx-probs/.mx-ph/.mx-pd/.mx-pa classes from the matches renderer so the
    probability bar matches the matches article pixel-for-pixel."""
    home_esc = _html.escape(m.get("home", ""))
    away_esc = _html.escape(m.get("away", ""))
    ko = m.get("kickoff", "")
    # Kickoff is stored as an ISO-8601 string; the rail only has room for HH:MM.
    ko_time = ko[11:16] if len(ko) >= 16 else "—"
    close_tag = '<span class="tag">Close</span>' if m.get("close") else ""
    top_line = (
        f'<div class="rail-row-top"><span class="rail-teams">{home_esc} vs {away_esc}'
        f'{close_tag}</span><span class="rail-ko">{_html.escape(ko_time)}</span></div>'
    )
    if m.get("finished") or m.get("final_score"):
        score = _html.escape(m.get("final_score", ""))
        body = (f'<div class="rail-score">{score}</div>'
                f'<span class="mx-badge final">Final</span>')
    else:
        p_home = m.get("p_home", 0.0) * 100
        p_draw = m.get("p_draw", 0.0) * 100
        p_away = m.get("p_away", 0.0) * 100
        body = (
            '<div class="mx-probs">'
            f'<div class="mx-ph">H {p_home:.0f}%</div>'
            f'<div class="mx-pd">D {p_draw:.0f}%</div>'
            f'<div class="mx-pa">A {p_away:.0f}%</div>'
            '</div>'
        )
    return f'<div class="rail-row">{top_line}{body}</div>'


def _fixtures_rail_html(round_no: int, fixtures: list) -> str:
    """The landing page's right-hand 'This round's ties' sidebar. fixtures is a
    list of match_predictions() entries (home/away/kickoff/p_home/p_draw/p_away/
    close/top_scoreline, and possibly finished/final_score)."""
    rows = "".join(_fixtures_rail_row(m) for m in fixtures)
    return (
        f'<aside class="rail"><div class="pagelabel">This round\'s ties</div>'
        f'{rows}'
        f'<a class="rail-link" href="/round/{round_no}/matches/">All match predictions →</a>'
        f'</aside>'
    )


def landing_page(round_no, featured, feed, date_str=None, fixtures=None):
    """v2 landing page — featured block + feed grid, with an optional right-hand
    odds rail ("This round's ties").

    featured: {slug, prose: {headline, standfirst, ...}, viz_html}
    feed: list of {slug, headline, teaser, stat_value, stat_label}
    date_str: human-readable date string, e.g. "24 June 2026" (optional)
    fixtures: optional list of match_predictions() entries; when provided, a
              sticky sidebar of this round's fixtures/odds renders alongside
              the main content in a two-column grid (single column on mobile,
              with the aside placed after the main content).
    """
    og_block = _og_meta(
        f"World Cup Fantasy Round {round_no} — simulation-based picks",
        f"Captain EV, expected points and match predictions for Round {round_no}, "
        f"from 50,000 Monte-Carlo simulations. Graded publicly.", "/", "website")
    org_ld = _json.dumps({
        "@context": "https://schema.org", "@type": "Organization", "name": "evmax",
        "url": SITE_URL, "logo": SITE_URL + "/brand/icon-512.png",
        "description": ("Simulation-based fantasy football analysis — 50,000 "
                        "Monte-Carlo simulations per matchday, graded publicly."),
    }).replace("</", "<\\/")
    site_ld = _json.dumps({
        "@context": "https://schema.org", "@type": "WebSite",
        "name": "evmax — fantasy football simulations", "url": SITE_URL,
    }).replace("</", "<\\/")
    feat_slug = featured["slug"]
    feat_prose = featured["prose"]
    feat_viz = featured.get("viz_html", "")
    feat_kicker = "Featured · " + _html.escape(
        feat_slug.replace("-", " ").title())
    feat_url = f"/round/{round_no}/{feat_slug}/"
    byline_date = f" · {_html.escape(date_str)}" if date_str else ""

    feed_cards = "".join(
        feed_card(
            f["slug"], round_no, f["headline"], f["teaser"],
            f["stat_value"], f["stat_label"], date_str=date_str)
        for f in feed)

    main_content = f"""<div class="pagelabel">World Cup Fantasy · Round {round_no}</div>
<section class="feat">
<div>
  <div class="kick">{feat_kicker}</div>
  <h1>{_html.escape(feat_prose["headline"])}</h1>
  <p class="stand">{_html.escape(feat_prose["standfirst"])}</p>
  <div class="byline"><span class="av">e</span><span>By the evmax model{byline_date}</span></div>
  <p style="margin-top:16px"><a href="{feat_url}" style="color:var(--green);font-weight:600;font-size:14px">Read the full analysis →</a></p>
</div>
<div class="viz">{feat_viz}</div>
</section>
<div class="pagelabel">Latest analysis</div>
<div class="feed">{feed_cards}</div>
{_newsletter_html()}
<p class="method"><b>Method.</b> {METHODOLOGY}</p>"""

    if fixtures:
        rail_html = _fixtures_rail_html(round_no, fixtures)
        body_content = (f'<div class="landing-grid">'
                        f'<div class="main-col">{main_content}</div>'
                        f'{rail_html}'
                        f'</div>')
    else:
        body_content = main_content

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>World Cup Fantasy Round {round_no} — picks, captains, differentials | {BRAND_SUFFIX}</title>
<meta name="description" content="Simulation-based World Cup Fantasy analysis for Round {round_no} from 50,000 Monte-Carlo runs.">
{og_block}
<script type="application/ld+json">{org_ld}</script>
<script type="application/ld+json">{site_ld}</script>
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}{_MATCH_CSS}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html(active="home")}
</div></header>
<div class="wrap">
{body_content}
</div>
{_footer_html()}</body></html>"""


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
    lines += [
        "",
        "## Track record",
        f"- [Every prediction, graded]({SITE_URL}/track-record/) — our published "
        "predictions graded against official FIFA fantasy points, misses included. "
        f"data: {SITE_URL}/api/track-record.json",
        "",
        "## API",
        f"- Article index: {SITE_URL}/api/latest.json",
        f"- Graded prediction accuracy: {SITE_URL}/api/track-record.json",
    ]
    return "\n".join(lines) + "\n"


def robots_txt():
    blocks = [f"User-agent: {b}\nAllow: /" for b in _AI_BOTS]
    blocks.append("User-agent: *\nAllow: /")
    return "\n\n".join(blocks) + f"\n\nSitemap: {SITE_URL}/sitemap.xml\n"


def sitemap_xml(round_no, nav, lastmod=None):
    urls = [f"{SITE_URL}/", f"{SITE_URL}/about/", f"{SITE_URL}/privacy/",
            f"{SITE_URL}/track-record/", f"{SITE_URL}/round/{round_no}/"]
    urls += [f"{SITE_URL}/round/{round_no}/{slug}/" for slug, _ in nav]
    lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
    items = "".join(f"<url><loc>{u}</loc>{lm}</url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f'{items}</urlset>')


def about_page():
    """Editorial About page explaining evmax methodology."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>About | {BRAND_SUFFIX}</title>
<meta name="description" content="evmax uses 50,000 Monte-Carlo simulations on de-vigged market odds to generate free, transparent World Cup Fantasy picks.">
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}
.about-body{{max-width:680px;margin:40px auto 80px}}
.about-body h1{{font-size:clamp(28px,4vw,40px);font-weight:800;line-height:1.05;letter-spacing:-1px;margin-bottom:16px}}
.about-body .lead{{font-family:var(--serif);font-size:20px;color:var(--ink2);line-height:1.5;margin-bottom:32px}}
.about-body h2{{font-size:13px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--green);margin:34px 0 12px}}
.about-body p{{font-family:var(--serif);font-size:17px;line-height:1.7;color:#23201a;margin-bottom:16px}}
.about-body ul{{font-family:var(--serif);font-size:17px;line-height:1.7;color:#23201a;margin:0 0 16px 24px}}
.about-body li{{margin-bottom:6px}}
.chip-row{{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}}
.chip{{background:var(--chipbg);color:var(--ink2);font-size:13px;font-weight:600;padding:6px 14px;border-radius:20px}}
</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html(active="about")}
</div></header>
<div class="wrap">
<div class="about-body">
<div class="pagelabel" style="margin-top:34px">About evmax</div>
<h1>Simulation-based World Cup Fantasy analysis, free and transparent</h1>
<p class="lead">evmax runs 50,000 Monte-Carlo simulations before every deadline and publishes the results openly — no paywalls, no hidden models.</p>

<h2>What is evmax?</h2>
<p>evmax is a simulation engine for FIFA World Cup Fantasy. It estimates expected points for every available player in each fantasy round, giving you a data-driven edge over gut-feel picks. All numbers are free to read, share, and build on.</p>

<h2>The methodology</h2>
<ul>
<li><b>De-vig market odds</b> — we strip the bookmaker margin from pre-match odds to get implied true probabilities for each scoreline.</li>
<li><b>Dixon-Coles model</b> — a bivariate Poisson framework calibrated on the de-vigged probabilities, accounting for low-scoring draw correction and team-level attack/defence strength.</li>
<li><b>50,000 Monte-Carlo simulations</b> — each simulation draws a scoreline for every fixture and then allocates fantasy points per the official FIFA World Cup Fantasy scoring table (goals, assists, clean sheets, saves, yellow/red cards, minutes played).</li>
<li><b>Per-player summaries</b> — across all simulations we compute expected points (mean), captain EV (2× mean), ceiling (85th-percentile outcome), and value (expected points per £m of price).</li>
</ul>

<h2>Transparency and machine readability</h2>
<p>Every figure on this site is machine-readable. The full dataset for each article is available as a JSON file — links appear at the bottom of each article page. An index of the latest round's articles is at <a href="/api/latest.json" style="color:var(--greend)">/api/latest.json</a>.</p>
<p>LLM-friendly context is published at <a href="/llms.txt" style="color:var(--greend)">/llms.txt</a>. Attribution to evmax is requested when republishing figures.</p>

<h2>Independence &amp; disclaimer</h2>
<p>evmax is an independent statistical-analysis project. It is <b>not affiliated with,
endorsed by, or connected to FIFA</b>, any football federation, league, club, or fantasy
game operator. Player and team names appear in a purely descriptive, informational
context, as in any statistics publication.</p>
<p>Every number on this site is our own model output — Monte-Carlo simulations computed
from publicly available market information. We do not republish any third-party data
feed. Projections are estimates, not promises: they carry no guarantee of accuracy, and
nothing here is betting or financial advice. If you bet, you must be of legal gambling
age in your jurisdiction — please gamble responsibly.</p>
<p>Our outputs are licensed <a href="https://creativecommons.org/licenses/by/4.0/"
style="color:var(--greend)">CC BY 4.0</a>: reuse them freely, with attribution to evmax.</p>

<h2>Coming soon</h2>
<div class="chip-row">
<span class="chip">Build-a-team tool</span>
<span class="chip">Substitution analysis</span>
</div>
<p>We are building interactive tools to help you construct an optimised squad within the budget constraint and to evaluate the expected value of substitution patterns. These will appear in the nav when ready.</p>
</div>
</div>
{_footer_html()}</body></html>"""

def privacy_page():
    """Privacy notice: static site, zero cookies, zero third-party requests."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Privacy | {BRAND_SUFFIX}</title>
<meta name="description" content="evmax sets no cookies, runs no analytics or trackers, and makes no third-party requests. What little processing exists is described here.">
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}
.legal h2{{font-size:16px;font-weight:700;margin:28px 0 8px}}
.legal p{{font-family:var(--serif);font-size:17px;line-height:1.6;color:#23201a;margin-bottom:12px;max-width:72ch}}
</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html()}
</div></header>
<div class="wrap legal" style="padding-bottom:40px">
<div class="pagelabel">Privacy notice</div>
<h1 style="font-size:clamp(26px,4vw,38px);font-weight:800">Privacy</h1>
<h2>The short version</h2>
<p>This site sets <b>no cookies</b>, runs <b>no analytics or trackers</b>, requires no
account, and makes <b>no third-party requests when you load a page</b> — the optional
newsletter form sends data only if you submit it. Fonts and all assets are served from
this domain. We do not collect, store, or process any personal data ourselves beyond
that optional, user-initiated form. That is why there is no cookie banner: there is
nothing to consent to.</p>
<h2>Newsletter (optional)</h2>
<p>If you submit the newsletter form, your email address is sent directly to
<b>Buttondown, Inc.</b>, our newsletter processor, solely to deliver the round-by-round
emails you signed up for. Subscribing is double opt-in — you'll get a confirmation
email before anything else is sent — and every email includes an unsubscribe link. The
form itself is a plain HTML submission: no JavaScript runs, and no request to
Buttondown happens unless you deliberately click subscribe. The site itself still sets
no cookies and makes no page-load third-party requests. See
<a href="https://buttondown.com/legal/privacy" style="color:var(--greend)">Buttondown's
privacy policy</a> for how they handle subscriber data.</p>
<h2>Hosting</h2>
<p>The site is served as static files via Cloudflare Pages (Cloudflare, Inc.), which —
like any web host — technically processes visitor IP addresses in transit to deliver
pages and protect against abuse. Cloudflare acts as a hosting provider/CDN; see
<a href="https://www.cloudflare.com/privacypolicy/" style="color:var(--greend)">Cloudflare's
privacy policy</a>. We do not receive or retain this data.</p>
<h2>External links</h2>
<p>Articles may link to external sites; their privacy practices are their own.</p>
<h2>Changes &amp; contact</h2>
<p>If our practices ever change further, this page will describe exactly what is
collected and why, before it happens.</p>
</div>
{_footer_html()}</body></html>"""

def _utility_page(title, kicker, heading, body_html, active=None):
    """Small editorial utility page (thanks/confirmed) — noindex, footer, nav."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{title} | {BRAND_SUFFIX}</title>
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html(active)}
</div></header>
<div class="wrap" style="padding-bottom:40px">
<div class="pagelabel">{kicker}</div>
<h1 style="font-size:clamp(26px,4vw,38px);font-weight:800">{heading}</h1>
<div class="prose" style="max-width:640px;margin-top:14px">{body_html}</div>
</div>
{_footer_html()}</body></html>"""


def thanks_page():
    """Post-submit landing: explain the double opt-in step."""
    return _utility_page(
        "Almost there", "Newsletter", "One click to go — check your inbox.",
        "<p>We just sent you a confirmation email. Click the link inside and "
        "you're subscribed — that's the double opt-in we promised, so nobody can "
        "sign you up against your will.</p>"
        "<p>No email within a few minutes? Check spam, or just "
        "<a href='/' style='color:var(--greend)'>head back to the picks</a>.</p>")


def confirmed_page():
    """Post-confirmation landing: welcome aboard."""
    return _utility_page(
        "Subscribed", "Newsletter", "You're in.",
        "<p>From the next round on, the sims land in your inbox before lock — "
        "captains, expected points and match predictions, all graded publicly on our "
        "<a href='/track-record/' style='color:var(--greend)'>track record</a> page.</p>"
        "<p><a href='/' style='color:var(--greend)'>Back to this round's picks →</a></p>")


