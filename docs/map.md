# Map, room and join (task 10)

Code: `kaiku/map/{osm,room,router,loadtest}.py`, templates `map.html room.html join.html`, `static/map.js map.css`, `static/vendor/maplibre/` (maplibre-gl 4.7.1, BSD-3, see VENDORED.md).
Needs the `qrcode` python package (`pip install qrcode`); requirements.txt is core's file, so add `qrcode==8.2` there.

## Data
- Businesses: OpenStreetMap contributors (ODbL), Overpass, 1.5 km around 60.4518, 22.2666, named amenity/shop/leisure/healthcare tags. Cached in `data/turku_businesses.json` (fetched_at, mirror, count). 813 real businesses, fetched from overpass-api.de on 6 Nov 2026. Rebuild: `python -m kaiku.map.osm` (3 mirrors, 60 s, 3 retries with backoff). If all fail, 40 points on real street lines named "Kahvila 12" are written, labelled "fictional placeholder" in the file and in the legend.
- Base map: OpenFreeMap positron style, recoloured dark in the browser (needs internet for tiles; without it the dots still show on a dark background).
- Holiday hours: no business has them in open data. A business counts as "known" only if its OSM opening_hours text mentions Dec 24 (2 of 813); those are never assigned to a visitor. Last year's hours are never invented: the suggest engine runs cold start and gives the question "Oletteko auki jouluaattona 24.12.?".
- Answers are demo data from the room. They are NOT written to Yext (the sandbox has one entity); the apply event says so.

## Room flow
`/room` (big screen: QR to PUBLIC_URL/join, live map in an iframe) > phone opens `/join` (cookie `kaiku_room`, sticky round robin, businesses nearest the centre first) > chip or free text > `POST /api/room/answer` > state in `data/room_state.json` (atomic write) > Events `decide` then `apply` (detail.map=true) on `/api/events` > `map.js` sets the feature state of that one dot (no layer re-render), updates counts and the latest list, pulses cyan.
`GET /api/room/reset` clears all answers (run before the live pitch); `GET /api/room/state` returns counts, businesses, latest. `KAIKU_DATA_DIR` overrides the data directory (tests).

## Load test
`python -m kaiku.map.loadtest http://127.0.0.1:8213 20`: 20 parallel answers, time from POST to the SSE apply event: max 381 ms, median 199 ms (serialised by the SQLite event write). A real browser on /map showed 20 answered immediately after the burst.

## Notes
`static/app.js` (core) throws `getTotalLength of null` on pages without the home arc; harmless here.
