# Data sources

Slide 8 asks for 3 to 5 key data sources, where Connect would get them in production, and what did not work. The five that feed the holiday chain are in the table; the sections below give licence, use and failures for each. Three more sources (OpenStreetMap, Föli and Digitraffic, Open-Meteo) serve the Turku map, the room and the FIWARE entry and are listed after. Checked against the running product on 7 Nov 2026 about 11:25Z. Fonecta gave no dataset format or sample during the event, so every file named here is ours or public.

## The five key sources at a glance
| # | Source | What it tells the chain | Where Connect would get it in production | What did not work |
|---|---|---|---|---|
| 1 | Public holidays: Nager.Date (live refresh over `data/holidays_fi_2026.json`, 38 dates) | which days are holidays, public or not | Connect's own holiday calendar per country (or the same API) | no uudenvuodenaatto, so we add it as a non-public day; movable days matched by name |
| 2 | The business's own regular hours and last year's exceptions: Yext sandbox entity SinceAI07 (live read) plus `data/furry_paw.json` (sample history) | the main proposal ("last year 9-13") and whether anything is missing | Connect's published hours and its exception-hours history per entity | the sandbox has no history, so last year is a labelled sample; Yext accepts an inverted interval (13:00 to 9:00), so we validate locally |
| 3 | The business's own website | a line with the holiday name or date plus a time or "suljettu" | the crawl Connect already does for listings | the sample site `furrypaw.example` does not resolve, so the signal returns nothing; the parser is tested on a mocked page only |
| 4 | What Google shows now: Serper places | whether the public listing disagrees with our proposal | Google Business Profile API through Connect's own publishing state | live call made on 7 Nov with the key set: for the fictional clinic it returns no hours (`{"status": "unknown"}`), so the message names Connect's published hours instead |
| 5 | Category peers: `data/peer_priors.json` | cold start: what similar businesses do on that holiday | Connect's customer base: the share of similar businesses that closed or shortened hours on each holiday | hand-made placeholder; nothing to test it against until Fonecta's data arrives; never above 0.65 confidence |

## Detail per source
### 1. Public holidays: Nager.Date
- Licence: MIT (the API is free, no key). URL: nager.date, `PublicHolidays/2026/FI`.
- How we use it: `data/holidays_fi_2026.json` bundled; a live refresh (5 s timeout) rewrites it if older than 30 days. We add flag days such as isänpäivä as `public_holiday=false`.
- Production: Connect's own holiday calendar per country, or the same API.
- Did not work: Nager.Date has no uudenvuodenaatto (New Year's Eve), so we add it as a non-public day. Moveable days (Pääsiäinen) are matched by name.

### 2. The business's own regular hours and last year's exceptions
- Licence: the customer's own data. Here: a labelled fictional sample (`data/furry_paw.json`) written by the team; the entity is Fonecta's Yext sandbox SinceAI07, whose regular hours we set on 6 Nov.
- How we use it: regular hours decide `no_change`; last year's exception on the same holiday (matched by name) is the main proposal (0.85, or 0.75 if the weekday differs).
- Production: Connect's published hours and exception-hours history (what Yext holds for the entity).
- Did not work: the sandbox has no history of its own, so last year is sample data. Yext accepts an inverted interval (13:00 to 09:00), so we validate locally.

### 3. Website opening hours
- Licence: the business's own public page; we only read a line with the holiday name or date plus a time or "suljettu".
- Production: the crawl Connect already does for listings.
- Did not work: the sample site `furrypaw.example` does not resolve, so the signal returns nothing; the parser is tested on a mocked page only.

### 4. Google Places via Serper
- Licence: Serper's terms (paid API). Google content is shown only as a status.
- How we use it: `google_now`, only with `SERPER_API_KEY`; otherwise `{"status":"unknown"}`. Google is named in a message only when hours came back.
- Production: Google Business Profile API through Connect's own publishing state.
- Did not work: the demo business is fictional, so Serper has no listing for it. The key is set and a live call on 7 Nov returned `{"status": "unknown"}`.

### 5. Category peers
- Licence: ours. `data/peer_priors.json` is hand-made (author's judgement of Finnish practice) and labelled so.
- How we use it: cold start, category by holiday: closed, short hours or regular. Never above 0.65.
- Production: Connect's own customer base, the share of similar businesses that closed or shortened hours on each holiday.
- Did not work: nothing to test it against; it is a placeholder until Fonecta's data arrives.

## Sources for the map, room and FIWARE entry
### 6. OpenStreetMap, 813 Turku businesses
- Licence: ODbL, (c) OpenStreetMap contributors. Fetched via Overpass on 6 Nov 2026, cached in `data/turku_businesses.json`. Base map tiles: OpenFreeMap.
- Production: Connect's customer list replaces it. Only 2 of 813 mention 24 Dec in opening_hours, so no business history is invented.
- Did not work: Overpass was at capacity; the loader tries 3 mirrors with backoff and falls back to 40 labelled placeholder points.

### 7. Föli SIRI vehicle monitoring and Digitraffic AIS
- Licence: CC BY 4.0 (Föli open data; Fintraffic Digitraffic). Every entity carries its `source` and `observedAt`. Used by `/aura` as Smart Data Models `Vehicle` entities, every 10 s and 20 s.
- Production: not part of Connect. It shows the broker handling live data.
- Did not work: Digitraffic needs gzip and a `Digitraffic-User` header; Föli sends no heading, so we derive it from movement.

### 8. Open-Meteo weather
- Licence: CC BY 4.0 (non-commercial free tier). `urn:ngsi-ld:WeatherObserved:turku` every 5 minutes.
- Production: not part of Connect.

## Things that did not work, in one list
- Overpass at capacity (mirrors, cache, labelled fallback).
- Nager.Date has no uudenvuodenaatto.
- Our Orion-LD build rejects `datasetId` writes after the entity is created (501), so the client deletes and re-creates the entity. Subscriptions with `q` on an object value do not match, so the router filters.
- The Yext sandbox has no publishers, so "where it shows" is an honest statement, not a live sync.
- The call lane first failed on ElevenLabs key permissions (401 missing_permissions) and on Zadarma number verification; both were fixed on 6 Nov and the call was placed and answered at 21:24Z and approved on the phone at 21:46:53Z, and placed again on 7 Nov 10:18Z and 10:23Z (`data/call_log.jsonl` on the demo host, docs/call.md).
- Serper: works, but a fictional business has no Google listing, so the Google signal is untested on a real match.

## Bonus: live sources that replaced dataset files, and what we learned
Slide 8 asks for at least one dataset file replaced by a live source. Four live sources are in the product, each with a receipt from 7 Nov 2026:

| File it replaces or avoids | Live source | Receipt | What we learned |
|---|---|---|---|
| Holiday list | Nager.Date `PublicHolidays/{year}/FI`, rewritten into `data/holidays_fi_2026.json` (38 dates, 2025 to 6.1.2027); `curl` of the API returned 200 on 7 Nov | file `source` field names the API; `kaiku/detect/holidays.py::build_cache` | the live source has no New Year's Eve and no flag days, so we add them; it needs a 5 s timeout and the bundled file as fallback to stay demo-safe |
| The clinic's hours, holiday rows, description, reviews as the owner sees them | Yext sandbox entity SinceAI07 read through the Management API for the "On Fonecta now" panel and the listing score | `GET /api/listing/furry-paw` returns entity SinceAI07 with `read_at`; `GET /api/score/furry-paw` returns a score (40, 3 of 7 checks at the time of writing; it moves) computed from it | the sandbox had no description or reviews, so the team wrote labelled samples; the sandbox has no publishers, so "where it shows" is a statement, not a syndication; the write is real and we read it back |
| 40 placeholder points on the map | OpenStreetMap via Overpass: 813 Turku businesses, `fallback: false`, fetched 6 Nov 19:15Z | `data/turku_businesses.json` (`count` 813) | Overpass is often at capacity, so the loader tries three mirrors with backoff; only 2 of 813 mention 24 Dec, so history is never invented |
| No file at all (no static sample exists for these) | Föli SIRI (buses), Digitraffic AIS (ships), Open-Meteo (weather) into the Orion-LD broker | `GET /api/aura/status` on 7 Nov 11:22Z: buses 156, ships 41, weather 1 (the numbers move) | Digitraffic needs gzip and a `Digitraffic-User` header; Föli sends no heading, so we derive it from movement |

The honest limit: the holiday history ("last year 9-13") is still a labelled sample, because the sandbox holds none. That is the one input a pilot with real Connect data would replace first.
