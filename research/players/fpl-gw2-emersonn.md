---
entity: player
name: Emersonn
status: starter
start_prob_override: 0.78
lambda_multiplier: 1.0
round: 2
from_round: 2
sources:
  - bet365 news 2026-08-08: £24m plus add-ons from Toulouse — obliterated Ipswich's club record
  - thesoutherngazette.com 2026-08: Ipswich past £120m spent, 7th-biggest spenders in the league
  - official feed live GW1: started, 65 minutes
updated: 2026-08-28
---

Role and rate are two different questions, and this note fixes only the role.

He has no Premier League history, so the model shrinks his scoring rate toward
the price prior — correct, and untouched here: 65 hot minutes prove nothing
about a rate. But the same shrinkage read his START probability as a coin flip,
and a £24m club-record striker who started gameweek 1 for the seventh-biggest
spenders in the window is not a coin flip. 0.78: starts while fit, with the
sub-at-65 pattern keeping it under 0.85.

`from_round: 2` per the transfer/role model gap (docs/STRATEGY.md) — promoted-
club record signings are the weak spot of a history-weighted minutes model.
Revisit once he owns four or five gameweeks of his own.
