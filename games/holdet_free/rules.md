# Holdet "FREE" — same scoring, only 3 contracts for the WHOLE tournament

**Same scoring table and economy as the other Holdet games** (shared in
`games/holdet_common.py`): kr growth table, 1% interest, captain ×2, budget 50M,
max 4/nation, 11 players no bench, locks at first kickoff, same position quirks.

## What differs: contracts
- You get **only 3 contracts (transfers) for the entire tournament**. Each transfer
  consumes one contract. **Hoard them.**
- **Captain changes cost no contract** — re-captain freely every round.
- Because contracts are scarce, the bar to spend one is far higher than the standard
  trade rule. A transfer should be reserved for a **multi-round** value swing or a
  squad-breaking injury/exit — not a single-round delta.

## Decision rule for spending a contract
Standard trade rule (delta > 1% × incoming price) is **necessary but not sufficient**.
Spend a contract only when the **cumulative** growth advantage of the incoming player
over the remaining rounds clears the standard bar AND beats the option value of
holding the contract for a later, bigger swing. Track contracts remaining in state.

## Order book
1. Expected growth + best (free) captain for the round.
2. Whether to spend a contract this round (default: NO — show the cumulative edge
   required and how many contracts remain).
