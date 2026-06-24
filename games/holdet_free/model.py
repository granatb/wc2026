"""Holdet FREE — same scoring, only 3 contracts for the whole tournament.

Captain changes are free; transfers are scarce. Default recommendation is to NOT
spend a contract, and to show the cumulative edge a swap would need to justify it.
"""

from __future__ import annotations

from games import holdet_common as hc


def run(state: dict, fantasy_round: int, sims: int = 50_000) -> None:
    if not state.get("squad") or state["squad"][0].get("_example"):
        print("  [holdet_free] state.json not populated — upload 'FREE' squad "
              "screenshot. Also confirm contracts used so far.")
        return
    growth, _ceiling = hc.growth_tables(fantasy_round, sims, state)
    left = state.get("contracts_total", 3) - state.get("contracts_used", 0)
    hc.print_order_book(f"Holdet FREE ({state.get('team_name', 'Always 2nd')})",
                        state, fantasy_round, growth, contracts_left=left)

    print("\n  Contract decision: default HOLD.")
    print("  Spend a contract only if the incoming player's CUMULATIVE growth edge "
          "over remaining rounds clears 1% × price AND beats holding the contract "
          f"for a later swing. Contracts remaining: {left}.")
