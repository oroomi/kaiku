# Task: /city, "Turku, one broker" (the first-sight screen for Sunday's stage and the FIWARE judge)
Owner: city builder. Branch task/city, worktree /root/hack/kaiku_wt/city. Test port 8230. Read CLAUDE.md first (non-negotiables, design, loop).
Owner's words (Dayo, 7 Nov): "something so visually appealing it blows everybody away at first sight". FIWARE must be the wow.
Timebox: 2.5 h. Commit every 20-30 min on task/city. End with RESULT line (see CLAUDE.md loop step 5).

## What it is
One full-screen page, /city. A cinematic fly-in from a black night globe down into Turku at a tilt with 3D buildings; 813 real
Turku businesses (OpenStreetMap) as glowing dots, each an NGSI-LD Store entity in our Orion-LD broker; about 100-135 Föli buses (whatever is live) and 45 AIS
ships moving, from the same broker; a weather chip. When a person in the room answers "are you open on Christmas Eve?" on their
phone (existing /join flow), the owner's answer is written to the broker, an NGSI-LD subscription fires, and THAT notification
turns the dot green with a pulse on the big screen. The dot never turns green from a poll of room_state; it turns green from the
broker notification (with a 5 s reconciliation poll of the broker read so a missed notification heals).

## Visual direction (locked from references; do not redesign)
References studied: MapLibre globe+atmosphere example; deck.gl TripsLayer demo (black base, grey 3D blocks, orange trails);
Google Earth / Mapbox globe descent (recalled); our own headless test (globe at night with a thin atmosphere rim, teal 3D blocks).
Palette = Horizon (CLAUDE.md): night #090b0d / #0c1418, teal #163746 / #2f6f8c, cyan #8fd3e8, amber #ffd27a, green #9fe0b5, white #eef6f9.
1. Opening (12 s, once per load, skip with ?intro=0, replay with key R or Space): black globe, Europe centred (center [18,58],
   zoom 1.6), thin atmosphere rim only (sky-color #0b1b24, horizon-color #163746, fog-color #090b0d, atmosphere-blend 1 to 0 by
   zoom 10-12). Hold 1.5 s while the title fades in. Then ONE flyTo to [22.2666, 60.4518], zoom 15.2, pitch 62, bearing -20,
   duration 7000, curve 1.42, easing cubic-out, essential true. On moveend: slow bearing drift 1 deg/s forever (pause on user
   interaction, resume after 8 s idle). prefers-reduced-motion: no fly, no drift, land directly.
2. Buildings: fill-extrusion layer from the openmaptiles source, source-layer building, minzoom 13, filter ['!',['has','hide_3d']],
   height coalesce(render_height, 6), base coalesce(render_min_height, 0), colour by height 0 #13303c, 20 #1f5366, 60 #2f6f8c,
   opacity .85, fill-extrusion-vertical-gradient true. Roads and water stay as in the OpenFreeMap dark style.
3. Dots (813 Store entities): two circle layers, halo (radius 6 to 18 by zoom 10 to 16, blur 1, opacity .35) and core (1.5 to 4).
   Colour by status: missing amber, known white, approved green. The dots fade in as the camera lands (circle-opacity transition
   1200 ms, set after zoom > 11), nearest the centre first if cheap, otherwise all at once.
4. Approval: an expanding ring pulse (radius 4 to 48 over 1400 ms, green, opacity .7 to 0, blur .6), the dot turns green, the
   APPROVED counter ticks, one line appears in the event list ("Subscription fired: Hugo approved Christmas Eve hours").
   Keep the pulse source under 10 features.
5. Buses: cyan arrows rotated by heading, tweened between broker reads (same approach as aura.js: prev/next positions, linear
   tween over the poll interval, setData at most 20 Hz). Ships: amber diamonds. Bus trails: the last 6 positions as a short
   fading line (one line layer, opacity by age), cheap, like the deck.gl trips look. Vehicles fade in 1 s after the dots.
6. HUD (glass, Plex Mono small caps, Inter, Newsreader): top-left strip "TURKU 19:42 | CHRISTMAS EVE IN 47 DAYS | 813 STORE
   ENTITIES | 108 BUSES | 45 SHIPS | ORION-LD LIVE" (every number from a data call; "no data" when missing; "FALLBACK" in amber
   when the broker is down). Under it, after landing, the one Newsreader sentence builds in two stages: "Christmas Eve is
   coming." then "2 of 813 businesses here have told the map their hours." (numbers from /api/city/stores). Right side, a
   narrow glass column: APPROVED <n> (count-up), the last 6 broker events. Bottom-left: attribution (OpenFreeMap, OpenMapTiles,
   OpenStreetMap, Foli, Fintraffic, Open-Meteo CC BY 4.0) always visible. ?room=1 adds the QR panel (image /api/room/qr.svg,
   "Scan. Take over a business. Tap Approve.") bottom-right. ?embed=1 hides the site header (is_embed) and the voice orb.
   "FOR THE JUDGE" link in the HUD opens a drawer with the curl line and one live Store entity from /api/city/judge.
7. Phone width (390): the HUD collapses to the strip and the counter; the map still runs; no horizontal scroll.
8. Performance: pixelRatio capped at 1.5, antialias false, setData <= 20 Hz, no per-frame DOM work. Test at 1920x1080.
MapLibre 5.9.0 is vendored at static/vendor/maplibre5/ (globe needs 5.x; only /city uses it; /aura and /map stay on 4.7.1).
Style: fetch https://tiles.openfreemap.org/styles/dark at runtime, set style.projection = {type:'globe'} and style.sky BEFORE
creating the map (setProjection before style.load errors), add the extrusion layer on style.load. If the fetch fails use the
bundled copy static/city/dark_style.json. Keep the OpenFreeMap glyphs URL.

## Data path (this is the FIWARE integration; it must be real and visible)
- kaiku/city/seed.py: the 813 businesses in data/turku_businesses.json -> NGSI-LD Store entities, id urn:ngsi-ld:Store:<osm id>
  (e.g. urn:ngsi-ld:Store:osm-n297492710), type Store, Smart Data Models dataModel.PointOfInterest context exactly as
  kaiku/broker/models.py does for Furry Paw (reuse its constants and helpers; never redefine). Attributes: name, location
  (GeoProperty Point [lon, lat]), category, address (PostalAddress streetAddress, addressLocality Turku), url (if website),
  openingHoursSpecification only if cheap, source ("OpenStreetMap contributors, ODbL"), and holidayHoursStatus
  {date: "2026-12-24", status: "known"|"missing"} (known = holiday_hours_found). Batch upsert via
  POST /ngsi-ld/v1/entityOperations/upsert?options=update in chunks of 100 (the pattern in kaiku/aura/feeder.py upsert(); measured
  20-45 ms per 115 entities on this build). Idempotent. Run at app lifespan start when the broker is alive (never block startup,
  never raise), on POST /api/reset, and by hand: python -m kaiku.city.seed. Log the count and ms.
- kaiku/city/router.py: GET /city (template city.html, extends base.html). GET /api/city/stores: read Orion
  (GET /entities?type=Store&idPattern=^urn:ngsi-ld:Store:osm-&limit=1000, Link header with the SDM context, attrs
  name,location,category,holidayHoursStatus,holidayHours) -> compact rows {id, n, c, lon, lat, s, a?} and counts; "source":
  "orion-ld". If the broker is down: rows from kaiku.map.room.snapshot() with "source": "fallback" (the page shows FALLBACK in
  amber). GET /api/city/vehicles: reuse kaiku.aura.router.read_broker() if importable (buses, ships, weather). GET /api/city/stream
  (SSE): "hello" with recent events, "store" events pushed from notifications, "positions" brief every 5 s (reuse aura's _brief
  if importable, else your own). GET /api/city/judge: {curl: <the exact curl for entities?type=Store&limit=2 with the Link
  header>, entity: one live Store entity read that way, broker_up}.
- Subscription: on startup (lifespan hook like broker/subs.py ensure_subscriptions, idempotent by subscriptionName
  "kaiku-city-store-status"): entities type Store, watchedAttributes [holidayHoursStatus], notification endpoint
  {PUBLIC_URL}/city/notify (format normalized), attrs [holidayHoursStatus, name, location]. IMPORTANT: if a subscription with
  that name exists but its endpoint URL differs (a test server on 8230 created it), PATCH or delete+recreate it so production
  (https://kaiku.hankintaviikko.fi) gets its own endpoint back. q on a key inside an object value is NOT evaluated on this
  Orion build: filter status == "approved" in the handler. POST /city/notify: for each entity with status approved push
  {id, name, lon, lat, status, ts} to the SSE queues, emit kaiku.events Event(step="broker", title_en="Subscription fired:
  <name> approved Christmas Eve hours", title_fi="Tilaus laukesi: <name> hyvaksyi jouluaaton aukioloajat", detail {...,
  source: "city"}), dedupe per (id, observedAt) for 5 s. Return 204.
- Room hook (small, surgical edit in kaiku/map/router.py answer(), after room.record): write the owner's answer to the broker
  through kaiku.broker.get_broker(): set_default(eid, "holidayHours", {"date": room.HOLIDAY, "hours": <parsed: list of
  {start,end} | "closed" | "regular">}) and a plain PATCH of holidayHoursStatus = {"date": room.HOLIDAY, "status": "approved",
  "via": "room"} (add a small set_status(eid, attr, value) to kaiku/broker/client.py and fallback.py if none fits; the fallback
  must evaluate its subscriptions on that write like it does for others). Wrap in try/except: the room answer must succeed and
  return even if the broker is down; log "broker write skipped". The existing decide/apply events stay.
- Never write to urn:ngsi-ld:Store:furry-paw. Never touch Yext. Room answers are demo data (room.NOTE) and stay labelled so.

## Wiring
- kaiku/app.py includes kaiku.<module>.router automatically (try/except ImportError); add kaiku/city/__init__.py and
  kaiku/city/router.py with router = APIRouter(). For the lifespan seeding + subscription, expose kaiku.city.startup() and call
  it from app.py lifespan inside try/except (one line each; the app must boot without the broker).
- One-line additions: fiware.html section 4 gets a link "Open the city twin (/city)"; base.html nav gets "City" after Map.
- docs/city.md: what it does, data path, the subscription, what did not work. DISCLOSURE.md: MapLibre 5.9.0 vendored (BSD-3),
  OpenFreeMap style copy (attribution).

## Checks (write first)
- tests/test_city.py with a fake broker (see how tests/test_fiware_page.py and tests/test_broker.py fake it): seed builds 813
  entities with id/type/location/holidayHoursStatus and the SDM context; /api/city/stores returns 813 rows and counts; a POST
  /city/notify with one approved Store pushes a "store" SSE event and emits a broker Event; POST /api/room/answer (with the
  cookie from GET /join) writes holidayHoursStatus approved to the fake broker and still returns ok when the broker raises.
- Run the server: cd /root/hack/kaiku_wt/city && PUBLIC_URL=http://127.0.0.1:8230 KAIKU_NO_CALL=1 KAIKU_BROKER_URL=http://127.0.0.1:1026
  /root/hack/kaiku/.venv/bin/uvicorn kaiku.app:app --host 127.0.0.1 --port 8230   (no .env in this worktree by design: no secrets,
  outbound silent). The shared Orion-LD on 1026 is the real one; seeding Store entities there is intended (same ids production
  will use). Stop with fuser -k 8230/tcp, never pkill -f.
- Screenshots: /root/hack/bin/shot.py http://127.0.0.1:8230/city?intro=0 --name city --out /root/hack/shots/city --wait 12000 and
  the same with ?intro=0&room=1; READ the PNGs (1440 and 390). Headless WebGL works with chromium args
  --use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader (shot.py may need no change; if the map is black, add them).
- Live proof: curl the judge line against 127.0.0.1:1026 and paste 1 entity into docs/city.md. Then: GET /join on 8230 with a
  cookie jar, POST /api/room/answer {business_id, answer: "10-14"}, and show in the server log that /city/notify was hit by Orion
  and the SSE emitted "store". If Orion never calls back, say so in the RESULT (do not fake the green).
- Video: bin/record_city.py (Playwright, 1920x1080, chromium args above, record_video_dir, then ffmpeg -c:v libx264 -crf 23 -pix_fmt
  yuv420p to /root/hack/shots/city_demo.mp4, under 25 MB): open /city?room=1 on 8230, let the fly-in play (12 s), idle 6 s, then
  8 room answers through the API 2 s apart (each a new cookie jar: GET /join, POST answer), 10 s more, stop. Write the path in
  the RESULT line. If headless WebGL is too slow for smooth video (under 15 fps), record at 1280x720 and say so.

## What not to do
- No new fonts, no purple, no emoji, no "Welcome". No fabricated numbers. No code copied from kompassi/jx2026/mock html.
- Do not edit /aura, /map, /room pages or map.js/aura.js (read them as words only). Do not change timers, contact, Yext, voice.
- Do not touch /root/hack/kaiku (the live checkout) or its .env. Do not restart hack-kaiku.
