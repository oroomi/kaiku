# /city: Turku, one broker

The first-sight screen for the stage and the FIWARE judge. A fly-in from a night globe into central Turku at a tilt with 3D
buildings; 813 real Turku businesses (OpenStreetMap) as glowing dots, each an NGSI-LD `Store` entity in our Orion-LD; the
Föli buses and AIS ships moving, read from the same broker; a weather chip. When someone in the room answers "are you open on
Christmas Eve?" on their phone (`/join`), the answer is written to the broker, an NGSI-LD subscription fires, and that
notification (not a poll) turns the dot green with a pulse.

URLs: `/city` (full intro, then act two on its own), `/city?intro=0` (land directly), `?room=1` (QR panel), `?embed=1` (no header, no voice orb),
`?hold=1` (wait for `window.__city.start()`, used by the recorder). Keys: R or Space replays the fly-in, H toggles the harbour view.

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
   max 180 m in 11 s on 7 Nov), draws buses as cyan arrows rotated by heading with a 10-position trail tapering 3 px to 0.5 px, ships as white diamonds with a cyan halo and a 3-position white wake (act two, below).
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
Descent tint: land is a faint Horizon teal above near-black water from the globe down to zoom 13 (then the buildings take over) and the OpenFreeMap Natural Earth relief raster shows on the globe at low opacity, fading out by zoom 8, so the fly-in never passes through a black frame (first cut had ~3 s of 80 % black pixels at 2-5 s).
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

## Act two (8 Nov 2026, after Dayo watched cut 3: "the zooming kinda went blank... the view doesn't really show the buses and the ships very well")
- No blank descent. `start()` (the intro) first pre-warms: an opaque night cover (#090b0d) with the title on top hides the map
  while the camera jumps through zoom 2, 4, 6, 8, 10, 12, 13.5, 15.2 (pitch and bearing scaled to match the flight), waiting
  at each for `map.areTilesLoaded()` (at least 200 ms, at most 1.5 s per step). Then jumpTo the globe, a 300 ms fade, the
  visible 7 s flight over tiles that are already in the cache. `start()` returns a promise that resolves when the pre-warm is
  done; the recorder drives the virtual clock until it resolves and records no frame before (measured on the burst box:
  5.4 s wall, 39-44 clock steps). R replays without a second pre-warm.
- The beacon (`city-beacon` halo, 35 px radius blurred, opacity breathing 0.35-0.8 over 2.2 s; `city-beacon-core` 2 px): a
  cyan point at Turku from the first globe frame, fading out between zoom 11 and 12.5. The title moved to 56 % from the top
  so it no longer covers the beacon on the globe.
- The glow (`city-glow`, MapLibre heatmap on the same `stores` source, zoom 5-12.5): amber ramp to transparent, radius 8 px
  at zoom 6 to 40 px at zoom 11, low intensity, opacity 0 by zoom 12, so the city arrives as warm light that resolves into
  the dots (the dot layers are unchanged).
- Land tint lifted to stay above luminance 20 down to street zoom (#0f1c23 at zoom 12, #0b1216 at 15).
- Buses: trail 10 positions (was 6), width 3 px newest to 0.5 px oldest at zoom 15, arrows 1.3x. Ships: white (#eef6f9)
  diamonds with a cyan halo, 1.4x, and a 3-position white wake (2 px). Positions are only what the broker gives; a ship that
  has not moved has no wake.
- The harbour move: `window.__city.harbour()`, the H key, and on the live page automatically 25 s after landing when nobody
  has touched the map (back to the centre 20 s after arriving, again every 60 s; a touch postpones it).
  `easeTo({center: [22.236, 60.4445], zoom: 13.45, pitch: 56, bearing: 56, duration: 9000, easeInOutCubic})`, then the
  1 deg/s drift. The brief's start value (22.218, 60.438, zoom 13.7, bearing -50) looked out to sea: no city in frame.
  Bearing 56 looks up the Aura from the port, so the ships sit in the lower half as white diamonds and the centre's dots
  glow in the upper third (checked from 1280x720 stills: 18 ships and 23 buses inside the view).
- Film timeline (frames mode, virtual s): 0-1.5 title on the globe, 1.5-8.5 flight, 8.5-14 landing + sentence, 14-30 the 8
  room answers 2 s apart, 30-39 harbour move, 39-48 hold. `--mode realtime` calls `harbour()` after the answers too.

## What did not work / known edges
- `q` on `holidayHoursStatus.status` is not evaluated by this Orion-LD build; the handler filters.
- The existing `kaiku-holiday-hours-resolved` subscription (broker module) watches `holidayHours` on every Store, so a room
  answer also produces its "hours resolved" broker event in the event feed. Left as is (not our module).
- Seeding the 813 Stores also triggers the two broker-module subscriptions once per created entity; their handler ignores
  `seed: true` values, so nothing is shown, but it is 813 HTTP deliveries on first seed.
- A test server (PUBLIC_URL http://127.0.0.1:82xx) creates its own subscription `kaiku-city-store-status-<port>`; production's plain-named one is never touched (added after the 7 Nov film: a production restart took the shared name mid-film and 7 of 8 approvals never reached the test page). Stop a test server with `fuser -k <port>/tcp` and delete its subscription afterwards.
