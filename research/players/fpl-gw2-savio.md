---
entity: player
name: Sávio
status: rotation_risk
start_prob_override: 0.1
lambda_multiplier: 1.0
round: 2
sources:
  - skysports.com 2026-08-21: Tottenham agree £85m deal for the Man City winger
  - official feed 2026-08-28: still listed at MCI
  - evmax/assets/renames.json: feed renamed Savinho → Sávio this week
updated: 2026-08-28
---

The £85m Spurs deal is agreed per Sky; completion unconfirmed as of this note.
Either way a player mid-transfer does not start for the selling club on Friday
night, so 0.1 for this round. Same handling as Marmoush: no manual club remap,
the feed diff picks up the move. Worth noting the feed renamed him this week
(Savinho → Sávio) days before the transfer news — rename plus exit rumours is a
pattern worth remembering as a churn signal.
