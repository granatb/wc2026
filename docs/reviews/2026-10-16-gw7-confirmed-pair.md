# GW7 owner confirmation and conditional lineup — 16 October 2026

The owner reported at 11:45 UTC: “ok saka and de cuyper are in”, following the
choice of Bruno Fernandes → Saka and Shaw → De Cuyper. These two transfers are
confirmed by the owner; the complete actual squad, bank, sale prices, chips and
other moves remain unverified. From three confirmed free transfers, one remains
if these are the only moves; rolling it gives two next week.

## Recorded fifteen after the confirmed pair

- GK: Raya, Sánchez.
- DEF: Tarkowski, Virgil, De Cuyper, N. Williams, Bobby Thomas.
- MID: Saka, Cole Palmer, Gibbs-White, Szoboszlai, E. Le Fée.
- FWD: Thiago, Evanilson, Calvert-Lewin.

Conditional XI (3-4-3): **Raya; De Cuyper, Tarkowski, Virgil; Saka (C),
Palmer, Le Fée, Gibbs-White; Thiago (VC), Calvert-Lewin, Evanilson.**
Outfield bench: **Bobby Thomas, N. Williams, Szoboszlai**, in that order.
Reserve GK: Sánchez, unavailable in the saved feed.

The exact pair was jointly recalculated from the retained 14 October GW7–11
boards. Exhaustive enumeration of legal XIs verifies 61.80 GW7 XI-plus-captain
mean, +4.52 versus holding, +8.358 discounted three-week and +10.197 five-week
gains. The saved hold-price calculation leaves £1.5m, not a verified account
bank. These are not Saka-plus-Gonzalo figures. The model excludes autosubs,
conditional vice value, future moves, chips and saved-transfer option value.

The base bench is Thomas 3.08, Szoboszlai 2.97, Williams 2.62. Injury uncertainty
justifies the cautious saved scenario's Thomas/Williams/Szoboszlai order. Its
XI/captain/vice stay the same, with 60.63 mean points. No fresh simulation or
calibrated injury probability is claimed. The cleared scenario can replace
Gibbs-White with Szoboszlai, but weekend starting fitness is not confirmed.
Thiago 5.95, Calvert-Lewin 5.90 and Palmer 5.84 are close vice choices; Saka is
7.02. The requested useful lineup was supplied before website work.

## Targeted news review

- [Liverpool official injury list](https://www.liverpoolfc.com/news/liverpools-injury-list-suspensions-and-availability),
  checked 16 October, is still dated 12 October. It confirms the hamstring issue,
  not recovery. [16 October reporting](https://www.thisisanfield.com/2026/10/dominik-szoboszlai-injury-update-liverpool-return/)
  describes a hoped-for return within a week; it does not confirm a weekend start.
- [Saka reporting](https://talksport.com/football/4644227/arsenal-bukayo-saka-england-fans-darren-bent/)
  records illness and a 25-minute goal-and-assist cameo. Direct retrieval of the
  previously saved Arsenal official report failed; no new official clearance is claimed.
- [Brighton official lineup](https://www.brightonandhovealbion.com/match-centre-lineups?gameId=2685825)
  records De Cuyper entering at half-time on Thursday.
- [Bournemouth match report](https://www.thetimes.com/sport/football/article/bournemouth-sturm-graz-europa-league-evanilson-bl2lwjdpm)
  records Evanilson scoring and leaving after 70 minutes. No club report was
  retrieved in the targeted search; this is secondary reporting.

## Website preparation and delivery blocker

The live 14 October export still says no transfers were confirmed. A dated
editorial follow-up is prepared at `/fpl/gw7/confirmed-pair/`, with machine-readable
JSON, sitemap/latest-feed discovery and an updated notice across landing/GW7/player
pages. It explicitly distinguishes owner-confirmed moves from the conditional
fifteen and retained 14 October forecast. The older hypothetical transfer article
is superseded only for those two moves. The accepted Model/Consensus website
rosters and historical evidence remain unchanged.

`scripts/publish_gw7_confirmed_pair.py` independently enumerates legal XIs, checks
the exact pair, validates the cumulative site and checks all 372 protected
hashes. Evidence: `data/releases/2026-10-16-gw7/calculation.json` and
`content-check.json`. It does not simulate, fetch or alter forecast timestamps.

Delivery is blocked: Git cannot read `/Users/bartlomiej.granat/.gitconfig`
(`Operation not permitted`), and `npx` is unavailable. No restriction was
bypassed, no commit/push/deployment occurred, and no live success is claimed.
Readable local branch ref remains `5e581006e0eee1d49007cfdb2c1b8feca7b1a83d`;
this is not a successful Git status or remote refresh. Existing handoff completion
notes were preserved. No real FPL account action occurred.

From the normal authorized terminal, before the 17 October 10:00 UTC deadline:

```sh
cd /Users/bartlomiej.granat/personal/projects/wc2026
bash scripts/ship_gw7_confirmed_pair.sh
```

The script refuses changed HEAD or staged work, rebuilds only the dated editorial
addition, stages explicit paths, commits, pushes, uses `scripts/deploy.sh`, then
checks seven live responses byte-for-byte. The older 14 October shipping script
must not be rerun. After success, record the actual commit and deployment receipt.
