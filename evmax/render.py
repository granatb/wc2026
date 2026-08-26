"""Pure emitters for the evmax static site (HTML/SVG/JSON/text). No I/O."""

import html as _html
import json as _json

SITE_URL = "https://evmax.ai"
BRAND_SUFFIX = "evmax — fantasy football simulations"
# <title> suffix: Bing flags titles over ~65 chars ("Title too long" SEO error,
# 07-06); the descriptive brand phrase lives in descriptions/schema instead.
TITLE_BRAND = "evmax"
GSC_META_TAG = (
    '<meta name="google-site-verification" '
    'content="TSaQglsr4AcaNMorvb7CgaHcSLkNhdt4xiaawRluLkQ" />')
# Our model outputs are licensed CC BY 4.0: anyone (humans or AI systems) may reuse
# the numbers WITH attribution to evmax — reuse-with-credit is the growth strategy,
# and a formal license both invites it and satisfies schema.org Dataset validation.
DATA_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
DATA_LICENSE_TEXT = ("CC BY 4.0 — free to reuse with attribution to evmax "
                     "(https://evmax.ai)")

# Favicons + mobile theme color, on every page. Google Search needs a raster icon
# of AT LEAST 48px (multiples of 48 preferred) declared via rel="icon" -- its
# favicon pipeline often skips SVG, and a 32px-only PNG gets you the generic globe
# in results. So: 192px PNG first for Google, SVG for modern browsers, 32px + 180px
# for legacy/Apple-touch.
_HEAD_COMMON = (
    '<link rel="icon" href="/brand/icon-192.png" type="image/png" sizes="192x192">'
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


def organization_ld() -> str:
    """The Organization entity, as a JSON-LD string, for every page that claims it.

    Entity disambiguation. "evmax" collides with established EV-charger brands
    (competitor landscape, 2026-07-03): a bare "evmax" search returns none of our
    pages, while "evmax fantasy" returns our top three. That is an entity problem,
    not an indexing one — search engines have nothing tying the string to this
    project rather than to a charging network.

    `sameAs` is the primary reconciliation signal: only list profiles we actually
    control and that resolve — a sameAs pointing somewhere that is not ours merges
    our entity into someone else's. Both entries were verified 200 before adding.
    `alternateName` carries the qualified forms we want to own; `knowsAbout`
    separates a fantasy football project from a charger brand topically. Shared by
    the landing page and /about/ via one `@id`, so the two pages assert ONE entity.
    `TITLE_BRAND` is deliberately untouched — shared with the WC pages (pinned by
    tests/test_site_render.py) and the landing title already sits near Bing's
    ~65-character limit.
    """
    return _json.dumps({
        "@context": "https://schema.org", "@type": "Organization",
        "@id": SITE_URL + "/#organization",
        "name": "evmax",
        "alternateName": ["evmax fantasy", "evmax fantasy football simulations",
                          "evmax.ai"],
        "url": SITE_URL, "logo": SITE_URL + "/brand/icon-512.png",
        "description": ("Simulation-based fantasy football analysis — 50,000 "
                        "Monte-Carlo simulations per matchday, graded publicly."),
        "knowsAbout": ["Fantasy Premier League", "fantasy football",
                       "Monte-Carlo simulation", "football analytics"],
        "sameAs": ["https://buttondown.com/evmax",
                   "https://github.com/granatb/wc2026"],
    }).replace("</", "<\\/")



METHODOLOGY = ("Market odds (de-vigged) → Dixon-Coles scorelines → 50k Monte-Carlo "
               "simulations, scored on the official FIFA World Cup Fantasy points table.")
# Buttondown chosen for its static-site-friendly no-JS embed form: a plain HTML
# <form> POST, no client-side script, no cookies set by us. The account is
# registered separately from this codebase. This is a user-initiated POST only
# (fires when a visitor deliberately submits the form) — it does not run on page
# load, so it does not violate the site's zero-cookie / zero-JS / zero-third-party-
# on-load compliance posture. Disclosed to visitors in /privacy/.
NEWSLETTER_ACTION = "https://buttondown.com/api/emails/embed-subscribe/evmax"


# One-line reader-facing ceiling definitions, reused in figcaptions and the
# article footer so the stat is never a bare unexplained number. The two
# sections compute DIFFERENT statistics and each must say what its own is:
#   WC:  the 85th percentile of the per-sim totals (games/fifa/model.
#        ceiling_points) — the historical text, pinned byte-identical.
#   FPL: the tail MEAN — the average of the best 15% of sims (games/fpl/model.
#        tail_mean), strictly >= the p85 — so percentile wording would
#        misstate it (review 2026-08-19, finding 6).
CEILING_EXPLAINER = (
    "Ceiling = the 85th-percentile outcome across our 50,000 simulations — "
    "the score when a player's best realistic game happens, not a fantasy cap.")
FPL_CEILING_EXPLAINER = (
    "Ceiling = the average of a player's best 15% of our 50,000 simulations — "
    "the score when his best realistic games happen, not a fantasy cap.")


class Section:
    """A URL namespace and its reader-facing vocabulary.

    The site serves two competitions from one renderer. Rather than fork the page
    functions (or do the September templating refactor early), each function takes
    a Section and defaults to WC, so every existing call site keeps producing
    byte-identical HTML.

    unit_abbr is the round-switcher pill label: "R5" for the World Cup, "GW5" for
    FPL. table_label names the official points table in reader-facing copy,
    methodology is the one-line method string pages print, and
    ceiling_explainer defines the section's own ceiling statistic — all default
    to the World Cup wording, which is what every existing page pins.
    """

    def __init__(self, key, label, unit, unit_abbr, base, api_base,
                 table_label=None, methodology=None, ceiling_explainer=None):
        self.key = key                # "round" | "fpl"
        self.label = label            # "World Cup Fantasy" | "Fantasy Premier League"
        self.unit = unit              # "Round" | "Gameweek"
        self.unit_abbr = unit_abbr    # "R" | "GW"
        self.base = base              # "/round/{r}" | "/fpl/gw{r}"
        self.api_base = api_base      # "/api/round/{r}" | "/api/fpl/gw{r}"
        self.table_label = table_label or "FIFA World Cup Fantasy"
        self.methodology = methodology or METHODOLOGY
        self.ceiling_explainer = ceiling_explainer or CEILING_EXPLAINER

    def landing_path(self, n):
        return self.base.format(r=n) + "/"

    def article_path(self, n, slug):
        return f"{self.base.format(r=n)}/{slug}/"

    def md_path(self, n, slug):
        return f"{self.base.format(r=n)}/{slug}.md"

    def json_path(self, n, slug):
        return f"{self.api_base.format(r=n)}/{slug}.json"

    def players_json_path(self, n):
        return f"{self.api_base.format(r=n)}/players.json"

    def kicker(self, n):
        return f"{self.unit} {n}"

    def switcher_base(self):
        return self.base + "/"


WC = Section("round", "World Cup Fantasy", "Round", "R",
             "/round/{r}", "/api/round/{r}")
FPL = Section("fpl", "Fantasy Premier League", "Gameweek", "GW",
              "/fpl/gw{r}", "/api/fpl/gw{r}",
              table_label="Fantasy Premier League",
              methodology=("Market odds (de-vigged) → Dixon-Coles scorelines → "
                           "50k Monte-Carlo simulations, scored on the official "
                           "Fantasy Premier League points table."),
              ceiling_explainer=FPL_CEILING_EXPLAINER)


def article_json(competition, fantasy_round, article, title, generated_at, sims, entries,
                 extra_fields=None, section=WC):
    """extra_fields: optional dict merged into the envelope as additional top-level
    keys (e.g. wildcard's {"squad": {...}} meta). Never overrides the standard keys.

    The unit key is named for the section — "round" for the World Cup, "gameweek"
    for FPL — because a consumer reading `"round": 1` off an FPL feed would
    reasonably think it meant a knockout round."""
    unit_key = "round" if section.key == "round" else "gameweek"
    env = {
        "competition": competition,
        unit_key: fantasy_round,
        "article": article,
        "title": title,
        "generated_at": generated_at,
        "sims": sims,
        "methodology": section.methodology,
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
    if article in ("our-squad", "consensus-squad"):
        # entries are squad_article's 15 in state order; the summary quotes the
        # duel-strip number (XI total with the captain doubled).
        from evmax.articles import formation_of
        xi = [e for e in entries if e.get("role") == "XI"] or entries[:11]
        cap = next((e for e in xi if e.get("is_captain")), xi[0])
        total = round(sum(e.get("x_points") or 0.0 for e in xi)
                      + (cap.get("x_points") or 0.0), 2)
        whose = "Our" if article == "our-squad" else "The expert-consensus"
        return (f"{whose} {formation_of(xi)} this gameweek: "
                f"{cap.get('name', '?')} captains, {total} projected points "
                f"with the armband doubled.")
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
    # FPL-only slugs (no World Cup article shares these names). The ticker's
    # rows are CLUBS with no x_points at all, so the generic fallback below
    # would KeyError; defcon's headline number is a probability, not points.
    if article == "ticker":
        return (f"{name} lead the fixture ticker at "
                f"{(top.get('exp_clean_sheets') or 0.0):.2f} expected clean sheets.")
    if article == "defcon":
        return (f"{name} ({team}) hits the defensive-contribution threshold in "
                f"{(top.get('p_defcon') or 0.0) * 100:.0f}% of simulations.")
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
              "top_def": "Best DEF", "top_gk": "Best GK",
              # FPL columns (spec §8): reader-facing labels so table headers and
              # landing stat labels never print a raw key.
              "p_defcon": "P(DefCon)", "defcon": "DefCon pts", "cs_points": "CS pts",
              "exp_clean_sheets": "Clean sheets", "fixtures": "Fixtures",
              "basis": "Basis", "bonus": "Bonus"}

# Columns whose value is already a display-ready string (not a number to format).
_STRING_COLS = {"top_def", "top_gk", "basis", "opponents"}


def _fmt(col, row):
    v = row.get(col)
    if v is None:
        return "—"
    if col in _STRING_COLS:
        return str(v)
    if col in ("ownership_pct", "p_advance"):
        return f"{v:.1f}%"
    if col in ("p_clean_sheet", "p_defcon"):
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
    ".wrap{max-width:1140px;margin:0 auto;padding:0 28px}"
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
    # hero-actions: the CTA + round switcher above the fold on the landing page.
    ".hero-actions{display:flex;align-items:center;justify-content:space-between;"
    "gap:16px;flex-wrap:wrap;margin-bottom:22px}"
    ".rate-cta{display:inline-flex;align-items:center;gap:8px;font-family:var(--sans);"
    "font-size:15px;font-weight:800;color:#fff;background:var(--green);"
    "padding:12px 22px;border-radius:10px;white-space:nowrap}"
    ".rate-cta:hover{background:var(--greend)}"
    ".rate-cta .arrow{transition:transform .15s}"
    ".rate-cta:hover .arrow{transform:translateX(3px)}"
    # round-switcher: pill row of every built round, also used (smaller) at the
    # top of article pages so old rounds stay reachable once the feed moves on.
    ".round-switcher{display:flex;align-items:center;gap:6px;flex-wrap:wrap}"
    ".round-switcher .rs-label{font-size:11px;font-weight:700;letter-spacing:1px;"
    "text-transform:uppercase;color:var(--ink3);margin-right:2px}"
    ".round-tab{font-family:var(--sans);font-size:13px;font-weight:700;color:var(--ink2);"
    "background:var(--chipbg);border:1px solid var(--line);border-radius:20px;"
    "padding:5px 13px}"
    ".round-tab:hover{border-color:var(--green);color:var(--greend)}"
    ".round-tab.active{background:var(--green);border-color:var(--green);color:#fff}"
    ".art .round-switcher{margin:2px 0 14px}"
    # live-xi: the mid-round "our published XI" strip on the landing page --
    # two rows (so-far / full-round target) on a shared 5-column grid so the
    # expected and ceiling figures line up vertically between the rows.
    # .lx-stats is display:contents so its three .lx-stat spans participate
    # in the row grid directly.
    ".live-xi{display:flex;flex-direction:column;gap:8px;"
    "background:var(--surf);border:1px solid var(--line);border-radius:12px;"
    "padding:12px 18px;margin-bottom:22px;font-size:13.5px}"
    ".live-xi .lx-row{display:grid;grid-template-columns:1fr 92px 176px 106px 62px;"
    "align-items:baseline;gap:12px}"
    ".live-xi .lx-target{border-top:1px dashed var(--line);padding-top:8px;font-size:12.5px}"
    ".live-xi .lx-label{font-weight:700;color:var(--ink2);display:flex;align-items:baseline;gap:8px}"
    ".live-xi .lx-target .lx-label{font-weight:600;color:var(--ink3)}"
    ".live-xi .lx-stats{display:contents}"
    ".live-xi .lx-stat{color:var(--ink3);white-space:nowrap;text-align:right}"
    ".live-xi .lx-stat b{font-size:17px;color:var(--ink);font-variant-numeric:tabular-nums}"
    ".live-xi .lx-diff{font-size:12px;padding:1px 7px;border-radius:10px;margin-left:2px}"
    ".live-xi .lx-diff.up{color:var(--greend);background:#eaf5ee}"
    ".live-xi .lx-diff.down{color:#a8331c;background:#fdeee9}"
    ".live-xi .lx-link{font-weight:600;color:var(--green);font-size:13px;"
    "white-space:nowrap;text-align:right}"
    "@media(max-width:760px){.live-xi .lx-row{display:flex;flex-wrap:wrap;gap:6px 14px}"
    ".live-xi .lx-stats{display:flex;gap:14px;flex-wrap:wrap}"
    ".live-xi .lx-stat{text-align:left}}"
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
    ".fig{max-width:560px;margin:20px auto;background:var(--surf);border:1px solid var(--line);"
    "border-radius:16px;padding:18px;display:flex;flex-direction:column;align-items:center}"
    ".fig.fig-pitch{max-width:420px}"
    "figcaption{font-size:12px;color:var(--ink3);text-align:center;margin-top:8px;line-height:1.5}"
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
    # Footer: the two disclaimer paragraphs sit side by side filling the wrap
    # (a lone 76ch column looked stranded/misaligned on wide screens); the
    # license/links line spans the full width beneath them.
    ".sitefoot{border-top:1px solid var(--line);margin-top:56px;padding:26px 0 40px;background:var(--surf)}"
    ".sitefoot .wrap{display:grid;grid-template-columns:1fr 1fr;gap:8px 48px;align-items:start}"
    ".sitefoot p{font-size:12.5px;color:var(--ink3);line-height:1.65;margin-bottom:10px}"
    ".sitefoot p:last-child{grid-column:1/-1;border-top:1px solid var(--line);"
    "padding-top:14px;margin-top:6px;margin-bottom:0}"
    ".sitefoot a{color:var(--greend);text-decoration:underline}"
    "@media(max-width:760px){.sitefoot .wrap{grid-template-columns:1fr}}"
    ".pitch-mini{width:200px}"
    ".landing-grid{display:grid;grid-template-columns:1fr 320px;gap:48px;"
    "grid-template-areas:\"feat rail\" \"feed rail\";align-items:start}"
    ".landing-grid .feat-area{grid-area:feat}"
    ".landing-grid .feed-area{grid-area:feed}"
    ".landing-grid .rail{grid-area:rail}"
    ".rail{position:sticky;top:80px;align-self:start;background:var(--surf);"
    "border:1px solid var(--line);border-radius:14px;padding:14px 16px}"
    ".rail .pagelabel{margin:0 0 12px;font-size:11px}"
    ".rail-toggle{display:none}"
    ".rail-fold-label{display:none}"
    ".qp-row{display:flex;align-items:baseline;justify-content:space-between;gap:10px;padding:10px 0;border-bottom:1px solid var(--line)}"
    ".qp-row:hover .qp-name{color:var(--green)}"
    ".qp-label{font-size:10.5px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--ink3);min-width:86px}"
    ".qp-name{font-weight:700;font-size:14px;flex:1}"
    ".qp-stat{font-size:12px;font-weight:700;color:var(--greend);white-space:nowrap}"
    ".rail-row{padding:12px 0;border-bottom:1px solid var(--line)}"
    ".rail-row:last-of-type{border-bottom:0}"
    ".rail-row-top{display:flex;align-items:baseline;justify-content:space-between;gap:8px;"
    "margin-bottom:6px}"
    ".rail-teams{font-size:14px;font-weight:700;letter-spacing:-.2px}"
    ".rail-ko{font-size:11px;color:var(--ink3);white-space:nowrap;text-align:right}"
    ".rail-score{font-size:18px;font-weight:800;color:var(--ink)}"
    ".rail-final-line{display:flex;align-items:center;gap:8px;margin-bottom:6px}"
    ".rail-meta{font-size:11px;color:var(--ink3);margin-top:6px}"
    ".rail-link{display:block;margin-top:14px;font-size:13px;font-weight:600;color:var(--green)}"
    "@media(max-width:900px){"
    ".landing-grid{grid-template-columns:1fr;grid-template-areas:\"feat\" \"rail\" \"feed\"}"
    ".landing-grid .rail{position:static}"
    ".rail-fold-label{display:flex;align-items:center;justify-content:space-between;"
    "background:var(--surf);border:1px solid var(--line);border-radius:14px;"
    "padding:14px 18px;font-size:13px;font-weight:700;color:var(--ink);cursor:pointer}"
    ".rail-fold-label::after{content:'\\25be';font-size:14px;color:var(--ink3);"
    "transition:transform .15s}"
    ".rail-toggle:checked ~ .rail-fold-label::after{transform:rotate(180deg)}"
    ".rail-content{display:none;margin-top:10px}"
    ".rail-toggle:checked ~ .rail-content{display:block}"
    "}"
    "@media(max-width:760px){"
    ".feat{grid-template-columns:1fr;gap:20px}"
    ".feed{grid-template-columns:1fr}"
    ".pitch-mini{width:100%;max-width:240px;margin:0 auto}"
    "}"
)


# Mobile nav-overflow fix: _STYLE's header nav (five pills, min-content
# ~370px after the logo) forces the whole BODY to scroll sideways below
# ~460px viewports (repro 2026-08-25 at 420px) — the duel strip, hero
# headline and stand all read as cut off at the right edge. The nav becomes
# its own scroll container instead. Additive and FPL-only, because _STYLE is
# embedded byte-for-byte in frozen published pages: injected on the FPL
# landing (extra_style chain, fpl_build) and the FPL /rate/ page (pitch_css).
_NAV_SCROLL_CSS = (
    "@media(max-width:760px){"
    "nav{overflow-x:auto;min-width:0;scrollbar-width:none}"
    "nav::-webkit-scrollbar{display:none}"
    "nav a{white-space:nowrap}"
    "}"
)


def _nav_html(active=None):
    """Fixed site nav, identical on every page.
    active ∈ {'home','about','track-record','rate',None}."""
    home_cls = ' class="on"' if active == "home" else ""
    track_cls = ' class="on"' if active == "track-record" else ""
    rate_cls = ' class="on"' if active == "rate" else ""
    about_cls = ' class="on"' if active == "about" else ""
    items = [
        f'<a href="/"{home_cls}>Home</a>',
        f'<a href="/track-record/"{track_cls}>Track record</a>',
        f'<a href="/rate/"{rate_cls}>Rate my team</a>',
        '<a class="soon">Analyse a sub</a>',
        f'<a href="/about/"{about_cls}>About</a>',
    ]
    return "<nav>" + "".join(items) + "</nav>"


def _round_switcher_html(available_rounds, current_round, base_path="/round/{r}/",
                         abbr="R"):
    """Pill row of every round that's actually been built (see build.py's
    available_rounds -- computed from what's on disk, so this never links to
    a round that doesn't exist). Without this, older rounds are still live
    (build() never overwrites a prior round's pages) but undiscoverable once
    the landing page moves on -- this is the only on-page way back to them."""
    if not available_rounds or len(available_rounds) <= 1:
        return ""
    tabs = "".join(
        f'<a class="round-tab{" active" if r == current_round else ""}" '
        f'href="{base_path.format(r=r)}">{abbr}{r}</a>'
        for r in available_rounds
    )
    label = "Rounds" if abbr == "R" else "Gameweeks"
    return f'<div class="round-switcher"><span class="rs-label">{label}</span>{tabs}</div>'


def _rate_cta_html():
    return ('<a class="rate-cta" href="/rate/">Rate my team <span class="arrow">&rarr;</span></a>')


def _live_xi_html(live_xi: dict, round_no: int, section=WC) -> str:
    """Mid-round strip: how the round's PUBLISHED XI (frozen at lock) is doing
    so far -- realized official points vs what those already-played players
    were expected to score, vs their combined ceiling. The articles themselves
    stay frozen; this is one of the site's few deliberately-live reality
    panels (matches scoreboard, track record, this strip)."""
    if not live_xi:
        return ""
    realized, expected = live_xi["realized"], live_xi["expected"]
    diff = realized - expected
    diff_cls = "up" if diff >= 0 else "down"
    diff_str = f"{'+' if diff >= 0 else '−'}{abs(diff):.1f}"
    done = live_xi["played"] >= live_xi["total"]
    badge = ('<span class="mx-badge final">Final</span>' if done
             else '<span class="live-tag">Live</span>')
    label = ("Our XI — round complete" if done
             else f'Our XI so far · {live_xi["played"]}/{live_xi["total"]} played')
    so_far_row = (
        f'<div class="lx-row">'
        f'<span class="lx-label">{badge} {label}</span>'
        f'<span class="lx-stats">'
        f'<span class="lx-stat"><b>{realized:.0f}</b> scored</span>'
        f'<span class="lx-stat">{expected:.1f} expected '
        f'<b class="lx-diff {diff_cls}">{diff_str}</b></span>'
        f'<span class="lx-stat">{live_xi["ceiling"]:.1f} ceiling</span>'
        f'</span>'
        f'<a class="lx-link" href="{section.article_path(round_no, "wildcard")}">The XI &rarr;</a>'
        f'</div>'
    )
    # second row: what the full XI is aiming for by the end of the round --
    # only meaningful while games remain; once everyone has played, the
    # so-far row IS the round total and this would just repeat it.
    target_row = ""
    if live_xi["played"] < live_xi["total"] and live_xi.get("expected_total") is not None:
        target_row = (
            f'<div class="lx-row lx-target">'
            f'<span class="lx-label">Full-round target · all {live_xi["total"]}</span>'
            f'<span class="lx-stats">'
            f'<span class="lx-stat">&nbsp;</span>'
            f'<span class="lx-stat">{live_xi["expected_total"]:.1f} expected</span>'
            f'<span class="lx-stat">{live_xi["ceiling_total"]:.1f} ceiling</span>'
            f'</span>'
            f'<span class="lx-link">&nbsp;</span>'
            f'</div>'
        )
    return f'<div class="live-xi">{so_far_row}{target_row}</div>'



def _footer_html():
    """Site-wide footer: legal disclaimer + privacy/about links, on every page."""
    return (
        '<footer class="sitefoot"><div class="wrap">'
        # One unbreakable clause: "with no affiliation to FIFA" -- never a sentence
        # boundary between "project" and the entity list. Google's snippet builder
        # once truncated the old wording ("...project. It is not affiliated with,
        # endorsed by, or connected to FIFA...") into "...project. connected to
        # FIFA..." -- the disclaimer INVERTED in search results.
        '<p><b>evmax</b> is an independent, unofficial statistical-analysis project '
        'with no affiliation to FIFA, any football federation, league, club, or '
        'fantasy game operator. All player and team names are used in a purely '
        'descriptive, informational context.</p>'
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


_NAME_SUFFIXES = {"Jr", "Jr.", "Sr", "Sr.", "II", "III"}


def _pitch_label(name: str) -> str:
    """Player label for a pitch node: the surname, with trailing generational
    suffixes ("Jr", "Sr", "II", "III") dropped first so "Vinicius Jr" reads as
    "Vinicius" rather than "Jr" -- the suffix strip takes priority over the
    short-name rule below, since "Jr" alone is never a usable label. Short
    full names (<=11 chars, after any suffix strip) are shown in full instead
    of being truncated to a single token."""
    tokens = name.split()
    while len(tokens) > 1 and tokens[-1] in _NAME_SUFFIXES:
        tokens = tokens[:-1]
    remaining = " ".join(tokens) if tokens else name
    if len(remaining) <= 11:
        return remaining
    return tokens[-1] if tokens else name


def pitch_svg(xi_entries):
    """SVG football pitch placing an XI by position lines. Captain (rank 1) is
    flagged. Node = small circle with xPts inside; the player's name sits
    below the node (on the grass), not crammed inside a giant circle."""
    from evmax.articles import formation_of  # lazy to avoid circular at module level
    xi = list(xi_entries)
    if not xi:
        return '<svg viewBox="0 0 360 460" xmlns="http://www.w3.org/2000/svg"/>'
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

    # Pitch dimensions. Row spacing must clear: node radius (14) + gap to name
    # baseline + name text height (~12px) + >=18px gap before the next row's
    # node top, so name labels never collide with the row below.
    W, H = 360, 460
    NODE_R = 14
    NAME_DY = 12 + 6  # name baseline offset below node centre (text height + pad)
    ROW_GAP = 14 + NAME_DY + 18  # node radius + name + minimum clear gap
    row_y = {"FWD": 62, "MID": 62 + ROW_GAP, "DEF": 62 + 2 * ROW_GAP, "GK": 62 + 3 * ROW_GAP}

    # Squad-article entries carry an explicit captain flag (the armband is a
    # state decision, not the top projection); everything else keeps the
    # rank-1/first-entry rule, so existing WC pitches render byte-identically.
    has_cap_flag = any("is_captain" in e for e in xi)

    def _row_nodes(players, y):
        if not players:
            return ""
        n = len(players)
        nodes = []
        for i, p in enumerate(players):
            x = W * (i + 1) / (n + 1)
            label = _html.escape(_pitch_label(p["name"]))
            xpts = p.get("x_points", 0.0)
            if has_cap_flag:
                is_captain = bool(p.get("is_captain"))
            else:
                is_captain = (p.get("rank") == 1) or (xi and p is xi[0])
            cap_badge = ""
            if is_captain:
                # 8px-radius badge at the node's top-right; offset far enough
                # (dx=12, dy=-12 from a r=14 node) that it clears both the
                # node circle and the name label below without overlap.
                bx, by = x + 12, y - 12
                cap_badge = (f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="8" fill="#e8482b"/>'
                             f'<text x="{bx:.1f}" y="{by + 2.8:.1f}" text-anchor="middle" '
                             f'font-size="8" font-weight="700" fill="#fff">C</text>')
            nodes.append(
                f'<circle cx="{x:.1f}" cy="{y}" r="{NODE_R}" fill="#fbfaf7" '
                f'stroke="var(--greend)" stroke-width="1.5"/>'
                f'<text x="{x:.1f}" y="{y + 4}" text-anchor="middle" '
                f'font-size="11" font-weight="700" fill="#15140f">{xpts:.1f}</text>'
                f'<text x="{x:.1f}" y="{y + NAME_DY:.1f}" text-anchor="middle" '
                f'font-size="11.5" font-weight="600" fill="#f2f8f4">{label}</text>'
                + cap_badge
            )
        return "".join(nodes)

    # Pitch grass + markings, subtler (opacity .35) than the old .3/.4 mix.
    pitch_bg = (
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#1a7a3c" rx="6"/>'
        f'<rect x="10" y="10" width="{W-20}" height="{H-20}" fill="none" stroke="#fff" '
        f'stroke-width="1" opacity=".35" rx="3"/>'
        # centre line
        f'<line x1="10" y1="{H//2}" x2="{W-10}" y2="{H//2}" '
        f'stroke="#fff" stroke-width=".8" opacity=".35"/>'
        # centre circle
        f'<circle cx="{W//2}" cy="{H//2}" r="36" fill="none" stroke="#fff" '
        f'stroke-width=".8" opacity=".35"/>'
    )

    nodes_svg = (
        _row_nodes(fwds, row_y["FWD"])
        + _row_nodes(mids, row_y["MID"])
        + _row_nodes(defs, row_y["DEF"])
        + _row_nodes(gks, row_y["GK"])
    )

    formation = formation_of(xi)
    formation_label = (
        f'<text x="{W//2}" y="{H-8}" text-anchor="middle" '
        f'font-size="11" font-weight="600" fill="#fff" opacity=".7">{formation}</text>'
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="XI pitch">'
        f'<g font-family="\'Hanken Grotesk\',sans-serif">'
        f'{pitch_bg}{nodes_svg}{formation_label}'
        f'</g></svg>'
    )


def pitch_svg_fpl(xi_entries):
    """The FPL squad pitch: an attacking HALF-pitch, so four rows fill the canvas.

    Differences from the shared pitch_svg (which WC pages pin byte-identically and
    therefore must not change): halfway line + centre arc at the top, penalty box,
    D and goal mouth at the bottom, mow-stripe grass, and a three-part player node
    — xPts disc, solid name pill below it (names never sit raw on the grass), club
    letters under the pill. Captain wears an armband-style badge on the disc; a
    vice badge renders only when the entry carries is_vice.
    """
    from evmax.articles import formation_of  # lazy to avoid circular at module level
    xi = list(xi_entries)
    if not xi:
        return '<svg viewBox="0 0 420 520" xmlns="http://www.w3.org/2000/svg"/>'
    gks = [e for e in xi if e.get("position") == "GK"]
    defs = [e for e in xi if e.get("position") == "DEF"]
    mids = [e for e in xi if e.get("position") == "MID"]
    fwds = [e for e in xi if e.get("position") == "FWD"]
    placed = set(id(e) for e in gks + defs + mids + fwds)
    for e in xi:
        if id(e) not in placed:
            mids.append(e)

    W, H = 420, 520
    INSET = 14
    GRASS_A, GRASS_B = "#2e7e4c", "#338755"
    LINE = 'stroke="#fff" stroke-width="1.2" opacity=".4" fill="none"'
    INK, PAPER, GREEND = "#15140f", "#fbfaf7", "#0a4f2d"

    row_y = {"FWD": 96, "MID": 208, "DEF": 318, "GK": 424}
    has_cap_flag = any("is_captain" in e for e in xi)

    def _pill_w(text):
        return max(46, round(len(text) * 6.4 + 14))

    def _row_nodes(players, y):
        if not players:
            return ""
        n = len(players)
        nodes = []
        for i, p in enumerate(players):
            x = W * (i + 1) / (n + 1)
            label = _html.escape(_pitch_label(p["name"]))
            club = _html.escape(str(p.get("team") or ""))
            xpts = p.get("x_points", 0.0)
            if has_cap_flag:
                is_captain = bool(p.get("is_captain"))
            else:
                is_captain = (p.get("rank") == 1) or (xi and p is xi[0])
            is_vice = bool(p.get("is_vice"))
            ring = GREEND if is_captain else "rgba(10,79,45,.55)"
            ring_w = 2.5 if is_captain else 1.6
            badge = ""
            if is_captain:
                bx, by = x + 14, y - 13
                badge = (f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="9" fill="{GREEND}" '
                         f'stroke="{PAPER}" stroke-width="1.5"/>'
                         f'<text x="{bx:.1f}" y="{by + 3.2:.1f}" text-anchor="middle" '
                         f'font-size="9.5" font-weight="800" fill="#fff">C</text>')
            elif is_vice:
                bx, by = x + 14, y - 13
                badge = (f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="9" fill="{PAPER}" '
                         f'stroke="{GREEND}" stroke-width="1.5"/>'
                         f'<text x="{bx:.1f}" y="{by + 3.2:.1f}" text-anchor="middle" '
                         f'font-size="9.5" font-weight="800" fill="{GREEND}">V</text>')
            pw = _pill_w(label)
            nodes.append(
                f'<circle cx="{x:.1f}" cy="{y}" r="17" fill="{PAPER}" '
                f'stroke="{ring}" stroke-width="{ring_w}"/>'
                f'<text x="{x:.1f}" y="{y + 4.5}" text-anchor="middle" '
                f'font-size="12.5" font-weight="800" fill="{INK}">{xpts:.1f}</text>'
                f'<rect x="{x - pw / 2:.1f}" y="{y + 23}" width="{pw}" height="18" '
                f'rx="9" fill="{PAPER}"/>'
                f'<text x="{x:.1f}" y="{y + 35.5}" text-anchor="middle" '
                f'font-size="10.5" font-weight="700" fill="{INK}">{label}</text>'
                + (f'<text x="{x:.1f}" y="{y + 54}" text-anchor="middle" '
                   f'font-size="8.5" font-weight="700" letter-spacing="1" '
                   f'fill="rgba(255,255,255,.75)">{club}</text>' if club else "")
                + badge
            )
        return "".join(nodes)

    stripes = "".join(
        f'<rect x="0" y="{i * H / 6:.1f}" width="{W}" height="{H / 6:.1f}" '
        f'fill="{GRASS_A if i % 2 == 0 else GRASS_B}"/>' for i in range(6))
    L, R = INSET, W - INSET
    B = H - INSET
    box_w, box_h = 212, 74
    six_w, six_h = 100, 30
    pitch = (
        f'<defs><clipPath id="pitchclip"><rect x="0" y="0" width="{W}" height="{H}" rx="10"/>'
        f'</clipPath></defs>'
        f'<g clip-path="url(#pitchclip)">{stripes}</g>'
        # boundary: halfway line is the TOP edge of this half
        f'<rect x="{L}" y="{INSET}" width="{R - L}" height="{B - INSET}" rx="2" {LINE}/>'
        # centre arc bulging down from the halfway line
        f'<path d="M {W / 2 - 42} {INSET} A 42 42 0 0 0 {W / 2 + 42} {INSET}" {LINE}/>'
        f'<circle cx="{W / 2}" cy="{INSET}" r="2.5" fill="#fff" opacity=".4"/>'
        # penalty box, six-yard box, spot, and the D
        f'<rect x="{W / 2 - box_w / 2}" y="{B - box_h}" width="{box_w}" height="{box_h}" {LINE}/>'
        f'<rect x="{W / 2 - six_w / 2}" y="{B - six_h}" width="{six_w}" height="{six_h}" {LINE}/>'
        f'<circle cx="{W / 2}" cy="{B - 50}" r="2.5" fill="#fff" opacity=".4"/>'
        f'<path d="M {W / 2 - 40} {B - box_h} A 44 44 0 0 1 {W / 2 + 40} {B - box_h}" {LINE}/>'
        # goal mouth
        f'<rect x="{W / 2 - 40}" y="{B}" width="80" height="6" {LINE}/>'
        # corner arcs
        f'<path d="M {L} {B - 12} A 12 12 0 0 0 {L + 12} {B}" {LINE}/>'
        f'<path d="M {R - 12} {B} A 12 12 0 0 0 {R} {B - 12}" {LINE}/>'
    )

    nodes_svg = (_row_nodes(fwds, row_y["FWD"]) + _row_nodes(mids, row_y["MID"])
                 + _row_nodes(defs, row_y["DEF"]) + _row_nodes(gks, row_y["GK"]))

    formation = formation_of(xi)
    chip_w = _pill_w(formation)
    formation_chip = (
        f'<rect x="{L + 8}" y="{INSET + 8}" width="{chip_w}" height="20" rx="10" '
        f'fill="{PAPER}"/>'
        f'<text x="{L + 8 + chip_w / 2:.1f}" y="{INSET + 22}" text-anchor="middle" '
        f'font-size="11" font-weight="800" fill="{GREEND}">{formation}</text>')

    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="XI pitch">'
        f'<g font-family="\'Hanken Grotesk\',sans-serif">'
        f'{pitch}{nodes_svg}{formation_chip}'
        f'</g></svg>'
    )


def ev_bar(entries, metric, width=360, row_h=30, max_rows=None,
          label_size=13, value_size=12, bar_h=15, reach_metric=None, reach_scale=1.0):
    """Horizontal bar viz (v2-styled). Top entry green, differentials red, others muted.

    max_rows: optional cap on the number of rows drawn (belt & braces alongside
    slicing at the call site) -- keeps a chart from growing unbounded when it's
    fed a long ranked list. None (default) draws every entry.

    label_size/value_size/bar_h: sizing knobs so the same emitter can serve two
    very different usages -- a bigger, easier-to-read featured chart on the
    landing page (row_h~40, label 15px, value 14px, bar 22px) and a denser
    in-article chart (defaults here).

    reach_metric/reach_scale: when set, the solid bar still encodes `metric`
    (the floor/EV), but a lighter "reach" segment extends it out to
    `reach_metric * reach_scale` (the ceiling) -- so every chart reads as
    "here's the safe floor, here's the boom scenario" at a glance, not just a
    single number. reach_scale=2.0 is for the captains chart, where the bar's
    own metric (captain_ev) is already 2x a single appearance, so the ceiling
    needs the same doubling to stay on the same scale. Only draws the reach
    segment where it's actually longer than the floor (a defender's model
    ceiling can dip at/below xPts -- see games/fifa/model.ceiling_points)."""
    entries = list(entries)
    if max_rows is not None:
        entries = entries[:max_rows]
    if not entries:
        return f'<svg viewBox="0 0 {width} 40" xmlns="http://www.w3.org/2000/svg"></svg>'
    reach_vals = [(e.get(reach_metric) or 0.0) * reach_scale for e in entries] if reach_metric else []
    vmax = max([e.get(metric) or 0.0 for e in entries] + reach_vals) or 1.0
    label_w, pad = 90, 6
    # "X.XX -> Y.YY" runs roughly twice as wide as a single "X.XX" value --
    # reserve more right-margin so the reach label never clips the viewBox
    # (SVG content past the viewBox edge is clipped, not wrapped).
    right_margin = 108 if reach_metric is not None else 58
    bar_max = width - label_w - right_margin
    height = row_h * len(entries) + 10
    bar_y_off = (row_h - bar_h) // 2
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
        text_y = y + bar_y_off + bar_h - (bar_h - label_size) / 2 - 2
        reach_rect = ""
        end_x = label_w + bw
        val_text = f"{val:.2f}"
        if reach_metric is not None:
            reach_val = (e.get(reach_metric) or 0.0) * reach_scale
            if reach_val > val:
                rw = max(0.0, bar_max * (reach_val / vmax) - bw)
                reach_rect = (
                    f'<rect x="{end_x:.1f}" y="{y + bar_y_off}" width="{rw:.1f}" '
                    f'height="{bar_h}" rx="3" fill="{bar_fill}" opacity="0.28"/>'
                )
                end_x += rw
                val_text = f"{val:.2f} → {reach_val:.2f}"
        rows.append(
            f'<text x="0" y="{text_y:.1f}" font-size="{label_size}" font-weight="700" '
            f'fill="{nm_fill}">{label}</text>'
            f'<rect x="{label_w}" y="{y + bar_y_off}" width="{bw:.1f}" height="{bar_h}" rx="3" '
            f'fill="{bar_fill}"/>'
            f'{reach_rect}'
            f'<text x="{end_x + 6:.1f}" y="{text_y:.1f}" font-size="{value_size}" '
            f'font-weight="700" fill="{val_fill}">{val_text}</text>'
        )
    _friendly = {"x_points": "xPts", "captain_ev": "captain EV", "ceiling": "ceiling"}
    floor_label = _friendly.get(metric, metric)
    reach_suffix = " (captained)" if reach_scale == 2.0 else ""
    legend = (
        f'<text x="{label_w}" y="{height - 2}" font-size="{max(9, label_size - 4)}" '
        f'fill="#8a8272">solid = {floor_label} · faint = ceiling upside{reach_suffix}</text>'
        if reach_metric is not None else ""
    )
    if legend:
        height += 16
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="{_html.escape(metric)} chart">'
        f'<g font-family="\'Hanken Grotesk\',sans-serif">'
        + "".join(rows) + legend +
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


# Max rows in the agent-facing Markdown twin's data table -- the JSON has the
# full list; the .md file is a readable content twin, not a full data dump.
_ARTICLE_MD_MAX_ROWS = 20

# matches entries have no player "name"/"team" -- these are the columns for the
# match-predictions table in the Markdown twin. fixtures (and everything else)
# use the generic `columns` path via _COL_LABEL/_fmt.
_MATCH_MD_COLUMNS = ["match", "kickoff", "top_scoreline", "p_home", "p_draw", "p_away"]
_MATCH_MD_LABELS = {"match": "Match", "kickoff": "Kickoff", "top_scoreline": "Top scoreline",
                    "p_home": "P(Home)", "p_draw": "P(Draw)", "p_away": "P(Away)",
                    "final_score": "Final score"}


def _escape_pipes(s) -> str:
    """Escape literal '|' characters so a value can't break a Markdown table row."""
    return str(s).replace("|", "\\|")


def _md_fmt(col, row):
    """Markdown-table cell formatter -- same value semantics as _fmt (HTML
    tables), but plain text (no HTML entity escaping) with pipes escaped."""
    if col == "match":
        return _escape_pipes(row.get("match", ""))
    if col == "kickoff":
        ko = row.get("kickoff") or ""
        return _escape_pipes(ko[:16].replace("T", " ") + " UTC") if ko else "—"
    if col in ("p_home", "p_draw", "p_away"):
        v = row.get(col)
        return f"{v * 100:.0f}%" if v is not None else "—"
    if col == "final_score":
        return _escape_pipes(row.get("final_score") or "—")
    v = row.get(col)
    if v is None:
        return "—"
    if col in _STRING_COLS:
        return _escape_pipes(v)
    if col in ("ownership_pct", "p_advance"):
        return f"{v:.1f}%"
    if col in ("p_clean_sheet", "p_defcon"):
        return f"{v * 100:.0f}%"
    if col == "price":
        return f"{v:.1f}"
    return f"{v:.2f}" if isinstance(v, float) else _escape_pipes(v)


def _article_md_table(article: str, entries: list, columns: list) -> str:
    """The 'The data' Markdown table for an article's .md twin.

    matches has no player rows (match/kickoff/odds columns instead, with an
    optional Final score column once fixtures complete); every other article
    (including fixtures, whose entries already carry team-shaped columns) uses
    the generic rank-table path: #, Player, Team, then the article's columns.
    """
    rows = entries[:_ARTICLE_MD_MAX_ROWS]
    if not rows:
        return "_No data available for this article._"

    if article == "matches":
        cols = list(_MATCH_MD_COLUMNS)
        if any(r.get("final_score") for r in rows):
            cols.append("final_score")
        header = "| " + " | ".join(_MATCH_MD_LABELS[c] for c in cols) + " |"
        sep = "|" + "|".join("---" for _ in cols) + "|"
        lines = [header, sep]
        for r in rows:
            lines.append("| " + " | ".join(_md_fmt(c, r) for c in cols) + " |")
        return "\n".join(lines)

    header_cells = ["#", "Player", "Team"] + [_COL_LABEL.get(c, c) for c in columns]
    header = "| " + " | ".join(header_cells) + " |"
    sep = "|" + "|".join("---" for _ in header_cells) + "|"
    lines = [header, sep]
    for r in rows:
        cells = [
            str(r.get("rank", "")),
            _escape_pipes(r.get("name", "")),
            _escape_pipes(r.get("team") or ""),
        ] + [_md_fmt(c, r) for c in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def article_md(round_no, slug, title, prose, entries, columns, generated_at,
               date_str, canonical_path, section=WC):
    """Content-only Markdown twin of an article, for AI agents (the llms.txt
    convention) -- purpose-built to replace paid edge markdown-conversion.

    canonical_path: the article's HTML path, e.g. "/round/5/captains/" -- used
    to build the "By the evmax model" byline URL and the API-JSON pointer.
    """
    headline = prose.get("headline", title)
    standfirst = prose.get("standfirst", "")
    body_md = prose.get("body_md", "")
    bottom_line = prose.get("bottom_line", "")
    table_md = _article_md_table(slug, entries, columns)
    json_url = f"{SITE_URL}{section.json_path(round_no, slug)}"

    parts = [
        f"# {headline}",
        "",
        f"> {standfirst}",
        "",
        f"By the evmax model · {date_str} · {SITE_URL}{canonical_path}",
        "",
        body_md,
        "",
        f"**Bottom line:** {bottom_line}",
        "",
        "## The data",
        "",
        table_md,
        "",
        "---",
        f"Method: {section.methodology}",
        f"Data license: CC BY 4.0 (attribution: evmax, {SITE_URL}). "
        f"Machine-readable JSON: {json_url}",
    ]
    return "\n".join(parts) + "\n"


_MATCH_CSS = (
    # "Games to watch" is a single muted line of chips, not its own bordered
    # card-in-a-card box -- it sits directly above the fixture grid.
    ".mx-lead{margin-bottom:16px;font-size:13px;color:var(--ink3);display:flex;"
    "align-items:center;flex-wrap:wrap;gap:8px}"
    ".mx-lead .mx-lead-label{font-weight:700;letter-spacing:.5px;text-transform:uppercase;"
    "font-size:11px;color:var(--ink3);margin-right:2px}"
    ".mx-close-tag{color:var(--acc);font-size:12.5px;font-weight:700;"
    "background:#fdeee9;padding:2px 9px;border-radius:20px}"
    ".mx-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}"
    ".mx-card{background:var(--surf);border:1px solid var(--line);border-radius:14px;"
    "padding:14px;display:flex;flex-direction:column;gap:8px}"
    ".mx-card.mx-close-card{border-color:var(--acc);border-width:2px}"
    ".mx-teams{font-size:15px;font-weight:800;letter-spacing:-.2px}"
    ".mx-score{font-size:22px;font-weight:800;color:var(--green);letter-spacing:.5px;"
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
    ".mx-final-score{font-size:22px;font-weight:800;color:var(--ink);letter-spacing:.5px;"
    "line-height:1}"
    ".mx-predicted{font-size:12.5px;color:var(--ink3)}"
)


def match_predictions_html(entries: list) -> str:
    """Render fixture prediction cards in v2 editorial style. Returned as raw
    cards HTML (plus its own <style> block) -- NOT wrapped in .artviz/.fig by
    the caller, since the cards are self-explanatory and a figure/caption
    wrapper around a whole grid of cards just adds a redundant box."""
    if not entries:
        return "<p style='color:var(--ink3);text-align:center'>No fixtures found for this round.</p>"

    close_matches = [e for e in entries if e.get("close")]

    # Lead strip: a single muted line of chips (no nested card-in-card box).
    lead_parts = []
    if close_matches:
        tags = "".join(
            f'<span class="mx-close-tag">{_html.escape(e["match"])}</span>'
            for e in close_matches
        )
        lead_parts.append(
            f'<div class="mx-lead"><span class="mx-lead-label">Games to watch</span>{tags}</div>'
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


# FPL-ledger styles for /track-record/ — injected ONLY when an FPL ledger is
# passed (FPL builds), so a World Cup build's page stays byte-identical.
_TR_FPL_CSS = (
    ".tr-section-h{font-size:22px;font-weight:800;letter-spacing:-.4px;"
    "margin:30px 0 12px}"
    ".tr-fpl-note{font-size:13px;color:var(--ink3);margin-top:14px}"
    ".tr-fpl-links{font-size:12.5px;color:var(--ink3);margin-top:6px}"
    ".tr-fpl-links a{color:var(--greend)}"
)


def _tr_fpl_section(ledger: list) -> str:
    """/track-record/'s FPL block (FPL builds only): the graded ledger from
    evmax/assets/accuracy/gw*.json — one row per graded gameweek (our MAE,
    ep_next MAE where captured, both frozen squad projections against realized
    official points, the running model-vs-crowd duel score) — followed by the
    heading the existing World Cup retrospective now sits under. Deterministic
    text only, the same bar as the rest of this page."""
    body_rows = []
    for r in ledger:
        ep = (f"{r['mae_ep_next']:.3f}" if r.get("mae_ep_next") is not None
              else '<span class="na">—</span>')
        body_rows.append(
            f"<tr><td>GW{r['gw']}</td>"
            f"<td>{r['mae_ours']:.3f}</td>"
            f"<td>{ep}</td>"
            f"<td>{r['model_projected']:.2f} → {r['model_realized']}</td>"
            f"<td>{r['consensus_projected']:.2f} → {r['consensus_realized']}</td>"
            f"<td>{r['duel_model']}-{r['duel_consensus']} "
            f"({_html.escape(r['duel_label'])})</td></tr>")
    links = " · ".join(
        f'<a href="{r["json_path"]}">gw{r["gw"]}.json</a>' for r in ledger)
    return f"""<h2 class="tr-section-h">FPL 2026/27 — the graded ledger</h2>
<p class="tr-claim">One row per graded gameweek: our mean absolute error on player
projections (against FPL's own <b>ep_next</b> where captured), both published squads'
frozen projected totals against realized official points, and the running
model-vs-crowd duel score.</p>
<div class="tr-card"><div class="tr-table-wrap"><table class="tr-metrics">
<thead><tr><th>GW</th><th>Our MAE</th><th>ep_next MAE</th>
<th>Model squad (proj → official)</th><th>Consensus squad (proj → official)</th>
<th>Duel (model-crowd)</th></tr></thead>
<tbody>{"".join(body_rows)}</tbody>
</table></div>
<p class="tr-fpl-note"><b>Method.</b> Projections frozen pre-deadline; grading JSONs public.</p>
<p class="tr-fpl-links">Grading data: {links}</p>
<p class="tr-fpl-links">The full working: <a href="/fpl/accuracy/">the accuracy
page</a> — per-gameweek error, the method in plain language and how to check it
yourself. The projections themselves: <a href="/data/">the open dataset</a>
(JSON + CSV, CC BY 4.0).</p>
</div>
<h2 class="tr-section-h">World Cup 2026 — the retrospective</h2>"""


# =============================================================================
# /fpl/accuracy/ — the graded ledger in full (phase 2B, spec P4)
# =============================================================================
# Deterministic text only, the same bar as /track-record/: every number comes
# straight from the graded JSONs, no LLM prose. FPL builds only, and reached
# from /track-record/'s FPL block rather than a nav pill — the nav is shared
# with the World Cup pages, which must stay byte-identical.

ACCURACY_PATH = "/fpl/accuracy/"

# Spec D5: ep_next was not captured before GW1, so the comparison cell SAYS SO.
# A bare dash in a column of numbers reads as a zero, and a zero here would
# claim FPL's own model was perfect that week.
_EP_NEXT_NOTE = "captured from GW2"

_ACCURACY_CSS = (
    ".ac{max-width:900px;margin:0 auto 80px}"
    ".ac h1{font-size:clamp(28px,4vw,40px);font-weight:800;line-height:1.05;"
    "letter-spacing:-1px;margin-bottom:14px}"
    ".ac .lead{font-family:var(--serif);font-size:19px;color:var(--ink2);"
    "line-height:1.55;margin-bottom:8px;max-width:70ch}"
    ".ac h2{font-size:13px;font-weight:700;letter-spacing:1.5px;"
    "text-transform:uppercase;color:var(--green);margin:36px 0 12px}"
    ".ac p{font-family:var(--serif);font-size:16.5px;line-height:1.65;"
    "color:#23201a;margin-bottom:12px;max-width:70ch}"
    ".ac dl{margin:0 0 8px}"
    ".ac dt{font-family:var(--sans);font-size:14px;font-weight:800;"
    "margin-top:14px}"
    ".ac dd{font-family:var(--serif);font-size:16px;line-height:1.6;"
    "color:var(--ink2);margin:4px 0 0;max-width:68ch}"
    ".ac code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;"
    "font-size:13px;background:var(--chipbg);padding:1px 6px;border-radius:5px}"
    ".ac-note{font-size:12.5px;color:var(--ink3);font-style:italic;"
    "white-space:nowrap}"
    ".ac-empty{background:var(--surf);border:1px solid var(--line);"
    "border-radius:14px;padding:26px;font-family:var(--serif);font-size:17px;"
    "color:var(--ink2)}"
    ".ac-check{background:var(--surf);border:1px solid var(--line);"
    "border-left:4px solid var(--green);border-radius:12px;padding:18px 22px;"
    "margin-top:8px}"
    ".ac-check p:last-child{margin-bottom:0}"
    ".ac a.lnk{color:var(--greend);font-weight:600}"
)


def _accuracy_summary_html(ledger: list) -> str:
    """Three stat tiles: gameweeks graded, mean MAE, the running duel."""
    maes = [r["mae_ours"] for r in ledger if r.get("mae_ours") is not None]
    mean_mae = sum(maes) / len(maes) if maes else None
    last = ledger[-1]
    duel = f'{last["duel_model"]}-{last["duel_consensus"]}'
    return (
        '<div class="tr-summary">'
        f'<div class="tr-stat"><b>{len(ledger)}</b>'
        f'<span>Gameweeks graded</span></div>'
        f'<div class="tr-stat"><b>{f"{mean_mae:.3f}" if mean_mae is not None else "—"}</b>'
        f'<span>Mean absolute error</span></div>'
        f'<div class="tr-stat"><b>{duel}</b>'
        f'<span>Model vs crowd — {_html.escape(last["duel_label"])}</span></div>'
        '</div>')


def _accuracy_table_html(ledger: list) -> str:
    rows = []
    for r in ledger:
        ep = (f'{r["mae_ep_next"]:.3f}' if r.get("mae_ep_next") is not None
              else f'<span class="ac-note">{_EP_NEXT_NOTE}</span>')
        graded = r.get("n")
        rows.append(
            f'<tr><td>GW{r["gw"]}</td>'
            f'<td>{"—" if graded is None else graded}</td>'
            f'<td>{r["mae_ours"]:.3f}</td>'
            f'<td>{ep}</td>'
            f'<td>{r["model_projected"]:.2f} → {r["model_realized"]}</td>'
            f'<td>{r["consensus_projected"]:.2f} → {r["consensus_realized"]}</td>'
            f'<td>{r["duel_model"]}-{r["duel_consensus"]} '
            f'({_html.escape(r["duel_label"])})</td>'
            f'<td><a class="lnk" href="{r["json_path"]}">gw{r["gw"]}.json</a>'
            f'</td></tr>')
    return (
        '<div class="tr-card"><div class="tr-table-wrap">'
        '<table class="tr-metrics"><thead><tr>'
        '<th>GW</th><th>Players graded</th><th>Our MAE</th>'
        '<th>FPL ep_next MAE</th><th>Model squad (proj → official)</th>'
        '<th>Consensus squad (proj → official)</th><th>Duel (model-crowd)</th>'
        '<th>Data</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></div>')


def accuracy_page(ledger: list, date_str: str = None) -> str:
    """/fpl/accuracy/ — the graded ledger in full, the method in plain
    language, links to every grading JSON, and how to check us.

    ledger: evmax.fpl_build.fpl_track_ledger() output (one row per graded
    gameweek). An empty ledger renders the page with an honest "nothing graded
    yet" panel rather than an empty table.
    """
    stamp = (f'<p style="font-size:13px;color:var(--ink3);margin-bottom:22px">'
             f'Last updated {_html.escape(date_str)}.</p>' if date_str else "")
    if ledger:
        body = _accuracy_summary_html(ledger) + _accuracy_table_html(ledger)
    else:
        body = ('<div class="ac-empty"><b>Nothing graded yet.</b> The first '
                'gameweek appears here the Monday after it finishes — we grade '
                'the snapshot that was frozen before the deadline, not a '
                'rebuild.</div>')
    description = ("Every evmax FPL projection graded against realized official "
                   "points — per-gameweek error, our squad against the crowd's, "
                   "and the raw grading data.")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>How accurate are we? | {TITLE_BRAND}</title>
<meta name="description" content="{_html.escape(description)}">
{_og_meta("How accurate are we?", description, ACCURACY_PATH, og_type="website")}
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}{_TRACK_RECORD_CSS}{_TR_FPL_CSS}{_ACCURACY_CSS}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html(active="track-record")}
</div></header>
<div class="wrap">
<div class="ac">
<div class="pagelabel" style="margin-top:34px">Accuracy</div>
<h1>How accurate are we?</h1>
<p class="lead">Every gameweek we publish a projected score for every player before
the deadline. Once the gameweek finishes we compare those exact numbers to what
actually happened. This page is the whole ledger — the good weeks and the bad
ones, with the raw data behind each row.</p>
{stamp}
{body}

<h2>What the columns mean</h2>
<dl>
<dt>Our MAE</dt>
<dd>Mean absolute error: the average gap between what we projected a player would
score and what he actually scored, across every player we published a number
about. Lower is better. Around 2.5 is roughly the state of the art for a single
gameweek — football is mostly noise, and anyone claiming a much lower number is
usually grading themselves on a handful of easy picks.</dd>
<dt>FPL ep_next MAE</dt>
<dd>The same measurement applied to FPL's own projection, <code>ep_next</code>,
captured from the official API before the same deadline. It is the fairest
benchmark available: same players, same week, same scoring. We started capturing
it from Gameweek 2, so GW1 has no comparison and the cell says so instead of
showing a zero.</dd>
<dt>Model squad / Consensus squad</dt>
<dd>Two real teams, both published before the deadline: ours, picked by the
optimiser, and a consensus XI assembled from what the popular FPL sources were
recommending that week. The arrow reads projected total → the official FPL score
that team actually returned, autosubs and captain fallback included.</dd>
<dt>Duel (model-crowd)</dt>
<dd>The running score between those two teams. A gameweek goes to whichever side
returned more official points; a tie moves neither column.</dd>
</dl>

<h2>How to check us</h2>
<div class="ac-check">
<p>You do not have to take any of this on trust. The chain is public end to end:</p>
<p><b>1. The claim was frozen before the deadline.</b> Every gameweek's projections
are written to a timestamped snapshot at build time, before kickoff, and committed
to the public repository. The build refuses to write a snapshot once the gameweek
has locked, so a number cannot be quietly improved after the fact.</p>
<p><b>2. The grading is a published file.</b> Each row above links its raw grading
JSON under <code>/api/fpl/accuracy/</code> — every graded player, our projection,
the realized points and the error, not just the average.</p>
<p><b>3. The projections themselves are downloadable.</b> The full board for every
gameweek is on <a class="lnk" href="/data/">the open dataset page</a> as JSON and
CSV under CC BY 4.0. Grade us yourself against any scoring you like.</p>
<p><b>4. The code is open.</b> The simulation, the grading and this page are in
<a class="lnk" href="https://github.com/granatb/wc2026">the repository</a>.</p>
</div>

<h2>What we do not do</h2>
<p>We do not drop bad gameweeks, re-run the model on a finished week and report the
better number, or quote accuracy over a hand-picked subset of players. The ledger
above is every gameweek we have graded, in order. The
<a class="lnk" href="/track-record/">track record</a> carries the same discipline
for the World Cup work.</p>
</div>
</div>
{_footer_html()}</body></html>"""


def track_record_page(record: dict, fpl: list = None) -> str:
    """/track-record/ — the site's credibility layer. Deterministic text only:
    every number here comes straight from evmax.backtest, no LLM prose, because
    trust requires that this specific page never has room for a model to shade
    the truth.

    fpl: the graded FPL ledger (evmax.fpl_build.fpl_track_ledger output). When
    passed — FPL builds — the FPL section renders FIRST and the World Cup
    record follows under its own heading. None (every World Cup build) keeps
    today's page byte-identical."""
    rounds = record.get("rounds", [])
    summary = record.get("summary", {})

    fpl_html = _tr_fpl_section(fpl) if fpl else ""
    fpl_css = _TR_FPL_CSS if fpl else ""
    description = (
        "evmax grades its own fantasy predictions against official points, misses "
        "included — the FPL gameweek ledger and the World Cup 2026 retrospective."
        if fpl else
        "evmax grades its own World Cup Fantasy predictions against official points, "
        "misses included. No cherry-picking — every round, every article.")

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
<title>Every prediction, graded | {TITLE_BRAND}</title>
<meta name="description" content="{description}">
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}{_TRACK_RECORD_CSS}{fpl_css}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html(active="track-record")}
</div></header>
<div class="wrap">
<article class="art" style="max-width:820px">
<div class="kick">Accountability</div>
<h1>Every prediction, graded</h1>
{fpl_html}<p class="stand">Before every round locks, we publish our picks as a frozen, timestamped
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


# Articles whose viz is the pitch SVG (a starting XI), vs everything else which
# gets an ev_bar top-slice chart. "matches" gets neither -- its cards are
# self-explanatory, so no figure/figcaption wrapper is added at all.
_PITCH_ARTICLES = {"best-xi", "wildcard", "our-squad", "consensus-squad"}

# Pitch figcaptions that differ from the default "model's optimal XI" line --
# the two published squads are FIELDED teams (one ours, one the crowd's), not
# an optimiser's output, and the caption must not claim otherwise.
_PITCH_CAPTIONS = {
    "our-squad": ("Our starting XI · number = projected points (xPts) · "
                  "C = captain"),
    "consensus-squad": ("The consensus starting XI · number = projected "
                        "points (xPts) · C = captain"),
}


# Articles whose chart pairs a floor bar with a faint ceiling reach -- kept in
# sync with build._CEILING_PAIRED_METRIC (render.py has no import on build.py).
_CEILING_REACH_ARTICLES = {"captains", "defenders", "risky", "blowout-transfers"}

# The ceiling definitions themselves (CEILING_EXPLAINER / FPL_CEILING_EXPLAINER)
# live above the Section class, which carries the right one per section.


def _article_fig_caption(article: str, columns: list, section=WC):
    """Caption text for the figure wrapping an article's viz, or None for
    articles (matches) that render without a figure at all -- the cards are
    self-explanatory."""
    if article == "matches":
        return None
    if article in _PITCH_ARTICLES:
        return _PITCH_CAPTIONS.get(
            article, "The model's optimal XI · number = projected points (xPts)")
    metric = columns[0] if columns else ""
    metric_label = _COL_LABEL.get(metric, metric)
    base = (f"Top {_ARTICLE_VIZ_ROWS_IN_CAPTION} by {metric_label}. Green = top pick · "
            "red = under 10% owned. Full list in the table below.")
    if article in _CEILING_REACH_ARTICLES:
        return (f"{base} Solid bar = {metric_label}, faint bar = ceiling. "
                f"{section.ceiling_explainer}")
    return base


# Kept in sync with build._ARTICLE_VIZ_MAX_ROWS (the actual cap applied to the
# chart data) purely for the caption text -- render.py has no import on build.py.
_ARTICLE_VIZ_ROWS_IN_CAPTION = 10


def _split_lede(body_html: str) -> tuple:
    """Split prose body_html at the first </p> so the lede paragraph can render
    directly after the byline, before the figure -- prose leads, chart follows.
    Guard: if there's no </p> at all, the whole body stays where it was
    (returned as the "rest", with an empty lede) rather than guessing."""
    idx = body_html.find("</p>")
    if idx == -1:
        return "", body_html
    split_at = idx + len("</p>")
    return body_html[:split_at], body_html[split_at:]


def article_page(round_no, article, title, prose, entries, columns, json_url, viz_html,
                 generated_at=None, date_str=None, show_table=True,
                 available_rounds=None, section=WC, live_html=""):
    """v2 editorial article page.

    Published articles are frozen claims: this page always renders the exact
    pre-lock projection, with no live/in-progress mutation. The places reality
    shows up post-lock are the matches article's predicted-vs-actual panel
    (see match_predictions_html), driven entirely by data on each entry
    (finished/final_score), and the FPL squad pages' realized-points panel:
    `live_html` (squad_live_panel_html output) renders ABOVE the frozen prose
    and touches nothing else — an empty string keeps the page byte-identical,
    which is what every non-live build passes.

    prose: dict {headline, standfirst, body_html, bottom_line, source}
    viz_html: already-safe HTML string (pitch SVG or ev_bar)
    generated_at: ISO-8601 timestamp string (optional)
    date_str: human-readable date string, e.g. "24 June 2026" (optional)

    Layout follows sports-data-journalism convention (FiveThirtyEight/The
    Athletic): prose leads -- the lede paragraph renders before the chart --
    the chart is a captioned summary of the top slice, and the full data sits
    in the table below.
    """
    summary = summary_sentence(article, entries)
    dataset_ld_raw = _json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": title,
        "description": section.methodology,
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
        _COL_LABEL.get(article, article.replace("-", " ").title())
        + f" · {section.kicker(round_no)}")
    table_html = _rank_table_html(entries, columns) if show_table else ""
    data_section = f"<h2>The data</h2>\n{table_html}" if show_table else ""
    bottom_line = _html.escape(prose.get("bottom_line", ""))
    byline_date = f" · {_html.escape(date_str)}" if date_str else ""

    # Prose-first layout: the lede paragraph (up to and including the first
    # </p>) renders right after the byline, then the figure, then the rest of
    # the body. If body_html has no </p> at all, it stays exactly where it was
    # (whole body after the figure) rather than guessing at a split.
    lede_html, rest_html = _split_lede(prose["body_html"])

    caption = _article_fig_caption(article, columns, section=section)
    if caption is None:
        # matches: cards are self-explanatory, no figure/figcaption wrapper.
        viz_section = viz_html
    else:
        fig_cls = "fig fig-pitch" if article in _PITCH_ARTICLES else "fig"
        viz_section = (
            f'<figure class="{fig_cls}">{viz_html}'
            f'<figcaption>{_html.escape(caption)}</figcaption></figure>'
        )

    # Any article whose table carries a ceiling column gets the one-line
    # definition in the footer, so the stat is never a bare unexplained number.
    # The section supplies its own: WC's ceiling is a percentile, FPL's a tail
    # mean, and each page must describe the statistic it actually publishes.
    ceiling_method_html = (
        f"{_html.escape(section.ceiling_explainer)}\n"
        if "ceiling" in (columns or []) else "")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(title)} | {TITLE_BRAND}</title>
<meta name="description" content="{_html.escape(summary)}">
<link rel="alternate" type="application/json" href="{json_url}">
<link rel="alternate" type="text/markdown" href="{section.md_path(round_no, article)}">
{_og_meta(prose["headline"], summary, section.article_path(round_no, article), "article")}
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}{_LIVE_PANEL_CSS if live_html else ""}{_NAV_SCROLL_CSS if section is not WC else ""}</style>
<script type="application/ld+json">{dataset_ld}</script>
<script type="application/ld+json">{article_ld}</script>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html()}
</div></header>
<div class="wrap">
<article class="art">
<div class="kick">{kicker_label}</div>
{_round_switcher_html(available_rounds or [round_no], round_no,
                      base_path=section.switcher_base(), abbr=section.unit_abbr)}
<h1>{_html.escape(prose["headline"])}</h1>
<p class="stand">{_html.escape(prose["standfirst"])}</p>
<div class="meta"><span class="av">e</span><span>By the evmax model{byline_date}</span></div>
{live_html}<div class="prose">{lede_html}
{viz_section}
{rest_html}
{data_section}
<h2>Bottom line</h2>
<p>{bottom_line}</p>
{_newsletter_html()}
<p class="method"><b>How we get these numbers.</b> {section.methodology}
{ceiling_method_html}Every figure here is machine-readable at <a href="{json_url}" style="color:var(--greend)">{json_url}</a>.</p>
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
<title>World Cup Fantasy Round {round_no} picks &amp; captains | {TITLE_BRAND}</title>
<meta name="description" content="evmax is an independent fantasy football simulation project: World Cup Fantasy Round {round_no} picks — best XI, captains and value from 50,000 Monte-Carlo runs.">
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


def feed_card(slug, round_no, headline, teaser, stat_value, stat_label, date_str=None,
              section=WC):
    """A single v2 feed card linking to the section's article page."""
    kicker = _html.escape(slug.replace("-", " ").title())
    date_html = (f'<span style="font-size:11px;color:var(--ink3);margin-top:-4px">'
                 f'{_html.escape(date_str)}</span>' if date_str else "")
    return (
        f'<a class="card" href="{section.article_path(round_no, slug)}">'
        f'<span class="ck">{kicker}</span>'
        f'<h3>{_html.escape(headline)}</h3>'
        f'{date_html}'
        f'<p>{_html.escape(teaser)}</p>'
        f'<div class="stat"><b>{_html.escape(str(stat_value))}</b>'
        f'<span>{_html.escape(stat_label)}</span></div>'
        f'</a>'
    )


def _format_kickoff_short(ko: str) -> str:
    """Parse a kickoff ISO-8601 string into '4 Jul · 17:00'. Strips the leading
    zero from the day manually where the platform's strftime lacks %-d (mirrors
    build._format_date's %-d fallback)."""
    if not ko:
        return "—"
    try:
        from datetime import datetime as _dt
        dt = _dt.fromisoformat(ko)
    except ValueError:
        return "—"
    try:
        return dt.strftime("%-d %b · %H:%M")
    except ValueError:
        return dt.strftime("%d %b · %H:%M").lstrip("0")


def _fixtures_rail_row(m: dict) -> str:
    """One compact fixture row for the landing page's odds rail. Reuses the
    .mx-probs/.mx-ph/.mx-pd/.mx-pa classes from the matches renderer so the
    probability bar matches the matches article pixel-for-pixel.

    Line 1: teams + kickoff date/time. Line 2: probs bar (plus the final score
    once finished -- the pre-match odds STAY visible so expected-vs-actual can
    be compared at a glance, that comparison is the whole point of the site).
    Line 3: a muted xG / predicted-scoreline caption, kept in both states."""
    home_esc = _html.escape(m.get("home", ""))
    away_esc = _html.escape(m.get("away", ""))
    ko_display = _format_kickoff_short(m.get("kickoff", ""))
    close_tag = '<span class="tag">Close</span>' if m.get("close") else ""
    top_line = (
        f'<div class="rail-row-top"><span class="rail-teams">{home_esc} vs {away_esc}'
        f'{close_tag}</span><span class="rail-ko">{_html.escape(ko_display)}</span></div>'
    )
    score = _html.escape(m.get("top_scoreline", "") or "")
    p_home = m.get("p_home", 0.0) * 100
    p_draw = m.get("p_draw", 0.0) * 100
    p_away = m.get("p_away", 0.0) * 100
    probs_bar = (
        '<div class="mx-probs">'
        f'<div class="mx-ph">H {p_home:.0f}%</div>'
        f'<div class="mx-pd">D {p_draw:.0f}%</div>'
        f'<div class="mx-pa">A {p_away:.0f}%</div>'
        '</div>'
    )
    xgh = m.get("exp_home_goals")
    xga = m.get("exp_away_goals")
    if xgh is not None and xga is not None:
        # HOME-AWAY order, same as the scoreline -- an ascending sort here
        # silently flipped which team the numbers belonged to (Argentina vs
        # Egypt rendered "xG 0.61-1.97", reading as Egypt favored)
        xg_meta = f'<div class="rail-meta">xG {xgh:.2f}–{xga:.2f} · pred {score}</div>'
    else:
        xg_meta = f'<div class="rail-meta">pred {score}</div>' if score else ""
    if m.get("finished") or m.get("final_score"):
        final_score = _html.escape(m.get("final_score", ""))
        body = (f'<div class="rail-final-line"><span class="rail-score">{final_score}</span>'
                f'<span class="mx-badge final">Final</span></div>'
                f'{probs_bar}')
        meta = xg_meta
    else:
        body = probs_bar
        meta = xg_meta
    return f'<div class="rail-row">{top_line}{body}{meta}</div>'


def _quick_picks_html(picks: list) -> str:
    """Sidebar 'answers at a glance' shortcuts: [{label, name, stat, href}]. Each row
    links into the article carrying the full reasoning."""
    rows = "".join(
        f'<a class="qp-row" href="{p["href"]}">'
        f'<span class="qp-label">{_html.escape(p["label"])}</span>'
        f'<span class="qp-name">{_html.escape(p["name"])}</span>'
        f'<span class="qp-stat">{_html.escape(p["stat"])}</span></a>'
        for p in picks)
    return f'<div class="pagelabel">Quick picks</div>{rows}'


def _fixtures_rail_html(round_no: int, fixtures: list, quick_picks=None,
                        section=WC) -> str:
    """The landing page's right-hand 'This round's ties' sidebar. fixtures is a
    list of match_predictions() entries (home/away/kickoff/p_home/p_draw/p_away/
    close/top_scoreline, and possibly finished/final_score).

    Foldable on mobile via a zero-JS checkbox pattern: the checkbox + label are
    hidden on desktop (content always shown); on mobile the label becomes a
    tappable card and `.rail-content` is display:none until the checkbox (its
    sibling) is checked. No JS anywhere on the site.

    The all-fixtures link points at the section's fixture article: the World Cup
    publishes a dedicated "matches" page; FPL's fixture coverage lives in the
    ticker, and linking a nonexistent /fpl/gwN/matches/ would ship a dead link."""
    rows = "".join(_fixtures_rail_row(m) for m in fixtures)
    qp = _quick_picks_html(quick_picks) if quick_picks else ""
    fixtures_slug = "matches" if section.key == "round" else "ticker"
    content = (
        f'{qp}<div class="pagelabel">This round\'s ties</div>'
        f'{rows}'
        f'<a class="rail-link" href="{section.article_path(round_no, fixtures_slug)}">All match predictions →</a>'
    )
    return (
        '<aside class="rail">'
        '<input type="checkbox" id="rail-toggle" class="rail-toggle">'
        '<label class="rail-fold-label" for="rail-toggle">Quick picks &amp; this round\'s ties</label>'
        f'<div class="rail-content">{content}</div>'
        '</aside>'
    )


# Duel-strip CSS is injected ONLY when a duel is passed (see landing_page):
# _STYLE is embedded byte-for-byte in every World Cup page, and those pages are
# frozen published claims — appending to _STYLE itself would change them all.
_DUEL_CSS = (
    ".duel{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;"
    "gap:14px;background:var(--surf);border:1px solid var(--line);"
    "border-radius:12px;padding:14px 18px;margin-bottom:22px}"
    ".duel-side{display:flex;flex-direction:column;gap:2px;min-width:0}"
    ".duel-side.consensus{text-align:right;align-items:flex-end}"
    ".duel-side:hover .duel-meta{color:var(--greend)}"
    ".duel-tag{font-size:10.5px;font-weight:800;letter-spacing:1.5px;"
    "text-transform:uppercase;color:var(--ink3)}"
    ".duel-total{font-size:24px;font-weight:800;color:var(--ink);"
    "font-variant-numeric:tabular-nums;line-height:1.15}"
    ".duel-total .du{font-size:12px;font-weight:600;color:var(--ink3);"
    "margin-left:4px}"
    ".duel-meta{font-size:12.5px;color:var(--ink2)}"
    ".duel-vs{font-size:12px;font-weight:800;color:var(--ink3);"
    "text-transform:uppercase;letter-spacing:1px}"
    ".duel-so-far{font-size:13px;color:var(--ink2);"
    "font-variant-numeric:tabular-nums}"
    ".duel-so-far b{font-size:16px;color:var(--greend)}"
)


def _duel_side_live_html(side_live: dict) -> str:
    """One side's realized 'so far' line, next to (never instead of) the frozen
    projection. side_live: that squad's fpl_live.grade_squad summary."""
    if not side_live:
        return ""
    pending = side_live["players_pending"]
    suffix = f"{pending} to play" if pending else "all played"
    return (f'<span class="duel-so-far"><b>{side_live["total_so_far"]}</b>'
            f' so far · {suffix}</span>')


def _duel_strip_html(duel: dict, round_no: int, section=WC) -> str:
    """The landing's compact model-vs-consensus strip: both published squads'
    projected XI totals (captain doubled) side by side, each side linking to
    its article. Data is the two squad articles' own meta — no new simulation,
    so the strip can never disagree with the pages it points at.

    duel: {"model": squad_article meta, "consensus": squad_article meta,
    optionally "live": {"model"/"consensus": fpl_live.grade_squad output}}.
    The live line shows REALIZED points so far beside the frozen projection —
    the WC "our XI so far" pattern (07-06): projections never mutate, reality
    renders next to them.
    """
    if not duel:
        return ""
    live = duel.get("live") or {}
    sides = {}
    for key, slug, label in (("model", "our-squad", "Model"),
                             ("consensus", "consensus-squad", "Consensus")):
        m = duel[key]
        sides[key] = (
            f'<a class="duel-side {key}" '
            f'href="{section.article_path(round_no, slug)}">'
            f'<span class="duel-tag">{label}</span>'
            f'<span class="duel-total">{m["projected_total"]:.2f}'
            f'<span class="du">proj</span></span>'
            f'{_duel_side_live_html(live.get(key))}'
            f'<span class="duel-meta">{_html.escape(m["formation"])} · '
            f'{_html.escape(m["captain"])} (c)</span>'
            f'</a>')
    return (f'<div class="duel">{sides["model"]}'
            f'<span class="duel-vs">vs</span>{sides["consensus"]}</div>')


# Squad-page live-panel CSS is injected ONLY when a panel is passed (see
# article_page): _STYLE is embedded byte-for-byte in every frozen article page
# — WC and FPL alike — and appending to it would change them all.
_LIVE_PANEL_CSS = (
    ".live-panel{background:var(--surf);border:1px solid var(--line);"
    "border-radius:12px;padding:14px 18px;margin:18px 0}"
    ".live-panel .lp-head{display:flex;align-items:baseline;gap:10px;"
    "flex-wrap:wrap;margin-bottom:8px}"
    ".live-panel .lp-total{font-size:14px;color:var(--ink2)}"
    ".live-panel .lp-total b{font-size:18px;color:var(--ink);"
    "font-variant-numeric:tabular-nums}"
    ".live-panel .lp-stamp{font-size:11.5px;color:var(--ink3);margin-left:auto}"
    ".live-panel table{width:100%;border-collapse:collapse;font-size:13px}"
    ".live-panel th{text-align:left;font-size:10.5px;font-weight:800;"
    "letter-spacing:1px;text-transform:uppercase;color:var(--ink3);"
    "padding:3px 8px 3px 0}"
    ".live-panel td{padding:3px 8px 3px 0;border-top:1px solid var(--line);"
    "color:var(--ink2);font-variant-numeric:tabular-nums}"
    ".live-panel td.lp-pts{font-weight:700;color:var(--ink)}"
    ".live-panel tr.lp-out td{color:var(--ink3)}"
)

_LIVE_STATUS_LABEL = {"played": "played", "pending": "to play",
                      "blank": "blank", "autosub_in": "autosub in"}


def squad_live_panel_html(grade: dict, fetched_at: str) -> str:
    """The squad page's realized-points panel — reality NEXT TO the frozen
    prose, never inside it (standing 07-04 rule: published articles do not
    mutate; this panel and the landing strip are the FPL section's deliberate
    live surfaces, like the WC's live-XI strip).

    grade: one squad's fpl_live.grade_squad output. fetched_at: the live
    payload's ISO fetch timestamp — printed on the panel so a stale rebuild
    labels its own staleness instead of passing as current.
    """
    if not grade:
        return ""
    rows = grade["rows"]
    pending = grade["players_pending"]
    suffix = f"{pending} to play" if pending else "all played"
    stamp = f"{fetched_at[:16].replace('T', ' ')} UTC" if fetched_at else "?"
    body = []
    for r in rows:
        mult = r["multiplier"]
        pts = f"{r['points'] * mult}" if mult else f"({r['points']})"
        if mult == 2:
            pts += " (c)"
        cls = ' class="lp-out"' if mult == 0 else ""
        note = f' — {r["note"]}' if r["note"] else ""
        body.append(
            f'<tr{cls}><td>{_html.escape(r["name"])}</td>'
            f'<td>{_html.escape(r["club"])}</td>'
            f'<td class="lp-pts">{pts}</td>'
            f'<td>{_LIVE_STATUS_LABEL.get(r["status"], r["status"])}'
            f'{_html.escape(note)}</td></tr>')
    return (
        '<div class="live-panel">'
        '<div class="lp-head"><span class="live-tag">Live</span>'
        f'<span class="lp-total"><b>{grade["total_so_far"]}</b> pts so far · '
        f'{suffix}</span>'
        f'<span class="lp-stamp">live — updates on rebuild · as of {stamp}'
        '</span></div>'
        '<table><thead><tr><th>Player</th><th>Club</th><th>Pts</th>'
        '<th>Status</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
        '</div>')


def landing_page(round_no, featured, feed, date_str=None, fixtures=None, quick_picks=None,
                 available_rounds=None, live_xi=None, duel=None, section=WC,
                 pre_feed_html="", extra_style="", pre_content_html=""):
    """v2 landing page — featured block + feed grid, with an optional right-hand
    odds rail ("This round's ties").

    featured: {slug, prose: {headline, standfirst, ...}, viz_html}
    feed: list of {slug, headline, teaser, stat_value, stat_label}
    date_str: human-readable date string, e.g. "24 June 2026" (optional)
    fixtures: optional list of match_predictions() entries; when provided, a
              sticky sidebar of this round's fixtures/odds renders alongside
              the main content in a two-column grid (single column on mobile,
              with the aside placed after the main content).
    pre_feed_html / extra_style: an optional module rendered above the feed
              and the style block it needs. Both default to "" so every
              existing call site — the whole World Cup tree — keeps producing
              byte-identical pages, same contract as `duel`.
    pre_content_html: an optional module rendered as the page's very FIRST
              content section, above everything else in the wrap — the FPL
              landing's full top-cards row (owner correction 2026-08-25: the
              cards go at the very top, above the duel strip and the hero
              article). Defaults to "" — World Cup landings byte-identical.
    """
    og_block = _og_meta(
        f"{section.label} {section.kicker(round_no)} — simulation-based picks",
        f"Captain EV, expected points and match predictions for {section.kicker(round_no)}, "
        f"from 50,000 Monte-Carlo simulations. Graded publicly.", "/", "website")
    # Entity disambiguation: "evmax" collides with established EV-charger brands
    # (competitor landscape, 2026-07-03) — a bare "evmax" search returns none of
    # our pages while "evmax fantasy" returns the top three. See organization_ld.
    org_ld = organization_ld()
    site_ld = _json.dumps({
        "@context": "https://schema.org", "@type": "WebSite",
        "name": "evmax — fantasy football simulations", "url": SITE_URL,
        # Ties the site to the Organization above rather than leaving two
        # unrelated entities on the same page for an engine to reconcile itself.
        "publisher": {"@id": SITE_URL + "/#organization"},
    }).replace("</", "<\\/")
    feat_slug = featured["slug"]
    feat_prose = featured["prose"]
    feat_viz = featured.get("viz_html", "")
    feat_kicker = "Featured · " + _html.escape(
        feat_slug.replace("-", " ").title())
    feat_url = section.article_path(round_no, feat_slug)
    byline_date = f" · {_html.escape(date_str)}" if date_str else ""

    feed_cards = "".join(
        feed_card(
            f["slug"], round_no, f["headline"], f["teaser"],
            f["stat_value"], f["stat_label"], date_str=date_str,
            section=section)
        for f in feed)

    hero_actions = (
        f'<div class="hero-actions">'
        f'{_round_switcher_html(available_rounds or [round_no], round_no, base_path=section.switcher_base(), abbr=section.unit_abbr)}'
        f'{_rate_cta_html()}</div>'
    )
    # duel shares live_xi's template line so a duel-less landing (every World
    # Cup build) keeps today's whitespace byte-for-byte.
    feat_content = f"""<div class="pagelabel">{section.label} · {section.kicker(round_no)}</div>
{hero_actions}
{_live_xi_html(live_xi, round_no, section=section)}{_duel_strip_html(duel, round_no, section=section)}
<section class="feat">
<div>
  <div class="kick">{feat_kicker}</div>
  <h1>{_html.escape(feat_prose["headline"])}</h1>
  <p class="stand">{_html.escape(feat_prose["standfirst"])}</p>
  <div class="byline"><span class="av">e</span><span>By the evmax model{byline_date}</span></div>
  <p style="margin-top:16px"><a href="{feat_url}" style="color:var(--green);font-weight:600;font-size:14px">Read the full analysis →</a></p>
</div>
<div class="viz">{feat_viz}</div>
</section>"""

    feed_content = f"""{pre_feed_html}<div class="pagelabel">Latest analysis</div>
<div class="feed">{feed_cards}</div>
{_newsletter_html()}
<p class="method"><b>Method.</b> {section.methodology}</p>"""

    if fixtures:
        # Grid-areas puts the rail in its own right-hand column spanning both
        # the "feat" and "feed" rows on desktop (grid-template-areas:
        # "feat rail" / "feed rail"), while feat still comes first in reading/
        # DOM order overall. On mobile the single-column stack collapses to
        # feat -> rail (folded) -> feed via the areas list, so the owner can
        # actually find the rail without scrolling to the very bottom.
        rail_html = _fixtures_rail_html(round_no, fixtures, quick_picks=quick_picks,
                                        section=section)
        body_content = (
            '<div class="landing-grid">'
            f'<div class="feat-area">{feat_content}</div>'
            f'{rail_html}'
            f'<div class="feed-area">{feed_content}</div>'
            '</div>'
        )
    else:
        body_content = feat_content + feed_content

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{section.label} {section.kicker(round_no)} picks &amp; captains | {TITLE_BRAND}</title>
<meta name="description" content="evmax is an independent fantasy football simulation project: {section.label} {section.kicker(round_no)} picks — best XI, captains and value from 50,000 Monte-Carlo runs.">
{og_block}
<script type="application/ld+json">{org_ld}</script>
<script type="application/ld+json">{site_ld}</script>
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}{_MATCH_CSS}{_DUEL_CSS if duel else ""}{extra_style}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html(active="home")}
</div></header>
<div class="wrap">
{pre_content_html}{body_content}
</div>
{_footer_html()}</body></html>"""


_AI_BOTS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-Web",
            "PerplexityBot", "Google-Extended", "CCBot", "Applebot-Extended"]


def llms_txt(round_no, nav, section=WC, extra_lines=None):
    """extra_lines: optional pre-built lines appended after the articles
    section (the FPL build's player-cards block). None — every World Cup call
    site — keeps today's output byte-identical."""
    lines = [
        f"# evmax — simulation-based {section.label} picks",
        "",
        "> Free, transparent fantasy picks from 50,000 Monte-Carlo simulations on "
        f"de-vigged market odds, scored on the official {section.table_label} table. "
        "Numbers are machine-readable JSON; attribution to evmax is requested.",
        "",
        f"## {section.kicker(round_no)} articles",
    ]
    for slug, title in nav:
        lines.append(f"- [{title}]({SITE_URL}{section.article_path(round_no, slug)}) — "
                     f"data: {SITE_URL}{section.json_path(round_no, slug)}"
                     f" · markdown: {SITE_URL}{section.md_path(round_no, slug)}")
    if extra_lines:
        lines += [""] + list(extra_lines)
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
        f"- Full player projections: {SITE_URL}{section.players_json_path(round_no)}",
    ]
    return "\n".join(lines) + "\n"


def robots_txt():
    blocks = [f"User-agent: {b}\nAllow: /" for b in _AI_BOTS]
    blocks.append("User-agent: *\nAllow: /")
    return "\n\n".join(blocks) + f"\n\nSitemap: {SITE_URL}/sitemap.xml\n"


def sitemap_xml(round_no, nav, lastmod=None, section=WC, extra_urls=None):
    """extra_urls: absolute site paths to include verbatim, beyond this section's
    own pages. The FPL build passes the World Cup tree here: those pages are still
    live and still indexed (spec D5), and a sitemap that silently drops them reads
    to a crawler as a request to deindex them. The static pages (/about/ etc.)
    stay listed for every section — they are shared site chrome, not section
    pages, and the existing WC sitemap pins them."""
    urls = [f"{SITE_URL}/", f"{SITE_URL}/about/", f"{SITE_URL}/privacy/",
            f"{SITE_URL}/track-record/", f"{SITE_URL}/rate/",
            f"{SITE_URL}{section.landing_path(round_no)}"]
    urls += [f"{SITE_URL}{section.article_path(round_no, slug)}" for slug, _ in nav]
    urls += [f"{SITE_URL}{p}" for p in (extra_urls or [])]
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
<title>About evmax — fantasy football simulations</title>
<meta name="description" content="evmax uses 50,000 Monte-Carlo simulations on de-vigged market odds to generate free, transparent World Cup Fantasy picks.">
<script type="application/ld+json">{organization_ld()}</script>
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
<p>evmax is an independent, unofficial statistical-analysis project with <b>no
affiliation to FIFA</b>, any football federation, league, club, or fantasy game
operator. Player and team names appear in a purely descriptive, informational
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
<span class="chip">Substitution analysis</span>
</div>
<p>We are building an interactive tool to evaluate the expected value of substitution
patterns. It will appear in the nav when ready. Squad construction is already live:
<a href="/rate/" style="color:var(--greend)">Rate my team</a> scores any 15 against
this round's simulations, including the model's own optimal XI to compare against.</p>
</div>
</div>
{_footer_html()}</body></html>"""

def privacy_page():
    """Privacy notice: static site, zero cookies, zero third-party requests."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Privacy | {TITLE_BRAND}</title>
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

# =============================================================================
# /data/ — the public CC BY dataset's human page (phase 2B, spec P2)
# =============================================================================
# FPL builds only. Nothing here is reachable from the shared nav or footer, so
# every World Cup page stays byte-identical; /data/ is discovered through the
# sitemap, llms.txt and the FPL block on /track-record/.

_DATA_CSS = (
    ".dp{max-width:860px;margin:0 auto 80px}"
    ".dp h1{font-size:clamp(28px,4vw,40px);font-weight:800;line-height:1.05;"
    "letter-spacing:-1px;margin-bottom:14px}"
    ".dp .lead{font-family:var(--serif);font-size:19px;color:var(--ink2);"
    "line-height:1.55;margin-bottom:26px;max-width:70ch}"
    ".dp h2{font-size:13px;font-weight:700;letter-spacing:1.5px;"
    "text-transform:uppercase;color:var(--green);margin:36px 0 12px}"
    ".dp p{font-family:var(--serif);font-size:16.5px;line-height:1.65;"
    "color:#23201a;margin-bottom:12px;max-width:70ch}"
    ".dp code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;"
    "font-size:13px;background:var(--chipbg);padding:1px 6px;border-radius:5px}"
    ".dp-lic{background:var(--surf);border:1px solid var(--line);"
    "border-left:4px solid var(--green);border-radius:12px;padding:18px 22px;"
    "margin:6px 0 8px}"
    ".dp-lic p{margin-bottom:8px}.dp-lic p:last-child{margin-bottom:0}"
    ".dp-attr{display:block;font-family:ui-monospace,SFMono-Regular,Menlo,"
    "monospace;font-size:13px;background:var(--bg);border:1px dashed "
    "var(--line);border-radius:8px;padding:10px 12px;margin-top:10px;"
    "color:var(--ink);overflow-x:auto;white-space:pre}"
    ".dp-files{display:grid;grid-template-columns:repeat(auto-fill,"
    "minmax(230px,1fr));gap:12px;margin:8px 0 4px}"
    ".dp-file{background:var(--surf);border:1px solid var(--line);"
    "border-radius:12px;padding:13px 16px}"
    ".dp-file b{display:block;font-size:15px;font-weight:800;margin-bottom:6px}"
    ".dp-file a{font-size:13px;font-weight:700;color:var(--greend);"
    "margin-right:12px}"
    ".dp-file a:hover{text-decoration:underline}"
    ".dp-file span{font-size:12px;color:var(--ink3)}"
    ".dp-pre{background:#15140f;color:#e9e5da;border-radius:12px;"
    "padding:16px 18px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;"
    "font-size:12.5px;line-height:1.7;overflow-x:auto;margin:6px 0 14px;"
    "white-space:pre}"
    ".dp-pre .c{color:#9a9384}"
    ".dp-tw{overflow-x:auto;border:1px solid var(--line);border-radius:12px;"
    "background:var(--surf);margin-top:8px}"
    "table.dp-cols{width:100%;border-collapse:collapse;font-size:13.5px}"
    "table.dp-cols th{text-align:left;font-size:10.5px;font-weight:700;"
    "letter-spacing:.8px;text-transform:uppercase;color:var(--ink3);"
    "padding:10px 14px;border-bottom:2px solid var(--ink);white-space:nowrap}"
    "table.dp-cols td{padding:10px 14px;border-bottom:1px solid var(--line);"
    "vertical-align:top;color:var(--ink2);line-height:1.5}"
    "table.dp-cols tr:last-child td{border-bottom:0}"
    "table.dp-cols td.t{color:var(--ink3);white-space:nowrap;font-size:12.5px}"
    "table.dp-cols td:first-child{white-space:nowrap}"
)


def _data_files_html(gameweeks: list) -> str:
    """One card per published gameweek plus the cumulative pair and the index.
    Every file the dataset publishes is linked from here — a bulk dataset whose
    files you have to guess at is not a published dataset."""
    from evmax import dataset

    cards = []
    for gw in gameweeks:
        paths = dataset.gameweek_paths(gw)
        cards.append(
            f'<div class="dp-file"><b>Gameweek {gw}</b>'
            f'<a href="{paths["json"]}">JSON</a>'
            f'<a href="{paths["csv"]}">CSV</a></div>')
    cards.append(
        f'<div class="dp-file"><b>Every gameweek</b>'
        f'<a href="{dataset.ALL_PATHS["json"]}">JSON</a>'
        f'<a href="{dataset.ALL_PATHS["csv"]}">CSV</a>'
        f'<span>Cumulative — every gameweek we have published.</span></div>')
    cards.append(
        f'<div class="dp-file"><b>Index</b>'
        f'<a href="{dataset.DATASET_BASE}/index.json">index.json</a>'
        f'<span>What exists right now, plus the column schema. Read this '
        f'first.</span></div>')
    return f'<div class="dp-files">{"".join(cards)}</div>'


def _data_glossary_html() -> str:
    """The column table, rendered from dataset.COLUMN_GLOSSARY — the same dict
    docs/DATASET.md mirrors, so the page and the repo doc cannot drift."""
    from evmax import dataset

    rows = "".join(
        f'<tr><td><code>{_html.escape(col)}</code></td>'
        f'<td class="t">{_html.escape(dataset.COLUMN_GLOSSARY[col][0])}</td>'
        f'<td>{_html.escape(dataset.COLUMN_GLOSSARY[col][1])}</td></tr>'
        for col in dataset.CSV_COLUMNS)
    extra = (
        f'<tr><td><code>{dataset.PMF_FIELD}</code></td><td class="t">object'
        f'</td><td>JSON only — the sparse point-mass function over integer FPL '
        f'points, <code>{{"points": count}}</code> across the 50,000 '
        f'simulations. Omitted for gameweeks published before we stored it.'
        f'</td></tr>')
    return ('<div class="dp-tw"><table class="dp-cols"><thead><tr>'
            '<th>Column</th><th>Type</th><th>What it means</th></tr></thead>'
            f'<tbody>{rows}{extra}</tbody></table></div>')


def _data_curl_html(gameweeks: list) -> str:
    """Three copy-pasteable examples: the index, one gameweek's CSV, and a
    filter over the cumulative JSON."""
    from evmax import dataset

    latest = max(gameweeks) if gameweeks else 1
    base = SITE_URL
    return (
        '<div class="dp-pre">'
        '<span class="c"># 1. What is published right now</span>\n'
        f'curl -s {base}{dataset.DATASET_BASE}/index.json | jq \'.gameweeks\''
        '</div>'
        '<div class="dp-pre">'
        f'<span class="c"># 2. One gameweek, flat CSV</span>\n'
        f'curl -s {base}{dataset.DATASET_BASE}/gw{latest}.csv -o '
        f'evmax-gw{latest}.csv'
        '</div>'
        '<div class="dp-pre">'
        '<span class="c"># 3. Every gameweek, top 10 midfielders by projected '
        'points</span>\n'
        f'curl -s {base}{dataset.ALL_PATHS["json"]} | \\\n'
        '  jq \'[.players[] | select(.position=="MID")]'
        ' | sort_by(-.x_points) | .[:10]\''
        '</div>')


def _data_schema_ld(gameweeks: list) -> str:
    """schema.org Dataset — what makes Google Dataset Search and an agent
    crawler recognise this as a dataset with a machine-readable licence."""
    from evmax import dataset

    dists = [{"@type": "DataDownload", "encodingFormat": "application/json",
              "contentUrl": f"{SITE_URL}{dataset.ALL_PATHS['json']}"},
             {"@type": "DataDownload", "encodingFormat": "text/csv",
              "contentUrl": f"{SITE_URL}{dataset.ALL_PATHS['csv']}"}]
    for gw in gameweeks:
        paths = dataset.gameweek_paths(gw)
        dists.append({"@type": "DataDownload",
                      "encodingFormat": "text/csv",
                      "contentUrl": f"{SITE_URL}{paths['csv']}"})
    return _json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "evmax FPL projections — the open dataset",
        "description": (
            "Per-gameweek Fantasy Premier League point projections for every "
            "simulated player, from 50,000 Monte-Carlo simulations on "
            "de-vigged market odds. JSON and CSV, CC BY 4.0."),
        "url": f"{SITE_URL}{dataset.DATA_PAGE}",
        "license": dataset.LICENSE_URL,
        "creator": {"@id": SITE_URL + "/#organization"},
        "isAccessibleForFree": True,
        "keywords": ["Fantasy Premier League", "FPL", "expected points",
                     "football analytics", "Monte-Carlo simulation"],
        "distribution": dists,
    }, indent=None).replace("</", "<\\/")


def data_page(gameweeks, date_str: str = None) -> str:
    """/data/ — what the dataset is, the CC BY terms with the exact attribution
    line, the column glossary, three curl examples, links to every file, and a
    citation block.

    gameweeks: every gameweek with a dataset file on disk, ascending.
    Rendered on FPL builds only.
    """
    from evmax import dataset

    gws = sorted(set(int(g) for g in (gameweeks or [])))
    stamp = (f'<p class="dp-updated" style="font-size:13px;color:var(--ink3);'
             f'margin-bottom:22px">Last updated {_html.escape(date_str)}.</p>'
             if date_str else "")
    count_line = (f"{len(gws)} gameweek{'s' if len(gws) != 1 else ''} published "
                  f"so far." if gws else
                  "The first gameweek publishes with the next build.")
    description = ("Every evmax FPL projection as bulk JSON and CSV, free under "
                   "CC BY 4.0 — one file per gameweek plus a cumulative file, "
                   "with the full column schema.")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The open FPL dataset | {TITLE_BRAND}</title>
<meta name="description" content="{_html.escape(description)}">
<script type="application/ld+json">{_data_schema_ld(gws)}</script>
{_og_meta("The open FPL dataset", description, dataset.DATA_PAGE, og_type="website")}
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}{_DATA_CSS}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html()}
</div></header>
<div class="wrap">
<div class="dp">
<div class="pagelabel" style="margin-top:34px">Open data</div>
<h1>Every projection we make, as a file you can download</h1>
<p class="lead">Before each Premier League deadline we simulate the gameweek 50,000
times and score every player on the official FPL points table. This page publishes
all of it — every player we simulated, not the ones we wrote about — as JSON and
CSV. Free, no key, no account, no rate limit. {_html.escape(count_line)}</p>
{stamp}

<h2>The licence</h2>
<div class="dp-lic">
<p><b>CC BY 4.0.</b> Use these numbers for anything — a blog post, a spreadsheet, a
podcast, a model of your own, a commercial product. The single condition is that you
credit evmax and link back. That is the whole deal, and it is the deal on purpose:
we would rather be cited than hidden.</p>
<p>Full terms: <a href="{dataset.LICENSE_URL}" style="color:var(--greend)">creativecommons.org/licenses/by/4.0/</a></p>
<p style="margin-top:12px"><b>Paste this credit line:</b></p>
<code class="dp-attr">{_html.escape(dataset.ATTRIBUTION_LINE)}</code>
</div>

<h2>The files</h2>
<p>One file per gameweek in both formats, plus a cumulative file covering every
gameweek we have ever published. Past gameweeks are never rewritten — a projection
published before a deadline stays exactly as it was published.</p>
{_data_files_html(gws)}

<h2>Try it</h2>
{_data_curl_html(gws)}

<h2>What the columns mean</h2>
<p>The CSV header is stable: columns are only ever added at the end, never
reordered or removed, so a script that reads it by position keeps working.
A cell can be empty when we could not compute that number for that player —
an empty cell is never a zero.</p>
{_data_glossary_html()}

<h2>How the numbers are made</h2>
<p>{_html.escape(dataset.METHOD)} We publish the grading too: see
<a href="/fpl/accuracy/" style="color:var(--greend)">our accuracy page</a> for
per-gameweek error against realized official points, and
<a href="/track-record/" style="color:var(--greend)">the track record</a> for the
full history. Nothing on this site is graded by us in private.</p>

<h2>Cite us</h2>
<p>For a paper, a README or a footnote:</p>
<code class="dp-attr">evmax. "FPL projections dataset." {SITE_URL}{dataset.DATA_PAGE}
Licensed CC BY 4.0.</code>
<p style="margin-top:14px">Building an agent? There is an MCP server for this data —
see <a href="https://github.com/granatb/wc2026" style="color:var(--greend)">the
repository</a>. Questions, corrections or a reuse you want us to know about:
<a href="/about/" style="color:var(--greend)">about evmax</a>.</p>
</div>
</div>
{_footer_html()}</body></html>"""


def _utility_page(title, kicker, heading, body_html, active=None,
                  description="evmax — independent fantasy football simulations."):
    """Small editorial utility page (thanks/confirmed) — noindex, footer, nav."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{title} | {TITLE_BRAND}</title>
<meta name="description" content="{_html.escape(description)}">
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
        "<a href='/' style='color:var(--greend)'>head back to the picks</a>.</p>",
        description="Confirm your evmax newsletter subscription — check your inbox for the double opt-in email.")


def confirmed_page():
    """Post-confirmation landing: welcome aboard."""
    return _utility_page(
        "Subscribed", "Newsletter", "You're in.",
        "<p>From the next round on, the sims land in your inbox before lock — "
        "captains, expected points and match predictions, all graded publicly on our "
        "<a href='/track-record/' style='color:var(--greend)'>track record</a> page.</p>"
        "<p><a href='/' style='color:var(--greend)'>Back to this round's picks →</a></p>",
        description="Subscription confirmed — evmax simulations land in your inbox before every round locks.")


# --- /rate/ -- the site's first first-party JavaScript ---------------------
# Policy: self-hosted (/js/rate.js), zero tracking, zero external requests, and
# the page must degrade gracefully with JS off (see <noscript> below). This is
# a deliberate, narrow exception to the site's zero-JS posture -- everything
# else on evmax (including this page's own markup/results container) still
# renders and reads fine without it.
_RATE_CSS = (
    ".rate-wrap{max-width:720px;margin:0 auto}"
    ".rate-wrap .kick{margin-bottom:14px}"
    ".rate-wrap h1{font-size:clamp(28px,4.6vw,42px);font-weight:800;line-height:1.06;"
    "letter-spacing:-1px}"
    ".rate-wrap .stand{font-family:var(--serif);font-size:19px;color:var(--ink2);"
    "line-height:1.5;margin-top:14px}"
    ".rate-form{margin:26px 0}"
    "#team-input{width:100%;font-family:var(--sans);font-size:15px;color:var(--ink);"
    "background:var(--surf);border:1px solid var(--line);border-radius:12px;"
    "padding:14px 16px;resize:vertical;line-height:1.5}"
    "#team-input:focus{outline:2px solid var(--green);outline-offset:1px}"
    ".rate-actions{display:flex;align-items:center;gap:14px;margin-top:12px;flex-wrap:wrap}"
    "#rate-btn{font-family:var(--sans);font-size:14.5px;font-weight:700;color:#fff;"
    "background:var(--green);border:0;border-radius:8px;padding:12px 22px;cursor:pointer}"
    "#rate-btn:hover{background:var(--greend)}"
    "#rate-btn:disabled{opacity:.6;cursor:default}"
    ".rate-hint{font-size:12.5px;color:var(--ink3)}"
    ".rate-noscript{background:var(--chipbg);border:1px solid var(--line);border-radius:12px;"
    "padding:14px 18px;font-size:13.5px;color:var(--ink2);line-height:1.55;margin:18px 0}"
    ".rate-noscript a{color:var(--greend);text-decoration:underline}"
    "#rate-results{margin-top:8px}"
    ".rate-card{background:var(--surf);border:1px solid var(--line);border-radius:14px;"
    "padding:22px 24px;margin-top:18px}"
    ".rate-row{display:flex;align-items:baseline;justify-content:space-between;gap:14px;"
    "padding:10px 0;border-bottom:1px solid var(--line);font-size:15px}"
    ".rate-row:last-of-type{border-bottom:0}"
    ".rate-row .rn{font-weight:700}"
    ".rate-row .rf{font-size:12.5px;font-weight:700;margin-left:8px}"
    ".rate-row .rf.out{color:var(--acc)}"
    ".rate-row .rf.doubtful{color:#a8331c}"
    ".rate-row .rc{color:var(--green);font-weight:700;font-size:11.5px;"
    "text-transform:uppercase;letter-spacing:.5px;margin-left:6px}"
    ".rate-row .rnote{display:block;font-size:12px;color:var(--ink3);margin-top:2px}"
    ".rate-row b.rx{font-variant-numeric:tabular-nums;white-space:nowrap}"
    ".rate-row .rx-wrap{display:flex;flex-direction:column;align-items:flex-end;gap:1px}"
    ".rate-row .rceil{font-size:11.5px;color:var(--ink3);font-variant-numeric:tabular-nums}"
    ".rate-total{display:flex;align-items:baseline;justify-content:space-between;"
    "margin-top:14px;padding-top:14px;border-top:2px solid var(--ink);font-size:17px}"
    ".rate-total b{font-size:22px;color:var(--green)}"
    ".rate-ceiling-total{margin-top:6px;padding-top:0;border-top:0;font-size:13.5px;"
    "color:var(--ink3)}"
    ".rate-ceiling-total b{font-size:15px;color:var(--ink2)}"
    ".rate-capcheck{font-family:var(--serif);font-size:15.5px;color:var(--ink2);"
    "line-height:1.5;margin-top:14px}"
    ".rate-optimal{margin-top:14px;padding-top:14px;border-top:1px solid var(--line)}"
    ".rate-optimal .rate-capcheck{margin-top:0}"
    ".rate-optimal .rnote{font-size:12.5px;color:var(--ink3);margin-top:6px;line-height:1.5}"
    ".rate-missing{font-size:13px;color:var(--ink3);margin-top:12px}"
    ".rate-warn{font-size:13px;color:#a8331c;background:#fdeee9;border-radius:8px;"
    "padding:8px 12px;margin-top:12px}"
    "#rate-copy{font-family:var(--sans);font-size:13.5px;font-weight:700;color:var(--green);"
    "background:none;border:1px solid var(--line);border-radius:8px;padding:8px 14px;"
    "cursor:pointer;margin-top:16px}"
    "#rate-copy:hover{border-color:var(--green)}"
    "#rate-error{color:#a8331c;font-size:14px;margin-top:12px}"
    # slot picker: 15 autocomplete inputs (11 XI + 4 bench) over a shared datalist
    ".slot-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));"
    "gap:8px 10px;margin-bottom:14px}"
    ".slot-head{grid-column:1/-1;font-size:12px;font-weight:800;text-transform:uppercase;"
    "letter-spacing:.8px;color:var(--ink2);margin-top:10px;display:flex;align-items:baseline;"
    "justify-content:space-between;gap:10px}"
    ".slot-head:first-child{margin-top:0}"
    ".slot-row{display:flex;align-items:center;gap:6px}"
    ".slot{flex:1;min-width:0;font-family:var(--sans);font-size:14px;color:var(--ink);"
    "background:var(--surf);border:1px solid var(--line);border-radius:9px;padding:9px 12px}"
    ".slot:focus{outline:2px solid var(--green);outline-offset:1px}"
    ".slot-bench{background:var(--chipbg)}"
    ".cappick{position:relative;flex:0 0 auto;cursor:pointer}"
    ".cappick input{position:absolute;opacity:0;pointer-events:none}"
    ".cappick span{display:inline-flex;align-items:center;justify-content:center;"
    "width:28px;height:28px;border:1px solid var(--line);border-radius:50%;font-size:12px;"
    "font-weight:800;color:var(--ink3);background:var(--surf)}"
    ".cappick input:checked+span{background:var(--green);border-color:var(--green);color:#fff}"
    ".cappick:hover span{border-color:var(--green)}"
    ".rate-paste{margin:6px 0 2px}"
    ".rate-paste summary{font-size:13px;color:var(--ink3);cursor:pointer;margin-bottom:10px}"
    ".rate-paste summary:hover{color:var(--greend)}"
)

# FPL-only pitch styling for the /rate/ slot picker (owner correction
# 2026-08-25: "rate my team doesn't look like a pitch"). Injected ONLY on FPL
# builds so the World Cup /rate/ page stays byte-identical. Visual language
# borrowed from pitch_svg_fpl: mow-stripe grass, white half-pitch markings
# (an inline aria-hidden SVG behind the rows), paper card-slot chips on top.
_RATE_PITCH_CSS = (
    ".pitch-picker{margin-bottom:14px}"
    ".pp-pitch{position:relative;margin-top:10px;border-radius:14px 14px 0 0;"
    "padding:34px 18px 40px;min-height:400px;display:flex;flex-direction:column;"
    "justify-content:space-between;gap:24px;overflow:hidden;"
    "background:repeating-linear-gradient(180deg,#2e7e4c 0,#2e7e4c 16.66%,"
    "#338755 16.66%,#338755 33.33%)}"
    ".pp-lines{position:absolute;inset:0;width:100%;height:100%;"
    "pointer-events:none}"
    ".pp-row{position:relative;display:flex;justify-content:center;gap:12px;"
    "flex-wrap:wrap}"
    ".pp-lab{position:absolute;left:4px;top:50%;transform:translateY(-50%);"
    "font-size:10px;font-weight:800;letter-spacing:1.5px;"
    "color:rgba(255,255,255,.75)}"
    ".pp-slot{position:relative;flex:0 1 122px;min-width:96px}"
    ".pp-slot .slot{width:100%;text-align:center;font-weight:700;"
    "font-size:13px;background:var(--surf);border:1px solid rgba(10,79,45,.45);"
    "border-radius:10px;padding:12px 8px;box-shadow:0 2px 6px rgba(0,0,0,.22)}"
    ".pp-slot .slot::placeholder{color:var(--ink3);font-weight:600;"
    "letter-spacing:.6px;text-transform:uppercase;font-size:11px}"
    ".pp-slot .cappick{position:absolute;top:-9px;right:-6px}"
    ".pp-slot .cappick span{width:22px;height:22px;font-size:10px;"
    "box-shadow:0 1px 3px rgba(0,0,0,.25)}"
    # the dugout: bench strip attached under the pitch
    ".pp-bench{background:var(--chipbg);border:1px solid var(--line);"
    "border-top:0;border-radius:0 0 14px 14px;padding:12px 16px 14px}"
    ".pp-bench .slot-head{margin-top:0;margin-bottom:8px}"
    ".pp-bench-slots{display:flex;gap:10px;flex-wrap:wrap}"
    ".pp-bench-slots .pp-slot{flex:1 1 110px}"
    ".pp-bench-slots .slot-bench{background:var(--surf)}"
    "@media(max-width:560px){.pp-pitch{padding:26px 10px 32px;min-height:340px;"
    "gap:16px}.pp-row{gap:8px}.pp-slot{flex:0 1 45%;min-width:0}"
    ".pp-lab{display:none}}"
)

# Half-pitch markings for the picker, same geometry as pitch_svg_fpl's
# 420x520 canvas (halfway line + centre arc at the top, penalty box, six-yard
# box, spot, D, goal mouth and corner arcs at the bottom); stretched to the
# picker's box with preserveAspectRatio="none". Decorative only.
_RATE_PITCH_LINES_SVG = (
    '<svg class="pp-lines" viewBox="0 0 420 520" preserveAspectRatio="none" '
    'xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">'
    '<g stroke="#fff" stroke-width="1.2" opacity=".4" fill="none">'
    '<rect x="14" y="14" width="392" height="492" rx="2"/>'
    '<path d="M 168 14 A 42 42 0 0 0 252 14"/>'
    '<rect x="104" y="432" width="212" height="74"/>'
    '<rect x="160" y="476" width="100" height="30"/>'
    '<path d="M 170 432 A 44 44 0 0 1 250 432"/>'
    '<rect x="170" y="506" width="80" height="6"/>'
    '<path d="M 14 494 A 12 12 0 0 0 26 506"/>'
    '<path d="M 394 506 A 12 12 0 0 0 406 494"/>'
    '</g>'
    '<circle cx="210" cy="14" r="2.5" fill="#fff" opacity=".4"/>'
    '<circle cx="210" cy="456" r="2.5" fill="#fff" opacity=".4"/>'
    '</svg>')

# XI rows on the pitch, top (attacking) to bottom (goal), 4-4-2. The rows are
# a visual guide only: every slot is the same free-text autocomplete input and
# rate.js reads slots in DOM order regardless of position, so any formation
# still rates correctly.
_RATE_PITCH_ROWS = (("FWD", 2), ("MID", 4), ("DEF", 4), ("GK", 1))


def _rate_pitch_picker_html(bench_hint: str) -> str:
    """The FPL /rate/ picker as a pitch: the same 11+4 .slot inputs and
    captain radios the grid picker carries (rate.js is untouched — selectors,
    data-bench attributes and DOM-order captain indices all match), laid out
    as positioned rows on the grass with the bench strip as a dugout below."""
    rows = []
    idx = 0
    for label, n in _RATE_PITCH_ROWS:
        slots = []
        for j in range(1, n + 1):
            ph = label if n == 1 else f"{label} {j}"
            slots.append(
                f'<div class="pp-slot"><input class="slot" list="players-dl" '
                f'data-bench="0" placeholder="{ph}" autocomplete="off" '
                f'spellcheck="false"><label class="cappick" title="captain">'
                f'<input type="radio" name="cap" value="{idx}"><span>C</span>'
                f'</label></div>')
            idx += 1
        rows.append(f'<div class="pp-row pp-{label.lower()}">'
                    f'<span class="pp-lab">{label}</span>{"".join(slots)}</div>')
    bench_slots = "".join(
        f'<div class="pp-slot"><input class="slot slot-bench" '
        f'list="players-dl" data-bench="1" placeholder="Bench {i}" '
        f'autocomplete="off" spellcheck="false"></div>'
        for i in range(1, 5))
    return (
        '<div class="pitch-picker" id="slot-grid">\n'
        '<div class="slot-head">Starting XI <span class="rate-hint">tap C to '
        'captain — any formation, the rows are just a guide</span></div>\n'
        f'<div class="pp-pitch">{_RATE_PITCH_LINES_SVG}{"".join(rows)}</div>\n'
        '<div class="pp-bench">\n'
        f'<div class="slot-head">Bench <span class="rate-hint">{bench_hint}'
        '</span></div>\n'
        f'<div class="pp-bench-slots">{bench_slots}</div>\n'
        '</div>\n'
        '</div>')


def rate_page(round_no: int, section=WC) -> str:
    """/rate/ -- paste-a-squad client-side team rater, serving whichever
    section built last.

    All computation happens in the browser (see /js/rate.js, fetched from the
    section's players feed, embedded via data-players-url below). This function
    only emits static markup + the <noscript> fallback; it makes no server-side
    prediction of the user's team.

    Section-aware copy only: an FPL build titles the page for FPL, states the
    15 = 2/5/5/3 squad shape, points at the gameweek feed and explains FPL's
    post-gameweek autosubs; a World Cup build keeps today's page byte-for-byte
    (including the manual-subs chain copy, which is a WC rule FPL lacks).
    """
    is_fpl = section.key != "round"
    json_url = section.players_json_path(round_no)
    if is_fpl:
        page_title = "Rate my FPL team"
        title = f"{page_title} | {TITLE_BRAND}"
        description = ("Paste your FPL squad and get an instant Monte-Carlo "
                       "projection, captain check and injury flags -- entirely in "
                       "your browser, nothing uploaded.")
        stand = ("Pick your 15 — 2 goalkeepers, 5 defenders, 5 midfielders, "
                 "3 forwards — and get instant Monte-Carlo projections, a captain "
                 "check and injury flags. Nothing leaves your browser.")
        # data-unit lets the shared rate.js label results "Gameweek N"; the WC
        # page omits the attribute and rate.js falls back to "Round".
        unit_attr = ' data-unit="Gameweek"'
        bench_hint = "counted separately — autosubs only fire after the gameweek"
        placeholder = ("Haaland (C), Saka, Virgil, Watkins (B), …  — comma or "
                       "newline separated, (C) marks captain, (B) marks bench")
        method_tail = ("Player names are matched against\n"
                       "this gameweek's projections entirely client-side against\n"
                       f'<a href="{json_url}" style="color:var(--greend)">{json_url}</a> '
                       "-- no squad is ever sent\n"
                       "to our servers or anyone else's. Mark bench players with (B): "
                       "they're shown with\nprojected points but left out of your "
                       "total. Your squad locks at the gameweek deadline --\nFPL's "
                       "automatic substitutions only fire after the gameweek ends, "
                       "replacing a starter\nwho recorded no minutes with the first "
                       "eligible name in your bench order -- so the\nbench is "
                       "insurance you set before the deadline, not a mid-week "
                       "decision.")
        # Owner correction 2026-08-25: the FPL picker looks like a pitch.
        picker = _rate_pitch_picker_html(bench_hint)
        pitch_css = _RATE_PITCH_CSS + _NAV_SCROLL_CSS
    else:
        page_title = "Rate my World Cup fantasy team"
        title = f"{page_title} | {TITLE_BRAND}"
        description = ("Paste your World Cup fantasy squad and get an instant Monte-Carlo "
                       "projection, captain check and injury flags -- entirely in your "
                       "browser, nothing uploaded.")
        stand = ("Pick your 15 — get instant Monte-Carlo projections, captain check,\n"
                 "sub-chain notes and injury flags. Nothing leaves your browser.")
        unit_attr = ""
        bench_hint = "counted separately, chain notes included"
        placeholder = ("Messi (C), Mbappé, Cunha, Freeman (B), …  — comma or "
                       "newline separated, (C) marks captain, (B) marks bench")
        method_tail = ("Player names are matched against\n"
                       "this round's projections entirely client-side against\n"
                       f'<a href="{json_url}" style="color:var(--greend)">{json_url}</a> '
                       "-- no squad is ever sent\n"
                       "to our servers or anyone else's. Mark bench players with (B): "
                       "they're shown with\nprojected points but left out of your total, "
                       "and flagged with a \"chain option\" note\nwhen a same-position "
                       "starter of yours kicks off earlier -- FIFA's automatic subs "
                       "only\nfire on a did-not-play at the very end of the round, but "
                       "manual subs are allowed up\nuntil the round's last kickoff, so a "
                       "strong bench pick with a later fixture is often a\ndeliberate "
                       "hedge, not a wasted slot.")
        # The World Cup picker keeps today's flat slot grid byte-for-byte.
        picker = f"""<div class="slot-grid" id="slot-grid">
<div class="slot-head">Starting XI <span class="rate-hint">tap C to captain</span></div>
{"".join(f'''<div class="slot-row"><input class="slot" list="players-dl" data-bench="0"
placeholder="Player {i}" autocomplete="off" spellcheck="false"><label class="cappick"
title="captain"><input type="radio" name="cap" value="{i - 1}"><span>C</span></label></div>''' for i in range(1, 12))}
<div class="slot-head">Bench <span class="rate-hint">{bench_hint}</span></div>
{"".join(f'''<div class="slot-row"><input class="slot slot-bench" list="players-dl" data-bench="1"
placeholder="Bench {i}" autocomplete="off" spellcheck="false"></div>''' for i in range(1, 5))}
</div>"""
        pitch_css = ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{_html.escape(description)}">
{_og_meta(
    page_title,
    description, "/rate/", "website")}
{GSC_META_TAG}
{_HEAD_COMMON}
{_FONTS}
<style>{_STYLE}{_RATE_CSS}{pitch_css}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{_nav_html(active="rate")}
</div></header>
<div class="wrap">
<div class="rate-wrap">
<div class="pagelabel" style="margin-top:34px">Interactive</div>
<h1>{page_title}</h1>
<p class="stand">{stand}</p>

<noscript><div class="rate-noscript">This tool needs JavaScript (self-hosted, no
tracking). Prefer no JS? The full projections are at
<a href="{json_url}">{json_url}</a> and in every article.</div></noscript>

<form class="rate-form" id="rate-form" data-round="{round_no}"{unit_attr} data-players-url="{json_url}">
<datalist id="players-dl"></datalist>
{picker}
<details class="rate-paste"><summary>prefer to paste the whole squad as text?</summary>
<textarea id="team-input" name="team" rows="6"
placeholder="{placeholder}"></textarea>
</details>
<div class="rate-actions">
<button type="submit" id="rate-btn">Rate my team</button>
<span class="rate-hint">or press &#8984;/Ctrl + Enter</span>
</div>
</form>

<div id="rate-results" aria-live="polite"></div>

<p class="method"><b>How this works.</b> {section.methodology} {method_tail}</p>
</div>
</div>
{_footer_html()}
<script src="/js/rate.js" defer></script>
</body></html>"""


