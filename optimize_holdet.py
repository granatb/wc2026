"""Greedy Holdet transfer optimiser.

Repeatedly applies the best same-position swap whose net growth beats the 1% fee,
respecting budget and the max-4-per-nation cap, until no positive-net swap remains
(the "experts churn 6-9 players" approach). Objective = mean growth (optimal/EV) or
ceiling (risky/variance).

Candidate pool = players that have BOTH a market price (data/holdet_prices.json) and a
modelled growth (core/ratings priors). Same-position swaps keep the formation valid.

Usage: python optimize_holdet.py <game> <ev|risky>
"""

from __future__ import annotations

import json
import sys
import unicodedata

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


def optimize(game: str, objective: str):
    state = json.load(open(f"{HERE}/games/{game}/state.json"))
    prices = json.load(open(f"{HERE}/data/holdet_prices.json"))["players"]
    w = 0.10 if objective == "ev" else 0.50
    mean, ceil = hc.growth_tables(2, 20000, {"research_weight": w, "ceiling_percentile": 0.85})
    growth = mean if objective == "ev" else ceil
    gnorm = {norm(n): v for n, v in growth.items()}

    squad = [{"name": p["name"], "pos": p["position"], "value": p["price"],
              "growth": growth.get(p["name"], 0.0), "nation": p["team"]}
             for p in state["squad"]]
    bank = state.get("cash", 0)

    owned = {norm(p["name"]) for p in state["squad"]}
    cands = []
    for c in prices:
        k = norm(c["name"])
        if k in owned or k not in gnorm:
            continue
        cands.append({"name": c["name"], "pos": c["position"], "price": c["price"],
                      "growth": gnorm[k], "nation": c["team"]})

    transfers = []
    while True:
        best = None
        for o in squad:
            for c in cands:
                if c["pos"] != o["pos"]:
                    continue
                fee = 0.01 * c["price"]
                if c["price"] + fee > o["value"] + bank:
                    continue
                nations = [s["nation"] for s in squad if s is not o] + [c["nation"]]
                if nations.count(c["nation"]) > 4:
                    continue
                net = (c["growth"] - o["growth"]) - fee
                if net > 0 and (best is None or net > best[0]):
                    best = (net, o, c, fee)
        if not best:
            break
        net, o, c, fee = best
        bank += o["value"] - c["price"] - fee
        squad = [dict(c, value=c["price"]) if s is o else s for s in squad]
        cands = [x for x in cands if x["name"] != c["name"]]
        transfers.append((o["name"], c["name"], net, fee))

    return transfers, squad, bank


if __name__ == "__main__":
    game = sys.argv[1] if len(sys.argv) > 1 else "holdet_gold"
    obj = sys.argv[2] if len(sys.argv) > 2 else "ev"
    transfers, squad, bank = optimize(game, obj)
    label = "MAX-EV (optimal)" if obj == "ev" else "RISKY (ceiling)"
    print(f"=== {game} — {label} ===")
    print(f"transfers ({len(transfers)}), fees deducted, bank left {bank:,.0f}:")
    for o, c, net, fee in transfers:
        print(f"  OUT {o:<18} -> IN {c:<18} net +{net:,.0f} (fee {fee:,.0f})")
    total = sum(s["growth"] for s in squad)
    print(f"\nresulting team (total {'growth' if obj=='ev' else 'ceiling'} {total:,.0f}):")
    for s in sorted(squad, key=lambda s: -s["growth"]):
        print(f"  {s['growth']:>9,.0f}  {s['name']:<18} {s['pos']} {s['nation']}")
