"""Transfer optimizer v1 — every legal single swap on discounted-horizon delta.

Drives the weekly transfer decision for both published squads and the
`transfers` content beat (spec §5); GW2's first user is the Watkins decision.
Pure: the caller (manage.py's --transfers) loads the states, the horizon
matrix (data/fpl/xpts_gw*.json), the dossier flags and the notes — this
module only ranks.

A swap is legal when it is same-position, budget-feasible (selling price +
bank funds the incoming price), keeps the 3-per-club cap AFTER the swap, and
the incoming player clears the minutes floor (start_prob >= START_FLOOR when
the horizon rows carry one, unless a sourced note vouches — the same bar the
optimizer and the publish gate hold).

Scoring: delta = discounted change in the best legal weekly XI plus captain
mean. Partial analysis pools use player sums. Autosub/vice option value is not
yet modelled.
DISCOUNT = 0.95 is the squad doctrine's horizon band (the GW1 build discounted
GW1-6 at 1.00 -> 0.78 ~= 0.95^5, docs/STRATEGY.md 08-19). A player missing
from a gameweek's rows contributes 0 for that week — a blank prices itself.

hit_adjusted_delta subtracts the 4-point hit exactly when free_transfers == 0
(this swap would be the week's second); otherwise it equals delta, so the two
columns diverging is itself the "this one costs a hit" signal.

Players in `flagged` (red dossiers — games/fpl/dossier) are forced to the top
of the table as sale candidates regardless of delta sign: a red flag is a
question the operator must answer, not a row to sort away.
"""

from __future__ import annotations

DISCOUNT = 0.95
HIT_COST = 4.0
TOP_N = 5
PER_PLAYER_CAP = 2   # rows any single outgoing player may occupy
MAX_PER_CLUB = 3
START_FLOOR = 0.75


def weekly_utility(squad: list, rows: dict) -> float:
    """Best legal XI plus captain mean; no claimed autosub/vice option value.

    Partial pools retain player-level valuation for analysis callers. Production
    15-player squads must support a legal formation and are valued as teams.
    """
    if len(squad) != 15:
        return sum((rows.get(p["name"]) or {}).get("x_points", 0) for p in squad)
    groups = {pos: sorted(((rows.get(p["name"]) or {}).get("x_points", 0)
                           for p in squad if p["position"] == pos), reverse=True)
              for pos in ("GK", "DEF", "MID", "FWD")}
    scores = []
    for defenders in range(3, 6):
        for midfielders in range(2, 6):
            forwards = 10 - defenders - midfielders
            counts = dict(GK=1, DEF=defenders, MID=midfielders, FWD=forwards)
            if not 1 <= forwards <= 3 or any(len(groups[p]) < n for p, n in counts.items()):
                continue
            xi = [xp for pos, n in counts.items() for xp in groups[pos][:n]]
            scores.append(sum(xi) + max(xi))
    if not scores:
        raise ValueError("squad cannot field a legal XI")
    return max(scores)


def _xp(rows_by_gw: dict, gws: list, name: str) -> list:
    return [(rows_by_gw[gw].get(name) or {}).get("x_points", 0.0)
            for gw in gws]


def recommend(state: dict, rows_by_gw: dict, free_transfers: int,
              bank: float, flagged=None, notes=None, cleared=None,
              top: int = TOP_N) -> list:
    """Top `top` legal single swaps for one squad state.

    state:       a games/fpl state dict, entries enriched with team + price
                 (games.fpl.state.validate_state output — prices are selling
                 prices for v1; the sell-on-fee ledger is future work).
    rows_by_gw:  {gameweek: {name: {"team", "position", "price", "x_points",
                 optional "start_prob"}}} — the horizon matrix.
    flagged:     names whose dossier is red — a red dossier means "we owe this
                 player a look", NOT "sell him". Mbeumo was red every week of
                 August purely for a post-blank outflow spike, and the table
                 called him a "forced sale candidate" on the same line as a
                 research note that said hold. Red-and-cleared players are
                 labelled as investigated and are NOT pushed to the head of the
                 table; only red-and-unresolved ones are.
    notes:       names with a sourced research note — may override the floor.
    cleared:     names whose note investigated the flag and found nothing —
                 red, but not for sale.

    Returns [{"out", "in", "position", "delta", "hit_adjusted_delta",
    "reasons"}], flagged sales first, then by delta descending.
    """
    flagged = set(flagged or ())
    notes = set(notes or ())
    cleared = set(cleared or ())
    for_sale = flagged - cleared
    gws = sorted(rows_by_gw)
    if not gws:
        return []
    pool = rows_by_gw[gws[0]]

    squad = list(state.get("squad", []))
    squad_names = {e["name"] for e in squad}
    before = [weekly_utility(squad, rows_by_gw[gw]) for gw in gws]
    club_counts: dict = {}
    for e in squad:
        club_counts[e["team"]] = club_counts.get(e["team"], 0) + 1

    swaps = []
    for out_e in squad:
        sell_budget = round(bank + (out_e.get("price") or 0.0), 1)
        for name, cand in pool.items():
            if name in squad_names or cand.get("position") != out_e["position"]:
                continue
            price = cand.get("price")
            if price is None or price > sell_budget:
                continue
            after = (club_counts.get(cand.get("team"), 0) + 1
                     - (1 if cand.get("team") == out_e["team"] else 0))
            if after > MAX_PER_CLUB:
                continue
            sp = cand.get("start_prob")
            if sp is not None and sp < START_FLOOR and name not in notes:
                continue
            after_squad = [e for e in squad if e["name"] != out_e["name"]] + [dict(cand, name=name)]
            delta = sum(DISCOUNT ** i * (weekly_utility(after_squad, rows_by_gw[gw]) - before[i])
                        for i, gw in enumerate(gws))
            delta = round(delta, 2)
            hit_adjusted = round(delta - HIT_COST, 2) \
                if free_transfers == 0 else delta

            reasons = []
            if len(squad) == 15:
                reasons.append("Legal weekly XI + captain mean; autosub and vice option value excluded")
            if out_e["name"] in for_sale:
                reasons.append(f"{out_e['name']} is flagged red by the "
                               f"dossier and unresolved — sale candidate")
            elif out_e["name"] in flagged:
                reasons.append(f"{out_e['name']} was flagged red and "
                               f"investigated — the note holds him; this row "
                               f"is an option, not a recommendation")
            reasons.append(f"{'+' if delta >= 0 else ''}{delta:.2f} xPts over "
                           f"the {len(gws)}-GW horizon (discounted "
                           f"{DISCOUNT}/week)")
            if free_transfers == 0:
                reasons.append(f"-{HIT_COST:.0f} hit applies "
                               f"(0 free transfers)")
            reasons.append(f"funds: {sell_budget:.1f} "
                           f"(sale {out_e.get('price', 0):.1f} + bank "
                           f"{bank:.1f}) covers {price:.1f}")
            swaps.append({"out": out_e["name"], "in": name,
                          "position": out_e["position"], "delta": delta,
                          "hit_adjusted_delta": hit_adjusted,
                          "reasons": reasons})

    swaps.sort(key=lambda s: (s["out"] not in for_sale, -s["delta"]))
    # One outgoing player with many affordable replacements would otherwise eat
    # the whole table: on GW2 Thursday five Gibbs-White rows hid the fact that
    # Watkins, who was leaving the league, needed selling at all.
    seen: dict = {}
    spread = []
    for swap in swaps:
        n = seen.get(swap["out"], 0)
        if n >= PER_PLAYER_CAP:
            continue
        seen[swap["out"]] = n + 1
        spread.append(swap)
    return spread[:top]


def format_table(recs: list, team_name: str, free_transfers: int,
                 bank: float) -> str:
    """The CLI table manage.py prints — one line per recommended swap."""
    lines = [f"\n=== Transfers — {team_name} "
             f"({free_transfers} FT, {bank:.1f} in the bank) ==="]
    if not recs:
        lines.append("  no legal swap improves the horizon — hold.")
        return "\n".join(lines)
    lines.append(f"  {'out':<18} {'in':<18} {'pos':<4} "
                 f"{'delta':>7} {'w/ hit':>7}")
    for r in recs:
        lines.append(f"  {r['out']:<18} {r['in']:<18} {r['position']:<4} "
                     f"{r['delta']:>7.2f} {r['hit_adjusted_delta']:>7.2f}")
        for reason in r["reasons"]:
            lines.append(f"      - {reason}")
    return "\n".join(lines)
