"""Holdet GOLD T1 ("Always 2nd") — straight expected-growth maximisation."""

from __future__ import annotations

from games import holdet_common as hc


def run(state: dict, fantasy_round: int, sims: int = 50_000) -> None:
    if not state.get("squad") or state["squad"][0].get("_example"):
        print("  [holdet_gold] state.json not populated — upload 'Always 2nd' "
              "squad + cash + team value screenshots.")
        return
    growth, _ceiling = hc.growth_tables(fantasy_round, sims, state)
    hc.print_order_book(f"Holdet GOLD ({state.get('team_name', 'Alwaysss 2nd')})",
                        state, fantasy_round, growth,
                        free_first_transfer=(fantasy_round == 1))
    print("\n  Transfers: in/out suggestions need the full player market (available "
          "players + prices), not yet loaded. Lowest-growth holds are the OUT "
          "candidates; captain shown above.")
