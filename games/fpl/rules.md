# FPL 2026/27 scoring — the model's reference

Every constant in `games/fpl/model.py` cites a row in this file.

**Provenance for each number below:**
- Scoring and BPS tables: the official rules page at
  `https://fantasy.premierleague.com/en/help/rules`, read 2026-07-28.
- Squad/transfer/chip mechanics: `bootstrap-static.game_config`, same date.
- **The two divisors (1 point per 3 saves, -1 per 2 conceded) come from the rules
  page only.** `game_config.scoring` carries unit values (`saves: 1`,
  `goals_conceded: -1`) and mis-prices every goalkeeper if read literally.
- Nothing in this file is an assumption. If a future rule change cannot be verified
  from one of those two sources, mark it explicitly as unverified rather than
  guessing.

---

# FPL 2026/27 rules — verbatim from official source

Source: https://fantasy.premierleague.com/en/help/rules (rendered via browser, 2026-07-28)
Cross-checked against `game_config.scoring` in https://fantasy.premierleague.com/api/bootstrap-static/

## Scoring

| Action | Points |
|---|---|
| For playing up to 60 minutes | 1 |
| For playing 60 minutes or more (excluding stoppage time) | 2 |
| For each goal scored by a goalkeeper | 10 |
| For each goal scored by a defender | 6 |
| For each goal scored by a midfielder | 5 |
| For each goal scored by a forward | 4 |
| For each goal assist | 3 |
| For a clean sheet by a goalkeeper or defender | 4 |
| For a clean sheet by a midfielder | 1 |
| **For every 3 shot saves by a goalkeeper** | **1** |
| For accumulating 10 or more clearances, blocked shots, interceptions (CBI) and tackles (defenders) | 2 |
| For accumulating 12 or more clearances, blocked shots, interceptions (CBI), tackles and recoveries (midfielders & forwards) | 2 |
| For each penalty save | 5 |
| For each penalty miss | -2 |
| Bonus points for the best players in a match | 1-3 |
| **For every 2 goals conceded by a goalkeeper or defender** | **-1** |
| For each yellow card | -1 |
| For each red card | -3 |
| For each own goal | -2 |

Both divisors CONFIRMED: saves = 1 pt per 3; goals conceded = -1 per 2.
DefCon thresholds CONFIRMED: DEF >= 10 CBIT; MID & FWD >= 12 CBIRT. GK not eligible.

## Bonus Points System (BPS)

| Action | BPS |
|---|---|
| Playing 1 to 60 minutes | 3 |
| Playing over 60 minutes | 6 |
| Scoring a goal direct from a penalty | 12 |
| Goalkeepers and defenders scoring a goal (non penalty) | 12 |
| Midfielders scoring a goal (non penalty) | 18 |
| Forwards scoring a goal (non penalty) | 24 |
| Assists | 9 |
| Goalkeepers and defenders keeping a clean sheet | 12 |
| Making a save | 2 |
| Making a save from a shot inside the box | 1 |
| Making a save from a big chance | 1 |
| Saving a penalty | 7 |
| For every 3 clearances, blocked shots and interceptions (total) | 1 |
| For every 3 recoveries | 1 |
| Creating a chance | 1 |
| Creating a big chance | 3 |
| Successful open play cross | 1 |
| Successful tackle | 2 |
| Successful dribble | 1 |
| Scoring the goal that wins a match | 3 |
| Making a goalline clearance | 9 |
| Foul won | 1 |
| Shot on target | 2 |
| 70 to 79% pass completion (at least 30 passes attempted) | 2 |
| 80 to 89% pass completion (at least 30 passes attempted) | 4 |
| 90%+ pass completion (at least 30 passes attempted) | 6 |
| Goalkeepers and defenders conceding a goal | -4 |
| Conceding a penalty | -3 |
| Missing a penalty | -6 |
| Yellow card | -3 |
| Red card | -9 |
| Own goal | -6 |
| Missing a big chance | -3 |
| Making an error which leads to a goal | -3 |
| Making an error which leads to an attempt at goal | -1 |
| Conceding a foul | -1 |
| Being caught offside | -1 |
| Shot off target | -1 |

Note: successful tackles still EARN +2 BPS. What was removed for 2026/27 is the
old -1 BPS for BEING tackled.

## Chips

| Name | Effect |
|---|---|
| Bench Boost | The points scored by your bench players in the next Gameweek are included in your total. |
| Free Hit | Make unlimited free transfers for a single Gameweek. At the next deadline your squad is returned to how it was at the start of the Gameweek. |
| Triple Captain | Your captain points are tripled instead of doubled in the next Gameweek. |
| Wildcard | All transfers (including those already made) in the Gameweek are free of charge. |

From `bootstrap-static.chips`: two sets, windows GW2-19 and GW20-38 for
wildcard/freehit; GW1-19 and GW20-38 for bboost/3xc.

## Squad / transfer rules (from bootstrap-static.game_config.rules)

- squad_squadsize 15, squad_squadplay 11, squad_team_limit 3
- squad_total_spend 1000 (= GBP 100.0m, ui_currency_multiplier 10)
- max_extra_free_transfers 4 (bank up to 5 FTs)
- transfers_sell_on_fee 0.5 (50% of profit)
- element_sell_at_purchase_price false
- transfers_cap 20
- No manager element_type -> Assistant Manager chip is gone

## Deadlines — TIMEZONE TRAP

The rules page renders deadlines in the VIEWER's local timezone. It showed
"Gameweek 1 | Fri 21 Aug 19:30", which is CEST (UTC+2) on this machine.
The API's `events[].deadline_time` is 2026-08-21T17:30:00Z.

**Always read deadlines from the API in UTC. Never scrape them from the page.**

GW1 deadline: 2026-08-21T17:30:00Z (= 18:30 BST = 19:30 CEST).
