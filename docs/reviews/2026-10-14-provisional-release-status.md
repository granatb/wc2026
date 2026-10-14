# GW7 website release — prepared, deployment blocked

The user explicitly authorized website publication on 14 October; account
transfers remain the user's Friday action. This authorization supersedes the
earlier local-only delivery scope. No real FPL account was accessed or changed.

## Prepared and verified

- Existing cumulative `dist/` rebuilt through `evmax.fpl_build`, retaining
  historical forecast evidence and serving final GW6 results/review.
- GW7 has 667 player pages, nine generated article types, the expert scan,
  a joint 0/1/2/3-transfer post and the final GW6 review. New editorial URLs:
  `/fpl/gw7/transfer-plan/`, `/fpl/gw7/gw6-review/`.
- The landing, GW7 pages and player pages visibly mark provisional status,
  unverified account holdings/finances, only three confirmed FTs and Friday news.
  Proposed transfers remain hypothetical. The held Model roster has Thiago
  captain; the held Consensus roster has Haaland. Saka captains the hypothetical
  Saka routes; Haaland still has the higher individual projection.
- The source-matched 14 October 10,000-draw board was reused without simulation
  or model changes. Archived inputs are private under `data/releases/2026-10-14-gw7/`.
  The build checks exact priors, player metadata, source fingerprint and official
  payload receipts. Freshness, dossier and publication gates remain active.
- Exact proposal `553cfb64f468b6b339b882189fb06e552ee15f323232e31bd5b774a961074907`
  was reviewed and accepted for website publication through the operator CLI.
  Account submission remains `unverified`; saved state files retain their bytes.
- New forecast artifact:
  `91272d7db80451db2ddac544b124f2e3aba423f43b66a0e105877e15edd41b10`.
- Full offline regressions: **1,430 tests passed, five existing skips**.
  Content/evidence check passes for GW1–7, all six visible transfer-table rows,
  captain ownership, source JSON, final GW6 grade and all 372 protected hashes.
  Existing expert schema and Git whitespace checks pass.
- Logs: `full-tests.log`, `dry-build.log`, `production-build.log`,
  `content-check.json`, `deploy.log` in the private release directory.

## Exact blockers

`bash scripts/deploy.sh` passed its site validator, then exited 127:
`scripts/deploy.sh: line 16: npx: command not found`.

The existing bundled Node runtime was checked as a possible launcher for the
same pinned Wrangler, but it exited before execution with an OpenSSL read error:
`Operation not permitted` for `/System/Library/OpenSSL//openssl.cnf`.
No OpenSSL configuration, security setting or permission was changed.

The earlier `.git/index.lock` write denial remains respected; no Git write was
retried or bypassed in this release turn. HEAD remains `0ddb44b`, branch
`chore/gw6-thursday`, ahead five of the locally recorded upstream. All release
changes are uncommitted. No push or Cloudflare deployment completed.

Browser review also failed at the same OpenSSL configuration read. A local
HTTP server was refused at `socket.bind` with `Operation not permitted`.
Static generated HTML and JSON were checked; no visual or live-delivery pass
is claimed. No production release identity can be reported until deployment.

## Minimal next step

From a normal Mac terminal with the project's existing Git and Node/Cloudflare
access, run:

```sh
cd /Users/bartlomiej.granat/personal/projects/wc2026
bash scripts/ship_gw7_provisional.sh
```

This checks freshness and evidence, refuses unexpected HEAD/staged work, stages
only the explicit release paths, commits, pushes the current branch, invokes
the established `scripts/deploy.sh`, then compares 17 live responses byte for
byte with the validated output. It excludes `.restriction-test-20261013-a91c/`
and all private raw inputs. No build or new research is needed while the
24-hour input freshness gate still passes. A later run requires an updated
pre-deadline review; never falsify capture timestamps to pass the gate.

After successful delivery, record the actual commit and Cloudflare deployment
identity here and in HANDOFF. No success is implied by these prepared commands.
