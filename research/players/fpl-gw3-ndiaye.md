---
entity: player
name: Ndiaye
status: rotation_risk
start_prob_override: 0.6
lambda_multiplier: 1.0
round: 3
from_round: 3
sources:
  - football360.com.au 2026-09-01: £65m to Man City, five-year deal (deadline day)
  - official feed 2026-09-03: club moved EVE → MCI
  - owner note 2026-09-03: City also signed Enzo Fernández, Elliot Anderson and Cherki — the squad is stacked
updated: 2026-09-03
---

Our XI midfielder moved to Man City on deadline day. Skill travels, role does not:
a £65m fee says he plays a lot over the season, but City spent £458m this summer
and now hold Cherki, Enzo Fernández, Anderson and him for a handful of attacking
midfield places, under a manager who rotates. Week one at a new club is the least
predictable minutes in the game.

0.60 for now, `from_round: 3` because the club change does not expire; revisit
after two City gameweeks. The model otherwise still carries his Everton rates
against City's far stronger attacking lambdas, which is why his horizon number
looks healthy — this note is the only thing pricing the bench risk.
