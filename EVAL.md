# Evaluation

**Rule: no number in this file without a receipt file in `eval/receipts/`. If nothing was measured, say so.**

## Question
Does <the core function> give the right answer on cases it has not seen?

## Held-out set
- n = <number> cases, built <how: hand-labelled Saturday afternoon / sampled from the data with known answers>.
- Stored in `eval/holdout.json`. Never used for prompting or tuning.
- Provenance: <where the ground truth came from and who labelled it>.

## Metric
<precision@1 / exact match / MAE / whatever fits>, defined as <one sentence>.

## Result
**<number>** (<n>/<N>). Receipt: `eval/receipts/<run-id>.json`. Rerun: `python3 -m eval.run` (takes <time>).

## Failure examples (real ones)
| Input | Expected | Got | Why |
|---|---|---|---|
| | | | |

## What this does not show
<honest limits: small n, one market, one weekend>

## If nothing was measured
State it plainly: "No held-out evaluation was completed in the available time." Do not invent a number.
