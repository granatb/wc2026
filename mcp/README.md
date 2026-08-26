# evmax-mcp

An MCP server that gives an AI assistant direct access to
[evmax](https://evmax.ai)'s Fantasy Premier League projections — the numbers
from 50,000 Monte-Carlo simulations run before every deadline, plus the graded
record of how accurate they turned out to be.

Ask your assistant *"who should I captain this week?"* or *"how wrong was evmax
about Haaland last gameweek?"* and it can fetch the actual numbers instead of
guessing.

The data is **CC BY 4.0** — free to use, including commercially, as long as you
credit evmax. Every tool response repeats that line, so an assistant using this
server always knows what it owes.

## Install

```bash
claude mcp add evmax -- npx -y evmax-mcp
```

Or, for any MCP client that reads a JSON config:

```json
{
  "mcpServers": {
    "evmax": {
      "command": "npx",
      "args": ["-y", "evmax-mcp"]
    }
  }
}
```

Run it directly if you want to see it start:

```bash
npx evmax-mcp
```

No API key, no account, no configuration. It is a read-only client over public
URLs — there is nothing to authenticate against and nothing it can change.

## Tools

| Tool | What it answers |
|---|---|
| `list_gameweeks` | Which gameweeks have data, and what each one carries. Call this first if you do not know what exists. |
| `get_projections({gameweek?, position?, limit?})` | Projected points for every simulated player in a gameweek, best first. Filter by position, cap the rows. |
| `get_player({name, gameweek?})` | One player in full — projection, captain EV, ceiling, price, ownership, verdict tier. Matches names through accents and punctuation. |
| `get_duel()` | The running model-vs-crowd score: evmax's published XI against a consensus XI, both frozen before the deadline, graded on official points. |
| `get_accuracy({gameweek?})` | The graded ledger — mean absolute error per gameweek against FPL's own `ep_next`. Pass a gameweek for the per-player detail, biggest misses included. |
| `get_distribution({name, gameweek?})` | The shape of a player's gameweek, not just the mean: floor, median, most likely, ceiling, and the probability of a haul or a blank. |

Arguments marked `?` are optional; `gameweek` defaults to whichever gameweek the
site is currently publishing.

### A note on what each tool can answer

The richest source is the bulk dataset at `/api/fpl/dataset/`, which carries
price, ownership, verdict tiers and outcome distributions. Where a gameweek
predates one of those, the server falls back to the feed that has always been
live and **says so in the response** rather than reporting a missing column as a
zero. `get_distribution` refuses outright — with an explanation and the mean it
does have — for a gameweek published before distributions were stored. A tool
that invented a plausible shape would be worse than one that admits it cannot.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `EVMAX_BASE_URL` | `https://evmax.ai` | Point at a local or staging build. |

## Development

```bash
npm install
node test-smoke.js        # hits the LIVE site, asserts every tool's shape
```

The smoke test is manual and deliberately outside the repository's Python test
suite: it makes real network requests, so it belongs to the pre-publish
checklist rather than to a run that must work offline. It asserts shape and
honesty — never a specific number — because the live site moves to a new
gameweek every week.

Requires Node 18 or newer. One dependency (`@modelcontextprotocol/sdk`), no
build step, no state, no secrets.

## The data

- **Human page:** <https://evmax.ai/data/> — the terms, the column glossary, curl examples.
- **Schema:** [`docs/DATASET.md`](../docs/DATASET.md) in the repository.
- **Accuracy:** <https://evmax.ai/fpl/accuracy/> — how well the projections have actually done.
- **Licence:** CC BY 4.0. Credit line to paste:

  ```
  Data: evmax (https://evmax.ai), CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
  ```

The server code itself is MIT. The data it fetches is CC BY 4.0.

## Not affiliated with the Premier League or Fantasy Premier League.
