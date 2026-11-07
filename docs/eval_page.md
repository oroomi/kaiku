# /eval, the judge-facing quality page

Code: `kaiku/evalpage/{router,loader,runner}.py`, `kaiku/web/templates/eval.html`, `kaiku/web/static/eval.{js,css}`.
Tests: `tests/test_evalpage.py`.

## What it does
- `GET /eval`: page. Shows a run of `data/sample_cases.json` by default, labelled "Our own 10 sample cases, written by the team; not Fonecta's data."
- `POST /api/eval/run` (multipart: `file`, optional `mapping` JSON `{field: header}`): parses the upload in memory, runs `backtest.run(network=False)` per row,
  returns per-row results (business, date, holiday, answer, `hours_flat`, confidence, reasons in English, match status, the full Suggestion) and
  `summary.metrics` = `backtest.metrics` over the rows that have an expected value. The page builds the JSON-lines download in the browser from the Suggestion objects.
- `GET /api/eval/sample`: the sample result as JSON.

## Accepted input
CSV (`,` `;` or tab; UTF-8 or cp1252) with columns guessed by `backtest.ALIASES`; JSON `{"cases":[...]}` or a list of cases; a list of businesses with a
`holidays`/`dates` list (items may be `{date,target}`); a list of flat JSON rows (same mapping as CSV). Dates: `2026-12-24` or `24.12.2026`.
The mapping used is shown on the page and can be changed (header names) and re-run. A file with no date column returns 400 with the headers so the remap form appears.

## Limits and safety
2 MB, 500 rows, 20 s per run (400 with a plain-words message, never 500). No network: signals `website` and `google_now` are off, the holiday table comes from the bundled file
and is never refreshed in a run. Nothing is stored, nothing is sent, nothing is written to Yext.
Rows without an expected value are shown as "no expected value" and excluded from hit rate (backtest would otherwise count a closed answer as correct for a missing target).

## Scoring differences and the flags
`KAIKU_EVAL_ALWAYS_ANSWER=1` (read in `kaiku/suggest/engine.py` at call time): below `ASK_BELOW` (0.6) the engine answers with its best guess instead of asking
(the source's own proposal, else the regular hours of that day); confidence is unchanged and a low-confidence reason is added. Use it if the hidden script
expects hours always or counts abstentions as misses. Flat hours string: `hours_flat` per row in the eval results.

## Mounting
Add `"evalpage"` to the module list in `kaiku/app.py` (line with `"score", "listing"`).
