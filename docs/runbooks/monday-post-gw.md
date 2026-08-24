# Monday post-gameweek runbook

The grading session (spec D5: the public headline is points vs the average
manager, plus the duel). Manual for now — say "run Monday". `N` is the
gameweek that just finished. Wait for the LAST whistle (a Monday fixture
counts) — grading a gameweek mid-flight banks a wrong number.

## 1. Grade the gameweek

```bash
python3 scripts/grade_gw.py --gw N --refresh
```

Fetches the final live stats, grades every player the site published a number
about (our `x_points` vs FPL's own frozen `ep_next` vs realized points), and
banks `evmax/assets/accuracy/gw{N}.json`. Commit that file — it is a published
claim, same as the projection snapshots. GW1 predates the ep_next capture and
grades as "no ep_next benchmark"; from GW2 the accuracy league is live.

## 2. The scoreboard numbers (duel + vs the average manager)

```bash
python3 -c "from core import fpl_api; fpl_api.refresh()"   # final bootstrap
python3 -c "
from core import fpl_api
e = [x for x in fpl_api.read_cache('bootstrap')['events'] if x['id'] == N][0]
print('GW average manager:', e['average_entry_score'], '· highest:', e.get('highest_score'))"
python3 -m evmax.build --gw N --live && scripts/deploy.sh   # final realized panels
python3 scripts/indexnow_ping.py --out dist                 # tell the engines (deploy.sh already pings; explicit re-run form)
```

Collect: both squads' final totals (the build's live layer prints them into
the duel strip), the GW average, and the cumulative season line. The claim
that matters each week: **model total vs consensus total vs the average
manager** — legible at a glance.

## 3. Draft the scorecard post

For r/FantasyPL (Bartek posts — D4): the three totals, one sentence on what
the model got right, one on what it got wrong (name it before commenters do —
that is the credibility engine), the accuracy line (MAE ours vs ep_next), link
to the site. No victory laps on a lucky week; no burying a bad one.

## 4. Transfer preview for the coming week

```bash
python3 manage.py fpl --round N+1 --transfers --bank 0.0
```

The early read the Thursday session re-runs on fresh odds. Red-dossier names
lead the table — those are next week's research items, starting now.

## 5. Season learnings entry

Append to `docs/research/season-learnings.md` (mistake → root cause →
structural fix → status) for anything this gameweek taught: a wrong minutes
read, a proxy that misled, a process step that got skipped. If the fix is
code, open the item with status `open` and close it when the commit lands —
that file is the pattern-detector for repeat mistakes.

## To schedule this later — PARKED (owner decision D3)

- Claude Code scheduled cloud agent: `/schedule` → "every Tuesday 08:00
  Europe/Copenhagen, run docs/runbooks/monday-post-gw.md steps 1-2 and post
  the scoreboard numbers" (Tuesday, so Monday fixtures are always final).
- Plain cron (grading only):
  `0 8 * * 2 cd ~/personal/projects/wc2026 && python3 scripts/grade_gw.py --gw N --refresh`
