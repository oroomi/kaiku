# Aura: Turku live in one broker (FIWARE entry)

Live Föli buses, AIS ships and the weather become NGSI-LD entities in our Orion-LD broker; `/aura` shows them moving; a person
types "tell me when a bus comes within 300 m of Kauppatori", the agent PROPOSES a geoQ subscription, one tap creates it, and the
firing appears live. The page reads the broker, not the feeds.

## Feeds (all CC BY 4.0; source labelled on every entity in `source`, with `observedAt`)
Föli `data.foli.fi/siri/vm` every 10 s (~115 buses) | Fintraffic Digitraffic AIS (30 km around 60.45,22.2; needs gzip and a
`Digitraffic-User` header; names from `/vessels`, cached 1 h) every 20 s (~45 ships) | Open-Meteo every 5 min.
Optional: `data/turku_businesses.json` shows as small dots if present.

## Entities (Smart Data Models, `@context` via the Link header)
- `urn:ngsi-ld:Vehicle:foli:<vehicleref>`: Vehicle, vehicleType bus, location, heading (Föli gives none: derived from two
  consecutive positions), custom lineRef, destination, delay, nextStop.
- `urn:ngsi-ld:Vehicle:ais:<mmsi>`: Smart Data Models has no Vessel/Ship type in Transportation, so ships are Vehicle with
  vehicleType ship, heading, speed (m/s), mmsi.
- `urn:ngsi-ld:WeatherObserved:turku`: temperature, windSpeed (m/s), precipitation, weatherType, dateObserved.
Extra attributes fall back to Orion's default vocabulary and read back with the same names.

## Write path (measured on this Orion-LD build)
`POST /ngsi-ld/v1/entityOperations/upsert?options=update` works: 201 on first write, 204 afterwards, no datasetId. Batch of
~115 entities: 20-45 ms. The POST/PATCH fallback is coded but was never needed. Entities unseen for 10 min are batch-deleted.
`data/aura_cache/latest.json` is the fallback cache; the panel then says "fallback cache".

## Subscription flow
`POST /api/aura/ask` -> Claude Sonnet 5.5 (`claude-sonnet-5-5`, one tool `propose_subscription`, tool_choice auto, effort low) ->
pending proposal -> `POST /api/aura/subscriptions/{id}/approve` creates on Orion: entities Vehicle, `q` vehicleType=="bus",
`geoQ` Point + `near;maxDistance==300`, watchedAttributes [location], throttling 20 s, notification to
`$AURA_NOTIFY_BASE|$PUBLIC_URL|127.0.0.1:8210` + `/aura/notify` (204). The notify route emits an Event (step broker) and pushes to SSE.
Proof (real run 6 Nov 19:22 EET, "tell me when a bus is within 300 m of Kauppatori"; "Kerro kun laiva on alle 2 km satamasta"):
`{"title_fi":"Tilaus laukesi: linja 20 on 94 m Kauppatorista","title_en":"Subscription fired: line 20 is 94 m from Kauppatori","subscription":"urn:ngsi-ld:Subscription:aura-f0d621d30c","distance_m":94}` and
`"Tilaus laukesi: alus MERILUOTO on 356 m Turun satamasta"`. After 5 minutes the Orion subscription showed timesSent 14.

## What did not work / limits
`strict: true` on the tool is rejected by the API for this schema (minItems), so the input is validated in code. Server-side
fallbacks were not enabled. One delivery can carry several vehicles: we show the nearest and count the rest (+N). Orion on the
public URL reaches the main app on 8210, not a test port: set `AURA_NOTIFY_BASE` when testing elsewhere. Core `app.js` throws on
pages without the home DOM, so aura.html carries a hidden stub block (remove when core guards it).

## Run
`python3 -m kaiku.aura.feeder` (unit `kaiku/aura/hack-kaiku-aura.service`, not installed) and the main app; open `/aura`.
`pytest -q tests/test_aura.py` (`KAIKU_LIVE=1` adds a broker test).
