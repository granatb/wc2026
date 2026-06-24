# FIFA World Cup Fantasy (official) — rules

Points game. 15-man squad. Live in-round management (captain chain + manual subs).

## Squad & scoring (CONFIRMED from in-app "How to score", 2026)
- 15 players: 2 GK, 5 DEF, 5 MID, 3 FWD. Pick 11 starters + 4 bench each round.
- Captain scores **×2**.

All players: appearance +1 (1-59 min) / +2 (60+ min); assist +3; yellow −1; red −2;
own goal −2; winning a penalty +2; conceding a penalty −1.
Bonus: goal from a direct free-kick +1 (on top of the goal); scouting bonus +2 (player
scores **>4** pts in a match **and** is owned by **<5%** of teams).

Goal scored: **GK 9, DEF 7, MID 6, FWD 5**.
Clean sheet (60+ min): GK 5, DEF 5, MID 1, FWD 0.
Goals conceded (GK/DEF): first = 0, then **−1 per additional** goal.
GK: penalty save +3 (not shootouts); +1 per 3 saves.
MID: +1 per 3 tackles; +1 per 2 chances created.
FWD: +1 per 2 shots on target.

There is **no Player-of-the-Match** and **no outside-the-box** bonus, and defenders get
**no** tackle/CBI points (tackles/chances are MID-only).

Model status (games/fifa/model.py): goals, assists, CS, appearance, cards, conceded,
GK saves, FWD SoT, MID tackles+chances (expected per-90 estimate), and scouting (EV of
P(pts>4)) are all in. Unmodeled (rare / not sampled): direct-FK bonus, penalty save,
winning/conceding a penalty, own goal.

## Live captain chain  (the key edge)
- The captain (×2) **can be moved freely during a live round** subject to:
  - the **new** captain's team **has not yet played** (match not kicked off), AND
  - the **old** captain's match is **complete**.
- This lets you "roll the armband down a chain" of players ordered by kickoff time:
  start the armband on the earliest-kicking candidate; once their match finishes,
  if they underperformed you can move it onto the next not-yet-started candidate.
- **Decision rule:** keep the armband on the current player iff their realised
  (doubled) points so far ≥ **expected value of the remaining chain** (the best
  EV among captain candidates whose matches haven't started). Otherwise roll it on.
- Model output: the ordered chain by kickoff, each candidate's captain-EV, and the
  live "hold vs roll" threshold after each completed match.

## Manual substitutions
- A bench player may be subbed IN only if **unlocked** (their match has not yet
  kicked off).
- You may sub OUT a starter only if their match is **complete OR not yet started**
  (never mid-match).
- A **finished** bench player can **NOT** be subbed in.
- **Any manual change cancels auto-subs for the round.** So only intervene manually
  when the manual EV gain exceeds the auto-sub safety net you give up.

## Scouting Bonus
- **+2** if the player was owned **< 5% at their own kickoff**.
- Ownership drifts during the round, so a pick that is sub-5% at a deadline can
  cross 5% before a **late** kickoff (and vice-versa) — evaluate ownership at each
  player's kickoff, not at lock.

## Order book the model prints
1. Optimal starting XI + captain for the round (pre-deadline).
2. Live captain chain: kickoff-ordered candidates, captain-EV, hold/roll threshold.
3. Manual-sub candidates with EV-gain vs auto-sub, flagged only when net positive.
4. Sub-5% scouting-bonus picks and the kickoff at which to re-check ownership.
