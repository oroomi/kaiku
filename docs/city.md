# /city: Turku, one broker

The first-sight screen for the stage and the FIWARE judge. A fly-in from a night globe into central Turku at a tilt with 3D
buildings; 813 real Turku businesses (OpenStreetMap) as glowing dots, each an NGSI-LD `Store` entity in our Orion-LD; the
Föli buses and AIS ships moving, read from the same broker; a weather chip. When someone in the room answers "are you open on
Christmas Eve?" on their phone (`/join`), the answer is written to the broker, an NGSI-LD subscription fires, and that
notification (not a poll) turns the dot green with a pulse.

URLs: `/city` (full intro), `/city?intro=0` (land directly), `?room=1` (QR panel), `?embed=1` (no header, no voice orb),
`?hold=1` (wait for `window.__city.start()`, used by the recorder). Keys: R or Space replays the fly-in.

## Data path (all real, all through Orion-LD)
1. Seed, `kaiku/city/seed.py`: `data/turku_businesses.json` (OpenStreetMap contributors, ODbL; 813 businesses within 1.5 km
   of the centre) -> `Store` entities `urn:ngsi-ld:Store:osm-<n|w><osm id>` built with `kaiku.broker.models.business_to_entity`
   (Smart Data Models dataModel.PointOfInterest context in the Link header): `name`, `location` (GeoProperty Point),
   `category`, `address` (PostalAddress, Turku), `url` when OSM has a website, `source`, and
   `holidayHoursStatus {date: 2026-12-24, status: known|missing, seed: true}` (`known` = public data had the holiday hours: 2
   of 813). `openingHoursSpecification` is left out: OSM `opening_hours` is free text and we do not parse it.
   Batch `POST /ngsi-ld/v1/entityOperations/upsert?options=update`, chunks of 100. Idempotent: start-up only creates missing
   entities (first run 813 in 2053 ms, re-run 0 written in 546 ms on 7 Nov); `POST /api/reset` and
   `python -m kaiku.city.seed --force` replace only the Stores whose status is no longer the seed value. `seed: true` tells
   every handler (including `/broker/notify`) that the start state is not a decision. Never touches `Store:furry-paw`.
2. Read, `GET /api/city/stores`: `GET /entities?type=Store&idPattern=^urn:ngsi-ld:Store:osm-&limit=1000&attrs=...` ->
   compact rows `{id, n, c, lon, lat, s: missing|known|approved, a?}` + counts, `source: "orion-ld"`. Broker down: rows from
   the room snapshot with `source: "fallback"` and the HUD says FALLBACK in amber. `?only=approved` is the 5 s reconciliation read.
3. Vehicles, `GET /api/city/vehicles` and the SSE `positions` brief every 5 s: `kaiku.aura.router.read_broker()` (Vehicle and
   WeatherObserved entities kept live in the same Orion-LD by the Aura feeder). The page tweens each vehicle between two broker
   reads (linear, over the measured read interval, at most 5 s; a jump over 300 m between reads snaps instead, measured
   max 180 m in 11 s on 7 Nov), draws buses as cyan arrows rotated by heading with a 6-position fading trail, ships as amber diamonds.
4. The subscription, `ensure_subscription()` at start-up: `subscriptionName kaiku-city-store-status`, entities type Store,
   watchedAttributes `[holidayHoursStatus]`, notification `{PUBLIC_URL}/city/notify`, normalized, attributes
   `[holidayHoursStatus, name, location]`. If a subscription with that name exists with another endpoint (a test server made
   it) it is deleted and recreated, so production gets its endpoint back on its next start.
5. The room hook (`kaiku/map/router.py` answer(), after the existing decide/apply events): `write_answer()` sets the
   `holidayHours` default instance `{date, hours: [{start,end}] | "closed" | "regular"}` and PATCHes
   `holidayHoursStatus {date, status: approved, via: room}` (new `set_status()` in broker client, fallback and AutoBroker; the
   fallback evaluates its subscriptions on that write). In try/except: the room answer returns ok when the broker is down and
   the log says "broker write skipped".
6. The notification, `POST /city/notify`: Orion-LD does not evaluate `q` on a key inside an object value, so the handler keeps
   only `status == approved`; dedupe per (id, observedAt) for 5 s; pushes `{id, name, lon, lat, status, ts}` as SSE `store`
   on `/api/city/stream` and emits a `broker` Event "Subscription fired: <name> approved Christmas Eve hours"
   (`detail.source = "city"`). Returns 204.
7. The page turns the dot green on the SSE `store` event (pulse ring 4 to 48 px over 1400 ms, the APPROVED counter ticks,
   one line in the event list). A Store seen approved in two consecutive 5 s broker reads without a notification is healed
   green quietly (no "Subscription fired" line, because none fired).

## For the judge
```
curl -s -H 'Accept: application/ld+json' -H 'Link: <https://raw.githubusercontent.com/smart-data-models/dataModel.PointOfInterest/master/context.jsonld>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"' 'http://127.0.0.1:1026/ngsi-ld/v1/entities?type=Store&limit=2'
```
One live entity read that way (7 Nov 2026, 17:46Z):
```json
{
  "@context": [
    "https://raw.githubusercontent.com/smart-data-models/dataModel.PointOfInterest/master/context.jsonld",
    "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.9.jsonld"
  ],
  "id": "urn:ngsi-ld:Store:osm-n297492710",
  "type": "Store",
  "name": {
    "type": "Property",
    "value": "Hugo"
  },
  "address": {
    "type": "Property",
    "value": {
      "type": "PostalAddress",
      "streetAddress": "Stålarminkatu 2",
      "addressLocality": "Turku",
      "addressCountry": "FI"
    }
  },
  "location": {
    "type": "GeoProperty",
    "value": {
      "type": "Point",
      "coordinates": [
        22.259131,
        60.439035
      ]
    }
  },
  "category": {
    "type": "Property",
    "value": "pub"
  },
  "url": {
    "type": "Property",
    "value": "https://www.pippurimylly.fi/hugo"
  },
  "holidayHoursStatus": {
    "type": "Property",
    "value": {
      "date": "2026-12-24",
      "status": "missing",
      "seed": true
    },
    "observedAt": "2026-11-07T17:31:19.000Z"
  },
  "source": {
    "type": "Property",
    "value": "OpenStreetMap contributors, ODbL"
  }
}
```

## Live proof (7 Nov 2026, test server on 8230, the shared Orion-LD on 1026)
`GET /join` with a cookie jar, `POST /api/room/answer {"business_id": "osm-n6784950719", "answer": "10-14"}` ->
`{"ok":true,...}`. Server log, Orion-LD calling us back:
```
city notify: urn:ngsi-ld:Store:osm-n6784950719 approved (subscription urn:ngsi-ld:subscription:c79147ce-dad1-11f1-8cec-3ce8d4bd1ac2), pushing SSE store to 1 client(s)
INFO:     127.0.0.1:35896 - "POST /city/notify?subscriptionId=urn:ngsi-ld:subscription:c79147ce-dad1-11f1-8cec-3ce8d4bd1ac2 HTTP/1.1" 204 No Content
```
and the SSE stream:
```
event: store
data: {"id": "osm-n6784950719", "name": "Café Eino", "lon": 22.266522, "lat": 60.451513, "status": "approved", "ts": "2026-11-07T17:36:52.000Z", "title_en": "Subscription fired: Café Eino approved Christmas Eve hours", ...}
```

## Design
Horizon palette on a black base: buildings extruded from the OpenMapTiles `building` layer (height colour #13303c / #1f5366 /
#2f6f8c), dots amber = missing, white = known, green = approved (larger). Globe with a thin atmosphere rim (sky #0b1b24,
horizon #163746, fog #090b0d, atmosphere fading out between zoom 10 and 12). Style fetched from OpenFreeMap at runtime, the
bundled copy if that fails. pixelRatio capped at 1.5, antialias off, vehicle setData at most 20 Hz, trails 4 Hz, pulses at
most 10 features. "Christmas Eve in N days" uses the real Helsinki date (the vehicles are live, so the city runs on real time,
not the chain's time-travel clock).

## Video
`bin/record_city.py` -> `/root/hack/shots/city_demo.mp4` (1920x1080, 20 fps): fly-in, idle, 8 room answers through the API
2 s apart (each a new cookie jar), 10 s more. Headless SwiftShader WebGL measured 0.8 fps at 1920x1080 and 3.8 fps at
1280x720 on this 2-core VPS (load 8), so a realtime capture was a slideshow. The default `--mode frames` runs the page on
Playwright's virtual clock and screenshots every 50 ms of page time. Every frame is the real page and the answers,
notifications and SSE pushes are real; vehicle motion is time-compressed because the broker positions refresh in wall time
while frames render. `--mode realtime` uses `record_video_dir` for a machine with a GPU.
Result on 7 Nov: 881 frames, 44.05 s, 20 fps, 1920x1080, 8 of 8 answers ok, counter 8, 8 `/city/notify` calls from Orion-LD in
the server log, no page errors; render wall time 48 min. The first encode (crf 23) was 53 MB, so the file was re-encoded at
crf 31 to 9.4 MB (the recorder now encodes at crf 30). The HUD clock and the event times differ by a few minutes in the film:
event times are the broker's observedAt (wall time), the clock runs on page time.
After the test the `kaiku-city-store-status` subscription (pointing at 8230) was deleted and the Stores reset to their seed
state, so production creates its own subscription on its next start.

## What did not work / known edges
- `q` on `holidayHoursStatus.status` is not evaluated by this Orion-LD build; the handler filters.
- The existing `kaiku-holiday-hours-resolved` subscription (broker module) watches `holidayHours` on every Store, so a room
  answer also produces its "hours resolved" broker event in the event feed. Left as is (not our module).
- Seeding the 813 Stores also triggers the two broker-module subscriptions once per created entity; their handler ignores
  `seed: true` values, so nothing is shown, but it is 813 HTTP deliveries on first seed.
- Test servers re-point the `kaiku-city-store-status` subscription to their own URL; production takes it back on start.
