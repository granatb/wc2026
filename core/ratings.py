"""Team strength / goal-share priors feeding the Monte Carlo engine.

Two jobs:
  1. Hold per-team attack/defence strength (odds-derived) so match lambdas can be
     produced consistently for every fixture.
  2. Hold per-player goal-share / assist-share / minutes priors so a team's match
     goals can be distributed to individual players inside the engine.

Nothing here is game-specific. `fixtures.py` consumes team strengths to emit the
(home_lambda, away_lambda) for each match; `engine_events.py` consumes player
priors to split team goals among players.

Numbers below are PLACEHOLDERS with sane defaults. Real values get set from odds
screenshots. Keep this file the single home for strength priors -- do not copy
ratings into individual game models.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import config

# Priors baseline + home advantage live in config.py (the single control panel).
BASE_GOALS = config.BASE_GOALS
HOME_ADV = config.HOME_ADV


@dataclass
class TeamRating:
    """Odds-derived strength for one national team.

    attack:  multiplier on BASE_GOALS for goals this team scores (1.0 = average).
    defence: multiplier on the opponent's expected goals (lower = stronger defence).
    """

    name: str
    attack: float = 1.0
    defence: float = 1.0
    # Optional: implied tournament-winner probability from odds, for sanity checks.
    win_prob: float = 0.0


@dataclass
class PlayerPrior:
    """Per-player priors used to distribute a team's simulated match output.

    goal_share / assist_share are fractions of the team's goals/assists this player
    is expected to take when on the pitch. Shares across a squad need not sum to 1
    (the engine normalises among players who are on the pitch in a given sim).
    """

    name: str
    team: str
    position: str            # GK / DEF / MID / FWD  (FIFA-style; see holdet quirks)
    start_prob: float = 0.8  # probability of starting a given match
    exp_minutes: float = 75  # expected minutes when in the squad
    goal_share: float = 0.0
    assist_share: float = 0.0
    sot_per90: float = 0.8   # shots on target per 90, for holdet SoT scoring
    pen_taker: bool = False


# ---------------------------------------------------------------------------
# Registries. Populated from odds/lineup screenshots.
# ---------------------------------------------------------------------------

TEAM_RATINGS: dict[str, TeamRating] = {
    # "Brazil": TeamRating("Brazil", attack=1.45, defence=0.78, win_prob=0.13),
    # ... filled from odds ...
}

# Priors for the players across our five squads. Keyed by the EXACT name strings used
# in each game's state.json (some players appear under short + long variants -> one
# entry per variant, same team). `team` is the ESPN displayName so it joins the cached
# schedule. goal_share / assist_share are role-based with star bumps; these are the
# EXPERT FALLBACK — once `--props` is fetched, market anytime-goal odds override the
# goal weight via the blend. (name, team, pos, start_prob, goal_share, assist_share)
_SQUAD_PRIORS = [
    # --- goalkeepers ---
    ("Rangel", "Mexico", "GK", 0.85, 0.0, 0.0),
    ("Raul Rangel", "Mexico", "GK", 0.85, 0.0, 0.0),
    ("Gregor Kobel", "Switzerland", "GK", 0.9, 0.0, 0.0),
    ("A. Beiranvand", "Iran", "GK", 0.9, 0.0, 0.0),
    ("Vargas", "Colombia", "GK", 0.85, 0.0, 0.0),  # Camilo Vargas, Colombia #1 (our bench GK)
    # --- defenders ---
    ("Nuno Mendes", "Portugal", "DEF", 0.88, 0.05, 0.12),
    ("Kimmich", "Germany", "DEF", 0.92, 0.05, 0.15),
    ("Muñoz", "Colombia", "DEF", 0.85, 0.05, 0.10),
    ("Cucurella", "Spain", "DEF", 0.85, 0.03, 0.07),
    ("Gabriel Magalhães", "Brazil", "DEF", 0.88, 0.10, 0.04),
    ("R. Rodriguez", "Switzerland", "DEF", 0.82, 0.10, 0.08),
    ("Cesar Montes", "Mexico", "DEF", 0.85, 0.08, 0.03),
    ("Pau Cubarsi", "Spain", "DEF", 0.85, 0.03, 0.04),
    ("Israel Reyes", "Mexico", "DEF", 0.8, 0.04, 0.04),
    ("D. Sanchez", "Colombia", "DEF", 0.85, 0.05, 0.05),
    ("David Alaba", "Austria", "DEF", 0.8, 0.06, 0.10),
    ("N. Brown", "Germany", "DEF", 0.85, 0.07, 0.12),  # Nathaniel Brown, Germany LB
    # --- midfielders ---
    ("Bruno Fernandes", "Portugal", "MID", 0.92, 0.18, 0.20),
    ("Ruben Vargas", "Switzerland", "MID", 0.82, 0.12, 0.12),
    ("Musiala", "Germany", "MID", 0.9, 0.20, 0.18),
    ("J. Musiala", "Germany", "MID", 0.9, 0.20, 0.18),
    ("Wirtz", "Germany", "MID", 0.9, 0.18, 0.20),
    ("F. Wirtz", "Germany", "MID", 0.9, 0.18, 0.20),
    ("Raphinha", "Brazil", "MID", 0.9, 0.22, 0.18),
    ("Alex Baena", "Spain", "MID", 0.78, 0.12, 0.15),
    ("Antonio Nusa", "Norway", "MID", 0.8, 0.12, 0.12),
    ("Fabian Ruiz", "Spain", "MID", 0.85, 0.12, 0.12),
    ("M. Ødegaard", "Norway", "MID", 0.9, 0.15, 0.20),
    ("Erik Lira", "Mexico", "MID", 0.78, 0.06, 0.08),
    ("R. Gravenberch", "Netherlands", "MID", 0.85, 0.08, 0.10),
    ("Pedri", "Spain", "MID", 0.9, 0.10, 0.16),
    ("M. Sabitzer", "Austria", "MID", 0.88, 0.12, 0.12),
    # --- forwards ---
    ("Oyarzabal", "Spain", "FWD", 0.85, 0.25, 0.12),
    ("M. Oyarzabal", "Spain", "FWD", 0.85, 0.25, 0.12),
    ("Jiménez", "Mexico", "FWD", 0.88, 0.22, 0.10),
    ("Kane", "England", "FWD", 0.95, 0.35, 0.12),
    ("Kai Havertz", "Germany", "FWD", 0.85, 0.25, 0.12),
    ("E. Haaland", "Norway", "FWD", 0.95, 0.40, 0.10),
    ("Mehdi Taremi", "Iran", "FWD", 0.88, 0.28, 0.10),
    # --- FIFA R2 transfer-IN candidates (forwards on the market) ---
    ("Thuram", "France", "FWD", 0.85, 0.20, 0.10),
    ("Gonçalo Ramos", "Portugal", "FWD", 0.6, 0.22, 0.08),    # start risk vs Ronaldo
    ("Enner Valencia", "Ecuador", "FWD", 0.9, 0.32, 0.10),    # on penalties
    ("Ueda", "Japan", "FWD", 0.85, 0.28, 0.08),               # on penalties, differential
    ("Lukaku", "Belgium", "FWD", 0.85, 0.30, 0.08),
    ("Gakpo", "Netherlands", "FWD", 0.85, 0.22, 0.12),
    ("Mané", "Senegal", "MID", 0.9, 0.28, 0.14),             # Senegal talisman vs Norway
    # --- FIFA R2 midfield transfer-IN candidates ---
    ("Bellingham", "England", "MID", 0.9, 0.18, 0.12),
    ("Vitinha", "Portugal", "MID", 0.85, 0.08, 0.18),        # set pieces/corners
    ("Rice", "England", "MID", 0.9, 0.06, 0.14),             # corners
    ("Nico Williams", "Spain", "MID", 0.85, 0.15, 0.15),
    ("Doué", "France", "MID", 0.7, 0.12, 0.12),              # France rotation risk
    ("Luis Díaz", "Colombia", "MID", 0.9, 0.20, 0.12),
    ("Mbappé", "France", "FWD", 0.9, 0.32, 0.10),            # pens, France 3.13 xG
    ("Vinicius Jr", "Brazil", "FWD", 0.85, 0.28, 0.14),
    ("Embolo", "Switzerland", "FWD", 0.8, 0.22, 0.10),
    ("Dani Olmo", "Spain", "MID", 0.75, 0.16, 0.16),
    ("Willian Pacho", "Ecuador", "DEF", 0.9, 0.04, 0.04),    # Ecuador CB vs Curaçao (CS spot)
    ("Anthony Valencia", "Ecuador", "FWD", 0.6, 0.18, 0.10),
    ("Felix Nmecha", "Germany", "MID", 0.8, 0.08, 0.10),     # YOLO pick vs Ivory Coast
    ("M. Llorente", "Spain", "MID", 0.8, 0.10, 0.10),        # Marcos Llorente vs Saudi
    # --- remainder of the priced Holdet pool (so the optimiser sees the full board) ---
    ("Lionel Messi", "Argentina", "FWD", 0.9, 0.25, 0.20),
    ("Lautaro Martinez", "Argentina", "FWD", 0.85, 0.28, 0.10),
    ("Julian Alvarez", "Argentina", "FWD", 0.7, 0.20, 0.10),
    ("Valentin Barco", "Argentina", "MID", 0.6, 0.06, 0.10),
    ("Michael Olise", "France", "FWD", 0.8, 0.18, 0.15),
    ("William Saliba", "France", "DEF", 0.9, 0.04, 0.04),    # France CS spot vs Iraq
    ("Kevin De Bruyne", "Belgium", "MID", 0.85, 0.15, 0.22),
    ("Jeremy Doku", "Belgium", "FWD", 0.75, 0.18, 0.14),
    ("C. De Ketelaere", "Belgium", "FWD", 0.7, 0.18, 0.10),
    ("Cristiano Ronaldo", "Portugal", "FWD", 0.65, 0.28, 0.08),  # start risk
    ("Bukayo Saka", "England", "FWD", 0.85, 0.20, 0.15),
    ("V. Livramento", "England", "DEF", 0.7, 0.05, 0.08),
    ("Viktor Gyökeres", "Sweden", "FWD", 0.85, 0.30, 0.08),
    ("G. Gudmundsson", "Sweden", "DEF", 0.8, 0.05, 0.06),
    ("Tijjani Reijnders", "Netherlands", "MID", 0.8, 0.12, 0.12),
    ("Darwin Nunez", "Uruguay", "FWD", 0.8, 0.30, 0.08),
    ("Gabriel Martinelli", "Brazil", "FWD", 0.7, 0.20, 0.12),
    ("Heung-Min Son", "South Korea", "FWD", 0.9, 0.28, 0.12),
    ("Iñaki Williams", "Ghana", "FWD", 0.85, 0.25, 0.10),
    ("Ronwen Williams", "South Africa", "GK", 0.9, 0.0, 0.0),
    ("Wilson Isidor", "Haiti", "FWD", 0.8, 0.25, 0.08),
    ("W. Singo", "Ivory Coast", "DEF", 0.85, 0.04, 0.06),
    ("Willy Semedo", "Cape Verde", "FWD", 0.8, 0.22, 0.08),
    ("Gabriel Avalos", "Paraguay", "FWD", 0.8, 0.25, 0.08),
]

# Designated penalty takers among the priced pool (conservative — only well-established
# spot-kick takers). Drives config.PEN_TAKER_GOAL_BONUS in the engine.
PEN_TAKERS = {
    "Kane", "Bruno Fernandes", "Oyarzabal", "M. Oyarzabal", "Enner Valencia", "Ueda",
    "Mbappé", "Heung-Min Son", "Lionel Messi", "E. Haaland", "Darwin Nunez",
    "Viktor Gyökeres", "Mehdi Taremi",
}

PLAYER_PRIORS: dict[str, PlayerPrior] = {
    n: PlayerPrior(n, t, pos, start_prob=s, goal_share=g, assist_share=a,
                   pen_taker=(n in PEN_TAKERS))
    for (n, t, pos, s, g, a) in _SQUAD_PRIORS
}


def get_team(name: str) -> TeamRating:
    """Return a team's rating, defaulting to league-average if unknown."""
    return TEAM_RATINGS.get(name, TeamRating(name))


def match_lambdas(home: str, away: str, *, neutral: bool = True) -> tuple[float, float]:
    """Expected goals (lambda_home, lambda_away) for a fixture.

    Multiplicative Dixon-Coles-style model: a side's expected goals scale with its own
    attack and the opponent's defence. Home advantage applied unless `neutral`.
    """
    h, a = get_team(home), get_team(away)
    lam_home = BASE_GOALS * h.attack * a.defence
    lam_away = BASE_GOALS * a.attack * h.defence
    if not neutral:
        lam_home *= HOME_ADV
    return round(lam_home, 3), round(lam_away, 3)


# --- Derived priors -------------------------------------------------------
# Hand-set priors cover only ~84 players, but data/players.json has every player
# (with price + position) from both APIs. For the knapsack we must be able to score
# ALL of them, so any team player without a hand-set prior gets one DERIVED from:
#   position (role base share) x price-as-quality (vs the position's median price),
# with start probability set by price rank within position (a proxy depth chart).
# Hand-set priors always win. Capped per team to bound Monte-Carlo cost.
_DERIVE_GOAL = {"GK": 0.0, "DEF": 0.05, "MID": 0.10, "FWD": 0.20}
_DERIVE_ASSIST = {"GK": 0.0, "DEF": 0.06, "MID": 0.13, "FWD": 0.11}
_DERIVE_SOT = {"GK": 0.0, "DEF": 0.4, "MID": 0.9, "FWD": 1.6}
_START_QUOTA = {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2}   # likely-XI shape
_DERIVE_CAP = 16                                          # players modelled per team

_POS_MEDIAN: dict = {}
_TEAM_PRIORS: dict = {}


def _position_medians() -> dict:
    if not _POS_MEDIAN:
        import statistics
        from . import players as pdb
        byp: dict = {}
        for r in pdb.load():
            pos, pr = r.get("fifa_pos"), r.get("holdet_price")
            if pos and pr and pr > 0:
                byp.setdefault(pos, []).append(pr)
        for pos, v in byp.items():
            _POS_MEDIAN[pos] = statistics.median(v)
    return _POS_MEDIAN


def _derive_prior(rec: dict, start_prob: float) -> PlayerPrior:
    pos = rec.get("fifa_pos") or rec.get("holdet_pos") or "MID"
    med = _position_medians().get(pos, 2_500_000)
    price = rec.get("holdet_price") or med
    q = min(3.0, max(0.3, price / med))   # quality vs the position's median price
    names = [rec["name"]] + rec.get("aliases", [])
    return PlayerPrior(
        name=rec["name"], team=rec.get("team"), position=pos,
        start_prob=start_prob, exp_minutes=60 + 25 * start_prob,
        goal_share=min(0.42, _DERIVE_GOAL.get(pos, 0.1) * q),
        assist_share=min(0.30, _DERIVE_ASSIST.get(pos, 0.1) * q),
        sot_per90=_DERIVE_SOT.get(pos, 0.8) * min(2.0, q),
        pen_taker=any(n in PEN_TAKERS for n in names),
    )


def _build_team_priors(team: str) -> list:
    from . import players as pdb
    # Dedup hand-set priors that are the SAME real player entered under two name
    # variants (e.g. "Oyarzabal" + "M. Oyarzabal") so they don't become a phantom
    # extra player in the sim. Keep the first; the app still resolves both via aliases.
    hand, _seen = {}, set()
    for p in PLAYER_PRIORS.values():
        if p.team != team:
            continue
        rec = pdb.resolve(p.name)
        cid = rec["name"] if rec else p.name
        if cid in _seen:
            continue
        _seen.add(cid)
        hand[p.name] = p
    out = dict(hand)
    bypos: dict = {}
    for r in pdb.load():
        if r.get("team") == team and (r.get("holdet_price") or 0) > 0:
            bypos.setdefault(r.get("fifa_pos") or "MID", []).append(r)
    derived = []
    for pos, rs in bypos.items():
        rs.sort(key=lambda r: -(r.get("holdet_price") or 0))
        quota = _START_QUOTA.get(pos, 3)
        for i, r in enumerate(rs):
            if r["name"] in hand or any(a in hand for a in r.get("aliases", [])):
                continue
            sp = 0.85 if i < quota else (0.35 if i < quota + 2 else 0.10)
            derived.append((r.get("holdet_price") or 0, _derive_prior(r, sp)))
    derived.sort(key=lambda x: -x[0])          # keep the most valuable to fill the cap
    kept = [pp for _pr, pp in derived[: max(0, _DERIVE_CAP - len(hand))]]
    # Budget-normalise: derived players fill only the residual attacking share left by
    # the hand-set priors, so adding a team's squad never over-dilutes its known stars.
    # A team with rich hand-set coverage (e.g. Spain) leaves little for derived; a team
    # with none (e.g. Iraq) lets derived fill the whole ~1.1 goal budget.
    hv = list(hand.values())
    sg = sum(pp.start_prob * pp.goal_share for pp in hv)
    sa = sum(pp.start_prob * pp.assist_share for pp in hv)
    dg = sum(pp.start_prob * pp.goal_share for pp in kept)
    da = sum(pp.start_prob * pp.assist_share for pp in kept)
    fg = (max(0.08, 1.10 - sg) / dg) if dg > 0 else 0.0
    fa = (max(0.08, 0.95 - sa) / da) if da > 0 else 0.0
    for pp in kept:
        pp.goal_share *= fg
        pp.assist_share *= fa
        out[pp.name] = pp
    # Derive a penalty taker for teams that have none marked: the main attacker
    # (highest goal-share, forwards preferred) is the usual spot-kick taker.
    if not any(pp.pen_taker for pp in out.values()):
        cand = [pp for pp in out.values() if pp.position in ("FWD", "MID")]
        if cand:
            max(cand, key=lambda pp: (pp.position == "FWD", pp.goal_share)).pen_taker = True
    return list(out.values())


def players_for_team(team: str) -> list[PlayerPrior]:
    if team not in _TEAM_PRIORS:
        _TEAM_PRIORS[team] = _build_team_priors(team)
    return _TEAM_PRIORS[team]


def clear_prior_cache() -> None:
    """Call after a player re-sync so derived priors rebuild from fresh data."""
    _TEAM_PRIORS.clear()
    _POS_MEDIAN.clear()
