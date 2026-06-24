"""Holdet YOLO-D — anti-chalk variance build (same rules as GOLD, variance objective)."""

from __future__ import annotations

from games import holdet_common as hc


def run(state: dict, fantasy_round: int, sims: int = 50_000) -> None:
    if not state.get("squad") or state["squad"][0].get("_example"):
        print("  [holdet_yolo] state.json not populated — upload 'YOLO-D' "
              "squad + ownership screenshots (ownership matters for anti-chalk).")
        return
    _mean, ceiling = hc.growth_tables(fantasy_round, sims, state)
    hc.print_order_book(f"Holdet YOLO ({state.get('team_name', 'Always 2nd 2')})",
                        state, fantasy_round, ceiling,
                        free_first_transfer=(fantasy_round == 1), variance_mode=True)
    _flag_differentials(state)


def _flag_differentials(state):
    diffs = [p for p in state["squad"]
             if p.get("ownership_pct") is not None and p["ownership_pct"] < 10]
    if diffs:
        print("\n  Differentials (<10% owned) carrying the variance bet:")
        for p in diffs:
            print(f"    {p['name']:<22} {p['team']:<14} own={p['ownership_pct']:.1f}%")
    else:
        print("\n  (No ownership data yet — upload to evaluate anti-chalk edges.)")
