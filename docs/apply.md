# APPLY: writing to the Yext sandbox

Code: `kaiku/apply/yext.py`, `publishers.py`, `cli.py`. Tests: `tests/test_apply.py` (`pytest -q`; the live test needs YEXT_API_KEY and writes then removes 2027-06-01).

## Endpoints (sandbox only)
Host `https://api-sandbox.yext.com/v2/accounts/me`, query `api_key=<YEXT_API_KEY>&v=20241101`, timeout 10 s. The production host rejects our key, so it is never used.
- `GET  /entities/SinceAI07` read (hours is absent until set)
- `PUT  /entities/SinceAI07` partial update: only the fields sent change, but `hours` is replaced as a whole, including its `holidayHours` list.

Entity: id `SinceAI07`, type location, "Furry Paw Vet Clinic", Tikkurilantie 9, 01300 Vantaa, language fi. Sandbox has zero publisher listings (`GET listings/listings` count 0).

## Payloads that worked
Regular hours (set once on 6.11.2026 by us, left in place): Mon-Fri 09:00-17:00, Sat 10:00-14:00, Sun closed.
```json
{"hours": {"monday": {"openIntervals": [{"start": "09:00", "end": "17:00"}]}, "...": "...",
           "sunday": {"isClosed": true},
           "holidayHours": [{"date": "2026-12-24", "openIntervals": [{"start": "09:00", "end": "13:00"}]},
                            {"date": "2026-12-25", "isClosed": true}]}}
```
The holiday list lives INSIDE `hours`. Client does read-modify-write so existing days and rows survive.

## Accepted and rejected
- Accepted (200): hours with holidayHours open row; closed row `{"date","isClosed":true}`; read-back returns the rows unchanged.
- Rejected (400, code 2230 ENTITY_FIELD_INVALID): top-level `holidayHours` outside `hours`.
- Rejected (400, code 2293): `Invalid field hours.holidayHours: Value must be a valid date` for date `24.12.2026`. Only `YYYY-MM-DD`.
- ACCEPTED BUT WRONG: inverted interval 13:00 to 09:00 returned 200. The client therefore validates start < end and HH:MM locally (`holiday_row`).
- Omitting `holidayHours` from `hours` does NOT clear it (old rows stay); to delete the last row send `"holidayHours": []`.
- Sending `hours` with a new `holidayHours` list REPLACES the old list, so merging is done client side (`merge_holiday_rows`).

## Safety
Every `apply_suggestion` first saves `data/yext_snapshot_<ts>.json` (current hours). `python -m kaiku.apply.cli revert FILE` puts it back. `apply_suggestion` never raises: it returns `{yext_status: "ok"|"error:<msg>", entity_version (Yext timestamp), written, snapshot, verified, environment: "sandbox"}`; `verified` is true only if a GET after the PUT shows the identical row.

CLI: `python -m kaiku.apply.cli show | set-holiday 2026-12-24 09:00 13:00 | set-closed DATE | remove DATE | revert FILE`.

## Test log (6.11.2026)
Wrote 2026-12-24 09:00-13:00, read back, verified, removed; also 2027-01-01 closed; probe rows removed. Entity ends with regular hours and no holiday rows.

## Where it shows (publishers.py)
Sources fetched 6.11.2026: https://yrityksille.fonecta.fi (says Kontakti is now Connect; names no channels) and https://fonectaconnect.fi/ . The latter names Fonecta Caller, Finder and 020202 Palvelut ("Vahvista, että yritystietosi ovat oikein Fonecta Callerissa, Finderissa ja 020202 Palvelussa"), mentions Google (Google-yritysprofiili, Google Maps), says information is updated to "yli 30 eri verkkosivustolle", and names only categories otherwise: search engines, map services, social media, AI services. We list exactly that. We do NOT name Apple, Bing, Facebook, Waze etc. because Fonecta's pages do not; if Fonecta confirms them at Q&A, add them to `CHANNELS`.

Each entry has `kind` named|category and status `sandbox: written to the entity; in production Connect syncs this to <channel>`.

## Sandbox limitation and demo wording
The sandbox has no publisher listings, so nothing syncs anywhere. The demo says: "Saved to the Yext entity just now, confirmed by reading it back. In production we update your information everywhere." Never "now live on Google". Show the verified read-back and the snapshot/revert as the proof.

## Revert and reset
`revert()` always sends `holidayHours` (as `[]` when the snapshot had none) and verifies by read-back, so rows written after the snapshot are removed. `reset_demo(entity_id)` removes all holiday rows, keeps regular hours, verifies, and returns the hours (for a demo-reset endpoint).

## Yext Suggestions API: not permitted for the sandbox key (probed 6.11.2026)
Base `https://sbx-api.yextapis.com/v2/accounts/me`, `v=20261106` (same result on `api-sandbox.yext.com`). Responses, key never shown:
- `GET /suggestions` -> HTTP 403, error code 20 `INSUFFICIENT_APP_ACCESS`, "App does not have access to this endpoint".
- `POST /suggestions` (upsert holidayHours for SinceAI07) -> HTTP 403, same error. `GET /suggestions/{id}` -> 403 same. `PUT /suggestions` -> 405.
- `POST /suggestions/{id}/actions` -> 404 (path does not exist; nothing was created, so nothing to clean up).
- For contrast `GET /reviews` -> 200 `{"reviews":[],"count":0}`.
Decision: the direct entity write stays (`apply_suggestion`, snapshot, PUT, read-back verify). No `kaiku/apply/suggestions.py` and no
`KAIKU_YEXT_SUGGESTIONS` switch were built, because every call would 403. If Fonecta enables the Suggestions API for the app, re-run the probe: the plan is propose on chain suggestion, approve on owner approval, then the same read-back.

## Description and review replies
`apply_description(entity, text)`: PUT `{"description": text}`, GET back, `verified` only if the stored text equals what we wrote.
Event: "Description saved to Yext, read back and verified". `apply_review_reply(entity, review_id, text)`: POST
`/v2/accounts/me/reviews/{id}/comments` on the sandbox gateway (`sbx-api.yextapis.com`); `posted` is true only when the Reviews API
read-back shows our comment. If the key refuses, the reply is appended to `data/review_replies.jsonl` and the event says
"Reply stored; the sandbox key cannot post review comments" (never "posted"). Replies for file-based sample reviews are always stored.
`kaiku/chat/actions.py`: `decide(..., edited_text=)` routes both kinds; approve = the card's text, edit = the owner's own text, decline
= learn event + `data/text_declines.jsonl`. The decision is stored as a suggestion (kind `ask`, date 1970-01-01 so it never matches a
holiday card) so `with_decisions` shows the status. `/api/reset` only clears holidayHours, so the sample description stays; re-run
`python tools/seed_sandbox.py` after anything that removes it (also restores the typo after a demo approval).
Live status at build: description PUT 200 and read back; reviews POST 201 (two sample reviews); comment endpoint answers 400 for an unknown review id (reachable), a real comment post was not tried so the sample review stays unanswered.
