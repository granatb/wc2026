"""FIFA World Cup Fantasy model.

Maps the shared engine's per-player samples onto the official points scale, then
emits the order book: starting XI + captain, the live captain chain with hold/roll
thresholds, manual-sub candidates, and sub-5% scouting picks.

Point VALUES are placeholders until confirmed from screenshots (see rules.md).
"""

from __future__ import annotations

from core import engine_events, fixtures, research, espn

# FIFA official points — CONFIRMED from the in-app "How to score" table (2026).
GOAL_PTS = {"GK": 9, "DEF": 7, "MID": 6, "FWD": 5}
ASSIST_PTS = 3
CS_PTS = {"GK": 5, "DEF": 5, "MID": 1, "FWD": 0}   # 60+ mins
APPEARANCE_60 = 2          # +1 for appearing, +1 more for 60+ mins (we model starters as 60+)
APPEARANCE_SUB = 1
YELLOW_PTS = -1
RED_PTS = -2
SCOUTING_BONUS = 2
SCOUTING_OWNERSHIP_CAP = 5.0  # percent

# Stat-based scoring (confirmed). SoT/saves/conceded are computed from simulated events;
# MID tackles/chances use an EXPECTED per-90 rate (the engine doesn't sample those events
# — the "+1 per N" scoring divisor is exact, only the rate is an estimate).
SOT_PTS = 0.5            # FWD: +1 per 2 shots on target
SAVE_PTS = 1.0 / 3.0     # GK:  +1 per 3 saves
CONCEDE_PTS = -1         # GK/DEF: -1 per goal conceded beyond the first
# MID defensive contribution (+1/3 tackles, +1/2 chances). Calibrated 2026-07-06 against
# realized FIFA points R1–R5 (n=288 full-90 MID player-rounds; official roundPoints minus
# goals/assists/CS/appearance/cards): realized stat credit averages 0.84 pts/90 — the old
# role-shaped constants paid ~1.27/90 to every MID, a +0.44/90 over-credit. The shaping
# itself had ZERO signal (corr(prior gs+ash, realized credit) = -0.00; OLS |t| < 0.7), so
# it's flattened: within-MID role differences are carried by goal/assist props, and the
# realized within-MID spread (ball-winners ~2/90 vs metronomes ~0.3/90) isn't predictable
# from our priors. Backtest R2–R5: MID MAE 2.20 -> 2.07, Spearman .215 -> .229, all rounds.
MID_TACKLES_MAX = 1.5    # tackles/90 (flat across roles)
MID_TACKLES_K = 0.0      # share-based tackle shaping removed — no realized signal
MID_CHANCES_BASE = 0.68  # chances/90 (flat across roles)
MID_CHANCES_K = 0.0      # assist-share chances shaping removed — no realized signal
# NOT in this game: Player of the Match, DEF tackle/CBI points, outside-box bonus.
# Unmodeled (rare / not sampled): direct-FK goal +1, penalty save +3 (GK), winning a
# penalty +2, conceding a penalty -1, own goal -2.


def expected_points(ev: dict) -> float:
    """Expected FIFA points for one player from mean events."""
    pos = ev["position"]
    pts = 0.0
    pts += ev["goals"] * GOAL_PTS.get(pos, 5)
    pts += ev["assists"] * ASSIST_PTS
    pts += ev["clean_sheet"] * CS_PTS.get(pos, 0)
    pts += ev["played"] * APPEARANCE_60  # simplification: treat appearance as 60+
    pts += ev["yellow"] * YELLOW_PTS
    pts += ev["red"] * RED_PTS
    if pos == "FWD":
        pts += ev["sot"] * SOT_PTS
    elif pos == "GK":
        pts += ev["saves"] * SAVE_PTS
        pts += ev["conc_beyond"] * CONCEDE_PTS
    elif pos == "MID":
        # Flat per-90 tackles + chances credit (see constants — realized-calibrated;
        # the K terms are 0 until share-based shaping shows signal in the data).
        gs, ash = ev.get("goal_share", 0.0), ev.get("assist_share", 0.0)
        tackles90 = max(0.0, MID_TACKLES_MAX - MID_TACKLES_K * (gs + ash))
        chances90 = MID_CHANCES_BASE + MID_CHANCES_K * ash
        pts += (ev["minutes"] / 90.0) * (tackles90 / 3.0 + chances90 / 2.0)
    elif pos == "DEF":
        pts += ev["conc_beyond"] * CONCEDE_PTS
    return pts


def scouting_ev(ev: dict, goal_samples: list) -> float:
    """EV of the +2 scouting bonus, paid only when a sub-5%-owned player scores MORE than
    4 pts in the match. Approximated from the goal distribution (non-goal points held at
    mean), so it reflects how *likely* the player is to clear 4 — not a blanket +2."""
    if not goal_samples:
        return 0.0
    gp = GOAL_PTS.get(ev["position"], 5)
    base = expected_points(ev) - ev["goals"] * gp  # non-goal points (mean)
    hits = sum(1 for g in goal_samples if base + g * gp > 4.0)
    return SCOUTING_BONUS * hits / len(goal_samples)


def ceiling_points_clamped(ev: dict, goal_samples: list, q: float = 0.85) -> float:
    """ceiling_points but never below the mean (a ceiling can't be < EV). The raw
    goal-variance ceiling dips below the mean for non-scoring defenders/GKs because it
    only models goal upside, not clean-sheet variance — clamp removes that artefact."""
    return max(expected_points(ev), ceiling_points(ev, goal_samples, q))


def ceiling_points(ev: dict, goal_samples: list, q: float = 0.85) -> float:
    """Goal-variance ceiling: expected points with the mean-goal contribution swapped
    for the q-percentile goal contribution. Mirrors Holdet's ceiling so the two are
    defined the same way (upside is driven by the goal distribution)."""
    pos = ev["position"]
    gpts = GOAL_PTS.get(pos, 4)
    p_goals = engine_events.percentile(goal_samples, q)
    return expected_points(ev) - ev["goals"] * gpts + p_goals * gpts


def run(state: dict, fantasy_round: int, sims: int = 50_000) -> None:
    if not state.get("squad") or state["squad"][0].get("_example"):
        print("  [fifa] state.json not populated — upload squad screenshot. "
              "Need: 15 players (name/team/pos/price/ownership), bench order, "
              "current captain/vice, free transfers, chips.")
        return

    players, _matches = engine_events.simulate_round(
        fantasy_round, sims=sims, market_rates=espn.load_player_rates(fantasy_round),
        research=research.load_entries("players", fantasy_round),
        research_weight=state.get("research_weight", 0.3))
    means = engine_events.event_means(players)

    rows = []
    for p in state["squad"]:
        ev = means.get(p["name"])
        xp = expected_points(ev) if ev else 0.0
        own = p.get("ownership_pct")
        if ev and own is not None and own < SCOUTING_OWNERSHIP_CAP:
            xp += scouting_ev(ev, players[p["name"]].goal_samples)
        rows.append((p, xp))

    rows.sort(key=lambda r: r[1], reverse=True)

    print(f"\n=== FIFA — round {fantasy_round} order book ===")
    print("\nStarting XI / captain by expected points:")
    for p, xp in rows[:11]:
        tag = " (C)" if p is rows[0][0] else ""
        print(f"  {xp:6.2f}  {p['name']:<22} {p['team']:<14} {p['position']}{tag}")

    print("\nCaptain chain (kickoff-ordered candidates):")
    chain = _captain_chain(state, means, fantasy_round)
    for kickoff, name, cap_ev in chain:
        ko = kickoff.strftime("%m-%d %H:%M") if kickoff else "??"
        print(f"  {ko}  {name:<22} captain-EV={cap_ev:6.2f}")
    print("  hold rule: keep armband iff realised doubled pts >= best remaining "
          "captain-EV after each match completes.")

    print("\nScouting (<5% at own kickoff — re-check ownership at each kickoff):")
    for p, _ in rows:
        own = p.get("ownership_pct")
        if own is not None and own < SCOUTING_OWNERSHIP_CAP:
            kos = fixtures.fixtures_for_team(p["team"], fantasy_round)
            ko = kos[0].kickoff.strftime("%m-%d %H:%M") if kos else "??"
            print(f"  {p['name']:<22} own={own:.1f}%  re-check at {ko}")


def _captain_chain(state, means, fantasy_round):
    """Order captain candidates by their team's kickoff; attach captain-EV (2x xP)."""
    chain = []
    for p in state["squad"]:
        if not p.get("is_starter"):
            continue
        ev = means.get(p["name"])
        cap_ev = 2 * expected_points(ev) if ev else 0.0
        kos = fixtures.fixtures_for_team(p["team"], fantasy_round)
        ko = kos[0].kickoff if kos else None
        chain.append((ko, p["name"], cap_ev))
    chain.sort(key=lambda c: (c[0] is None, c[0]))
    return chain
