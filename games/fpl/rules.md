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

---

# Lineup notes — the owner's team news

**This codebase does not fetch team news.** No scraping, no search, no lineup API.
The owner reads Discord, Fantasy Football Scout and the press conferences himself
and trusts his own filtering over an automated pass that might weight a bad source
(owner decision, 2026-08-03). It is about who is accountable for the judgement.
`scripts/fpl_notes.py` is the *ingestion* path only: it makes the notes cheap to
write, safe to consume, and loud when they are missing, stale or wrong.

The bootstrap feed's `status` field only knows about declared injuries. It has
nothing to say about rotation, cup-tie resting, or a manager telling a presser
that a 17-year-old starts. That gap is what these notes fill.

## Writing them

```bash
python3 scripts/fpl_notes.py --gw 1 <<'EOF'
Jacquet nailed 0.9    # Slot presser, 20 Aug
Gomez out
Bradley rotation
EOF
```

Also `--file notes.txt` instead of stdin, and `--check` to parse and name-match
without writing anything.

One player per line: `<name> [status] [start_prob] [# source]`

| Token | Meaning |
|---|---|
| `nailed` / `starter` / `starts` | `status: nailed` |
| `rotation` / `rotation_risk` / `risk` | `status: rotation_risk` |
| `doubt` / `doubtful` | `status: doubtful` |
| `out` / `injured` | `status: out` |
| `susp` / `suspended` / `banned` | `status: suspended` |
| a float in `[0, 1]` | `start_prob_override` |
| `# ...` trailing | becomes the note's `sources` entry |
| `# ...` whole line, or a blank line | ignored |

Status and probability can appear together, in either order, and the status word
is case-insensitive. Multi-word names work (`Van Hecke nailed`).

**Nothing is ever silently dropped.** An unrecognised word, a probability outside
`[0, 1]`, a bare name with no status or probability, and two lines for one player
are all errors that abort the batch. A dropped token is a lost instruction.

## What each status does to the model

`core/research.py` splits notes into hard facts and soft nudges, and only the soft
ones are scaled by the game's research weight — FPL's is `config.weight("fpl")` =
**0.30**.

| Note | Effect |
|---|---|
| `out`, `suspended` | **HARD.** Zeroes the player outright, *bypassing the weight entirely.* |
| a `start_prob` float | **HARD.** Pins start probability absolutely, ignoring the weight. |
| `nailed`, `rotation_risk`, `doubtful` | **SOFT.** Blended at w = 0.30, and drives the site's public availability flag. |

The practical consequence: a bare `nailed` or `rotation` moves the minutes only
gently. **Pair a status with an explicit start probability when you want the
projection to actually move** — `Jacquet nailed 0.9`, not `Jacquet nailed`.

## Names — the failure mode this whole path exists to prevent

The feed uses FPL's `web_name`: **"Virgil", not "Van Dijk". "B.Fernandes", not
"Bruno Fernandes".** The overlay is keyed on the literal `name:` string and looked
up with `==`, so a note whose name matches nothing is read by nobody and changes
nothing — while reading as done. That is exactly how the World Cup site once came
within one guard of publishing an article about a ruled-out player.

So the name is checked twice:

- **At write time.** `fpl_notes.py` resolves every name against the cached
  bootstrap (case-, punctuation- and diacritic-insensitively, accepting a unique
  prefix or substring, never guessing between two candidates). One unmatched name
  aborts the *whole batch* with suggestions and a non-zero exit — a typo cannot
  become a silent no-op, and a half-applied batch never exists.
- **At build time.** `evmax/fpl_build.py`'s preflight re-checks every note the
  overlay would load against the live player pool and names the offending file.
  This catches a hand-edited note, a renamed player, and any note that predates a
  feed change.

Matching is done against the *post-disambiguation* pool: `core/fpl_priors.py`
renames colliding web_names (Cole Palmer / Alex Palmer both arrive as "Palmer")
before the engine sees them, and that renamed string is what the overlay keys on.

## Expiry

Every written note carries `round: <gw>`, so it applies to that gameweek only and
expires on its own rather than leaking into next week's projections. Preflight
reports FPL notes pinned to a *past* gameweek — they are already inert, so the
player is silently back on bootstrap availability alone. Re-pin if the read still
holds, or retire the file by renaming it with a leading `_`.

Preflight also says so, informationally, when a gameweek has **no** lineup notes
at all: the model is then running on the bootstrap `status` field alone.

## Files

Notes are written to `research/players/fpl-<slug>.md`, one file per player,
overwritten rather than appended to. The `fpl-` prefix keeps them clear of the
hand-written World Cup notes sharing that directory (there is already a `kane.md`)
and lets preflight scope "pinned to a past round" to one competition — the two
number their rounds in the same integer space. One file per player is also what
keeps `core.research.find_duplicate_names` quiet: the 2026-07-19 collision was
four Nico Williams files where which one was live came down to directory listing
order.
