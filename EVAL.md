# Evaluation

**Status: no held-out evaluation against real data has been done.** Fonecta's dataset and scoring script had not arrived when this was written (6 Nov 2026). What exists is a self-consistency check on 10 cases we wrote. Treat the numbers below as "the rules run and agree with their author", not as accuracy.

## Question
Does the suggestion engine propose the right hours, and abstain when it should?

## Set
10 hand-made cases in `data/sample_cases.json`: last-year exception, isänpäivä for a vet closed on Sundays, joulupäivä closed, five cold-start cases, a case where last year equals the regular hours, and a cafe open on Sunday. The targets were written by the same author as the rules, so the set cannot show whether the rules are right, only that they behave as designed.

## Metrics (defined in `kaiku/suggest/backtest.py`)
- Wrong-suggestion rate: share of all cases where Kaiku proposed hours that differ from the target. Asking is not wrong.
- Abstain rate: share of cases where Kaiku asked a question instead of proposing.
- Exact match (answered only): share of answered cases with the target hours.
- Closed-day accuracy: share of closed targets answered closed.

## Result (run 6 Nov 2026)
`python3 -m kaiku.suggest.backtest data/sample_cases.json`

| Metric | Value |
|---|---|
| Cases | 10 |
| Wrong-suggestion rate | 0.0 |
| Abstain rate | 0.2 (2 of 10) |
| Exact match, all | 0.8 |
| Exact match, answered only | 1.0 |
| Closed-day accuracy | 1.0 |

No receipt file exists under `eval/receipts/`; the command above prints the numbers and takes about a second.

## How wrong suggestions are prevented
- Confidence gate, first match wins: exception already set gives `no_change` (0.95); regular hours closed that weekday gives `no_change` (0.95); last year's exception gives a proposal (0.85, or 0.75 if the weekday differs); website hours give 0.80; a public holiday where the category prior is "closed" gives `closed` at 0.65; a peer prior alone gives 0.50.
- `ASK_BELOW = 0.6`: below it Kaiku sends one question ("Oletteko auki jouluaattona 24.12.? Vastaa esimerkiksi 9-13 tai suljettu.", gloss: Are you open on Christmas Eve 24.12.? Reply for example 9-13 or closed) and proposes nothing. No cold-start case exceeds 0.65.
- `no_change` rules: a proposal equal to the regular hours becomes `no_change`; a date already past gives nothing; Isänpäivä for a vet closed on Sundays is `no_change` because it is not a public holiday.
- The customer approves every write.
- Learning: two declines of the same holiday turn it into `no_change`; one decline lowers confidence by 0.15; an edit is proposed next time at confidence at least 0.9.

## The Google signal
Kaiku checks what Google shows through Serper places (`SERPER_API_KEY`). The status for the fictional Furry Paw business is unknown: it is not a real Google listing . `SERPER_API_KEY` is set on the build box and `google_now` in `kaiku/detect/signals.py` calls Serper places for it, but a fictional business returns no hours. When Google is unverified the message names Connect's published hours instead. Note: the home page headline still says "Google still says 9-17" for the demo business; that is the brief's own framing and the sample data, not a live Google read.

## Failure and edge rows (real engine output)
| Case | Expected by author | Got | Why |
|---|---|---|---|
| 4 cold-start cafe, public holiday, prior short hours | 9-14 | ask (0.50) | Prior alone is below 0.6, so it asks rather than guesses |
| 8 cold-start restaurant, uudenvuodenaatto (not public) | 11-18 | ask (0.50) | Nager.Date has no uudenvuodenaatto; no prior is strong enough |
| 10 cafe open Sunday, isänpäivä | 10-16 | no_change (0.70) | Prior says "regular"; nothing is written |

## What this does not show
Accuracy on real businesses, any other country, or Fonecta's hidden data. Peer priors are the author's judgement (`data/peer_priors.json`, labelled). The website parser is tested on a mocked page only. Fonecta's scoring format is unknown; `backtest.load_cases` guesses CSV and JSON headers and writes the Suggestion contract as JSON lines, and one line would add a flat hours string if the script wants one.
