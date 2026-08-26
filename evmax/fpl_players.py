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

# Letter -> a one-word call, derived from RANK and nothing else.
#
# This used to be printed on the card face, and it was the worst thing on the
# page: it told a reader to BUY Haaland while our own published squad refused
# to own him. Owner, 2026-08-26: "We say we don't buy haaland and call him S
# premium buy". A site cannot recommend against its own team.
#
# It survives in the JSON as `rank_call`, documented there as rank-derived and
# NOT a recommendation, because a consumer keyed on it should keep working —
# but nothing on any rendered surface reads it any more. What the card shows
# instead is our actual position (squad_stance, below) plus the model's tier.
_CALL_BY_LETTER = {"S": "buy", "A": "buy", "B": "hold", "C": "hold", "D": "pass"}

# Our stance on one player, read off the two PUBLISHED squads. First match
# wins: our own team outranks the reference squad, and a starter outranks a
# bench slot.
#
# The owner named four states. A fifth is unavoidable and is flagged as an
# interpretation: the consensus squad is a full 15 like ours, so it has a
# bench, and a player sitting on it is neither "in the consensus XI" nor "not
# in either squad". Both of those would be false, so he gets his own line.
STANCE_OUR_XI = "in our XI"
STANCE_OUR_BENCH = "on our bench"
STANCE_CONSENSUS_XI = "in the consensus XI"
STANCE_CONSENSUS_BENCH = "on the consensus bench"
STANCE_NEITHER = "not in either squad"


def squad_stance(model_role=None, consensus_role=None) -> str:
    """Where this player stands with US — the card's replacement for the call.

    Roles are the "XI"/"Bench" strings both published squads' entries carry
    (evmax.fpl_articles.squad_article), or None for a player in neither.
    Nothing here is an instruction to the reader: it is a statement of what
    the site has already published, which is the only claim the card is
    entitled to make about buying and selling.
    """
    if model_role == "XI":
        return STANCE_OUR_XI
    if model_role:
        return STANCE_OUR_BENCH
    if consensus_role == "XI":
        return STANCE_CONSENSUS_XI
    if consensus_role:
        return STANCE_CONSENSUS_BENCH
    return STANCE_NEITHER


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

# Per-player JSON `distribution`. The engine now captures per-sim histograms
# into the artifact (spec 2026-08-26, D2), so the key that was reserved as
# null now carries the real thing: the sparse PMF under "histogram", the sim
# count it was built from, and the six statistics games.fpl.model derives from
# it. Still emitted as null — the reserved shape — for an artifact written
# before histograms existed, so a consumer that keyed on the null never breaks.
DISTRIBUTION_RESERVED = None

_DISTRIBUTION_STATS = ("p10", "median", "mode", "p90", "p_haul", "p_blank")


def distribution_block(row: dict):
    """The JSON `distribution` object for one artifact row, or None.

    `sims` is carried explicitly rather than left for the reader to sum: the
    card's caption states it ("50,000 simulations"), and a consumer comparing
    two gameweeks needs to know the denominator changed if it ever does.
    """
    hist = row.get("distribution")
    if not hist:
        return DISTRIBUTION_RESERVED
    block = {"histogram": {int(k): v for k, v in hist.items()},
             "sims": sum(hist.values())}
    block.update({f: row.get(f) for f in _DISTRIBUTION_STATS})
    return block

_PROJECTION_FIELDS = ("x_points", "captain_ev", "ceiling", "value", "bonus",
                      "defcon", "p_defcon", "cs_points", "start_prob")

# --- The dot timeline ---------------------------------------------------------
# The card's stat-art was an area wave of the six-gameweek PROJECTION: a
# forecast a reader could not tell from a record, and a shape nobody could read
# (owner 2026-08-26, superseding his own earlier note: "but we can have last
# few realised and next few projected dots right? the wave seems hard to get").
#
# It is now one strip of dots — the last few gameweeks he actually PLAYED, then
# the next few PROJECTED, split by a "now" line. Solid dots are things that
# happened; hollow dots are things the model thinks will happen. Height is the
# points, on a scale shared by both halves, so the eye compares a forecast to
# the record it follows without a single word of explanation.

DOTS_PLAYED_MAX = 3      # the last three he played — enough to show direction
DOTS_TOTAL_MAX = 7       # legible at card width (~230px in the landing row)


def _played_rows(payload: dict) -> list:
    """His history rows with football in them, ascending by round.

    "Played" is minutes > 0. An unused substitute has a history row and no
    football in it, and a dot at zero for a week he was never on the pitch
    would read as a bad performance rather than an absence.
    """
    history = payload.get("form_history") or []
    rows = [h for h in history if (h.get("minutes") or 0) > 0]
    return sorted(rows, key=lambda h: int(h.get("round") or 0))


def played_gameweeks(payload: dict) -> int:
    """How many gameweeks this player has actually played this season.

    The bar for two separate honesty rules — the timeline's realized dots and
    whether realized pts/£m is worth printing at all — so it is counted once,
    here, and both read the same number.
    """
    return len(_played_rows(payload))


def form_dots(payload: dict, gameweek: int = None) -> list:
    """The timeline: [{"gw", "value", "display", "mode"}, ...] left to right.

    value:   what the dot's HEIGHT encodes. Realized dots carry the actual
             points; projected dots carry xPts ROUNDED TO WHOLE POINTS, so a
             projection sits on the same integer lattice as the record beside
             it rather than hovering a hair off it for no reason a reader can see.
    display: the precise figure, for the title text — the rounding is a drawing
             decision and must not become a published claim.
    mode:    "played" | "projected".

    Degrades to whichever half exists, and to [] when neither does.
    """
    played = _played_rows(payload)[-DOTS_PLAYED_MAX:]
    dots = [{"gw": int(h["round"]),
             "value": float(h.get("total_points") or 0.0),
             "display": f'{int(h.get("total_points") or 0)}',
             "mode": "played"}
            for h in played]

    sw = payload.get("six_week_xpts") or {}
    horizon = []
    try:
        cutoff = int(gameweek if gameweek is not None
                     else payload.get("gameweek") or 0)
        horizon = sorted((int(k), float(v)) for k, v in sw.items())
    except (TypeError, ValueError):
        horizon = []
    # Everything from this gameweek on. A horizon matrix that still carries
    # finished gameweeks must not put a "projection" where the record already
    # sits — the played dots own those rounds.
    played_rounds = {d["gw"] for d in dots}
    for gw, value in horizon:
        if gw < cutoff or gw in played_rounds:
            continue
        if len(dots) >= DOTS_TOTAL_MAX:
            break
        dots.append({"gw": gw, "value": float(round(value)),
                     "display": f"{value:.1f}", "mode": "projected"})
    return dots


def assemble_payloads(rows: list, players_by_name: dict, elements_by_id: dict,
                      notes: dict, squad_roles: dict, six_week,
                      fx_rows: list, odds_by_gw: dict, gameweek: int,
                      generated_at: str, form_history=None) -> tuple:
    """(payloads sorted by x_points desc, [unmatched row names]).

    rows: the gameweek artifact rows (disambiguated names).
    players_by_name: {disambiguated name: parsed bootstrap player} (has "id").
    elements_by_id: {element id: RAW bootstrap element} — season totals
      (total_points/event_points) live only on the raw feed.
    notes: research.load_entries("players", gameweek).
    squad_roles: {"model": {name: "XI"|"Bench"}, "consensus": {...}} from the
      two published squads' article entries (already row-matched by the
      build). The ROLE, not just membership: the card's stance line
      distinguishes our XI from our bench, and it cannot invent that later.
    six_week: the horizon matrix (data/fpl/xpts_gw*.json payload) or None —
      absent cache degrades six_week_xpts to null per player.
    form_history: core.fpl_api.fetch_form_history's mapping,
      {element id: [{round, total_points, minutes}, ...]}, or None. Absent
      cache degrades form_history to [] per player, which is honest: the dot
      timeline then draws projected dots only.
    A row whose name no longer matches the bootstrap (cached artifact vs a
    renamed player) is skipped and reported, never guessed at.
    """
    letters = verdict_letters(rows)
    xp_rank, own_rank = rank_maps(rows)
    from evmax.articles import player_flag, price_tier

    form_by_id = {int(k): v for k, v in (form_history or {}).items()}

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
        model_role = (squad_roles.get("model") or {}).get(name)
        consensus_role = (squad_roles.get("consensus") or {}).get(name)
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
                # What the card prints: where this player stands with US.
                "stance": squad_stance(model_role, consensus_role),
                # Rank-derived, NOT a recommendation. Kept for consumers that
                # already keyed on the old `call`; no rendered surface reads
                # it. See _CALL_BY_LETTER.
                "rank_call": _CALL_BY_LETTER[letter],
            },
            "six_week_xpts": sw,
            "form_history": form_by_id.get(pid, []),
            "fixtures": fixture_strip(r.get("team"), gameweek, fx_rows,
                                      odds_by_gw),
            "squads": {
                "model": model_role is not None,
                "consensus": consensus_role is not None,
                # the roles the stance line is computed from, published so a
                # consumer can re-derive it rather than parse the sentence
                "model_role": model_role,
                "consensus_role": consensus_role,
            },
            "notes": [name] if name in notes else [],
            "distribution": distribution_block(r),
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
    # form art: the dot timeline — played gameweeks, then projected ones.
    # pc-form is min-height'd so a player with neither (an empty band) keeps
    # the same card height as one with both, and a row of cards stays level.
    ".player-card .pc-form{margin:8px 0 2px;min-height:78px}"
    ".player-card .pc-dots{height:52px}"
    ".player-card .pc-dots svg{display:block;width:100%;height:52px}"
    ".player-card .pc-dots-empty{display:flex;align-items:center;"
    "justify-content:center;border:1px dashed var(--line);border-radius:8px;"
    "background:rgba(15,122,69,.03)}"
    ".player-card .pc-dots-empty span{font-size:10.5px;color:var(--ink3);"
    "letter-spacing:.3px}"
    ".player-card .pc-dotgws{display:grid;margin-top:1px}"
    ".player-card .pc-dotgws span{font-size:9px;color:var(--ink3);"
    "text-align:center;letter-spacing:.2px;font-variant-numeric:tabular-nums}"
    # the caption IS the legend: each word wears its own dot style
    ".player-card .pc-dotcap{font-size:9.5px;line-height:1.35;"
    "color:var(--ink3);letter-spacing:.3px;margin-top:3px}"
    ".player-card .pc-dotcap span{display:inline-flex;align-items:center;"
    "gap:4px}"
    ".player-card .pc-dotcap span::before{content:'';width:7px;height:7px;"
    "border-radius:50%;display:inline-block}"
    ".player-card .pc-dc-played::before{background:#0a4f2d}"
    ".player-card .pc-dc-proj::before{background:var(--surf);"
    "border:1.5px solid #0f7a45}"
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
    # the fixture strip's key — the tint meant nothing without it
    ".player-card .pc-fxcap{font-size:9.5px;line-height:1.35;"
    "color:var(--ink3);letter-spacing:.3px;margin-top:6px}"
    # verdict line
    ".player-card .pc-verdict{font-size:12px;font-weight:800;"
    "letter-spacing:1.2px;text-transform:uppercase;color:var(--green);"
    "border-top:1px solid var(--line);margin-top:12px;padding-top:10px}"
    # -- the distribution chart (D1: free, not premium) ---------------------
    ".player-card .pc-dist{margin:12px 0 2px;padding-top:10px;"
    "border-top:1px solid var(--line)}"
    ".player-card .pc-dist-marks{display:flex;justify-content:space-between;"
    "gap:8px;font-size:11px;color:var(--ink3);margin-bottom:5px;"
    "font-variant-numeric:tabular-nums}"
    ".player-card .pc-dist-marks b{font-weight:800;color:var(--ink2)}"
    ".player-card .pc-dm-mode b{color:var(--greend)}"
    ".player-card .pc-dm-mode i{font-style:normal;color:var(--ink3);font-size:.92em}"
    ".player-card .pc-dist svg{display:block;width:100%;height:64px}"
    ".player-card .pc-dist-cap{font-size:9.5px;line-height:1.35;color:var(--ink3);"
    "letter-spacing:.3px;margin-top:3px}"
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
# END CARD STYLE BLOCK
# =============================================================================

# Landing-only styles for the full-card top row (owner correction 2026-08-25:
# the compact thumbnail module was rejected — "I wanted cards at the very top
# really like trading cards as we designed"). Kept OUT of CARD_CSS so player
# pages, which embed CARD_CSS via _page_shell, do not carry landing layout
# rules. The row shows four full card_html faces: 4-up on desktop, 2x2 under
# 900px, a horizontal scroller inside its own overflow container on mobile.
TOP_CARDS_CSS = (
    ".top-cards-full{margin:26px 0 6px}"
    ".tcf-kicker{font-size:12px;font-weight:800;letter-spacing:2px;"
    "text-transform:uppercase;color:var(--ink3)}"
    ".tcf-check{margin:6px 0 0;font-size:13.5px;font-weight:600}"
    ".tcf-check a{color:var(--green)}"
    ".tcf-row{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;"
    "margin-top:12px}"
    ".tcf-row>a{display:block;color:inherit;text-decoration:none}"
    ".tcf-row .player-card{margin:0;height:100%;"
    "transition:border-color .12s,transform .12s}"
    ".tcf-row>a:hover .player-card{border-color:var(--green);"
    "transform:translateY(-2px)}"
    # full faces at quarter width: scale the display type down a notch
    ".tcf-row .pc-name{font-size:19px}"
    ".tcf-row .pc-hero b{font-size:34px}"
    "@media(max-width:900px){.tcf-row{grid-template-columns:repeat(2,1fr)}}"
    "@media(max-width:600px){.tcf-row{display:flex;overflow-x:auto;"
    "-webkit-overflow-scrolling:touch;padding-bottom:10px}"
    ".tcf-row>a{flex:0 0 272px}}"
)


# --- HTML emitters ------------------------------------------------------------

def _fmt(v, digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}" if isinstance(v, float) else str(v)


# Dot-timeline geometry: a 300x52 viewBox stretched to whatever width the card
# happens to be (preserveAspectRatio="none"), with EVERY mark drawn as a stroke
# carrying vector-effect="non-scaling-stroke".
#
# That combination is the whole trick, and it is the same one _distribution_svg
# relies on for its rules. This strip renders full-card-width on a player page
# (~700px) and quarter-width in the landing row (~230px); a <circle> inside a
# non-uniformly stretched viewBox is an EGG at one of those sizes and a circle
# at neither. A zero-length <line> with stroke-linecap="round" and a
# non-scaling stroke is a perfect disc of exactly `stroke-width` DEVICE pixels
# on every surface, so the dots are identical everywhere and the x/y grid still
# stretches to fill the card. The hollow (projected) dot is the same disc with
# a smaller surface-coloured disc punched over it.
#
# Text is likewise absent by design: the gameweek labels are HTML underneath,
# where CSS pins them at one size on both surfaces.
_DOT_W, _DOT_H = 300.0, 52.0
_DOT_TOP, _DOT_BASE = 9.0, 43.0
_DOT_R = 8.0            # device px, outer disc
_DOT_HOLE = 4.4         # device px, the hollow dot's punched centre
_DOT_PLAYED = "#0a4f2d"
_DOT_PROJECTED = "#0f7a45"
_DOT_SURFACE = "#fff"   # var(--surf); the same literal the dist chart's halo uses
_NON_SCALING = ' vector-effect="non-scaling-stroke"'


def _dots_svg(dots: list) -> str:
    """The dot strip: one lollipop per gameweek, played then projected, split
    by the "now" line. Returns "" when there is nothing to draw.

    Heights share ONE scale across both halves — that is the entire point of
    putting them in the same strip. A projected 8 must sit level with a
    realized 8, or the card would be inviting a comparison it then fakes.
    """
    if not dots:
        return ""
    n = len(dots)
    cell = _DOT_W / n
    vmax = max([d["value"] for d in dots] + [1.0])
    usable = _DOT_BASE - _DOT_TOP

    def x_of(i: int) -> float:
        return (i + 0.5) * cell

    def y_of(value: float) -> float:
        return _DOT_BASE - (max(value, 0.0) / vmax) * usable

    baseline = (f'<line x1="0" y1="{_DOT_BASE:.1f}" x2="{_DOT_W:.0f}" '
                f'y2="{_DOT_BASE:.1f}"{_NON_SCALING} stroke="#e7e2d6" '
                f'stroke-width="1"/>')

    # The "now" line: everything left of it happened, everything right of it is
    # a forecast. Drawn only when the strip actually straddles the boundary.
    divider = ""
    n_played = sum(1 for d in dots if d["mode"] == "played")
    if 0 < n_played < n:
        dx = n_played * cell
        divider = (f'<line class="pc-now" x1="{dx:.2f}" y1="{_DOT_TOP - 6:.1f}" '
                   f'x2="{dx:.2f}" y2="{_DOT_BASE + 4:.1f}"{_NON_SCALING} '
                   f'stroke="#8a8275" stroke-width="1" '
                   f'stroke-dasharray="2 2"/>')

    stems, discs = [], []
    for i, d in enumerate(dots):
        x, y = x_of(i), y_of(d["value"])
        played = d["mode"] == "played"
        colour = _DOT_PLAYED if played else _DOT_PROJECTED
        stems.append(f'<line x1="{x:.2f}" y1="{_DOT_BASE:.1f}" x2="{x:.2f}" '
                     f'y2="{y:.2f}"{_NON_SCALING} stroke="{colour}" '
                     f'stroke-width="1" stroke-opacity="{".45" if played else ".25"}"/>')
        disc = (f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{x:.2f}" y2="{y:.2f}"'
                f'{_NON_SCALING} stroke-linecap="round" ')
        if played:
            discs.append(f'{disc}stroke="{colour}" stroke-width="{_DOT_R:.1f}"/>')
        else:
            discs.append(
                f'{disc}stroke="{colour}" stroke-width="{_DOT_R:.1f}" '
                f'stroke-opacity=".85"/>'
                f'{disc}stroke="{_DOT_SURFACE}" stroke-width="{_DOT_HOLE:.1f}"/>')

    title = dots_title(dots)
    return (f'<svg viewBox="0 0 {_DOT_W:.0f} {_DOT_H:.0f}" '
            f'preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg" '
            f'role="img" aria-label="Points by gameweek: played, then '
            f'projected">'
            f'<title>{_html.escape(title)}</title>'
            f'{baseline}{"".join(stems)}{divider}{"".join(discs)}'
            f'</svg>')


def dots_title(dots: list) -> str:
    """"GW1 2 points played · GW2 8.6 projected · …" — the strip spelled out
    for a screen reader and for anyone who hovers it."""
    return " · ".join(
        f'GW{d["gw"]} {d["display"]} '
        f'{"points played" if d["mode"] == "played" else "projected"}'
        for d in dots)


def _dots_html(payload: dict) -> str:
    """The timeline block: the strip, the gameweek labels, and the caption
    that doubles as the legend.

    The labels are an equal-column grid over the same n cells the SVG divides
    itself into, so label i sits under dot i at any card width without a single
    magic number shared between the two.
    """
    dots = form_dots(payload)
    svg = _dots_svg(dots)
    if not svg:
        # Neither a record nor a forecast. The band stays, at its full height,
        # saying so — a card that silently skipped the block shrank out of line
        # with the rest of the row (owner caught that on 2026-08-26).
        return ('<div class="pc-form"><div class="pc-dots pc-dots-empty">'
                '<span>no gameweek history yet</span></div>'
                '<div class="pc-dotcap">no played or projected gameweeks '
                'on file</div></div>')

    n = len(dots)
    labels = "".join(f'<span>GW{d["gw"]}</span>' for d in dots)
    legend = []
    if any(d["mode"] == "played" for d in dots):
        legend.append('<span class="pc-dc-played">played</span>')
    if any(d["mode"] == "projected" for d in dots):
        legend.append('<span class="pc-dc-proj">projected</span>')
    return (f'<div class="pc-form">'
            f'<div class="pc-dots">{svg}</div>'
            f'<div class="pc-dotgws" style="grid-template-columns:'
            f'repeat({n},1fr)">{labels}</div>'
            f'<div class="pc-dotcap">{" · ".join(legend)}</div>'
            f'</div>')


# Distribution-chart geometry.
#
# The SVG carries GEOMETRY ONLY — bars and rules, no text. That is the whole
# trick to it being legible at two very different sizes: this chart renders
# full-card-width on a player page (~700px) and quarter-width in the landing
# card row (~230px), and text inside a scaled viewBox scales with it, so a
# 7px label becomes a 27px shout on one surface and unreadable on the other.
# The numbers therefore live in HTML above the chart, where CSS pins them at
# one size everywhere. Same reason _form_svg draws at preserveAspectRatio
# "none": with nothing but rectangles inside, non-uniform scaling costs
# nothing and buys a predictable height on every surface.
_DIST_W, _DIST_H = 180.0, 40.0
_DIST_TOP = 3.0             # top of the tallest bar
_DIST_BASE = 34.0           # bar baseline
_DIST_CLIP_Q = 0.99         # freak-sim clip: draw up to the 99th percentile
_DIST_HAUL = 10             # >= this is a haul (games.fpl.model.HAUL_THRESHOLD)
_DIST_BLANK = 2             # <= this is a blank (model.BLANK_THRESHOLD)


def _dist_percentile(pmf: dict, q: float) -> int:
    """Lower-bound percentile over an int-keyed PMF.

    Deliberately a local four-liner rather than an import of
    games.fpl.model._pmf_percentile: this module is a pure emitter with no
    engine dependency (see the module docstring), and it needs the convention
    only to choose where to STOP DRAWING — the published p10/median/p90 come
    off the payload, computed once in the engine.
    """
    total = sum(pmf.values())
    if not total:
        return 0
    cumulative = 0
    for pts in sorted(pmf):
        cumulative += pmf[pts]
        if cumulative >= q * total:
            return pts
    return max(pmf)


def _distribution_svg(payload: dict) -> str:
    """The card's distribution chart: a bar chart of the simulated points PMF
    with the floor (P10), the most likely score and the ceiling (P90) marked.

    This is the surface nobody else ships (spec 2026-08-26, P1): every rival
    publishes a mean, and a mean cannot tell a 6.0 that is six every week from
    a 6.0 that is zero four times and twenty-four once. The bars ARE that
    difference.

    Three reading aids, in order of how much they carry:
      * the bars are banded by outcome — muted for a blank (<= 2 points),
        green for an ordinary return, dark green for a haul (>= 10). The
        reader sees the shape of his week before he reads a single number.
      * thin rules mark P10 / mode / P90. P10 and P90 are dashed and quiet;
        the mode is solid green, because "most likely" is the number a reader
        actually acts on. Their VALUES are printed in HTML by
        _distribution_html, not here — see the geometry note above.
      * the drawn range stops at the 99th percentile. One sim in a thousand
        returning 40 points is real, but letting it set the x-axis would
        squash every bar a reader cares about into the left eighth of the
        chart.

    Deterministic (no RNG, sorted iteration) — the site layer's byte-identical
    rebuild contract, same as _form_svg. Returns "" when there is nothing to
    draw, so a card built off an artifact that predates histograms simply has
    no chart rather than an empty frame.
    """
    dist = payload.get("distribution")
    if not dist:
        return ""
    raw = dist.get("histogram") or {}
    try:
        pmf = {int(k): int(v) for k, v in raw.items() if int(v) > 0}
    except (TypeError, ValueError):
        return ""
    sims = sum(pmf.values())
    if not pmf or sims <= 0:
        return ""

    p10 = dist.get("p10")
    p90 = dist.get("p90")
    mode = dist.get("mode")
    if p10 is None or p90 is None or mode is None:
        return ""

    # Always start at 0 (or lower, if a red card put mass below it): the atom
    # of probability at zero is the most important feature of a rotation
    # risk's week, and starting the axis at his lowest positive return would
    # hide it.
    lo = min(0, min(pmf))
    hi = max(_dist_percentile(pmf, _DIST_CLIP_Q), p90, mode, lo)
    n = hi - lo + 1
    step = _DIST_W / n
    peak = max(pmf.values())
    usable = _DIST_BASE - _DIST_TOP

    def bar_x(pts: int) -> float:
        return (pts - lo) * step

    def centre(pts: int) -> float:
        return bar_x(pts) + step / 2.0

    gap = min(0.7, step * 0.12)
    bars = []
    for pts in range(lo, hi + 1):
        count = pmf.get(pts, 0)
        if not count:
            continue
        h = max((count / peak) * usable, 0.6)
        if pts >= _DIST_HAUL:
            fill, opacity = "#0a4f2d", "1"
        elif pts <= _DIST_BLANK:
            fill, opacity = "#8a8275", ".38"
        else:
            fill, opacity = "#0f7a45", ".62"
        bars.append(
            f'<rect x="{bar_x(pts) + gap:.2f}" y="{_DIST_BASE - h:.2f}" '
            f'width="{max(step - 2 * gap, 0.4):.2f}" height="{h:.2f}" '
            f'fill="{fill}" fill-opacity="{opacity}"/>')

    # preserveAspectRatio="none" stretches the viewBox unevenly, which would
    # otherwise make a "1 unit" rule 4px wide on a full-width player page and
    # 1px in a landing card. non-scaling-stroke pins every stroke to device
    # pixels, so the rules look the same on both surfaces — and it is the only
    # reason the halo below can be tuned once and be right everywhere.
    _NSS = ' vector-effect="non-scaling-stroke"'

    def rule(pts: int, colour: str, dash: str) -> str:
        """A marker rule, drawn over a white halo.

        The halo is what makes the mode rule survive: the mode is by
        definition the tallest bar, and on a haul-coloured (dark green) bar a
        green line is invisible. Over the card's own surface the halo is the
        same colour as the background and costs nothing; it only shows where
        the rule crosses a bar, which is exactly where it is needed.
        """
        x = centre(pts)
        line = (f'<line x1="{x:.2f}" y1="0" x2="{x:.2f}" '
                f'y2="{_DIST_BASE + 3:.1f}"{_NSS} ')
        return (f'{line}stroke="#fff" stroke-width="2.5"/>'
                f'{line}stroke="{colour}" stroke-width="1"{dash}/>')

    rules = [rule(p10, "#8a8275", ' stroke-dasharray="2 2"'),
             rule(p90, "#8a8275", ' stroke-dasharray="2 2"'),
             rule(mode, "#0f7a45", "")]

    baseline = (f'<line x1="0" y1="{_DIST_BASE:.1f}" x2="{_DIST_W:.0f}" '
                f'y2="{_DIST_BASE:.1f}"{_NSS} stroke="#e7e2d6" '
                f'stroke-width="1"/>')
    hist_t = dist.get("histogram") or {}
    mode_n = hist_t.get(str(mode), hist_t.get(mode, 0)) or 0
    mode_share = f' ({mode_n / sims * 100:.0f}% of simulations)' if sims and mode_n else ''
    title = (f'{sims:,} simulations: floor {p10}, most likely {mode}'
             f'{mode_share}, ceiling {p90} points')
    return (f'<svg viewBox="0 0 {_DIST_W:.0f} {_DIST_H:.0f}" '
            f'preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg" '
            f'role="img" aria-label="Simulated points distribution">'
            f'<title>{_html.escape(title)}</title>'
            f'{"".join(bars)}{baseline}{"".join(rules)}'
            f'</svg>')


def _distribution_html(payload: dict) -> str:
    """The marks, the chart and its caption — or "" when there is no PMF.

    The three marks are printed here in HTML rather than inside the SVG so
    they stay one size on every surface (see _distribution_svg's geometry
    note), and they run left-to-right in the same order as the rules they
    name, so the eye maps the words onto the chart without a legend.
    """
    svg = _distribution_svg(payload)
    if not svg:
        return ""
    dist = payload.get("distribution") or {}
    sims = dist.get("sims") or 0
    # The mode of a wide distribution is a WEAK claim: Bruno's GW2 peak is 10
    # points at 9.3%, with 13 right behind at 8.5%. Printing "most likely 10"
    # bare implies a confidence the number does not carry, so the mode ships
    # with its own share attached (owner caught this 2026-08-26).
    hist = dist.get("histogram") or {}
    mode = dist.get("mode")
    share = ""
    if sims and hist:
        count = hist.get(str(mode), hist.get(mode, 0)) or 0
        if count:
            share = f' <i>{count / sims * 100:.0f}%</i>'
    marks = (f'<div class="pc-dist-marks">'
             f'<span>floor <b>{dist.get("p10")}</b></span>'
             f'<span class="pc-dm-mode">most likely '
             f'<b>{mode}</b>{share}</span>'
             f'<span>ceiling <b>{dist.get("p90")}</b></span></div>')
    return (f'<div class="pc-dist">{marks}{svg}'
            f'<div class="pc-dist-cap">{sims:,} simulations</div></div>')


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


def fixtures_caption(fixtures: list) -> str:
    """The one-line key under the fixture chips.

    The chips were difficulty-tinted with nothing anywhere saying what the
    tint meant — owner, 2026-08-26: "we don't know what green means in GW
    below". The grey clause is added ONLY when a grey chip is actually on the
    strip, so the caption never explains a colour the reader cannot see.
    """
    caption = f"next {len(fixtures)} · greener = easier fixture"
    if any(f.get("difficulty") is None for f in fixtures):
        caption += " · grey = not priced yet"
    return caption


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
                 f'<span>xPts</span></div>')

    # The form band is fixed-height on EVERY card, present or not: a new
    # signing with no history (M.Sangaré, GW2) used to skip the block and his
    # card visibly shrank out of line with the row (owner caught it
    # 2026-08-26). An honest empty state keeps the grid true.
    sw_html = _dots_html(payload)

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
        fx_html = (f'<div class="pc-fixtures">{"".join(cells)}</div>'
                   f'<div class="pc-fxcap">{fixtures_caption(payload["fixtures"])}'
                   f'</div>')

    # Our POSITION, not an instruction. The card used to open this line with a
    # rank-derived "buy" and it contradicted the squad the same site publishes
    # (owner 2026-08-26: "We say we don't buy haaland and call him S premium
    # buy"). The model's opinion is the tier; the stance is ours; nothing here
    # tells anyone to buy anything.
    verdict_html = (f'<div class="pc-verdict">'
                    f'{_html.escape(verdict["stance"])} · '
                    f'tier {verdict["tier"]} · {verdict["price_band"]}</div>')

    # No premium slot. It was reserved on 2026-08-24 and removed on 2026-08-26
    # (owner): a lock promising features that do not exist yet is clutter on a
    # card whose whole job is to answer a question in five seconds. When the
    # your-team tools are real they can earn their own space.
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
        f'data-stance="{_html.escape(verdict["stance"])}" '
        f'data-status="{_html.escape(payload["status"])}">'
        f'{head_html}'
        f'{news_html}'
        f'{hero_html}'
        f'{sw_html}'
        f'{_decomp_html(proj)}'
        f'{statrow}'
        f'{_distribution_html(payload)}'
        f'{fx_html}'
        f'{verdict_html}'
        f'</figure>')


def top_cards_html(payloads: list, count: int = 4) -> str:
    """The FPL landing's top-cards row: the FULL Ledger card face (card_html —
    form-wave art, decomposition strip, stat rows, fixture chips, verdict,
    premium slot) for the top `count` players by x_points, each face linking
    to its player page. Rendered as the landing's FIRST content section (owner
    correction 2026-08-25 — the compact thumbnail module was rejected). One
    kicker line above the row, the "Check your player" link right under it.
    Reuses card_html verbatim (heading="h2") — no second card implementation;
    the size difference is TOP_CARDS_CSS only."""
    cards = []
    for p in payloads[:count]:
        cards.append(
            f'<a href="{page_path(p["slug"])}" '
            f'aria-label="{_html.escape(p["name"])} — full player card">'
            f'{card_html(p, heading="h2")}</a>')
    return (
        '<section class="top-cards-full">'
        '<div class="tcf-kicker">This week\'s top cards — from 50,000 '
        'simulations</div>'
        f'<p class="tcf-check"><a href="{PLAYERS_BASE}/">Check your player — '
        'search all cards →</a></p>'
        f'<div class="tcf-row">{"".join(cards)}</div>'
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
<style>{render._STYLE}{CARD_CSS}{render._NAV_SCROLL_CSS}</style>
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
        # The model's opinion and OUR position, kept apart — one is a
        # projection, the other is a squad we have already published, and
        # running them together into a single "verdict" is what produced the
        # buy-a-player-we-refuse-to-own contradiction in the first place.
        ("Model tier",
         f'{payload["verdict"]["tier"]} · {payload["verdict"]["price_band"]}'),
        ("Our position", payload["verdict"]["stance"]),
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

    # Named by ROLE. Saying "in the consensus XI" about a player sitting on
    # the consensus bench is the same class of untruth the stance line exists
    # to remove.
    squads = payload["squads"]
    memberships = []
    for key, ours in (("model", "our squad"), ("consensus", "the consensus squad")):
        role = squads.get(f"{key}_role")
        if role:
            memberships.append(f'{"the XI" if role == "XI" else "the bench"} '
                               f'of {ours}')
        elif squads.get(key):        # a payload written before roles existed
            memberships.append(ours)
    squad_line = ""
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
