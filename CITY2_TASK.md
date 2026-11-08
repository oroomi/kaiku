# /city act two: no blank descent, a beacon to fly to, buses and ships you can see, a harbour move

Worktree: /root/hack/kaiku_wt/city2, branch task/city2 (from origin/main b5ae73c). Test port 8231. Timebox 90 min.
Read first: CLAUDE.md, docs/city.md, kaiku/web/static/city.js (396 lines), kaiku/web/static/city.css, bin/record_city.py.
Dayo watched cut 3 of /root/hack/shots/city_demo.mp4 (8 Nov 02:20 EET) and said: "the zooming kinda went blank, instead of
really looking like it was zoomed... and the view doesn't really show the buses and the ships very well". Fix exactly that.
Keep everything that works: the data path, the subscription, the room hook, the HUD, the sentence, the judge drawer, tests.

## 1. The descent never looks blank
Cause: during the 7 s flyTo the camera crosses zoom 4 to 11 in about 2 s; vector tiles for those zooms arrive after the
camera has passed, so the frames show tinted land with no detail (worse under the recorder's virtual clock).
Do all three:
a) Pre-warm. While the title card ("Turku, one broker") is up and before the visible flight, run the same flight once with
   the map hidden under an opaque cover (the cover is the night colour #090b0d with the title on top; the map canvas keeps
   rendering so tiles load), or step the camera through 8 intermediate zooms (2, 4, 6, 8, 10, 12, 13.5, 15.2 at the matching
   pitch) with `map.jumpTo` and wait for `map.areTilesLoaded()` at each (cap 1.5 s per step). Then jumpTo EUROPE, drop the
   cover with a 300 ms fade and play the visible flight. Under the recorder (`?hold=1`) the pre-warm must finish before
   `window.__city.start()` returns, so the recorder's frames never include a loading tile.
b) A beacon to fly to. From the first globe frame, a cyan (#8fd3e8) point at Turku: a 4 px core with a 70 px soft halo that
   breathes (opacity 0.35 to 0.8, 2.2 s period), drawn as a GeoJSON circle layer with zoom-interpolated radius so it stays
   about the same screen size from zoom 1.6 to 11, then fades out between zoom 11 and 12.5 as the real dots take over.
c) The stores as one glow before they are dots. Between zoom 6 and 11.5 draw the 813 stores as a heatmap layer (MapLibre
   `heatmap`, amber #ffd27a ramp to transparent, radius interpolated 8 px at zoom 6 to 40 px at zoom 11, intensity low,
   opacity fading to 0 by zoom 12) over the same source, so the city appears as a warm glow that resolves into the dots
   (the current dots layer stays as is, minzoom unchanged). The viewer watches light grow, not tiles load.

## 2. Buses and ships you can see
- Buses: trail 10 positions (was 6), line-width 3 at zoom 15 tapering by position (newest 3 px, oldest 0.5 px) using a
  per-segment opacity or separate features per segment; arrow icon 1.3x the current size; keep cyan.
- Ships: NOT amber any more (amber is the stores' colour). Ships become white (#eef6f9) diamonds 1.4x the current size with
  a cyan halo (shadowBlur 10) and a short white wake (3 positions, width 2 px). Update the legend/attribution words if any
  name the colour.
- Both: when fewer than 10 vehicles are inside the current viewport, nothing changes; do not fake positions. At night
  (now: 35 buses) the HUD number is the truth.

## 3. Act two: the harbour move
Measured 8 Nov 00:40Z from /api/city/vehicles: 40 ships, 18 of them inside lon 22.19-22.26 lat 60.42-60.46 (the port and
the river mouth), median ship at 22.208, 60.437; buses cluster at the centre (median 22.266, 60.453).
After the room answers (see the recorder timeline below), the camera eases west along the Aura river to the harbour:
`map.easeTo({center: [22.218, 60.438], zoom: 13.7, pitch: 58, bearing: -50, duration: 9000, easing: easeInOutCubic})`,
then holds with the 1 deg/s drift. Check the framing yourself from a screenshot: ships must be visible as white diamonds
with wakes, the city-centre dots still in the upper part of the frame, the river leading the eye. Adjust center/zoom/bearing
until that is true and write the final numbers in docs/city.md. Then (optional, only if time) a slow return to TURKU.
Trigger: `window.__city.harbour()` for the recorder, the H key for a human, and on the live page automatically 25 s after
landing when nobody has touched the map (state.lastTouch), returning to TURKU 20 s later and repeating every 60 s. The
HUD stays. The sentence stays. Approvals arriving during the harbour view still pulse where they are (may be off-screen;
the counter and the list still tick, that is fine).

## 4. Recorder timeline (bin/record_city.py, frames mode)
0-1.5 s title on the globe (pre-warm already done inside start()), 1.5-8.5 s flight, 8.5-14 s landing + sentence,
14-30 s the 8 room answers 2 s apart (as now), 30-39 s harbour move, 39-48 s hold on the harbour with ships moving.
Total about 48 s. Same encode (crf 30, 20 fps, 1920x1080). The recorder calls `window.__city.harbour()` at 30 s.
Virtual clock as now. Keep `--mode realtime` working.

## 5. Checks (all mandatory, in order)
1. `pytest -q tests/test_city.py` green; add a test that the vehicles API shape is unchanged and that `/city` HTML
   contains the beacon and heatmap layer ids (ids: "city-beacon", "city-glow").
2. Test server: `cd /root/hack/kaiku_wt/city2 && PUBLIC_URL=http://127.0.0.1:8231 KAIKU_NO_CALL=1 KAIKU_BROKER_URL=http://127.0.0.1:1026 /root/hack/kaiku/.venv/bin/uvicorn kaiku.app:app --host 127.0.0.1 --port 8231` (no .env, outbound silent). It creates its own subscription kaiku-city-store-status-8231 (never production's).
3. Stills with `/root/hack/bin/shot.py` at `?intro=0` (desktop+mobile) and a Playwright script of your own that captures the
   flight at 2, 3.5, 5, 6.5 s after start and the harbour view at the end: READ them. Pass = no frame of the flight is
   more than 60 % pixels below luminance 20 (measure with PIL), the beacon is visible on the globe, ships are visible
   white diamonds in the harbour frame. Put them in /root/hack/shots/city2/.
4. Render the film on the burst box, not on this VPS: copy bin/record_city.py to /root/hack/burst_city/record_city.py and
   run `/root/hack/bin/burst run /root/hack/burst_city -p 8231 -o out -- python3 record_city.py --base http://127.0.0.1:8231 --out out/city_demo.mp4 --size 1920x1080`
   (about 6 min; the box reaches your test server through the forwarded port). Then extract frames every 4 s and READ them;
   run the cut detector `ffmpeg -i <mp4> -vf "select='gt(scene,0.25)',showinfo" -f null - 2>&1 | grep -c pts_time` (must be 0).
   Copy the result to /root/hack/shots/city_demo_v4.mp4 (do NOT overwrite city_demo.mp4).
5. Cleanup: `fuser -k 8231/tcp`, delete the kaiku-city-store-status-8231 subscription from Orion (curl DELETE), and
   `KAIKU_BROKER_URL=http://127.0.0.1:1026 /root/hack/kaiku/.venv/bin/python -m kaiku.city.seed --force`.
6. docs/city.md: a short "act two" section (what changed, the harbour camera numbers, the pre-warm). DISCLOSURE.md only if a
   new library or data source was added (none expected).

Rules: never pkill -f / killall; never touch .env or any secret; never write Store:furry-paw; do not touch /root/hack/kaiku
(the live checkout, owned by another session); commit on task/city2 every 20-30 min with clear messages.
End with: RESULT: <one sentence> | tests: N passed | film: /root/hack/shots/city_demo_v4.mp4 <duration, size> | blocked: <none|what>
