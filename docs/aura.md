# Aura: Turku live in one broker (FIWARE entry)

Live Föli buses, AIS ships and the weather become NGSI-LD entities in our Orion-LD broker; `/aura` shows them moving; a person
types "tell me when a bus comes within 300 m of Kauppatori", the agent PROPOSES a geoQ subscription, one tap creates it, and the
firing appears live. The page reads the broker, not the feeds.
## Feeds (all CC BY 4.0; source labelled on every entity in `source`, with `observedAt`)
Föli `data.foli.fi/siri/vm` every 10 s (~115 buses) | Fintraffic Digitraffic AIS (30 km around 60.45,22.2; needs gzip and a
`Digitraffic-User` header; names from `/vessels`, cached 1 h) every 20 s (~45 ships) | Open-Meteo every 5 min.
## Entities (Smart Data Models Transportation/Vehicle; checked against its schema.json: required id, type, vehicleType, category, location)
Each entity carries `@context` [SDM Transportation context, small Aura vocabulary `themishakingroup.com/aura/ns#`], sent as
`application/ld+json`. Attribute mapping (units as the schema defines them):
- Bus `urn:ngsi-ld:Vehicle:foli:<vehicleref>`: vehicleType `bus`; category `["public","tracked"]`; location Point [lon,lat];
  speed km/h (unitCode KMH, from two consecutive positions, -1 = unknown); heading degrees 0..359 (DD; Föli sends none, derived
  from movement; **-1 when speed is 0**); name; source (+ observedAt on location/speed/heading).
- Ship `urn:ngsi-ld:Vehicle:ais:<mmsi>`: vehicleType `vessel` (the SDM enum has vessel, cargoVessel, passengerVessel and more;
  we use the generic one); category `["tracked"]` (AIS transponder; we do not claim public or private); speed = AIS knots x 1.852
  in km/h (KMH; 102.3 kn "n/a" becomes -1); heading = true heading, else course over ground (-1 at speed 0); name from Digitraffic.
- Custom (Aura vocabulary, expand to `.../aura/ns#x`): lineRef, destination, delay (s, SEC), nextStop, mmsi.
- `urn:ngsi-ld:WeatherObserved:turku`: temperature (CEL), windSpeed (m/s, MTS), precipitation (MMT), weatherType, dateObserved.
Orion-LD stores a one-element array as a scalar (`"tracked"`); in JSON-LD that is the same value.
## For the judge: read the entities
`curl -s -H 'Accept: application/ld+json' -H 'Link: <https://raw.githubusercontent.com/smart-data-models/dataModel.Transportation/master/context.jsonld>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"' 'http://127.0.0.1:1026/ngsi-ld/v1/entities?type=Vehicle&limit=2'`
The Link header is REQUIRED: without it Orion-LD cannot resolve `Vehicle` and returns `[]`. `GET /api/aura/judge` returns this
curl line and one live entity read exactly that way; `GET /api/aura/context` returns the context we send.
## Write path (measured on this Orion-LD build)
`POST /ngsi-ld/v1/entityOperations/upsert?options=update` works: 201 on first write, 204 afterwards, no datasetId. Batch of
~115 entities: 20-45 ms. The POST/PATCH fallback is coded but was never needed. Stale entities: every minute the feeder lists ITS OWN entities (ids `Vehicle:foli:*` and `Vehicle:ais:*`) and batch-deletes those whose
location.observedAt is over 10 min old (also orphans from earlier runs); the page itself hides buses older than 120 s and ships older than 300 s.
`data/aura_cache/latest.json` is the fallback cache ("fallback cache" in the panel).
## Subscription flow
`POST /api/aura/ask` -> Claude Sonnet 5.5 (`claude-sonnet-5-5`, one tool `propose_subscription`, tool_choice auto, effort low) ->
pending proposal -> `POST /api/aura/subscriptions/{id}/approve` creates on Orion: entities Vehicle, `q` vehicleType=="bus",
`geoQ` Point + `near;maxDistance==300`, watchedAttributes [location], throttling 20 s, notification to
`$AURA_NOTIFY_BASE|$PUBLIC_URL|127.0.0.1:8210` + `/aura/notify` (204). The notify route emits an Event (step broker) and pushes to SSE.
Proof (real run 6 Nov): `"Tilaus laukesi: linja 20 on 94 m Kauppatorista"` / `"Subscription fired: line 20 is 94 m from Kauppatori"`; Orion timesSent 14 after 5 min.
## What did not work / limits
`strict: true` is rejected for this schema (minItems), so input is validated in code. One delivery can carry several vehicles: we show the nearest and count the rest (+N). Orion on the
public URL reaches the main app on 8210, not a test port: set `AURA_NOTIFY_BASE` when testing elsewhere. The agent always fills explanation_fi (Finnish) and explanation_en (English); a wrong-language field is swapped, translated with one extra
model call, or replaced by a template. Core `app.js` throws on
pages without the home DOM, so aura.html carries a hidden stub block (remove when core guards it).
## Run
`python3 -m kaiku.aura.feeder` and the main app; open `/aura`. `pytest -q tests/test_aura.py` (`KAIKU_LIVE=1` adds a broker test).
