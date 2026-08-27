---
entity: player
name: M.Sangaré
status: starter
start_prob_override: 0.85
lambda_multiplier: 1.0
round: 2
from_round: 2
sources:
  - brentfordfc.com 2026-08-23 debut analysis
  - official feed live GW1: 75 minutes, 14 points, 2 assists, 41 bps
  - skysports.com 2026-08-25: rested to a 48-minute cameo in the cup win at Birmingham
  - dknetwork.draftkings.com 2026-08-25 GW2 targets
updated: 2026-08-27
---

Club-record £39m signing from Lens with a full pre-season, 14 points and two
assists on debut, then rested to a cameo in midweek — the pattern of a protected
league starter, not a squad player.

`from_round: 2` because of a model gap this player exposes, not because of new
team news. The minutes model weights last season's sample by its match count, and
his last season was 1 start in 38 at a different club. That record is real, but it
describes a role he no longer has: 38 matches of "fringe at his old club" outvote
one match of "started for his new one" by 38 to 1, and the model put him at a 7%
starter. Scoped to round 2 alone, his card read 5.0 xPts for GW2 and 0.4 a week
after that — a cliff no reader could make sense of.

The general fix is for the model to treat skill as persisting across a transfer
while role does not, which needs last-season club data we do not currently keep
(see docs/STRATEGY.md). Until then this note carries him forward, and it should be
revisited once he has four or five gameweeks of his own.
