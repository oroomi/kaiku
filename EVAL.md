# Evaluation

**Status: no held-out evaluation against real data has been done.** Fonecta gave no dataset format and no sample data during the event, and we never saw the scoring script (7 Nov 2026). What exists is a self-consistency check on 10 cases we wrote. Treat the numbers below as "the rules run and agree with their author", not as accuracy.

## Question
Does the suggestion engine propose the right hours, and abstain when it should?

## Set
10 hand-made cases in `data/sample_cases.json`: last-year exception, isänpäivä for a vet closed on Sundays, joulupäivä closed, five cold-start cases, a case where last year equals the regular hours, and a cafe open on Sunday. The targets were written by the same author as the rules, so the set cannot show whether the rules are right, only that they behave as designed.

## Metrics (defined in `kaiku/suggest/backtest.py`)
- Wrong-suggestion rate: share of all cases where Kaiku proposed hours that differ from the target. Asking is not wrong.
- Abstain rate: share of cases where Kaiku asked a question instead of proposing.
- Exact match (answered only): share of answered cases with the target hours.
- Closed-day accuracy: share of closed targets answered closed.

## Result (re-run 7 Nov 2026 about 11:25Z, same numbers)
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
- Learning: two declines of the same holiday turn it into `no_change`; one decline lowers confidence by 0.15; an edit is proposed next time at confidence at least 0.9 (`kaiku/learn/prefs.py`, applied in `kaiku/chain.py::_apply_prefs` before contact and read in `kaiku/suggest/feed.py` for the standing-permission wording).

## The Google signal
Kaiku checks what Google shows through Serper places (`SERPER_API_KEY`). The status for the fictional Furry Paw business is unknown: it is not a real Google listing. The key is set and `google_now` in `kaiku/detect/signals.py` called Serper places live on 7 Nov and returned `{"status": "unknown"}`. When Google is unverified the message names Connect's published hours instead. Note: the home page headline still says "Google still says 9-17" for the demo business; that is the brief's own framing and the sample data, not a live Google read.

## Failure and edge rows (real engine output)
| Case | Expected by author | Got | Why |
|---|---|---|---|
| 4 cold-start cafe, public holiday, prior short hours | 9-14 | ask (0.50) | Prior alone is below 0.6, so it asks rather than guesses |
| 8 cold-start restaurant, uudenvuodenaatto (not public) | 11-18 | ask (0.50) | Nager.Date has no uudenvuodenaatto; no prior is strong enough |
| 10 cafe open Sunday, isänpäivä | 10-16 | no_change (0.70) | Prior says "regular"; nothing is written |

## What this does not show
Accuracy on real businesses, any other country, or Fonecta's hidden data. Peer priors are the author's judgement (`data/peer_priors.json`, labelled). The website parser is tested on a mocked page only. Fonecta gave no dataset format or sample, so the loader guesses. `kaiku.suggest.backtest.load_cases` accepts a CSV (header names matched case-insensitively against aliases: id/business_id/customer_id, name, category/toimiala, regular_hours/opening_hours, last_year/last_year_hours, date/holiday_date, target/truth/label, today) or a JSON file with a `cases` list or a plain list; hours may be `9-13`, `09:00-13:00`, `closed`/`suljettu`/`kiinni`. `--jsonl [PATH]` writes one Suggestion (the contract in CLAUDE.md) per line for a scoring script; one more line would add a flat hours string if the script wants one.

## How this answers Fonecta's evaluation criteria (slide 7)
Each paragraph says what is true on the live product (https://kaiku.hankintaviikko.fi, 7 Nov 2026), the evidence, and what is not shown. The test suite: `.venv/bin/python -m pytest -q` gives 454 passed, 7 skipped (the skipped ones send or fetch live and need `KAIKU_LIVE=1`) on the box with its `.env`; in a fresh checkout `tests/test_email.py::test_real_smtp_path` also fails because it needs the SMTP environment.

**Suggestion quality.** The engine proposes last year's exception for the same holiday (0.85, or 0.75 when the weekday differs), website hours (0.80), a closed day where the whole category is closed (0.65), and otherwise asks; every proposal carries its reasons with the data source and a datasetId (`GET /api/feed/furry-paw` returns, for Christmas Eve, 9-13 at confidence 0.75 with the reasons "Last year on 24.12. you were 09:00-13:00 (it was a Wednesday that year)" and "Fonecta Connect now shows your regular Thursday hours (09:00-17:00)"). What we cannot claim: accuracy. The hidden dataset is unknown to us; our 10-case set is written by the rules' own author and gives wrong-suggestion rate 0.0 and abstain rate 0.2 as a self-consistency check only. `backtest.load_cases` accepts the CSV and JSON shapes above and prints machine-readable JSON lines, so Fonecta's script can be pointed at it. Failure rows are listed above.

**Customer experience.** The owner is reached without a login: an email with a one-tap decision link at once, a WhatsApp message after 60 s without a decision (`EMAIL_ESCALATE_AFTER_S=60` in the live config), then a call by Kaiku after `WA_ESCALATE_AFTER_S` (600 s live). The last question on every channel is how the owner would like to be reached next time; the answer is stored and re-orders the ladder. The WhatsApp opener is a warm text in Kaiku's voice with two buttons, Accept and Discard, and the line "To change the hours, just reply with them." We deliberately differ from Fonecta's example buttons Approve / Edit / No thanks: the two common answers are one tap, and a typed edit carries the actual hours. On the page the listing score (40 of 100 at the time of writing (it moves with the sandbox state), 3 of 7 checks, `GET /api/score/furry-paw`) shows what Connect holds, cards offer Accept, Suggest a change and Discard, Accept applies at once, and the chat opens empty and answers with a receipt ("Done. 24.12. 9-13 is saved. We'll update your information everywhere within the hour."), the recurring question only when last year's data exists, then the next item with its reason. One receipt per decision; chat memory persists across restarts. Evidence: tests/test_chat.py, tests/test_wa_chat.py, [final_messages.md](docs/final_messages.md). Not shown: a usability test with a real busy owner; the WhatsApp templates `kaiku_hours_fi` and `kaiku_hours_en` were pending at Meta at last check, so outside Meta's 24 hour window delivery relies on the test number's `hello_world` template.

**Reliability.** The customer always has the last word: nothing is written to Yext before the owner taps Accept, replies yes, or sends hours; Discard and "no" leave the listing as it is. Wrong suggestions are prevented by the confidence gate (`ASK_BELOW = 0.6`: below it Kaiku asks and proposes nothing), by "no change" notes (8.11. Father's Day for a vet closed on Sundays), by conflict cards that ask which source is right, by local validation of hours (Yext accepts an inverted interval, we do not), and by receipts built from the apply result: if the write failed Kaiku says "I could not save it", never "saved" (`flow.receipt`, tests/test_chat.py::test_failed_write_on_accept_is_not_reported_as_saved). The Yext write never depends on the Orion-LD broker (`kaiku/broker/fallback.py`). Not shown: behaviour at scale (the signal fetch per business is the first wall, see README).

**Extensibility.** The same loop already runs three more use cases on the live page, each as a card with a reason and the same Accept / Suggest a change / Discard actions: a correction to the description ("vacination" to "vaccination", confidence 0.9), a drafted reply to an unanswered review (0.7), and a holiday period as one card of six dates (0.65). The description and review text in the sandbox are samples written by the team (labelled in `data/furry_paw_description_sample.txt` and `data/furry_paw_reviews_sample.json`); the sandbox key cannot post review replies, so an approved reply is stored, not posted. The Orion-LD spine and the `ngsi-ld-mcp` server let other agents propose to the same attribute with their own datasetId. Not shown: automatic posts.

**Learning.** After an edit the next suggestion for that holiday is the edited hours at confidence at least 0.9; one decline lowers confidence by 0.15; two declines turn the holiday into "no change"; a standing permission is stored per holiday or for all (`kaiku/learn/prefs.py`, applied in `kaiku/chain.py` before contact and in `kaiku/suggest/feed.py`; tests/test_learn.py: 10 tests). Kaiku asks "Do you want to make it recurring, this time of the year?" only when last year's data exists, and on yes stores the permission and says "Every Christmas Eve from now on, unless you tell me otherwise." A stored standing permission is applied by the chain on the next run for that holiday: nothing is asked, the write happens, and the owner gets one line afterwards that they can answer with other hours (`kaiku/chain.py`, `tests/test_core.py::test_standing_permission_applies_without_asking`). Limit: not shown live over a second year, because the demo clock covers one Christmas.

**All five steps.** Detect: the broker subscription or the feed build finds the holiday and the missing exception hours. Suggest: the engine (above). Contact: email, WhatsApp, call. Decide: Accept, Discard, a typed edit, on the page, in WhatsApp, in the email link or by voice. Apply: a write to the Yext sandbox entity SinceAI07 with a read-back (`GET /api/listing/furry-paw` shows the holiday row 24.12. 9-13) and a receipt telling the owner where it shows. Live proof of the channels: email sent 2026-11-06T23:48:04Z (`data/email_log.jsonl`), WhatsApp text 23:49:08Z (`data/wa_sends.jsonl`), call answered with an approval and a Yext write at 21:46:53Z on 6 Nov (`data/call_log.jsonl`, docs/call.md). The Yext sandbox has no publisher listings, so "where it shows" is a statement from Connect's publisher list, not a syndication we observed.
Accuracy on real businesses, any other country, or Fonecta's hidden data. Peer priors are the author's judgement (`data/peer_priors.json`, labelled). The website parser is tested on a mocked page only. Fonecta gave no format; `backtest.load_cases` guesses CSV and JSON headers and writes the Suggestion contract as JSON lines, and one line would add a flat hours string if the script wants one.

## What /eval does instead of a score on Fonecta's data
Fonecta gave no dataset format or sample during the event, so we cannot report a hit rate on their data and do not. Instead the live page `/eval` lets anyone drop a dataset (CSV or JSON) and see every suggestion with its reason and the hit rate computed on the spot.

## Run it on your own data: /eval
`/eval` is a page where a CSV or JSON file (2 MB, 500 rows) is run through the same engine and `backtest.metrics` offline, with per-row answers, reasons, the column mapping used (remappable) and a JSON-lines download of the Suggestion contract. It starts with our 10 sample cases, labelled as ours. See `docs/eval_page.md`. `KAIKU_EVAL_ALWAYS_ANSWER=1` makes the engine answer below the 0.6 gate for scripts that count abstentions as misses.
