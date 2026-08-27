---
entity: player
name: Watkins
status: unavailable
start_prob_override: 0.05
lambda_multiplier: 1.0
round: 2
from_round: 2
sources:
  - goal.com 2026-08-27: Al-Hilal agreed €58.4m + €2m add-ons, medical booked in Riyadh, three-year deal
  - caughtoffside.com 2026-08-27: Villa signing Nicolas Jackson as the replacement
  - official feed live GW1: 0 minutes, omitted from the matchday squad at Brighton
  - official feed 2026-08-27: status still 'a', news empty — FPL has not caught up
updated: 2026-08-27
---

Leaving, not injured. Fee agreed with Al-Hilal and the medical is booked; Villa are
signing Jackson to replace him; he played zero minutes in GW1 after the freeze-out.
The feed still reads status 'a' with empty news, which is why the override exists —
FPL flags departures late, and a clean status here means "not yet processed", not
"available".

`from_round: 2` because this does not expire on Sunday. Scoped to round 2 alone,
the horizon projected him at 4-5 points a week from GW3 as though he were still a
Villa striker, which understated the sale by about 19 points across GW3-6 and sent
the optimizer after the wrong replacement.

0.05 rather than 0.00 because the deal is not signed and a collapse would put him
back in a Villa shirt, but Villa play LAST in this gameweek (Monday 20:00 UK, kicking
off 49 hours after our Friday deadline). Holding him is not a wait-and-see — it is
committing to a near-certain zero with no route to correct it. Forced sale.
