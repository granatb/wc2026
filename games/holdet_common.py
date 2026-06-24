"""Shared Holdet engine for all three Holdet games (gold, yolo, free).

The kroner scoring table IS the value growth. This module owns:
  - the scoring table (single copy, imported by every holdet model)
  - per-player expected growth from engine event means
  - the trade rule (execute iff next-round growth delta > 1% * incoming price)
  - position quirks vs FIFA (Kimmich=MID, Raphinha/Olise/Doku/Saka/Gakpo=FWD)
  - squad constraints (budget 50M, max 4 / nation, 11 players, no bench)

The three games differ only in:
  - holdet_gold: unlimited contracts (Guld). Variance-neutral, growth-max.
  - holdet_yolo: unlimited contracts, but anti-chalk / high-variance objective.
  - holdet_free: only 3 contracts (transfers) for the WHOLE tournament; captain
    changes are free. -> hoard contracts, raise the trade bar.
Each model passes a small config to the helpers here.

Values denominated in kroner (kr).
"""

from __future__ import annotations

from core import engine_events, fixtures, research, espn, odds_math

# --- Scoring table (kr) -----------------------------------------------------
GOAL = {"FWD": 125_000, "MID": 150_000, "DEF": 175_000, "GK": 250_000}
ASSIST = 60_000
SOT = 10_000
DECISIVE_WIN = 40_000           # decisive-to-win
DECISIVE_DRAW = 20_000          # decisive-to-draw
MOTM = 33_000
RESULT = {"win": 25_000, "draw": 5_000, "loss": -8_000}
TEAM_GOAL = 10_000              # per goal the player's team scores
OPP_GOAL = -8_000               # per goal conceded
CS = {"DEF": 50_000, "GK": 75_000}
GK_SAVE = 5_000
PEN_SAVE = 100_000
YELLOW = -20_000
RED = -50_000
OWN_GOAL = -50_000
HATTRICK = 100_000
PLAYED = 7_000
NOT_PLAYED = -5_000

INTEREST_PER_ROUND = 0.01       # 1% on cash
TRANSFER_FEE_RATE = 0.01        # 1% of incoming player's value (R1 free)
TRADE_THRESHOLD_RATE = 0.01     # execute iff growth delta > 1% * incoming price

BUDGET = 50_000_000
MAX_PER_NATION = 4
SQUAD_SIZE = 11                 # no bench

# Position quirks: Holdet position differs from FIFA for these players.
POSITION_OVERRIDE = {
    "Kimmich": "MID",
    "Raphinha": "FWD",
    "Olise": "FWD",
    "Doku": "FWD",
    "Saka": "FWD",
    "Gakpo": "FWD",
}


def holdet_position(name: str, fifa_position: str) -> str:
    return POSITION_OVERRIDE.get(name, fifa_position)


def team_context(fantasy_round: int) -> dict:
    """{team: (lam_for, lam_against, pWin, pDraw, pLoss)} for the round, from the
    cached match odds (Dixon-Coles), else the ratings priors. Drives the result and
    team-goal/opp-goal terms — the downside that makes a hard fixture a value drop."""
    ctx: dict[str, tuple] = {}
    for f in fixtures.by_round(fantasy_round):
        cached = espn.load_match_odds(f.match_id)
        if cached and cached.get("lam_home") is not None:
            lh, la, rho = cached["lam_home"], cached["lam_away"], cached.get("rho", 0.0)
        else:
            lh, la = f.lambdas()
            rho = 0.0
        pH, pD, pA = odds_math.outcome_from_matrix(odds_math.score_matrix_dc(lh, la, rho))
        ctx[f.home] = (lh, la, pH, pD, pA)
        ctx[f.away] = (la, lh, pA, pD, pH)
    return ctx


def expected_growth(ev: dict, name: str, team_ctx: dict | None = None) -> float:
    """Expected kr growth for one player in a round, from mean events + team context.

    `ev` is an engine_events.event_means() entry. `team_ctx` (from team_context) adds
    the team-level terms — result (win/draw/loss), team-goals (+10k each) and
    opp-goals (−8k each) — which every playing player accrues and which capture
    hard-fixture downside.
    """
    pos = holdet_position(name, ev["position"])
    g = ev["goals"]
    kr = 0.0
    kr += g * GOAL.get(pos, GOAL["FWD"])
    kr += ev["assists"] * ASSIST
    kr += ev["sot"] * SOT
    kr += ev["motm"] * MOTM
    kr += ev["decisive_win"] * DECISIVE_WIN + ev["decisive_draw"] * DECISIVE_DRAW
    kr += ev["played"] * PLAYED + (1 - ev["played"]) * NOT_PLAYED
    if pos in CS:
        kr += ev["clean_sheet"] * CS[pos]
    if pos == "GK":
        kr += ev["saves"] * GK_SAVE
    kr += ev["yellow"] * YELLOW
    kr += ev["red"] * RED
    if team_ctx and ev["team"] in team_ctx:
        lam_for, lam_against, pW, pD, pL = team_ctx[ev["team"]]
        result_ev = pW * RESULT["win"] + pD * RESULT["draw"] + pL * RESULT["loss"]
        team_term = result_ev + TEAM_GOAL * lam_for + OPP_GOAL * lam_against
        kr += ev["played"] * team_term  # only when the player is on the pitch
    return kr


def load_round_market_rates(fantasy_round: int) -> dict[str, float]:
    """Per-player goal rates from cached bookmaker props for this round.

    Reads the ESPN player-prop cache for the round (written by `manage.py --refresh`).
    Returns {} until props are fetched — the engine then falls back to priors via the
    blend rules.
    """
    return espn.load_player_rates(fantasy_round)


def growth_tables(fantasy_round: int, sims: int, state: dict):
    """Run the blended sim once and return (mean_growth, ceiling_growth) per player.

    mean_growth   -> used by EV-max games (GOLD, FREE).
    ceiling_growth-> P-q of the goal distribution priced through the kr table; used by
                     the variance game (YOLO).
    """
    w = state.get("research_weight", 0.0)
    q = state.get("ceiling_percentile", 0.85)
    entries = research.load_entries("players", fantasy_round)
    market = load_round_market_rates(fantasy_round)
    players, _ = engine_events.simulate_round(
        fantasy_round, sims=sims, market_rates=market, research=entries,
        research_weight=w)
    means = engine_events.event_means(players)
    ctx = team_context(fantasy_round)

    mean_growth: dict[str, float] = {}
    ceiling_growth: dict[str, float] = {}
    for name, ev in means.items():
        gs = players[name].goal_samples
        p_hat = (sum(1 for x in gs if x >= 3) / len(gs)) if gs else 0.0
        base = expected_growth(ev, name, ctx) + p_hat * HATTRICK   # MOTM now flows via ev
        mean_growth[name] = base
        pos = holdet_position(name, ev["position"])
        gv = GOAL.get(pos, GOAL["FWD"])
        p_goals = engine_events.percentile(gs, q)
        # Swap the mean-goal contribution for the q-percentile (ceiling) one.
        ceiling_growth[name] = base - ev["goals"] * gv + p_goals * gv
    return mean_growth, ceiling_growth


def trade_is_worth_it(out_player: dict, in_player: dict,
                      growth: dict[str, float], *, free_transfer: bool) -> tuple[bool, float]:
    """Core trade rule. Returns (execute?, net_kr_delta).

    Execute iff next-round growth delta > 1% * incoming price (the transfer fee),
    unless the transfer is free.
    """
    in_price = in_player.get("price", 0.0)
    fee = 0.0 if free_transfer else TRANSFER_FEE_RATE * in_price
    delta = growth.get(in_player["name"], 0.0) - growth.get(out_player["name"], 0.0)
    bar = TRADE_THRESHOLD_RATE * in_price  # the "> 1% * incoming price" rule
    return (delta - fee) > bar, delta - fee


def best_captain(squad: list[dict], growth: dict[str, float]) -> dict | None:
    """Captain = x2 growth (free to change each round) -> pick max-growth player."""
    if not squad:
        return None
    return max(squad, key=lambda p: growth.get(p["name"], 0.0))


def print_order_book(label: str, state: dict, fantasy_round: int,
                     growth: dict[str, float], *, contracts_left=None,
                     free_first_transfer=False, variance_mode=False) -> None:
    squad = state.get("squad", [])
    print(f"\n=== {label} — round {fantasy_round} order book ===")
    lock = fixtures.round_lock_time(fantasy_round)
    print(f"  lock (first kickoff): {lock} — everything locks here, NO live mgmt.")

    ranked = sorted(squad, key=lambda p: growth.get(p["name"], 0.0), reverse=True)
    print("\n  Expected growth (kr) this round:")
    for p in ranked:
        print(f"    {growth.get(p['name'], 0.0):>10,.0f}  {p['name']:<22} "
              f"{p['team']:<14} {holdet_position(p['name'], p['position'])}")

    cap = best_captain(squad, growth)
    if cap:
        print(f"\n  Captain (x2, free): {cap['name']} "
              f"(+{growth.get(cap['name'], 0.0):,.0f} kr doubled)")

    if contracts_left is not None:
        print(f"\n  Contracts left for whole tournament: {contracts_left} "
              f"— hoard; only trade on big edges.")
    if variance_mode:
        print("  Objective: anti-chalk / variance — prefer low-owned, high-ceiling "
              "differentials over raw EV where rank upside justifies it.")
