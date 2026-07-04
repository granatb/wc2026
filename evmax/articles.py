"""Pure ranking/selection logic for the evmax static site (no I/O except load_player_meta)."""

import json
import os

from core import fifa_api, fixtures
from games.fifa import model as fifa_model

POS_MIN = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
POS_MAX = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}
XI_SIZE = 11
DIFF_MAX_OWNERSHIP = 10.0   # percent — "differential" cutoff
DIFF_MIN_XPTS = 4.0         # only surface differentials worth owning
BLOWOUT_FIXTURES = 2        # how many top-lambda fixtures count as "blowouts"
LOW_CEILING_RATIO = 1.15    # ceiling/xPts below this = "safe floor, no haul upside"
# Fixture-guide environment thresholds (fixture_guide()): a fixture's exp_total
# (combined expected goals) classifies it as a high-scoring "blowout" worth
# targeting attackers in, a low-scoring "avoid" environment where forwards
# should be faded, or "balanced" in between.
FIXTURE_ENV_BLOWOUT_MIN = 3.0
FIXTURE_ENV_AVOID_MAX = 2.1
# 2026 World Cup fixed format: fantasy rounds 1-3 are group matchdays (a draw is just
# a draw — both teams keep playing); round 4 onward is straight knockout (R32, R16,
# QF, SF, Bronze, Final), where a 90' draw resolves via extra time/penalties. This is
# NOT derivable from data/schedule.json's `stage` field, which carries ESPN's raw
# match-status string (e.g. "STATUS_SCHEDULED"), not the tournament stage — so we
# hardcode the known threshold for this one tournament rather than infer it.
KNOCKOUT_ROUND_START = 4
ARTICLES = ["captains", "matches", "fixtures", "transfers", "best-xi", "defenders", "risky",
            "efficiency", "blowout-transfers"]
ARTICLE_TITLES = {
    "captains": "Best captain picks",
    "matches": "Match predictions & games to watch",
    "fixtures": "Fixture guide — clean sheets, blowouts and games to avoid",
    "transfers": "Priority transfers this round",
    "best-xi": "Best XI by expected points",
    "defenders": "Best defenders",
    "risky": "Risky chances — highest ceilings",
    "efficiency": "Best value — points per million",
    "blowout-transfers": "Blowout-fixture targets",
}

_PLAYERS_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "players.json")


def build_rows(means: dict, samples: dict, meta: dict, kickoffs: dict) -> list:
    """Enrich the engine's per-player means with metadata into ranked-ready rows.

    means:    name -> event-means dict (from engine_events.event_means)
    samples:  name -> goal_samples list (from PlayerSample.goal_samples)
    meta:     name -> {team, position, price, ownership_pct} (load_player_meta)
    kickoffs: team -> ISO-8601 kickoff string for the round
    Players missing metadata or a position are skipped.
    """
    rows = []
    for name, ev in means.items():
        m = meta.get(name)
        if not m or not m.get("position"):
            continue
        xp = fifa_model.expected_points(ev)
        ceiling = fifa_model.ceiling_points(ev, samples.get(name, []))
        price = m.get("price")
        rows.append({
            "name": name,
            "team": m.get("team"),
            "position": m["position"],
            "x_points": round(xp, 2),
            "captain_ev": round(2 * xp, 2),
            "ceiling": round(ceiling, 2),
            # ceiling/xPts: close to 1.0 means "no big-haul scenario" (structurally
            # true for goalkeepers, who can't score outfield-style points) — a real
            # signal for captaincy, where the x2 multiplier is meant to buy upside.
            "ceiling_ratio": round(ceiling / xp, 3) if xp > 0 else 1.0,
            "price": price,
            "ownership_pct": m.get("ownership_pct"),
            "value": round(xp / price, 3) if price else None,
            "kickoff": kickoffs.get(m.get("team")),
        })
    return rows


def select_xi(rows: list, key: str) -> list:
    """Greedy formation-constrained XI maximizing `key` (e.g. 'x_points' or 'ceiling').
    Fills position minimums first, then the remaining slots by best `key` within maxima."""
    pools = {pos: sorted([r for r in rows if r["position"] == pos and r.get(key) is not None],
                         key=lambda r: r[key], reverse=True)
             for pos in POS_MIN}
    for pos in POS_MIN:
        if len(pools[pos]) < POS_MIN[pos]:
            raise ValueError(
                f"insufficient {pos} pool for XI: need {POS_MIN[pos]}, have {len(pools[pos])}"
            )
    chosen, counts = [], {}
    for pos in POS_MIN:
        take = pools[pos][:POS_MIN[pos]]
        chosen += take
        counts[pos] = len(take)
    leftovers = []
    for pos in POS_MIN:
        leftovers += pools[pos][POS_MIN[pos]:]
    leftovers.sort(key=lambda r: r[key], reverse=True)
    for r in leftovers:
        if len(chosen) >= XI_SIZE:
            break
        pos = r["position"]
        if counts.get(pos, 0) < POS_MAX[pos]:
            chosen.append(r)
            counts[pos] = counts.get(pos, 0) + 1
    chosen.sort(key=lambda r: r[key], reverse=True)
    chosen = [dict(r) for r in chosen]
    for i, r in enumerate(chosen, 1):
        r["rank"] = i
    return chosen


def _ranked(rows, key, reverse=True):
    out = [dict(r) for r in sorted(rows, key=lambda r: r[key], reverse=reverse)]
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def rank_captains(rows: list) -> list:
    return _ranked(rows, "captain_ev")


def rank_value(rows: list) -> list:
    return _ranked([r for r in rows if r.get("value") is not None], "value")


def efficiency(rows: list) -> list:
    """The EV-per-dollar article: rows ranked by value (xPts / price). Public alias."""
    return rank_value(rows)


def formation_of(xi: list) -> str:
    """Formation string like '3-4-3' from an XI (outfield only, GK omitted by convention)."""
    counts = {}
    for r in xi:
        counts[r.get("position")] = counts.get(r.get("position"), 0) + 1
    return f"{counts.get('DEF', 0)}-{counts.get('MID', 0)}-{counts.get('FWD', 0)}"


def differentials(rows: list, max_ownership: float = DIFF_MAX_OWNERSHIP,
                  min_xpts: float = DIFF_MIN_XPTS) -> list:
    pool = [r for r in rows
            if r.get("ownership_pct") is not None
            and r["ownership_pct"] < max_ownership
            and r["x_points"] >= min_xpts]
    return _ranked(pool, "x_points")


def load_player_meta(path: str = _PLAYERS_JSON) -> dict:
    """name (and aliases) -> {team, position, price, ownership_pct} from data/players.json."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    out = {}
    for p in raw.get("players", []):
        meta = {
            "team": p.get("team"),
            "position": p.get("fifa_pos"),
            "price": p.get("fifa_price"),
            "ownership_pct": p.get("ownership"),
        }
        out[p["name"]] = meta
        for alias in p.get("aliases", []):
            out.setdefault(alias, meta)
    return out


def by_position(rows: list, pos: str) -> list:
    """Rows where position == pos, ranked by x_points desc with rank."""
    pool = [r for r in rows if r.get("position") == pos]
    return _ranked(pool, "x_points")


def risky(rows: list, max_ownership: float = 25.0) -> list:
    """Rows with ownership_pct not None and < max_ownership, ranked by ceiling desc with rank.
    Boom-or-bust upside picks."""
    pool = [r for r in rows
            if r.get("ownership_pct") is not None
            and r["ownership_pct"] < max_ownership]
    return _ranked(pool, "ceiling")


def blowout_teams(fantasy_round: int, top_n: int = BLOWOUT_FIXTURES) -> set:
    """Teams playing in the round's highest combined-lambda (most lopsided/high-scoring)
    fixtures. Uses core.fixtures lambdas (odds-derived where present)."""
    fx = fixtures.by_round(fantasy_round)
    scored = []
    for f in fx:
        lh, la = f.lambdas()
        scored.append((lh + la, f))
    scored.sort(key=lambda t: t[0], reverse=True)
    teams = set()
    for _total, f in scored[:top_n]:
        teams.add(f.home)
        teams.add(f.away)
    return teams


def blowout_transfers(rows: list, teams: set) -> list:
    """Attackers (FWD/MID) from the blowout fixtures, ranked by x_points."""
    pool = [r for r in rows if r["team"] in teams and r["position"] in ("FWD", "MID")]
    return _ranked(pool, "x_points")


def _best_by_position(rows: list, team: str, position: str):
    """The row with the highest x_points for `team` at `position`, or None."""
    pool = [r for r in rows if r.get("team") == team and r.get("position") == position]
    if not pool:
        return None
    return max(pool, key=lambda r: r["x_points"])


def _fmt_best(row) -> str:
    """'Van Dijk (5.7)' style label for the fixture-guide table, or a dash."""
    if row is None:
        return "—"
    return f"{row['name']} ({row['x_points']:.1f})"


def fixture_guide(match_entries: list, rows: list) -> list:
    """One entry per TEAM in the round: clean-sheet probability, goal environment
    (blowout / avoid / balanced), and that team's best defender/goalkeeper.

    match_entries: output of match_predictions() (carries exp_home_goals/
                   exp_away_goals/exp_total/p_cs_home/p_cs_away per fixture).
    rows:          the enriched player rows (from build_rows), used to find
                   each team's best DEF/GK by x_points.

    Sorted by p_clean_sheet desc, with a 1-based rank.
    """
    out = []
    for m in match_entries:
        exp_total = m.get("exp_total", 0.0)
        if exp_total >= FIXTURE_ENV_BLOWOUT_MIN:
            env = "blowout"
        elif exp_total <= FIXTURE_ENV_AVOID_MAX:
            env = "avoid"
        else:
            env = "balanced"

        for side, team, opponent, p_cs, goals_for, goals_against in (
            ("home", m["home"], m["away"], m.get("p_cs_home", 0.0),
             m.get("exp_home_goals", 0.0), m.get("exp_away_goals", 0.0)),
            ("away", m["away"], m["home"], m.get("p_cs_away", 0.0),
             m.get("exp_away_goals", 0.0), m.get("exp_home_goals", 0.0)),
        ):
            best_def = _best_by_position(rows, team, "DEF")
            best_gk = _best_by_position(rows, team, "GK")
            out.append({
                "name": team,
                "team": f"vs {opponent}",
                "position": "—",
                "p_clean_sheet": p_cs,
                "exp_goals_for": goals_for,
                "exp_goals_against": goals_against,
                "env": env,
                "top_def": _fmt_best(best_def),
                "top_gk": _fmt_best(best_gk),
            })

    out.sort(key=lambda r: r["p_clean_sheet"], reverse=True)
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


_FINISHED_STATUS_MARKERS = ("FULL_TIME", "FINAL", "COMPLETE")


def _is_finished_status(status) -> bool:
    """True if a raw feed status string indicates the match has finished.

    Feeds disagree on casing/vocabulary: core.fixtures' ESPN-derived `stage`
    uses upper-snake-case ("STATUS_FULL_TIME", "STATUS_FINAL_AET", ...), while
    core.fifa_api's own feed uses lowercase ("complete", "scheduled"). Normalise
    to uppercase and check for any known "done" marker rather than an exact
    string, so this keeps working regardless of which feed supplied the value.
    """
    if not status:
        return False
    upper = status.upper()
    return any(marker in upper for marker in _FINISHED_STATUS_MARKERS)


def finished_results_map(fantasy_round: int) -> dict:
    """(home, away) team-name pairs -> {"hs": int, "as": int} for fixtures in
    `fantasy_round` that the cached FIFA feed (core.fifa_api.fixtures()) reports
    as finished. Keys are normalised with fifa_api._ckey so ESPN-vs-FIFA team
    name spelling differences (e.g. "South Korea" vs "Korea Republic") match up.

    Only rounds/fixtures actually present -- and finished -- in the cached feed
    are returned; everything else is simply absent from the map, which callers
    treat as "not yet finished" rather than an error (the cache is refreshed by
    the production controller before a real build, so a stale/empty cache here
    is expected outside of that window).
    """
    out: dict[tuple, dict] = {}
    for m in fifa_api.fixtures():
        if not _is_finished_status(m.get("status")):
            continue
        home, away = m.get("home"), m.get("away")
        hs, as_ = m.get("hs"), m.get("as")
        if home is None or away is None or hs is None or as_ is None:
            continue
        out[(fifa_api._ckey(home), fifa_api._ckey(away))] = {"hs": hs, "as": as_}
    return out


def match_predictions(match_samples: dict, fantasy_round: int, results=None) -> list:
    """Return one prediction dict per fixture in fantasy_round, sorted by kickoff.

    Derives predictions from the simulated scoreline distribution in match_samples
    (a dict of match_id -> MatchSample from engine_events.simulate_round).
    Falls back to lambda-Poisson grid if a match_id is absent from match_samples.

    Each entry has:
      match, home, away, kickoff (ISO str), exp_home_goals, exp_away_goals,
      exp_total, top_scoreline ("H-A"), p_home, p_draw, p_away, close (bool),
      p_cs_home (P(away scores 0), i.e. home keeps a clean sheet), p_cs_away
      (P(home scores 0), i.e. away keeps a clean sheet).

    results: optional output of finished_results_map(fantasy_round) -- when a
    fixture's (home, away) pair (normalised via fifa_api._ckey) is present, the
    entry additionally carries final_score ("H-A") and finished=True, while
    keeping every prediction field intact (predicted-vs-actual, not a replacement).
    """
    import math

    def _poisson_prob(lam: float, k: int) -> float:
        if lam <= 0:
            return 1.0 if k == 0 else 0.0
        return math.exp(-lam) * (lam ** k) / math.factorial(k)

    def _outcome_probs_from_lambdas(lam_h: float, lam_a: float, max_g: int = 7):
        """Compute 1X2 probs + top scoreline from a Poisson grid."""
        p_home = p_draw = p_away = 0.0
        best_score = (0, 0)
        best_p = 0.0
        exp_h = exp_a = 0.0
        for hg in range(max_g + 1):
            ph = _poisson_prob(lam_h, hg)
            for ag in range(max_g + 1):
                pa = _poisson_prob(lam_a, ag)
                p = ph * pa
                if hg > ag:
                    p_home += p
                elif hg == ag:
                    p_draw += p
                else:
                    p_away += p
                if p > best_p:
                    best_p = p
                    best_score = (hg, ag)
                exp_h += hg * p
                exp_a += ag * p
        return p_home, p_draw, p_away, best_score, exp_h, exp_a

    fx_list = fixtures.by_round(fantasy_round)
    entries_out = []
    for f in fx_list:
        ms = match_samples.get(f.match_id)
        if ms is not None and ms.sims > 0:
            # Use simulated scoreline distribution
            probs = ms.outcome_probs()
            p_home = probs.get("H", 0.0)
            p_draw = probs.get("D", 0.0)
            p_away = probs.get("A", 0.0)
            # Top scoreline
            best_sl = max(ms.scorelines, key=lambda k: ms.scorelines[k])
            # Expected goals from marginals
            mh = ms.marginal_home()
            ma = ms.marginal_away()
            exp_h = sum(g * p for g, p in mh.items())
            exp_a = sum(g * p for g, p in ma.items())
            # Clean sheet probs: home keeps a CS iff away scores 0, and vice versa.
            p_cs_home = ma.get(0, 0.0)
            p_cs_away = mh.get(0, 0.0)
        else:
            # Fallback: Poisson grid from lambdas
            lam_h, lam_a = f.lambdas()
            p_home, p_draw, p_away, best_sl, exp_h, exp_a = \
                _outcome_probs_from_lambdas(lam_h, lam_a)
            p_cs_home = math.exp(-lam_a)
            p_cs_away = math.exp(-lam_h)

        # Normalise (avoid floating-point drift)
        total_p = p_home + p_draw + p_away
        if total_p > 0:
            p_home /= total_p
            p_draw /= total_p
            p_away /= total_p

        close = max(p_home, p_draw, p_away) < 0.45

        entry = {
            "match": f"{f.home} vs {f.away}",
            "home": f.home,
            "away": f.away,
            "kickoff": f.kickoff.isoformat(),
            "exp_home_goals": round(exp_h, 2),
            "exp_away_goals": round(exp_a, 2),
            "exp_total": round(exp_h + exp_a, 2),
            "top_scoreline": f"{best_sl[0]}-{best_sl[1]}",
            "p_home": round(p_home, 2),
            "p_draw": round(p_draw, 2),
            "p_away": round(p_away, 2),
            "close": close,
            "p_cs_home": round(p_cs_home, 3),
            "p_cs_away": round(p_cs_away, 3),
        }

        if fantasy_round >= KNOCKOUT_ROUND_START:
            # Straight knockout: a 90' draw goes to extra time/penalties. We don't
            # simulate ET separately, so approximate its winner by splitting the
            # drawn-match probability in proportion to each side's attacking
            # strength (lambda share) rather than assuming a 50/50 coin flip —
            # a lightweight stand-in for a full ET model (on the engine roadmap).
            lam_h, lam_a = f.lambdas()
            total_lam = lam_h + lam_a
            strength_h = (lam_h / total_lam) if total_lam > 0 else 0.5
            entry["p_advance_home"] = round(p_home + p_draw * strength_h, 3)
            entry["p_advance_away"] = round(p_away + p_draw * (1 - strength_h), 3)

        if results is not None:
            key = (fifa_api._ckey(f.home), fifa_api._ckey(f.away))
            actual = results.get(key)
            if actual is not None:
                entry["final_score"] = f"{actual['hs']}-{actual['as']}"
                entry["finished"] = True

        entries_out.append(entry)

    entries_out.sort(key=lambda r: r["kickoff"])
    return entries_out


def advancement_map(match_entries: list) -> dict:
    """team -> P(advance past this round), from match_predictions() output.

    Only populated for knockout rounds (match_predictions only emits p_advance_*
    fields when fantasy_round >= KNOCKOUT_ROUND_START); empty in group rounds,
    where transfer_priorities() correctly falls back to no elimination discount.
    """
    out = {}
    for m in match_entries:
        if "p_advance_home" in m:
            out[m["home"]] = m["p_advance_home"]
            out[m["away"]] = m["p_advance_away"]
    return out


def _replacement_level(rows: list) -> dict:
    """Median xPts per position — the 'replacement level' a transfer is judged against."""
    from statistics import median
    out = {}
    for pos in POS_MIN:
        vals = [r["x_points"] for r in rows if r.get("position") == pos]
        out[pos] = median(vals) if vals else 0.0
    return out


def transfer_priorities(rows: list, adv_map: dict, top_n: int = 20) -> list:
    """Rank transfer targets by value-over-replacement, boosted by the probability
    their team survives to contribute again next round (knockout rounds only —
    adv_map is empty in group rounds, so this degrades to pure VOR ranking there).

    priority_score = vor * (1 + p_advance). A player with excellent value this round
    but a coin-flip knockout tie ranks below an equally good one on a near-certain
    advancer, because the risky one may be dead weight next round.
    """
    repl = _replacement_level(rows)
    out = []
    for r in rows:
        pos = r.get("position")
        if pos not in repl:
            continue
        vor = round(r["x_points"] - repl[pos], 3)
        p_adv = adv_map.get(r.get("team"), 1.0)
        row = dict(r)
        row["vor"] = vor
        row["p_advance"] = round(p_adv * 100, 1)  # percent-scale, matches ownership_pct
        row["priority_score"] = round(vor * (1 + p_adv), 3)
        out.append(row)
    return _ranked(out, "priority_score")[:top_n]
