# Detect and Suggest

Code: `kaiku/detect/{holidays,signals,engine}.py`, `kaiku/suggest/{schema,engine,explain,cli,backtest}.py`.
Run: `python -m kaiku.suggest.cli --business data/furry_paw.json --date 2026-12-24 --today 2026-12-17`
(falls back to the sample business in `data/sample_cases.json` if core's seed is not merged yet).
Backtest: `python -m kaiku.suggest.backtest [cases.json|csv] --jsonl out.jsonl` (one Suggestion JSON per line).

## Signals (Detection.signals)
| signal | source | production source in Connect |
|---|---|---|
| regular_that_day | business.regular_hours by weekday | Connect's own published hours |
| last_year | same holiday one year earlier, matched by name via the holiday table (moveable days like Pääsiäinen work) | Connect's exception-hours history |
| website | fetch site (5 s), find a line with the holiday name or date plus a time or "suljettu" | same crawl Connect already does for listings |
| google_now | Serper places, only if SERPER_API_KEY is in `.env`; else `{"status":"unknown"}` | Connect's own publishing state / Google Business Profile API |
| peers | `data/peer_priors.json`, category x holiday | hand-made priors, to be replaced by Fonecta's dataset |
| holidays | Nager.Date `PublicHolidays/{year}/FI`, cached in `data/holidays_fi_2026.json`, plus flag days (isänpäivä, äitienpäivä, uudenvuodenaatto) with `public_holiday=false` | same API or Fonecta's calendar |

Reason codes: PUBLIC_HOLIDAY, NOT_PUBLIC_HOLIDAY, REGULAR_CLOSED_THAT_DAY, LAST_YEAR_FOUND, EXCEPTION_ALREADY_SET,
NO_EXCEPTION_THIS_YEAR, WEBSITE_SAYS, GOOGLE_SHOWS_REGULAR, GOOGLE_SHOWS_HOURS, PEER_PRIOR.

## The reliability gate (first match wins)
0. Exception already set for the date: no_change 0.95.
1. Not a public holiday and regular hours closed: no_change 0.95 (isänpäivä for a vet closed on Sundays).
2. Last year's exception exists: propose it, 0.85 (0.75 if the weekday differs, e.g. 24.12. was Wed, now Thu).
3. Website quotes exception hours: 0.80.
4. Public holiday and category prior "closed": closed 0.65.
5. Peer prior only: 0.50. A prior of "regular" gives no_change 0.70 (nothing is written).
`ASK_BELOW = 0.6`: below it the kind is `ask` with one Finnish question ("Oletteko auki jouluaattona 24.12.? Vastaa
esimerkiksi 9-13 tai suljettu."), `proposed` is null. A proposal equal to the regular hours becomes no_change.
The customer approves every write anyway; the gate decides between proposing and asking.

## Cold start (no history)
No last-year data: rules 4 and 5 only. Public holiday where the whole category is closed (Tapaninpäivä, juhannusaatto
for shops and so on) gives a "closed" proposal at 0.65 and says it is based on similar businesses. Any other case
(short hours priors, non-public days with a prior) stays at 0.50 and becomes a question. No cold-start case can exceed
0.65 and none above 0.6 is a guess about hours.

## For Fonecta's scoring script
We do not know its format yet. `backtest.load_cases` guesses CSV headers (business id/name, category, regular hours,
last-year exception, date, target; Finnish aliases included) and JSON. Output is JSON lines: the Suggestion contract
(`kind`, `proposed` as [{start,end}] or null, `confidence`, `reasons`). Closed is `kind: "closed"` with `proposed: null`;
abstention is `kind: "ask"`. If the script wants a flat `hours` string, add it in `backtest.run` (one line).
Metrics: exact match (all and answered only), closed-day accuracy, abstain rate, wrong-suggestion rate
(a proposal that differs from the target). Sample result on the 10 hand-made cases: wrong 0.0, abstain 0.2,
closed-day accuracy 1.0. These cases are written by us and prove the logic, not accuracy on real data.

## What did not work or is untested
- Serper places: no key in `.env` on this box, so `google_now` is untested live; it returns unknown. The code expects an
  `openingHours` dict in the first place and degrades silently. Without it the message says Google shows the regular
  hours, which is true for Connect's own published state, not verified against Google.
- The sample website `furrypaw.example` does not resolve; the signal returns None. Website parsing is tested only against
  a mocked page.
- Peer priors are the author's judgement, labelled as such in the file.
- Nager.Date has no uudenvuodenaatto (not a public holiday); we add it as a non-public day.
- Finnish inflection is a lookup table (`ESSIVE` in explain.py); an unknown holiday name falls back to "päivänä 24.12.".
