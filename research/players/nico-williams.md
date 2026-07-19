---
entity: player
name: Nico Williams
status: doubtful
start_prob_override: 0.20
lambda_multiplier: 1.0
round: 8
sources:
  - https://www.espn.com/soccer/story/_/id/49200729/spain-nico-williams-injury-yeremy-pino-2026-world-cup
  - https://www.sportsmole.co.uk/football/spain/world-cup-2026/predicted-lineups/yamal-oyarzabal-to-lead-la-rojas-attack-predicted-spain-lineup-vs-belgium_600882.html
  - https://www.sportsmole.co.uk/football/france/world-cup-2026/preview/france-vs-spain-prediction-team-news-lineups_601083.html
  - owner observation (realized minutes): 1pt appearance-only in both R6 (QF vs
    Belgium) and R7 (SF vs France) -- confirmed bench, Baena preferred both times
updated: 2026-07-19
---

3rd-place playoff (vs Argentina): benched in the QF and again in the SF, both
confirmed 1pt (appearance-only) returns -- Baena has settled in as first choice post
injury, not just early-return caution anymore. Two straight benchings is stronger
signal than the original "reassess for SF" framing, so start prob is down to 20%.
Treat as a bench option only.

History: adductor injury forced him out for R32 (round 4), "fully returned but not
reintegrated" through R16/QF (rounds 5-6), and the SF confirmed the same (round 7).
Consolidated from nico-williams-r4.md / -r6.md / -r7.md, retired (renamed with a
leading `_`, which core/research.py's loader already skips) rather than deleted, so
the history stays in git. This exact collision (4 files, disagreeing status/
start_prob, one silently "winning" by filesystem list order) is why
find_duplicate_names() exists now as a build-time guard.
