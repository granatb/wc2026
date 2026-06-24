"""Pure ranking/selection logic for the evmax static site (no I/O except load_player_meta)."""

import json
import os

from core import fixtures
from games.fifa import model as fifa_model

POS_MIN = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
POS_MAX = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}
XI_SIZE = 11
DIFF_MAX_OWNERSHIP = 10.0   # percent — "differential" cutoff
DIFF_MIN_XPTS = 4.0         # only surface differentials worth owning
BLOWOUT_FIXTURES = 2        # how many top-lambda fixtures count as "blowouts"
ARTICLES = ["captains", "matches", "best-xi", "defenders", "risky", "efficiency",
            "blowout-transfers"]
ARTICLE_TITLES = {
    "captains": "Best captain picks",
    "matches": "Match predictions & games to watch",
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


def match_predictions(match_samples: dict, fantasy_round: int) -> list:
    """Return one prediction dict per fixture in fantasy_round, sorted by kickoff.

    Derives predictions from the simulated scoreline distribution in match_samples
    (a dict of match_id -> MatchSample from engine_events.simulate_round).
    Falls back to lambda-Poisson grid if a match_id is absent from match_samples.

    Each entry has:
      match, home, away, kickoff (ISO str), exp_home_goals, exp_away_goals,
      exp_total, top_scoreline ("H-A"), p_home, p_draw, p_away, close (bool).
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
    results = []
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
        else:
            # Fallback: Poisson grid from lambdas
            lam_h, lam_a = f.lambdas()
            p_home, p_draw, p_away, best_sl, exp_h, exp_a = \
                _outcome_probs_from_lambdas(lam_h, lam_a)

        # Normalise (avoid floating-point drift)
        total_p = p_home + p_draw + p_away
        if total_p > 0:
            p_home /= total_p
            p_draw /= total_p
            p_away /= total_p

        close = max(p_home, p_draw, p_away) < 0.45

        results.append({
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
        })

    results.sort(key=lambda r: r["kickoff"])
    return results
