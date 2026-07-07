"""Greedy Holdet transfer optimiser.

Repeatedly applies the best same-position swap whose net LIFE-WEIGHTED growth beats
the 1% fee, respecting budget and the max-4-per-nation cap, until no positive-net
swap remains (the "experts churn 6-9 players" approach).

Objective value of a slot = round growth x slot_life(team) — the expected number of
remaining rounds the slot stays alive (holdet_common.slot_life). In knockouts this
tilts equal round-EV toward teams likely to advance: a France slot keeps earning in
later rounds, a coin-flip slot dies with the team (Germany R32, USA R16).

EV games (`ev` objective) additionally cap coin-flip teams (advance prob inside
holdet_common.COINFLIP_BAND) at CONCENTRATION_LIMIT players — the mean is linear so
EV never sees correlated elimination risk; the cap is the guardrail.

Candidate pool = live market rows from holdet_api (current prices + ownership) that
have a modelled growth. Same-position swaps keep the formation valid.

Usage: python optimize_holdet.py <game> <ev|risky> [round]
       (round defaults to the game's state.json current_round)
"""

from __future__ import annotations

import json
import sys
import unicodedata

from core import holdet_api
from games import holdet_common as hc

HERE = __file__.rsplit("/", 1)[0]


def norm(s: str) -> str:
    """Full-name match key: strip accents, lowercase, letters only, drop Jr/Junior.
    Full name (not surname) so common surnames like 'Williams' don't collide."""
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")
    toks = [t for t in "".join(ch if ch.isalpha() else " " for ch in s.lower()).split()
            if t not in ("jr", "junior", "jnr")]
    return "".join(toks)


def optimize(game: str, objective: str, rnd: int | None = None):
    state = json.load(open(f"{HERE}/games/{game}/state.json"))
    rnd = rnd or state.get("current_round", 1)
    w = 0.10 if objective == "ev" else 0.50
    mean, ceil = hc.growth_tables(rnd, 20000, {"research_weight": w,
                                               "ceiling_percentile": 0.85})
    growth = mean if objective == "ev" else ceil
    gnorm: dict[str, float] = {}
    for n, v in growth.items():
        gnorm[norm(n)] = max(v, gnorm.get(norm(n), float("-inf")))

    ctx = hc.team_context(rnd)
    life = {team: hc.slot_life(team, rnd, ctx) for team in ctx}

    def value(g: float, nation: str) -> float:
        return g * life.get(nation, 1.0)

    def coinflip(nation: str) -> bool:
        p = hc.advance_prob(nation, rnd, ctx)
        return hc.COINFLIP_BAND[0] <= p <= hc.COINFLIP_BAND[1]

    squad = [{"name": p["name"], "pos": p["position"], "value": p["price"],
              "growth": gnorm.get(norm(p["name"]), 0.0), "nation": p["team"]}
             for p in state["squad"]]
    bank = state.get("cash", 0)

    owned = {norm(p["name"]) for p in state["squad"]}
    cands = []
    for c in holdet_api.players(rnd):
        k = norm(c["name"])
        if not c.get("price") or k in owned or k not in gnorm:
            continue
        cands.append({"name": c["name"], "pos": c["pos"], "price": c["price"],
                      "growth": gnorm[k], "nation": c["team"],
                      "own": (c.get("ownership") or 0.0) * 100})

    transfers = []
    while True:
        best = None
        for o in squad:
            for c in cands:
                if c["pos"] != o["pos"]:
                    continue
                fee = hc.TRANSFER_FEE_RATE * c["price"]
                if c["price"] + fee > o["value"] + bank:
                    continue
                nations = [s["nation"] for s in squad if s is not o] + [c["nation"]]
                if nations.count(c["nation"]) > hc.MAX_PER_NATION:
                    continue
                # EV games: don't build >CONCENTRATION_LIMIT on a coin-flip team.
                if objective == "ev" and coinflip(c["nation"]) \
                        and nations.count(c["nation"]) > hc.CONCENTRATION_LIMIT:
                    continue
                net = value(c["growth"], c["nation"]) - value(o["growth"], o["nation"]) - fee
                if net > 0 and (best is None or net > best[0]):
                    best = (net, o, c, fee)
        if not best:
            break
        net, o, c, fee = best
        bank += o["value"] - c["price"] - fee
        squad = [dict(c, value=c["price"]) if s is o else s for s in squad]
        cands = [x for x in cands if x["name"] != c["name"]]
        transfers.append((o["name"], c["name"], c["nation"], c.get("own", 0.0), net, fee))

    return transfers, squad, bank, life, rnd


if __name__ == "__main__":
    game = sys.argv[1] if len(sys.argv) > 1 else "holdet_gold"
    obj = sys.argv[2] if len(sys.argv) > 2 else "ev"
    rnd_arg = int(sys.argv[3]) if len(sys.argv) > 3 else None
    transfers, squad, bank, life, rnd = optimize(game, obj, rnd_arg)
    label = "MAX-EV (optimal)" if obj == "ev" else "RISKY (ceiling)"
    print(f"=== {game} — {label} — round {rnd} (growth x slot-life) ===")
    print(f"transfers ({len(transfers)}), fees deducted, bank left {bank:,.0f}:")
    for o, c, nat, own, net, fee in transfers:
        print(f"  OUT {o:<18} -> IN {c:<20} ({nat}, {own:.1f}%, life {life.get(nat, 1.0):.2f})"
              f"  net +{net:,.0f} (fee {fee:,.0f})")
    total = sum(s["growth"] * life.get(s["nation"], 1.0) for s in squad)
    print(f"\nresulting team (total life-weighted "
          f"{'growth' if obj == 'ev' else 'ceiling'} {total:,.0f}):")
    for s in sorted(squad, key=lambda s: -s["growth"] * life.get(s["nation"], 1.0)):
        print(f"  {s['growth'] * life.get(s['nation'], 1.0):>9,.0f}  "
              f"{s['name']:<20} {s['pos']:<4} {s['nation']:<14} life {life.get(s['nation'], 1.0):.2f}")
    for team, n, p_adv in hc.concentration_flags(
            [{"name": s["name"], "team": s["nation"]} for s in squad], rnd):
        print(f"\n⚠ CONCENTRATION: {n} players on {team} at P(advance)={p_adv:.0%}")
