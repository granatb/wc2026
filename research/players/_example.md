---
entity: player
name: Example Player
status: nailed
start_prob_override: null
lambda_multiplier: 1.0
sources:
  - https://example.com/article
updated: 2026-06-18
---
Template for a player research note. Copy this file, rename it, fill the frontmatter,
and write the reasoning + citations below. Files beginning with `_` are skipped by the
loader. Hard facts: set `status: out` (or `suspended`) to zero the player regardless of
the game's research weight, or `start_prob_override` to pin a start probability. Soft
reads: nudge `lambda_multiplier` above/below 1.0 (scaled by the game's `w`).
