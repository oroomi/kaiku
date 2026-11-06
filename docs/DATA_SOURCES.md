# Data sources

Eight sources, five of them in the holiday chain. For each: licence, how we use it, where Connect would get it in production, what did not work. Live: Nager.Date (refresh), Föli, Digitraffic, Open-Meteo, OSM (cached at build time). Files: the business's own hours and last-year exceptions (sample data for Furry Paw), peer priors (hand-made).

## The five key sources for the holiday chain
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
- Did not work: no key on the build box and the demo business is fictional, so the status is unknown and untested live.

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
- ElevenLabs key permissions: the key we have lacks the convai permissions (401 missing_permissions), so the Conversational AI agent for the call lane could not be created; speech to text and text to speech work.
- Zadarma phone number verification: the account needed a login and verification step; no number was bought by 6 Nov.
- Serper: no key, Google signal unverified.

## Bonus: a live source replacing a dataset file
Holidays refresh live from Nager.Date over the bundled file. Learned: the bundled file is the safety net, and the live source needed an explicit timeout and a fallback to stay demo-safe. The map's businesses are a cached live Overpass fetch.
