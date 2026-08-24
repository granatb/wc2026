"""Rebuild the Consensus XI from actual ownership — the GW2+ method.

Owner decision 2026-08-24 (phase 4c): from GW2 the Consensus XI is the actual
most-owned legal template. Real ownership data (bootstrap selected_by_percent)
exists once a season is under way, so the GW1 expert mention-tally is retired
with a method note, and the squad declares its first Wildcard to do the full
rebuild under real rules. GW1 is still graded as published.

Pure: input is core.fpl_api.parse_players output, output is an UNVALIDATED
state dict in games/fpl/state.py's shape. The caller (evmax.fpl_build.
reset_consensus) validates it against the same player pool before writing —
an illegal template must abort, never publish.

Method, in the order the constraints bind:
  1. candidacy: available players only (status "u" — gone from the game — is
     excluded), one squad slot per web_name, and a (name, position) pair that
     is ambiguous in the pool is skipped outright — the validator would
     rightly refuse to publish a guess.
  2. squad: top selected_by_percent per position up to the quota, skipping
     candidates the club cap refuses.
  3. budget: while over 100.0m, the swap losing the least ownership per pound
     saved (cheaper player, same position, cap-legal) — mirroring
     fpl_articles._squad_for_formation's repair, ownership-denominated.
  4. XI: the legal formation whose top-owned members sum to the most
     ownership; bench = the other GK at bench_order 1, then the remaining
     outfielders by ownership.
  5. armband: captain = the highest-owned premium (>= PREMIUM_PRICE) in the
     XI, vice the next; short of two premiums, the highest-owned XI players
     fill in.
"""

from __future__ import annotations

from games.fpl.state import MAX_PER_CLUB, SQUAD_BUDGET, SQUAD_QUOTA, XI_MAX, XI_MIN

# The armband tier. FPL prices its captaincy staples (Haaland, Salah, the
# season's premium forwards/mids) from 10.0m up; the template's captain is
# whichever of them the crowd owns most.
PREMIUM_PRICE = 10.0

TEAM_NAME = "The Consensus XI"


def _rank_key(p: dict) -> tuple:
    """Ownership first; price then name break ties deterministically."""
    return (-p["ownership"], p["price"], p["name"])


def _legal_formations() -> list:
    """Every legal XI outfield split as {"GK": 1, "DEF": d, "MID": m, "FWD": f}."""
    out = []
    for d in range(XI_MIN["DEF"], XI_MAX["DEF"] + 1):
        for m in range(XI_MIN["MID"], XI_MAX["MID"] + 1):
            f = 10 - d - m
            if XI_MIN["FWD"] <= f <= XI_MAX["FWD"]:
                out.append({"GK": 1, "DEF": d, "MID": m, "FWD": f})
    return out


def _candidates(players: list) -> list:
    """The candidate pool: priced, owned by someone, still in the game, and
    unambiguous — see the module docstring's step 1."""
    seen: dict = {}
    for p in players:
        if p.get("price") is None or p.get("status") == "u":
            continue
        seen.setdefault((p["name"], p["position"]), []).append(p)
    return sorted((v[0] for v in seen.values() if len(v) == 1), key=_rank_key)


def build_consensus_state(players: list, gameweek: int) -> dict:
    """The most-owned legal 15 as a state dict. Raises ValueError when no
    legal template exists (or the pool carries no ownership data at all —
    a stale pre-season bootstrap must not silently produce an all-4.0m squad).
    """
    pool = _candidates(players)
    if not any(p["ownership"] > 0 for p in pool):
        raise ValueError("the player pool carries no ownership data — refresh "
                         "the bootstrap before resetting the consensus squad")

    # --- 2. quota fill, club cap inline -------------------------------------
    squad: list = []
    names: set = set()

    def club_count(team, exclude=None):
        return sum(1 for s in squad if s["team"] == team and s is not exclude)

    for pos, need in SQUAD_QUOTA.items():
        taken = 0
        for p in pool:
            if taken >= need or p["position"] != pos:
                continue
            if p["name"] in names or club_count(p["team"]) >= MAX_PER_CLUB:
                continue
            squad.append(dict(p))
            names.add(p["name"])
            taken += 1
        if taken < need:
            raise ValueError(f"cannot fill the {pos} quota ({need}) from the "
                             f"pool under the {MAX_PER_CLUB}-per-club cap")

    # --- 3. budget repair: least ownership lost per pound saved --------------
    def total_cost():
        return round(sum(s["price"] for s in squad), 1)

    guard = 0
    while total_cost() > SQUAD_BUDGET and guard < len(squad) * len(pool):
        guard += 1
        best_swap, best_ratio = None, None
        for i, slot in enumerate(squad):
            cheaper = [p for p in pool
                       if p["position"] == slot["position"]
                       and p["name"] not in names
                       and p["price"] < slot["price"]
                       and club_count(p["team"], exclude=slot) < MAX_PER_CLUB]
            if not cheaper:
                continue
            repl = cheaper[0]                    # pool is ownership-sorted
            saved = slot["price"] - repl["price"]
            ratio = (slot["ownership"] - repl["ownership"]) / saved
            if best_ratio is None or ratio < best_ratio:
                best_ratio, best_swap = ratio, (i, repl)
        if best_swap is None:
            break
        i, repl = best_swap
        names.discard(squad[i]["name"])
        squad[i] = dict(repl)
        names.add(repl["name"])
    if total_cost() > SQUAD_BUDGET:
        raise ValueError(f"no most-owned squad fits the {SQUAD_BUDGET}m budget "
                         f"(cheapest repair still costs {total_cost()}m)")

    # --- 4. XI: the formation the crowd owns hardest -------------------------
    by_pos = {pos: sorted((s for s in squad if s["position"] == pos),
                          key=_rank_key)
              for pos in SQUAD_QUOTA}
    best_xi, best_key = None, None
    for formation in _legal_formations():
        xi = [p for pos in ("GK", "DEF", "MID", "FWD")
              for p in by_pos[pos][:formation[pos]]]
        key = (sum(p["ownership"] for p in xi),
               formation["DEF"], formation["MID"])   # deterministic tie-break
        if best_key is None or key > best_key:
            best_key, best_xi = key, xi
    xi_names = {p["name"] for p in best_xi}
    bench_gk = next(s for s in squad if s["position"] == "GK"
                    and s["name"] not in xi_names)
    bench_out = sorted((s for s in squad if s["position"] != "GK"
                        and s["name"] not in xi_names), key=_rank_key)
    bench = [bench_gk] + bench_out

    # --- 5. armband ----------------------------------------------------------
    xi_sorted = sorted(best_xi, key=_rank_key)
    premiums = [p["name"] for p in xi_sorted if p["price"] >= PREMIUM_PRICE]
    order = premiums + [p["name"] for p in xi_sorted
                        if p["name"] not in premiums]
    captain, vice = order[0], order[1]

    # --- state ---------------------------------------------------------------
    def entry(p, starter, bench_order=None):
        return {"name": p["name"], "position": p["position"],
                "is_starter": starter, "bench_order": bench_order,
                "is_captain": p["name"] == captain,
                "is_vice": p["name"] == vice}

    return {
        "team_name": TEAM_NAME,
        "strategy": "consensus",
        "free_transfers": 1,
        "chips_used": ["wildcard"],
        "method_note": (
            f"Rebuilt for gameweek {gameweek} as the most-owned legal "
            f"template: top selected_by_percent per position from the "
            f"official bootstrap, greedily legalised under budget, quota and "
            f"club cap; captain = highest-owned premium "
            f"(>= {PREMIUM_PRICE}m), vice next. This rebuild is the squad's "
            f"declared Wildcard; the GW1 expert mention-tally method is "
            f"retired. GW1 is graded as published."),
        "squad": ([entry(p, True) for p in best_xi]
                  + [entry(p, False, i) for i, p in enumerate(bench, 1)]),
    }
