# Holdet "GOLD T1" — team **Always 2nd**

Kroner-growth game. Your team value grows by the kr scoring table; rank = total value.
**Guld**: unlimited contracts (transfers). 11 players, **no bench**. Everything LOCKS
at the round's first kickoff — **no live management**.

## Scoring table (kr) — shared, see `games/holdet_common.py`
- Goal: FWD 125k / MID 150k / DEF 175k / GK 250k
- Assist 60k · Shot on target 10k · Decisive-to-win 40k / to-draw 20k · MOTM 33k
- Result: win 25k / draw 5k / loss −8k
- Team goal +10k each · Opponent goal −8k each
- Clean sheet: DEF 50k / GK 75k · GK save 5k · Penalty save 100k
- Yellow −20k · Red −50k · Own goal −50k · Hat-trick 100k
- Played +7k · Did **not** play −5k
- **Captain = ×2 growth**, free to change each round.

## Economy
- Cash earns **1% interest / round**.
- Transfer fee = **1% of the incoming player's value** (Round 1 transfers free).
- **Trade rule:** execute a transfer iff next-round growth delta **> 1% × incoming price**.

## Constraints
- Budget **50M**. Max **4 players per nation**. 11 players, no bench.
- Position quirks vs FIFA: **Kimmich = MID**; **Raphinha / Olise / Doku / Saka / Gakpo = FWD**.

## This team's objective
GOLD T1 = the "main" gold team. Straight **expected-growth maximisation** (chalk OK).
Contrast with YOLO-D (variance build).

## Order book
1. Expected kr growth per owned player this round (captain = max-growth, ×2).
2. Recommended transfers that pass the trade rule (delta > 1% × incoming price), net of fee.
3. Lock time (first kickoff) reminder.
