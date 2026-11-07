# Detect and Suggest

Code: `kaiku/detect/{holidays,signals,engine}.py`, `kaiku/suggest/{schema,engine,explain,cli,backtest}.py`.
Run: `python -m kaiku.suggest.cli --business data/furry_paw.json --date 2026-12-24 --today 2026-12-17`
(falls back to the sample business in `data/sample_cases.json` if core's seed is not merged yet).
CLI flags: `--jsonl` prints one Suggestion JSON per line to stdout (`--jsonl PATH` writes a file), several dates allowed after
`--date`. A bad `--date` or `--today` exits with code 2 and one line on stderr. A past date prints a `PAST:` line.
Backtest: `python -m kaiku.suggest.backtest [cases.json|csv] --jsonl [out.jsonl]` (one Suggestion JSON per line).

Extra Suggestion fields for the contact lane: business_name, holiday_name_fi, holiday_name_en, last_year_hours
(list of {start,end}, "closed" or null), google_now ({status, ...}), decide_url (null; core fills it).

## Signals (Detection.signals)
| signal | source | production source in Connect |
|---|---|---|
| regular_that_day | business.regular_hours by weekday | Connect's own published hours |
| last_year | same holiday one year earlier, matched by name via the holiday table (moveable days like Pääsiäinen work) | Connect's exception-hours history |
| website | fetch site (5 s), find a line with the holiday name or date plus a time or "suljettu" | same crawl Connect already does for listings |
| google_now | Serper places, only if SERPER_API_KEY is in `.env`; else `{"status":"unknown"}` | Connect's own publishing state / Google Business Profile API |
| peers | `data/peer_priors.json`, category x holiday | hand-made priors, to be replaced by Fonecta's dataset |
| holidays | bundled `data/holidays_fi_2026.json` first (Nager.Date `PublicHolidays/{year}/FI` plus computed flag days with `public_holiday=false`); if the file is missing or older than 30 days, a live refresh from Nager.Date (5 s timeout, in try/except) rewrites it; on any failure the bundled file is kept and nothing crashes | same API or Fonecta's calendar |

Reason codes: PUBLIC_HOLIDAY, NOT_PUBLIC_HOLIDAY, REGULAR_CLOSED_THAT_DAY, LAST_YEAR_FOUND, EXCEPTION_ALREADY_SET,
NO_EXCEPTION_THIS_YEAR, WEBSITE_SAYS, GOOGLE_SHOWS_REGULAR / GOOGLE_SHOWS_HOURS (only when Serper verified Google),
CONNECT_SHOWS_REGULAR (Google not verified), PEER_PRIOR, PAST_DATE.

## The reliability gate (first match wins)
-1. Date before `today`: Detection.status = "past", Suggestion kind no_change, status expired, confidence 0, no proposal.
0. Exception already set for the date: no_change 0.95.
1. Regular hours closed that weekday: no_change 0.95. Not a public holiday: isänpäivä for a vet closed on Sundays.
   Public holiday: "Itsenäisyyspäivä 6.12. on sunnuntai ja olette silloin kiinni, joten muutosta ei tarvita."

Every interval is validated (HH:MM, start before end, no overlap). Invalid last-year, website or prior data is
dropped and the gate falls through to the next signal or to a question, never to a proposal.
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
closed-day accuracy 1.0. These are self-consistency checks on 10 cases we wrote ourselves (the targets come from the
same author as the rules). They prove the logic runs, not accuracy, and are not Fonecta's hidden test set.

## What did not work or is untested
- Serper places: no key in `.env` on this box, so `google_now` is untested live; it returns unknown. The code expects an
  `openingHours` dict in the first place and degrades silently. Without it the message says "Fonecta Connect näyttää nyt
  tavalliset aukioloajat", the only thing we know; Google is named only when Serper returned hours.
- The sample website `furrypaw.example` does not resolve; the signal returns None. Website parsing is tested only against
  a mocked page.
- Peer priors are the author's judgement, labelled as such in the file.
- Nager.Date has no uudenvuodenaatto (not a public holiday); we add it as a non-public day.
- Finnish inflection is a lookup table (`ESSIVE` in explain.py); an unknown holiday name falls back to "päivänä 24.12.".

## Suggestions feed (the owner's first screen: "Kaiku noticed N things")
Code: `kaiku/suggest/feed.py` (`build_feed(business_id, today=None)`), `kaiku/suggest/router.py` (`router = APIRouter()`, needs `"suggest"` in the module list of `kaiku/app.py` to be mounted).
`GET /api/feed/{business_id}?date=YYYY-MM-DD[&network=0]` returns
`{business_id, today, count, suggestions:[{id, kind, title_en, text_en, title_fi, text_fi, proposed, confidence, reasons:[{source, dataset_id, text_en, text_fi}], status, holiday_date?, period?}]}`.
`date` defaults to the time-travel clock. Field names are stable and machine-readable on purpose: this is the surface a scoring script
(Fonecta's hidden test data) can read directly, one card per suggestion, each with its reasons and the datasetId of every source.

Kinds, each only when real data supports it (no data, no card; nothing is invented):
- `holiday_hours`: the engine's suggestion for holidays within 45 days of `today` (in a period, the nearest date).
- `conflict`: two or more sources (last year, website, Google via Serper) returned different hours for the same day. Lists each value with its datasetId; `proposed` and `confidence` are the engine's. Needs live signals: with no website or Google data there is nothing to disagree.
- `period`: several holidays in one period (Christmas period 24.12. to 6.1.). One bundle with a per-date proposal in `proposed`, `standing_permission_offered` and the question "Want me to handle this period every year?" (not offered if the business already gave standing permission).
- `no_change`: the engine says no change (Father's Day 8.11., not a public holiday and closed on Sundays) shown as a reliability card with its reason.
- `description`, `review`: pluggable loaders (`register_loader`) reading the Yext entity description and the reviews endpoint. Sandbox 6.11.2026: `GET /reviews` returns 200 with 0 reviews, the entity has no description, so neither card appears.
`ask` suggestions (not enough data) are not feed cards; they go through the chain as before.

## Description and review sources (kinds `description`, `review`)
Loaders in `kaiku/suggest/feed.py`, helpers in `kaiku/suggest/sources.py`. Both read Yext live and return `[]` without data.
- **description**: missing -> "Your listing has no description" with a short draft (brain from name, category, address, hours;
  template fallback; labelled "draft by Kaiku"). Present -> typo pass: word list + double space + lower-case sentence start
  first, then the brain in strict JSON (`{"typos":[{"wrong","right"}]}`, each `wrong` must be a real substring, cached 10 min,
  fallback empty). Card "Typo in your description", `proposed` = the corrected full text, confidence 0.9, reason dataset
  `urn:kaiku:src:yext:description`.
- **review**: unanswered Yext reviews (Reviews API), 3 stars or less first, up to 3 cards. Text = quote (<= 160 chars) + "Here is a reply you could post:", `proposed` = the drafted reply
  (<= 60 words, no promises or discounts, Finnish for `owner_language: fi`, template when the brain is unavailable), confidence 0.7.
  Source `yext_reviews`; if the sandbox has no reviews, `data/furry_paw_reviews_sample.json` (source `sample_reviews`).
- **Sample data is labelled.** The sandbox entity SinceAI07 shipped with no description and no reviews. `tools/seed_sandbox.py`
  (idempotent) writes the sample description and two sample reviews; every card that comes from them carries the reason row
  "source: sample description/reviews written by the team". Not real customer data.
- Cards: `holiday_date: null`, extra fields `entity_id`, `review_id`, `rating`, `typos`.
- Not done: the Suggestions API is 403 for our key, so nothing is read from Yext's own suggestion engine.
