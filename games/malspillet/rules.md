# Målspillet — exact-scoreline betting

Per match you predict a scoreline. Scoring is **1 + 1 + 1** (max 3 / match):
- **+1** correct **home goals**
- **+1** correct **away goals**
- **+1** correct **outcome** (home win / away win / **draw counts**)

These three components score **independently**. So 2–1 predicted vs 2–0 actual still
scores 1 (home goals right) + 0 (away goals wrong) + 1 (outcome: home win right) = 2.

## Optimal pick — NOT the modal scoreline
Maximise **expected points** under the 1+1+1 structure, computed from the **joint
Poisson** of the match's team lambdas (from `core/fixtures.py`):

- Best **home-goals** guess = argmax over h of P(home scores exactly h).
- Best **away-goals** guess = argmax over a of P(away scores exactly a).
- Best **outcome** guess = argmax over {H, D, A} of P(outcome).
- Because the three are scored independently, the EV-optimal *scoreline to submit*
  is essentially (modal home goals, modal away goals) — but verify the implied
  outcome equals the modal outcome; if the modes disagree with the modal outcome,
  pick the (h, a) that maximises **total** expected points (sometimes nudging one
  goal count to align the outcome is +EV). The model computes this exactly.

## Chance Bamse
- One match per round is **doubled**. It **LOCKS at that match's kickoff** (you can
  set/keep it any time before that match starts).
- In **single-match rounds** (bronze final, final) it is **auto-assigned** to that match.
- Assign Bamse to the match with the **highest expected-points-doubling value** among
  matches you **haven't locked yet** — i.e. the unlocked match with the greatest
  expected points (doubling the highest-EV match gains the most).

## Order book
1. Per match: EV-optimal scoreline to submit + its expected points, with the marginal
   home/away goal distributions and outcome probabilities.
2. Chance Bamse recommendation: the unlocked match with highest expected points
   (auto-assigned in single-match rounds), with its lock = kickoff time.
