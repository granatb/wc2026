"""Player cards — per-player pages, JSON, tier boards and the landing module.

Phase 1 of the 2026/27 campaign (STRATEGY §12): the product face. One living
page per player under /fpl/players/{slug}/, a per-player JSON twin under
/api/fpl/gw{N}/players/{id}.json, an instant-search index at /fpl/players/,
one tier board per position under /fpl/tiers/{pos}/, and the "this week's top
cards" module the FPL landing embeds. All of it regenerated every gameweek —
these are living surfaces like the landing, NOT frozen articles.

Pure emitters + pure assembly only (mirrors evmax/render.py): the build
(evmax/fpl_build.py) does all I/O and hands everything in. No network, no
disk reads here.

DESIGN STATUS: the card face implements direction "A — Ledger" (owner
decision 2026-08-24): site-native editorial — paper/ink/green tokens, serif
name and hero number, an area-chart of the six-week vector as the stat-art
element (data-drawn, layered to suggest the simulation cloud), a
decomposition strip, difficulty-tinted fixture chips, and club SHORT-CODES in
club color only (no photos, no AI likenesses, no crests/kits — the legal line
from the same decision). The wordmark/logo is untouched site-wide.
  * ALL card styling lives in the single CARD_CSS block below;
  * the card markup (card_html) is semantic — figure.player-card with data-*
    attributes carrying the stats — so any further restyle never touches data.
"""
from __future__ import annotations

import html as _html
import json as _json
import unicodedata


# --- URL scheme --------------------------------------------------------------

PLAYERS_BASE = "/fpl/players"          # index + one dir per player
TIERS_BASE = "/fpl/tiers"              # one board per position

# Position vocabulary -> tier-board path segment, in board nav order.
TIER_SEGMENTS = (("GK", "gk"), ("DEF", "def"), ("MID", "mid"), ("FWD", "fwd"))
_SEGMENT_BY_POS = dict(TIER_SEGMENTS)


# Letters NFD cannot decompose (they are base letters, not letter+mark) that
# real web_names carry — Ø/ø (Ødegaard), Æ, ł (Kiwior teammates…), đ, ß.
_TRANSLIT = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE",
                           "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
                           "ß": "ss"})


def slugify(element_id: int, web_name: str) -> str:
    """"233-haaland" — element id (the stable key) + kebab web_name (the
    readable part). Diacritics stripped, anything non-alphanumeric collapsed
    to single hyphens, so "B.Fernandes" -> "58-b-fernandes" and renames only
    change the cosmetic tail, never the id the URL is keyed on."""
    decomposed = unicodedata.normalize("NFD",
                                       (web_name or "").translate(_TRANSLIT))
    ascii_name = "".join(c for c in decomposed
                         if unicodedata.category(c) != "Mn").lower()
    kebab = "".join(c if c.isalnum() else "-" for c in ascii_name)
    while "--" in kebab:
        kebab = kebab.replace("--", "-")
    kebab = kebab.strip("-")
    return f"{element_id}-{kebab}" if kebab else str(element_id)


def page_path(slug: str) -> str:
    return f"{PLAYERS_BASE}/{slug}/"


def json_path(gameweek: int, element_id: int) -> str:
    return f"/api/fpl/gw{gameweek}/players/{element_id}.json"


def tier_path(position: str) -> str:
    return f"{TIERS_BASE}/{_SEGMENT_BY_POS[position]}/"


# --- Verdicts ----------------------------------------------------------------

# S/A/B/C/D by x_points percentile WITHIN the player's position (a 5.5 xPts
# defender and a 5.5 xPts forward are different achievements). Cumulative
# fractions: S = top 5%, A = next 15%, B = next 30%, C = next 30%, D = rest.
_LETTER_CUTS = ((0.05, "S"), (0.20, "A"), (0.50, "B"), (0.80, "C"))

# Letter -> the one-word call. Placeholder heuristic for the scaffold: rank
# IS the framing until the transfer optimizer's horizon deltas feed this.
_CALL_BY_LETTER = {"S": "buy", "A": "buy", "B": "hold", "C": "hold", "D": "pass"}


def verdict_letters(rows: list) -> dict:
    """{row name: letter}. Ties broken by name so the boards are stable."""
    by_pos: dict = {}
    for r in rows:
        by_pos.setdefault(r.get("position"), []).append(r)
    out = {}
    for group in by_pos.values():
        ranked = sorted(group, key=lambda r: (-(r.get("x_points") or 0.0),
                                              r["name"]))
        n = len(ranked)
        for i, r in enumerate(ranked):
            frac = i / n
            letter = "D"
            for cut, lt in _LETTER_CUTS:
                if frac < cut:
                    letter = lt
                    break
            out[r["name"]] = letter
    return out


def rank_maps(rows: list) -> tuple:
    """(xpts_rank, own_rank) as {name: 1-based rank}. own_rank ranks by
    ownership DESC, so gap = own_rank - xpts_rank reads: positive = the crowd
    owns him less than the projection merits (under-owned)."""
    xp = sorted(rows, key=lambda r: (-(r.get("x_points") or 0.0), r["name"]))
    own = sorted(rows, key=lambda r: (-(r.get("ownership_pct") or 0.0),
                                      r["name"]))
    return ({r["name"]: i for i, r in enumerate(xp, 1)},
            {r["name"]: i for i, r in enumerate(own, 1)})


# --- Fixture strip -----------------------------------------------------------

def _difficulty(lam_for: float, lam_against: float) -> int:
    """1 (easiest) .. 5 (hardest) from the fixture's lambda differential seen
    from the player's team. Buckets are a scaffold placeholder — the design
    pass / strength-table work may re-derive them."""
    d = lam_against - lam_for
    if d <= -0.75:
        return 1
    if d <= -0.25:
        return 2
    if d < 0.25:
        return 3
    if d < 0.75:
        return 4
    return 5


def fixture_strip(team: str, gameweek: int, fx_rows: list, odds_by_gw: dict,
                  limit: int = 4) -> list:
    """The team's next `limit` fixtures from `gameweek` on, difficulty-priced
    where a lambda source exists.

    fx_rows: core.fpl_api.parse_fixtures output (the WHOLE season).
    odds_by_gw: {gw: odds payload dict} — each per-GW cache as stored under
    data/fpl/odds_gw{N}.json ({"matches": {match_id: {lam_home, lam_away,
    source?}}}). A missing cache or match degrades that fixture to
    source "unpriced" with a null difficulty — never a crash, never a guess.
    """
    mine = sorted((r for r in fx_rows
                   if r.get("fantasy_round", 0) >= gameweek
                   and team in (r.get("home"), r.get("away"))),
                  key=lambda r: (r["fantasy_round"], r.get("kickoff_utc") or ""))
    out = []
    for r in mine[:limit]:
        home = r["home"] == team
        entry = {
            "gw": r["fantasy_round"],
            "opponent": r["away"] if home else r["home"],
            "venue": "H" if home else "A",
            "kickoff": r.get("kickoff_utc"),
            "difficulty": None,
            "lam_for": None,
            "lam_against": None,
            "source": "unpriced",
        }
        odds = odds_by_gw.get(r["fantasy_round"]) or {}
        m = (odds.get("matches") or {}).get(r["match_id"])
        if m and m.get("lam_home") is not None and m.get("lam_away") is not None:
            lam_for = m["lam_home"] if home else m["lam_away"]
            lam_against = m["lam_away"] if home else m["lam_home"]
            entry.update({
                "difficulty": _difficulty(lam_for, lam_against),
                "lam_for": lam_for,
                "lam_against": lam_against,
                # Real market captures predate the source stamp; absent means
                # market (fdr_prior_* / strength_table_v1 stamp themselves).
                "source": m.get("source") or "market",
            })
        out.append(entry)
    return out


# --- Payload assembly ---------------------------------------------------------

# Reserved distribution shape (per-player JSON `distribution`): once the
# engine captures per-sim histograms into the artifact (follow-up task), the
# key becomes {"p10", "p25", "median", "p75", "mode", "ceiling",
# "histogram": []}. Until then it is emitted as null so consumers can key on
# it today without a schema break later.
DISTRIBUTION_RESERVED = None

_PROJECTION_FIELDS = ("x_points", "captain_ev", "ceiling", "value", "bonus",
                      "defcon", "p_defcon", "cs_points", "start_prob")


def assemble_payloads(rows: list, players_by_name: dict, elements_by_id: dict,
                      notes: dict, squad_names: dict, six_week,
                      fx_rows: list, odds_by_gw: dict, gameweek: int,
                      generated_at: str) -> tuple:
    """(payloads sorted by x_points desc, [unmatched row names]).

    rows: the gameweek artifact rows (disambiguated names).
    players_by_name: {disambiguated name: parsed bootstrap player} (has "id").
    elements_by_id: {element id: RAW bootstrap element} — season totals
      (total_points/event_points) live only on the raw feed.
    notes: research.load_entries("players", gameweek).
    squad_names: {"model": set of names, "consensus": set} from the two
      published squads' article entries (already row-matched by the build).
    six_week: the horizon matrix (data/fpl/xpts_gw*.json payload) or None —
      absent cache degrades six_week_xpts to null per player.
    A row whose name no longer matches the bootstrap (cached artifact vs a
    renamed player) is skipped and reported, never guessed at.
    """
    letters = verdict_letters(rows)
    xp_rank, own_rank = rank_maps(rows)
    from evmax.articles import player_flag, price_tier

    payloads, unmatched = [], []
    for r in sorted(rows, key=lambda r: (-(r.get("x_points") or 0.0),
                                         r["name"])):
        name = r["name"]
        p = players_by_name.get(name)
        el = elements_by_id.get((p or {}).get("id"))
        if p is None or el is None:
            unmatched.append(name)
            continue
        pid = p["id"]
        slug = slugify(pid, el.get("web_name") or name)
        letter = letters[name]
        price = r.get("price")
        total_points = el.get("total_points") or 0
        sw = None
        if six_week:
            rec = six_week.get(name)
            if rec and rec.get("gw"):
                sw = rec["gw"]
        payloads.append({
            "gameweek": gameweek,
            "generated_at": generated_at,
            "id": pid,
            "name": name,
            "web_name": el.get("web_name") or name,
            "team": r.get("team"),
            "position": r.get("position"),
            "price": price,
            "ownership_pct": r.get("ownership_pct"),
            "status": el.get("status", "a"),
            "news": el.get("news", ""),
            "flag": player_flag(name, notes),
            "kickoff": r.get("kickoff"),
            "projection": {f: r.get(f) for f in _PROJECTION_FIELDS},
            "season": {
                "total_points": total_points,
                "event_points": el.get("event_points") or 0,
                "minutes": el.get("minutes") or 0,
                "realized_ppm": (round(total_points / price, 2)
                                 if price else None),
            },
            "ranks": {
                "xpts_rank": xp_rank[name],
                "own_rank": own_rank[name],
                "own_vs_xpts_gap": own_rank[name] - xp_rank[name],
            },
            "verdict_tier": letter,
            "verdict": {
                "tier": letter,
                "price_band": price_tier(price),
                "call": _CALL_BY_LETTER[letter],
            },
            "six_week_xpts": sw,
            "fixtures": fixture_strip(r.get("team"), gameweek, fx_rows,
                                      odds_by_gw),
            "squads": {
                "model": name in squad_names.get("model", ()),
                "consensus": name in squad_names.get("consensus", ()),
            },
            "notes": [name] if name in notes else [],
            "distribution": DISTRIBUTION_RESERVED,
            "page": page_path(slug),
            "slug": slug,
        })
    return payloads, unmatched


def player_json(payload: dict, methodology: str, site_url: str,
                license_url: str, license_text: str) -> dict:
    """The public per-player JSON envelope: the payload + the same
    provenance/licensing block every other feed on the site carries."""
    env = dict(payload)
    env.pop("slug", None)          # page is the public pointer; slug is internal
    env.update({
        "methodology": methodology,
        "source": site_url,
        "license": license_url,
        "license_text": license_text,
    })
    return env


# =============================================================================
# CARD STYLE — DIRECTION "A: LEDGER" (owner decision 2026-08-24)
# =============================================================================
# Everything visual about the card, the top-cards landing module, the players
# index and the tier boards lives in THIS ONE BLOCK — site palette only (paper
# --bg/--surf, ink --ink*, green --green accents), club COLOR only (the
# .club-* classes below), no images, no club assets. The markup in card_html
# is semantic and carries the stats as data-* attributes, so any further
# restyle should not need to touch any emitter.
# =============================================================================

# Club short-code accent colors (color only — never a crest or kit design,
# per the stat-art decision). Light kit colors are darkened for contrast on
# the paper background; an unmapped club falls back to var(--ink2).
CLUB_COLORS = {
    "ARS": "#c2000b", "AVL": "#670e36", "BOU": "#b3001e", "BRE": "#c30610",
    "BHA": "#0057b8", "BUR": "#6c1d45", "CHE": "#034694", "CRY": "#1b458f",
    "EVE": "#003399", "FUL": "#15140f", "LEE": "#9c7c00", "LIV": "#c8102e",
    "MCI": "#1e6f9c", "MUN": "#b7000f", "NEW": "#241f20", "NFO": "#b30000",
    "SUN": "#c8102e", "TOT": "#132257", "WHU": "#7a263a", "WOL": "#a87c00",
}

# Decomposition strip segment colors (spec: #0f7a45/#3E8E8C/#A8925A/#C9A227).
_DECOMP_SEGMENTS = (
    ("attack", "#0f7a45", "Goals, assists & appearance"),
    ("cs", "#3e8e8c", "Clean sheets (per-match est.)"),
    ("defcon", "#a8925a", "Defensive contribution (per-match est.)"),
    ("bonus", "#c9a227", "Bonus (per-match est.)"),
)

CARD_CSS = (
    # -- the card face (player pages + anything embedding card_html) --------
    ".player-card{background:var(--surf);border:1px solid var(--line);"
    "border-radius:14px;padding:18px;margin:6px 0 26px;"
    "box-shadow:0 1px 3px rgba(21,20,15,.08)}"
    ".player-card .pc-head{display:block;margin:0}"
    ".player-card .pc-toprow{display:flex;align-items:center;"
    "justify-content:space-between;gap:10px;margin-bottom:10px}"
    ".pc-tier{display:inline-flex;align-items:center;gap:6px;font-size:11px;"
    "font-weight:800;letter-spacing:1.4px;text-transform:uppercase;"
    "color:var(--greend);background:#eaf3ec;border-radius:8px;padding:4px 9px}"
    ".player-card .pc-clubcode{font-size:12px;font-weight:800;"
    "letter-spacing:1.6px;color:var(--ink2)}"
    + "".join(f".player-card .club-{code}{{color:{color}}}"
              for code, color in CLUB_COLORS.items()) +
    ".player-card .pc-name{font-family:var(--serif),Georgia,serif;"
    "font-size:25px;font-weight:700;line-height:1.1;margin:0;"
    "letter-spacing:-.3px}"
    ".player-card .pc-meta{font-size:12.5px;color:var(--ink3);margin-top:2px}"
    ".player-card .pc-hero{display:flex;align-items:baseline;gap:7px;"
    "margin:10px 0 4px}"
    ".player-card .pc-hero b{font-family:var(--serif),Georgia,serif;"
    "font-size:44px;font-weight:700;color:var(--greend);line-height:1;"
    "font-variant-numeric:tabular-nums}"
    ".player-card .pc-hero span{font-size:11px;font-weight:700;"
    "letter-spacing:1px;text-transform:uppercase;color:var(--ink3)}"
    ".player-card .pc-news{font-size:13px;color:#a8331c;background:#fdeee9;"
    "border-radius:8px;padding:8px 12px;margin:10px 0 2px}"
    # form art: layered area chart of the six-week vector (the sim cloud)
    ".player-card .pc-sixweek{margin:8px 0 2px}"
    ".player-card .pc-sixweek svg{display:block;width:100%;height:60px}"
    # decomposition strip: thin stacked segments, rounded
    ".player-card .pc-decomp{display:flex;height:8px;border-radius:4px;"
    "overflow:hidden;margin:10px 0 2px;background:var(--chipbg)}"
    ".player-card .pc-decomp span{display:block;height:100%}"
    + "".join(f".player-card .pcd-{key}{{background:{color}}}"
              for key, color, _label in _DECOMP_SEGMENTS) +
    # stat rows: ceiling · captain · own / season pts · realized · gap
    ".player-card .pc-statrow{display:flex;justify-content:space-between;"
    "gap:10px;flex-wrap:wrap;font-size:11.5px;color:var(--ink2);"
    "margin-top:8px;font-variant-numeric:tabular-nums}"
    ".player-card .pc-statrow b{font-weight:800;color:var(--ink)}"
    ".player-card .pc-statrow.pc-statrow2{color:var(--ink3);margin-top:4px}"
    # fixture strip: next-4 chips, difficulty tinted (green = easy per
    # lambda, warm = hard, gray + dashed = unpriced)
    ".player-card .pc-fixtures{display:flex;gap:6px;flex-wrap:wrap;"
    "margin-top:12px;padding-top:12px;border-top:1px solid var(--line)}"
    ".player-card .fx{display:inline-flex;align-items:baseline;gap:6px;"
    "font-size:11px;font-weight:700;border-radius:8px;padding:4px 9px;"
    "background:var(--chipbg);color:var(--ink2)}"
    ".player-card .fx i{font-style:normal;font-weight:600;font-size:10px;"
    "color:var(--ink3)}"
    ".player-card .fx-d1,.player-card .fx-d2{background:#eaf3ec;"
    "color:var(--greend)}"
    ".player-card .fx-d4,.player-card .fx-d5{background:#fdeee9;"
    "color:#a8331c}"
    ".player-card .fx-unpriced{background:var(--chipbg);color:var(--ink3);"
    "border:1px dashed var(--line);font-weight:600}"
    # verdict line
    ".player-card .pc-verdict{font-size:12px;font-weight:800;"
    "letter-spacing:1.2px;text-transform:uppercase;color:var(--green);"
    "border-top:1px solid var(--line);margin-top:12px;padding-top:10px}"
    # -- the premium slot (decision 2026-08-24: reserved from day one,
    #    ships ~GW10+; muted + lock glyph until then) ------------------------
    ".player-card .pc-premium{font-size:10.5px;font-weight:700;"
    "letter-spacing:.6px;text-transform:uppercase;color:#b9b2a4;"
    "margin-top:10px}"
    ".player-card .pc-premium .pc-lock{margin-right:5px}"
    ".player-card .pc-premium .pc-dist-chart{height:14px;border-radius:4px;"
    "background:repeating-linear-gradient(90deg,var(--chipbg),"
    "var(--chipbg) 5px,var(--surf) 5px,var(--surf) 10px);margin-top:6px}"
    # -- player page below-the-card pieces ----------------------------------
    ".pd-table{width:100%;border-collapse:collapse;margin:8px 0 6px;"
    "font-family:var(--sans)}"
    ".pd-table th{font-size:11px;font-weight:700;letter-spacing:1px;"
    "text-transform:uppercase;color:var(--ink3);text-align:left;"
    "padding:10px 10px;border-bottom:2px solid var(--ink)}"
    ".pd-table td{padding:10px;border-bottom:1px solid var(--line);"
    "font-size:14.5px;font-variant-numeric:tabular-nums}"
    ".pd-table td:last-child{text-align:right;font-weight:700}"
    ".pc-provenance{font-size:13px;color:var(--ink3);margin:14px 0}"
    # -- "this week's top cards" landing module ------------------------------
    ".tc-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;"
    "margin-top:8px}"
    ".tc-card{background:var(--surf);border:1px solid var(--line);"
    "border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;"
    "gap:4px;transition:border-color .12s,transform .12s}"
    ".tc-card:hover{border-color:var(--green);transform:translateY(-2px)}"
    ".tc-card .tc-club{font-size:10.5px;font-weight:700;color:var(--ink3);"
    "text-transform:uppercase;letter-spacing:.8px;display:flex;"
    "justify-content:space-between;align-items:center}"
    ".tc-card h3{font-family:var(--serif),Georgia,serif;font-size:17px;"
    "font-weight:700;letter-spacing:-.2px}"
    ".tc-card .tc-xp{font-family:var(--serif),Georgia,serif;font-size:20px;"
    "font-weight:700;color:var(--greend);font-variant-numeric:tabular-nums}"
    ".tc-card .tc-xp span{font-size:10.5px;color:var(--ink3);font-weight:600;"
    "text-transform:uppercase;letter-spacing:.5px;margin-left:5px}"
    ".tc-all{margin:14px 0 4px;font-size:13.5px;font-weight:600}"
    ".tc-all a{color:var(--green)}"
    "@media(max-width:760px){.tc-grid{grid-template-columns:repeat(2,1fr)}}"
    # -- players index (search) ----------------------------------------------
    ".pi-search{margin:18px 0 8px}"
    "#player-search{width:100%;max-width:420px;font-family:var(--sans);"
    "font-size:15px;color:var(--ink);background:var(--surf);"
    "border:1px solid var(--line);border-radius:10px;padding:12px 16px}"
    "#player-search:focus{outline:2px solid var(--green);outline-offset:1px}"
    "#player-search-results{margin:8px 0}"
    ".pi-hint{font-size:12.5px;color:var(--ink3);margin-top:6px}"
    ".tier-nav{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 18px}"
    ".tier-nav a{font-size:13px;font-weight:700;color:var(--ink2);"
    "background:var(--chipbg);border:1px solid var(--line);"
    "border-radius:20px;padding:5px 13px}"
    ".tier-nav a:hover{border-color:var(--green);color:var(--greend)}"
    ".tier-nav a.active{background:var(--green);border-color:var(--green);"
    "color:#fff}"
    ".pi-letter{display:inline-flex;align-items:center;justify-content:center;"
    "min-width:22px;height:22px;border-radius:6px;background:var(--chipbg);"
    "color:var(--ink2);font-weight:800;font-size:12px}"
)
# =============================================================================
# END CARD STYLE PLACEHOLDER
# =============================================================================


# --- HTML emitters ------------------------------------------------------------

def _fmt(v, digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}" if isinstance(v, float) else str(v)


def _smooth_path(points: list) -> str:
    """Catmull-Rom-derived cubic Bezier path through `points` [(x, y), ...].
    Pure geometry, deterministic, no dependencies."""
    if len(points) < 2:
        return ""
    d = [f"M{points[0][0]:.1f},{points[0][1]:.1f}"]
    n = len(points)
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < n else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        d.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} "
                 f"{p2[0]:.1f},{p2[1]:.1f}")
    return "".join(d)


# Form-art geometry: 300x60 viewBox, 4 layers. The jitter is a fixed
# sinusoid per (layer, index) — deterministic, so a rebuild with unchanged
# inputs emits byte-identical pages (no RNG anywhere in the site layer).
_FORM_W, _FORM_H, _FORM_TOP = 300.0, 60.0, 8.0
_FORM_LAYERS = 4
_FORM_JITTER = 0.10


def _form_svg(six_week: dict) -> str:
    """The card's stat-art element: a layered area chart of the six-week
    xPts vector — the extra translucent layers suggest the simulation cloud
    around the central estimate. Returns "" when there is nothing to draw."""
    import math

    try:
        series = sorted(((int(k), float(v)) for k, v in six_week.items()),
                        key=lambda kv: kv[0])
    except (TypeError, ValueError):
        return ""
    if len(series) < 2:
        return ""
    gws = [gw for gw, _v in series]
    values = [v for _gw, v in series]

    layers = [values]
    for k in range(1, _FORM_LAYERS):
        layers.append([v * (1 + _FORM_JITTER * math.sin(i * 2.399 + k * 1.913))
                       for i, v in enumerate(values)])
    vmax = max(v for layer in layers for v in layer)
    if vmax <= 0:
        return ""

    step = _FORM_W / (len(values) - 1)
    usable = _FORM_H - _FORM_TOP - 4.0

    def pts(layer):
        return [(i * step,
                 _FORM_H - 4.0 - (v / vmax) * usable)
                for i, v in enumerate(layer)]

    shapes = []
    for k, layer in enumerate(reversed(layers)):        # cloud first, line last
        is_line = (k == _FORM_LAYERS - 1)               # the true series
        path = _smooth_path(pts(layer))
        area = f"{path}L{_FORM_W:.1f},{_FORM_H:.1f}L0,{_FORM_H:.1f}Z"
        if is_line:
            shapes.append(f'<path d="{area}" fill="#0f7a45" '
                          f'fill-opacity=".16" stroke="none"/>')
            shapes.append(f'<path d="{path}" fill="none" stroke="#0a4f2d" '
                          f'stroke-width="1.5"/>')
        else:
            shapes.append(f'<path d="{area}" fill="#0f7a45" '
                          f'fill-opacity=".08" stroke="none"/>')
    ticks = (f'<text x="1" y="{_FORM_H - 1:.0f}" font-size="9" '
             f'fill="#8a8275">GW{gws[0]}</text>'
             f'<text x="{_FORM_W - 1:.0f}" y="{_FORM_H - 1:.0f}" '
             f'font-size="9" text-anchor="end" fill="#8a8275">'
             f'GW{gws[-1]}</text>')
    title = " · ".join(f"GW{gw} {v:.2f}" for gw, v in series)
    return (f'<svg viewBox="0 0 {_FORM_W:.0f} {_FORM_H:.0f}" '
            f'preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg" '
            f'role="img" aria-label="Six-gameweek expected-points form">'
            f'<title>{_html.escape(title)}</title>{"".join(shapes)}{ticks}'
            f'</svg>')


def _decomp_html(proj: dict) -> str:
    """The decomposition strip: thin stacked segments of the projection.
    cs/defcon/bonus are per-match estimates (games/fpl/model._derive_row's
    unit warning) — the title attrs say so; the attack segment is the
    remainder. Skipped entirely when x_points isn't positive."""
    xp = proj.get("x_points") or 0.0
    if xp <= 0:
        return ""
    parts = {"cs": max(proj.get("cs_points") or 0.0, 0.0),
             "defcon": max(proj.get("defcon") or 0.0, 0.0),
             "bonus": max(proj.get("bonus") or 0.0, 0.0)}
    parts["attack"] = max(xp - sum(parts.values()), 0.0)
    total = sum(parts.values())
    if total <= 0:
        return ""
    spans = []
    for key, _color, label in _DECOMP_SEGMENTS:
        v = parts[key]
        if v <= 0:
            continue
        spans.append(f'<span class="pcd-{key}" '
                     f'style="width:{v / total * 100:.1f}%" '
                     f'title="{_html.escape(label)} — {v:.2f} xPts"></span>')
    return (f'<div class="pc-decomp" role="img" aria-label="Projection '
            f'decomposition">{"".join(spans)}</div>')


def card_html(payload: dict, heading: str = "h1") -> str:
    """The card face (direction A — Ledger): semantic figure.player-card,
    stats duplicated as data-* attributes so scripts/design tooling can read
    them without parsing text. `heading` is the element used for the player
    name — "h1" on his own page, "h2" when embedded elsewhere."""
    proj = payload["projection"]
    season = payload["season"]
    ranks = payload["ranks"]
    verdict = payload["verdict"]
    name = _html.escape(payload["name"])
    team = payload["team"] or ""
    gap = ranks["own_vs_xpts_gap"]

    news_html = ""
    if payload.get("news"):
        news_html = (f'<p class="pc-news">{_html.escape(payload["news"])}'
                     f' <small>(status: {_html.escape(payload["status"])})</small></p>')

    club_cls = f" club-{team}" if team in CLUB_COLORS else ""
    head_html = (
        f'<figcaption class="pc-head">'
        f'<div class="pc-toprow">'
        f'<span class="pc-tier">Tier {verdict["tier"]} · '
        f'{verdict["price_band"]}</span>'
        f'<span class="pc-clubcode{club_cls}">{_html.escape(team)}</span>'
        f'</div>'
        f'<{heading} class="pc-name">{name}</{heading}>'
        f'<div class="pc-meta">{_html.escape(payload["position"] or "")} · '
        f'£{_fmt(payload["price"], 1)}m · Gameweek {payload["gameweek"]}</div>'
        f'</figcaption>')

    hero_html = (f'<div class="pc-hero"><b>{_fmt(proj.get("x_points"))}</b>'
                 f'<span>xPts this gameweek</span></div>')

    sw_html = ""
    if payload.get("six_week_xpts"):
        svg = _form_svg(payload["six_week_xpts"])
        if svg:
            sw_html = f'<div class="pc-sixweek">{svg}</div>'

    statrow = (
        f'<div class="pc-statrow">'
        f'<span>ceiling <b>{_fmt(proj.get("ceiling"))}</b></span>'
        f'<span>captain EV <b>{_fmt(proj.get("captain_ev"))}</b></span>'
        f'<span>owned <b>{_fmt(payload.get("ownership_pct"), 1)}%</b></span>'
        f'</div>'
        f'<div class="pc-statrow pc-statrow2">'
        f'<span>season <b>{season["total_points"]} pts</b></span>'
        f'<span>realized <b>{_fmt(season["realized_ppm"])} pts/£m</b></span>'
        f'<span>own vs xPts rank <b>{gap:+d}</b></span>'
        f'</div>')

    fx_html = ""
    if payload["fixtures"]:
        cells = []
        for f in payload["fixtures"]:
            if f["difficulty"] is None:
                cls, dattr = "fx-unpriced", ""
                title = f'GW{f["gw"]} · unpriced'
            else:
                cls, dattr = f'fx-d{f["difficulty"]}', f["difficulty"]
                title = (f'GW{f["gw"]} · difficulty {f["difficulty"]}/5 '
                         f'({f["source"]})')
            cells.append(
                f'<span class="fx {cls}" data-gw="{f["gw"]}" '
                f'data-difficulty="{dattr}" '
                f'data-source="{_html.escape(f["source"])}" '
                f'title="{_html.escape(title)}">'
                f'{_html.escape(f["opponent"])} ({f["venue"]})'
                f'<i>GW{f["gw"]}</i></span>')
        fx_html = f'<div class="pc-fixtures">{"".join(cells)}</div>'

    verdict_html = (f'<div class="pc-verdict">{verdict["call"]} · '
                    f'tier {verdict["tier"]} · {verdict["price_band"]}</div>')

    # Premium slot (decision 2026-08-24): reserved from day one, muted with a
    # lock glyph until ~GW10+; the striped strip is the distribution chart's
    # reserved space.
    premium_html = (
        '<div class="pc-premium"><span class="pc-lock">🔒</span>'
        'Premium — coming soon: full distribution · your-team fit'
        '<div class="pc-dist-chart"></div></div>')

    return (
        f'<figure class="player-card" data-id="{payload["id"]}" '
        f'data-team="{_html.escape(team)}" '
        f'data-position="{_html.escape(payload["position"] or "")}" '
        f'data-price="{payload["price"]}" '
        f'data-x-points="{proj.get("x_points")}" '
        f'data-ceiling="{proj.get("ceiling")}" '
        f'data-captain-ev="{proj.get("captain_ev")}" '
        f'data-ownership="{payload.get("ownership_pct")}" '
        f'data-own-gap="{gap}" '
        f'data-season-points="{season["total_points"]}" '
        f'data-tier="{verdict["tier"]}" '
        f'data-price-band="{verdict["price_band"]}" '
        f'data-call="{verdict["call"]}" '
        f'data-status="{_html.escape(payload["status"])}">'
        f'{head_html}'
        f'{news_html}'
        f'{hero_html}'
        f'{sw_html}'
        f'{_decomp_html(proj)}'
        f'{statrow}'
        f'{fx_html}'
        f'{verdict_html}'
        f'{premium_html}'
        f'</figure>')


def top_cards_html(payloads: list, count: int = 6) -> str:
    """The FPL landing's "this week's top cards" module: compact thumbnails
    for the top `count` by x_points, each opening the player page; the module
    itself opens the searchable index (decision 2026-08-24)."""
    cards = []
    for p in payloads[:count]:
        cards.append(
            f'<a class="tc-card" href="{page_path(p["slug"])}" '
            f'data-id="{p["id"]}" data-tier="{p["verdict"]["tier"]}">'
            f'<span class="tc-club">{_html.escape(p["team"] or "")} · '
            f'{_html.escape(p["position"] or "")}'
            f'<span class="pc-tier">{p["verdict"]["tier"]}</span></span>'
            f'<h3>{_html.escape(p["name"])}</h3>'
            f'<span class="tc-xp">{_fmt(p["projection"].get("x_points"))}'
            f'<span>xPts</span></span>'
            f'</a>')
    return (
        '<section class="top-cards">'
        '<div class="pagelabel">This week\'s top cards</div>'
        f'<div class="tc-grid">{"".join(cards)}</div>'
        f'<p class="tc-all"><a href="{PLAYERS_BASE}/">Check your player — '
        'search all cards →</a></p>'
        '</section>')


def _tier_nav_html(active: str = None) -> str:
    idx_cls = ' class="active"' if active == "index" else ""
    links = [f'<a href="{PLAYERS_BASE}/"{idx_cls}>All players</a>']
    for pos, seg in TIER_SEGMENTS:
        cls = ' class="active"' if active == pos else ""
        links.append(f'<a href="{TIERS_BASE}/{seg}/"{cls}>{pos} tiers</a>')
    return f'<nav class="tier-nav">{"".join(links)}</nav>'


def _page_shell(title: str, description: str, canonical_path: str,
                body: str, head_extra: str = "") -> str:
    """Shared chrome for the player surfaces — same header/nav/footer as every
    other page, CARD_CSS appended as the one extra style block."""
    from evmax import render
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(title)} | {render.TITLE_BRAND}</title>
<meta name="description" content="{_html.escape(description)}">
{head_extra}{render._og_meta(title, description, canonical_path, "website")}
{render.GSC_META_TAG}
{render._HEAD_COMMON}
{render._FONTS}
<style>{render._STYLE}{CARD_CSS}</style>
</head><body>
<header><div class="wrap" style="display:flex;align-items:center;height:100%;width:100%">
<a class="logo" href="/">ev<b>max</b></a>{render._nav_html()}
</div></header>
<div class="wrap">
{body}
</div>
{render._footer_html()}"""


def player_page_html(payload: dict, gameweek: int, date_str: str = None,
                     methodology: str = "") -> str:
    """One player's living page: card on top, the full data table below,
    note provenance, and the JSON twin declared via <link rel=alternate>.
    Regenerated every gameweek — never frozen."""
    name = payload["name"]
    proj = payload["projection"]
    title = (f"{name} — FPL Gameweek {gameweek} projection, "
             f"{_fmt(proj.get('x_points'))} xPts")
    description = (f"{name} ({payload['team']}, {payload['position']}): "
                   f"{_fmt(proj.get('x_points'))} expected points in Gameweek "
                   f"{gameweek}, tier {payload['verdict']['tier']}, "
                   f"£{_fmt(payload['price'], 1)}m. From 50,000 Monte-Carlo "
                   f"simulations, regenerated every gameweek.")
    jpath = json_path(gameweek, payload["id"])
    head_extra = (f'<link rel="alternate" type="application/json" '
                  f'href="{jpath}">\n')

    rows = [
        ("Expected points (xPts)", _fmt(proj.get("x_points"))),
        ("Captain EV", _fmt(proj.get("captain_ev"))),
        ("Ceiling (best 15% of sims)", _fmt(proj.get("ceiling"))),
        ("Projected pts/£m", _fmt(proj.get("value"), 3)),
        ("Expected bonus (per match)", _fmt(proj.get("bonus"))),
        ("DefCon points (per match)", _fmt(proj.get("defcon"))),
        ("P(DefCon threshold)", _fmt(proj.get("p_defcon"), 3)),
        ("Clean-sheet points (per match)", _fmt(proj.get("cs_points"))),
        ("Start probability", _fmt(proj.get("start_prob"), 2)),
        ("Price", f'£{_fmt(payload["price"], 1)}m'),
        ("Ownership", f'{_fmt(payload.get("ownership_pct"), 1)}%'),
        ("xPts rank / ownership rank",
         f'{payload["ranks"]["xpts_rank"]} / {payload["ranks"]["own_rank"]}'),
        ("Season points (minutes)",
         f'{payload["season"]["total_points"]} '
         f'({payload["season"]["minutes"]}′)'),
        ("Realized pts/£m", _fmt(payload["season"]["realized_ppm"])),
        ("Verdict",
         f'{payload["verdict"]["tier"]} · {payload["verdict"]["price_band"]}'
         f' · {payload["verdict"]["call"]}'),
    ]
    table = ("".join(f'<tr><td>{_html.escape(k)}</td><td>{v}</td></tr>'
                     for k, v in rows))
    table_html = (f'<table class="pd-table"><thead><tr>'
                  f'<th>Metric</th><th>Gameweek {gameweek}</th></tr></thead>'
                  f'<tbody>{table}</tbody></table>')

    if payload["notes"]:
        note_names = ", ".join(_html.escape(n) for n in payload["notes"])
        provenance = (f'<p class="pc-provenance">Research notes on file: '
                      f'{note_names}. Notes carry sourced minutes/rotation '
                      f'judgement that overrides the raw model.</p>')
    else:
        provenance = ('<p class="pc-provenance">No research notes on file '
                      'for this player this gameweek — the numbers above are '
                      'pure model output.</p>')

    squad_line = ""
    memberships = [label for key, label in
                   (("model", "our model squad"),
                    ("consensus", "the consensus XI"))
                   if payload["squads"].get(key)]
    if memberships:
        squad_line = (f'<p class="pc-provenance">Currently in '
                      f'{" and ".join(memberships)}.</p>')

    byline_date = f" · {_html.escape(date_str)}" if date_str else ""
    body = f"""<article class="art">
<div class="kick">Player card · Gameweek {gameweek}</div>
{card_html(payload)}
<div class="meta"><span class="av">e</span><span>By the evmax model{byline_date} · regenerated every gameweek</span></div>
<div class="prose">
<h2>The data</h2>
{table_html}
{provenance}
{squad_line}
<p class="method"><b>How we get these numbers.</b> {methodology}
Machine-readable at <a href="{jpath}" style="color:var(--greend)">{jpath}</a>.</p>
</div>
</article>"""
    return _page_shell(title, description, page_path(payload["slug"]), body,
                       head_extra=head_extra) + "</body></html>"


def index_page_html(payloads: list, gameweek: int, players_json_url: str,
                    date_str: str = None) -> str:
    """/fpl/players/ — "Check your player": instant client-side search
    (first-party /js/players.js over the bulk players feed) over a no-JS
    alphabetical table fallback that always renders."""
    title = "Check your player — FPL player cards"
    description = ("Search every Premier League player's card: expected "
                   f"points, ceiling, value and verdict tier for Gameweek "
                   f"{gameweek}, from 50,000 Monte-Carlo simulations.")
    rows = sorted(payloads, key=lambda p: p["slug"].split("-", 1)[-1])
    trs = "".join(
        f'<tr><td><a href="{page_path(p["slug"])}" class="nm" '
        f'style="color:var(--greend)">{_html.escape(p["name"])}</a></td>'
        f'<td>{_html.escape(p["team"] or "")}</td>'
        f'<td>{_html.escape(p["position"] or "")}</td>'
        f'<td><span class="pi-letter">{p["verdict"]["tier"]}</span></td>'
        f'<td>{_fmt(p["projection"].get("x_points"))}</td>'
        f'<td>£{_fmt(p["price"], 1)}m</td></tr>'
        for p in rows)
    table = (f'<table class="pd-table" id="player-index-table"><thead><tr>'
             f'<th>Player</th><th>Team</th><th>Pos</th><th>Tier</th>'
             f'<th>xPts</th><th>Price</th></tr></thead>'
             f'<tbody>{trs}</tbody></table>')

    byline_date = f" · {_html.escape(date_str)}" if date_str else ""
    body = f"""<div class="rate-wrap" style="max-width:860px">
<div class="pagelabel" style="margin-top:34px">Player cards · Gameweek {gameweek}</div>
<h1>Check your player</h1>
<p class="stand">Every player's card: this week's projection, ceiling, value
and a verdict tier — regenerated each gameweek from 50,000 simulations.{byline_date}</p>
{_tier_nav_html(active="index")}
<form class="pi-search" id="player-search-form" data-players-url="{players_json_url}">
<input type="search" id="player-search" placeholder="Type a player's name…"
 autocomplete="off" spellcheck="false" aria-label="Search players">
<p class="pi-hint">Search runs entirely in your browser against
<a href="{players_json_url}" style="color:var(--greend)">{players_json_url}</a>
— nothing you type is sent anywhere.</p>
</form>
<div id="player-search-results" aria-live="polite"></div>
<noscript><div class="rate-noscript" style="background:var(--chipbg);border:1px solid var(--line);border-radius:12px;padding:14px 18px;font-size:13.5px;color:var(--ink2)">Search needs JavaScript
(self-hosted, no tracking). The full alphabetical table below works without it.</div></noscript>
{table}
</div>"""
    return (_page_shell(title, description, f"{PLAYERS_BASE}/", body)
            + '\n<script src="/js/players.js" defer></script>'
            + "</body></html>")


_TIER_LABEL = {"S": "S — elite this week", "A": "A — strong",
               "B": "B — solid", "C": "C — fringe", "D": "D — avoid"}
_POSITION_LABEL = {"GK": "Goalkeepers", "DEF": "Defenders",
                   "MID": "Midfielders", "FWD": "Forwards"}


def tier_page_html(position: str, payloads: list, gameweek: int,
                   date_str: str = None) -> str:
    """/fpl/tiers/{pos}/ — one plain, table-based board per position, players
    grouped S→D with letter, this-week xPts and price. The design pass will
    restyle; the scaffold keeps it legible and crawlable."""
    label = _POSITION_LABEL[position]
    title = f"{label} tier list — FPL Gameweek {gameweek}"
    description = (f"Every {label.lower().rstrip('s')} tiered S to D by "
                   f"Gameweek {gameweek} expected points, from 50,000 "
                   f"Monte-Carlo simulations. Regenerated every gameweek.")
    mine = sorted((p for p in payloads if p["position"] == position),
                  key=lambda p: (-(p["projection"].get("x_points") or 0.0),
                                 p["name"]))
    groups = []
    for letter in "SABCD":
        members = [p for p in mine if p["verdict"]["tier"] == letter]
        if not members:
            continue
        trs = "".join(
            f'<tr><td><a href="{page_path(p["slug"])}" '
            f'style="color:var(--greend)">{_html.escape(p["name"])}</a></td>'
            f'<td>{_html.escape(p["team"] or "")}</td>'
            f'<td>{_fmt(p["projection"].get("x_points"))}</td>'
            f'<td>£{_fmt(p["price"], 1)}m</td></tr>'
            for p in members)
        groups.append(
            f'<h2 style="font-size:15px;font-weight:800;letter-spacing:1px;'
            f'text-transform:uppercase;color:var(--green);margin:26px 0 8px">'
            f'{_TIER_LABEL[letter]}</h2>'
            f'<table class="pd-table"><thead><tr><th>Player</th><th>Team</th>'
            f'<th>xPts</th><th>Price</th></tr></thead>'
            f'<tbody>{trs}</tbody></table>')

    byline_date = f" · {_html.escape(date_str)}" if date_str else ""
    body = f"""<div class="rate-wrap" style="max-width:760px">
<div class="pagelabel" style="margin-top:34px">Tier boards · Gameweek {gameweek}</div>
<h1>{label}, tiered S to D</h1>
<p class="stand">Ranked within position by this gameweek's expected points:
S is the top 5%, A the next 15%, B and C the middle 60%, D the rest.{byline_date}</p>
{_tier_nav_html(active=position)}
{"".join(groups)}
</div>"""
    return _page_shell(title, description, tier_path(position),
                       body) + "</body></html>"
