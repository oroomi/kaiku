/* /city: Turku, one broker. Every number on screen comes from /api/city/* (Orion-LD reads); "no data" when missing.
   A dot turns green from the broker NOTIFICATION (SSE "store"); a 5 s broker read heals a missed notification. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const P = new URLSearchParams(location.search);
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const INTRO = P.get("intro") !== "0" && !REDUCE;
  const EUROPE = { center: [18, 58], zoom: 1.6, pitch: 0, bearing: 0 };
  const TURKU = { center: [22.2666, 60.4518], zoom: 15.2, pitch: 62, bearing: -20 };
  // act two: west along the Aura to the port and the river mouth (18 of 40 ships measured inside 22.19-22.26 / 60.42-60.46)
  const HARBOUR = { center: [22.236, 60.4445], zoom: 13.45, pitch: 56, bearing: 56 }; // looking up the Aura to the centre
  const BEACON = [22.2666, 60.4518];
  const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const C = { night: "#090b0d", amber: "#ffd27a", green: "#9fe0b5", white: "#eef6f9", cyan: "#8fd3e8" };
  const fmt = new Intl.NumberFormat("en-US");
  const state = { rows: new Map(), counts: null, source: null, total: 0, approved: 0, seenApproved: new Map(),
                  vehicles: new Map(), pulses: [], landed: false, dotsOn: false, vehOn: false, drift: false,
                  lastTouch: 0, flying: false, warmed: false, view: "turku",
                  landedAt: 0, nextHarbour: 0, returnAt: 0 };
  let map;

  // ---------------------------------------------------------------- style
  async function getStyle() {
    try {
      const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 4000);
      const r = await fetch("https://tiles.openfreemap.org/styles/dark", { signal: ctl.signal }); clearTimeout(t);
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } catch (e) {
      const r = await fetch("/static/city/dark_style.json");
      return r.json();
    }
  }

  function prepStyle(s) {
    s.projection = { type: "globe" };
    s.sky = { "sky-color": "#0b1b24", "horizon-color": "#163746", "fog-color": C.night,
              "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.6, "fog-ground-blend": 0.2,
              "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 10, 1, 12, 0] };
    // Land keeps a faint Horizon teal above the water until the buildings take over at street zoom, so the descent
    // never passes through a black screen; Natural Earth relief shows on the globe and fades out by zoom 8.
    const LAND = ["interpolate", ["linear"], ["zoom"], 0, "#132530", 6, "#10202a", 10, "#101e26", 12, "#0f1c23", 13.5, "#0e1a20", 15, "#0b1216"];
    const WATER = ["interpolate", ["linear"], ["zoom"], 0, "#04070a", 9, "#06090d", 12, "#0e1c24", 14, "#12232c"];
    for (const l of s.layers) {
      if (l.id === "background") { l.paint = Object.assign({}, l.paint, { "background-color": LAND }); }
      if (l.id === "water") { l.paint = Object.assign({}, l.paint, { "fill-color": WATER }); }
      if (l.id === "waterway") { l.paint = Object.assign({}, l.paint, { "line-color": "#12232c" }); }
    }
    if (s.sources && s.sources.ne2_shaded) {
      const i = s.layers.findIndex((l) => l.id === "background") + 1;
      s.layers.splice(i, 0, { id: "city-relief", type: "raster", source: "ne2_shaded", maxzoom: 9,
        paint: { "raster-opacity": ["interpolate", ["linear"], ["zoom"], 0, 0.55, 5, 0.4, 8, 0],
                 "raster-brightness-min": 0, "raster-brightness-max": 0.32, "raster-saturation": -0.75, "raster-contrast": 0.25 } });
    }
    return s;
  }

  // ---------------------------------------------------------------- icons (canvas, no files)
  function icon(draw, size = 40) {
    const c = document.createElement("canvas"); c.width = c.height = size;
    const g = c.getContext("2d"); draw(g, size);
    return g.getImageData(0, 0, size, size);
  }
  const ARROW = () => icon((g, s) => {
    g.translate(s / 2, s / 2); g.fillStyle = C.cyan; g.shadowColor = C.cyan; g.shadowBlur = 6;
    g.beginPath(); g.moveTo(0, -14); g.lineTo(9, 11); g.lineTo(0, 6); g.lineTo(-9, 11); g.closePath(); g.fill();
  });
  // ships: white diamonds with a cyan halo (amber is the stores' colour)
  const DIAMOND = () => icon((g, s) => {
    g.translate(s / 2, s / 2); g.fillStyle = C.white; g.shadowColor = C.cyan; g.shadowBlur = 10;
    const d = () => { g.beginPath(); g.moveTo(0, -11); g.lineTo(8, 0); g.lineTo(0, 11); g.lineTo(-8, 0); g.closePath(); g.fill(); };
    d(); d();
  }, 56);

  // ---------------------------------------------------------------- layers
  function firstSymbol() { return (map.getStyle().layers.find((l) => l.type === "symbol") || {}).id; }
  const EMPTY = { type: "FeatureCollection", features: [] };

  function addLayers() {
    const before = firstSymbol();
    map.addLayer({
      id: "city-3d", type: "fill-extrusion", source: "openmaptiles", "source-layer": "building", minzoom: 13,
      filter: ["!", ["has", "hide_3d"]],
      paint: {
        "fill-extrusion-color": ["interpolate", ["linear"], ["coalesce", ["get", "render_height"], 6],
                                 0, "#13303c", 20, "#1f5366", 60, "#2f6f8c"],
        "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6],
        "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
        "fill-extrusion-opacity": 0.85, "fill-extrusion-vertical-gradient": true,
      },
    }, before);
    for (const id of ["stores", "pulse", "buses", "ships", "trails"]) map.addSource(id, { type: "geojson", data: EMPTY });
    map.addSource("beacon", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: BEACON } } });
    map.addImage("bus-arrow", ARROW(), { pixelRatio: 2 });
    map.addImage("ship-diamond", DIAMOND(), { pixelRatio: 2 });
    const col = ["match", ["get", "s"], "approved", C.green, "known", C.white, C.amber];
    const BIG = ["match", ["get", "s"], "approved", 1.7, 1];
    // the stores as one warm glow during the descent (zoom 6 to 12), resolving into the dots below
    map.addLayer({ id: "city-glow", type: "heatmap", source: "stores", minzoom: 5, maxzoom: 12.5,
      paint: { "heatmap-weight": 1,
               "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 6, 0.04, 9, 0.08, 11, 0.12],
               "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 6, 8, 11, 40],
               "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(255,210,122,0)", 0.15, "rgba(255,210,122,0.12)",
                                 0.4, "rgba(255,210,122,0.38)", 0.75, "rgba(255,210,122,0.7)", 1, "rgba(255,226,170,0.9)"],
               "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 5.5, 0, 6.5, 0.9, 11.5, 0.75, 12, 0] } }, before);
    // buses: 10-position trail tapering 3 px -> 0.5 px; ships: 3-position white wake, 2 px
    const SHIP = ["==", ["get", "k"], "ship"];
    const busW = (a, b) => ["interpolate", ["linear"], ["get", "age"], 0, a, 9, b];
    map.addLayer({ id: "trails", type: "line", source: "trails", layout: { "line-cap": "round" },
      paint: { "line-color": ["case", SHIP, C.white, C.cyan],
               "line-width": ["interpolate", ["linear"], ["zoom"], 11, ["case", SHIP, 1, busW(1.2, 0.3)], 15, ["case", SHIP, 2, busW(3, 0.5)]],
               "line-opacity": 0, "line-opacity-transition": { duration: 1000 } } });
    map.addLayer({ id: "st-halo", type: "circle", source: "stores",
      paint: { "circle-color": col, "circle-blur": 1,
               "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, ["*", BIG, 6], 16, ["*", BIG, 18]],
               "circle-opacity": 0, "circle-opacity-transition": { duration: 1200 } } });
    map.addLayer({ id: "st-core", type: "circle", source: "stores",
      paint: { "circle-color": col, "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 1.5, 16, 4],
               "circle-opacity": 0, "circle-opacity-transition": { duration: 1200 } } });
    map.addLayer({ id: "pulse", type: "circle", source: "pulse",
      paint: { "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": C.green, "circle-stroke-width": 2.5,
               "circle-blur": 0.6, "circle-radius": ["get", "r"], "circle-stroke-opacity": ["get", "o"],
               "circle-pitch-alignment": "map" } });
    const sym = (id, img, size) => map.addLayer({ id, type: "symbol", source: id,
      layout: { "icon-image": img, "icon-size": size, "icon-rotate": ["coalesce", ["get", "h"], 0],
                "icon-rotation-alignment": "map", "icon-pitch-alignment": "map",
                "icon-allow-overlap": true, "icon-ignore-placement": true },
      paint: { "icon-opacity": 0, "icon-opacity-transition": { duration: 1000 } } });
    sym("buses", "bus-arrow", ["interpolate", ["linear"], ["zoom"], 11, 0.65, 16, 1.43]);
    sym("ships", "ship-diamond", ["interpolate", ["linear"], ["zoom"], 11, 0.84, 16, 1.68]);
    // the beacon to fly to: a cyan point at Turku from the first globe frame, fading out between zoom 11 and 12.5
    map.addLayer({ id: "city-beacon", type: "circle", source: "beacon",
      paint: { "circle-color": C.cyan, "circle-blur": 1, "circle-pitch-alignment": "viewport",
               "circle-radius": ["interpolate", ["linear"], ["zoom"], 1.6, 35, 11, 35, 12.5, 30],
               "circle-opacity": beaconOpacity(0.6) } });
    map.addLayer({ id: "city-beacon-core", type: "circle", source: "beacon",
      paint: { "circle-color": C.cyan, "circle-blur": 0.2, "circle-pitch-alignment": "viewport",
               "circle-radius": ["interpolate", ["linear"], ["zoom"], 1.6, 2, 11, 2, 12.5, 2],
               "circle-opacity": beaconOpacity(1) } });
  }

  const TRAIL_OPACITY = ["case", ["==", ["get", "k"], "ship"], ["interpolate", ["linear"], ["get", "age"], 0, 0.7, 2, 0.15],
                         ["interpolate", ["linear"], ["get", "age"], 0, 0.8, 9, 0.06]];
  function beaconOpacity(v) { return ["interpolate", ["linear"], ["zoom"], 11, v, 12.5, 0]; }
  let lastBeacon = 0;
  function beaconFrame(now) { // breathe 0.35..0.8 over 2.2 s, at most 15 Hz, only while it can be seen
    if (now - lastBeacon < 66 || map.getZoom() > 12.6) return; lastBeacon = now;
    const b = 0.575 + 0.225 * Math.sin((now / 2200) * 2 * Math.PI);
    map.setPaintProperty("city-beacon", "circle-opacity", beaconOpacity(b));
  }

  function showDots() {
    if (state.dotsOn || !map.getLayer("st-core")) return;
    state.dotsOn = true;
    map.setPaintProperty("st-halo", "circle-opacity", ["match", ["get", "s"], "approved", 0.8, 0.35]);
    map.setPaintProperty("st-core", "circle-opacity", 1);
    setTimeout(() => {
      state.vehOn = true;
      map.setPaintProperty("buses", "icon-opacity", 1);
      map.setPaintProperty("ships", "icon-opacity", 0.95);
      map.setPaintProperty("trails", "line-opacity", TRAIL_OPACITY);
    }, 1000);
  }

  // ---------------------------------------------------------------- HUD
  function setText(id, t, cls) { const el = $(id); if (!el) return; el.textContent = t; if (cls !== undefined) el.className = cls; }
  let skew = 0; // server clock minus page clock, so the HUD time is the server's (also under a recorder's virtual clock)
  function clock() {
    const t = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Helsinki", hour: "2-digit", minute: "2-digit" }).format(new Date(Date.now() + skew));
    setText("h-time", "TURKU " + t);
  }

  function recount() {
    if (!state.counts) return;
    const c = { total: 0, missing: 0, known: 0, approved: 0 };
    for (const r of state.rows.values()) { c.total++; c[r.s] = (c[r.s] || 0) + 1; }
    state.counts = c;
  }
  function renderCounts() {
    recount();
    const c = state.counts;
    if (!c) { setText("h-stores", "STORE ENTITIES: NO DATA"); return; }
    setText("h-stores", fmt.format(c.total) + " STORE ENTITIES");
    if (state.source === "orion-ld") setText("h-broker", "ORION-LD LIVE", "live");
    else setText("h-broker", "FALLBACK: BROKER OFFLINE", "fb");
    const told = (c.known || 0) + (c.approved || 0);
    $("s2").innerHTML = "";
    $("s2").append(document.createTextNode(`${fmt.format(told)} of ${fmt.format(c.total)} businesses here have told the map their hours.`));
    countTo(c.approved || 0);
  }

  let shown = 0, raf = 0;
  function countTo(n) {
    const from = shown, t0 = performance.now(), dur = 700;
    cancelAnimationFrame(raf);
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur);
      shown = Math.round(from + (n - from) * (1 - Math.pow(1 - k, 3)));
      $("c-approved").textContent = fmt.format(shown);
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  }

  function hhmm(ts) {
    const d = ts ? new Date(ts) : new Date();
    if (isNaN(d)) return "";
    return new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Helsinki", hour: "2-digit", minute: "2-digit" }).format(d);
  }
  function addEvent(item) {
    const ol = $("c-events");
    const empty = ol.querySelector(".empty"); if (empty) empty.remove();
    const li = document.createElement("li");
    const t = document.createElement("span"); t.className = "t"; t.textContent = hhmm(item.ts);
    const x = document.createElement("span");
    const i = document.createElement("i"); i.textContent = "Subscription fired: ";
    x.append(i, document.createTextNode(`${item.name} approved Christmas Eve hours`));
    li.append(t, x);
    ol.prepend(li);
    while (ol.children.length > 6) ol.lastChild.remove();
  }

  // ---------------------------------------------------------------- stores
  function storesGeo() {
    const f = [];
    for (const r of state.rows.values()) f.push({ type: "Feature", properties: { id: r.id, s: r.s, n: r.n },
                                                  geometry: { type: "Point", coordinates: [r.lon, r.lat] } });
    return { type: "FeatureCollection", features: f };
  }
  function pushStores() { const s = map && map.getSource("stores"); if (s) s.setData(storesGeo()); }

  async function loadStores() {
    try {
      const d = await (await fetch("/api/city/stores")).json();
      state.source = d.source; state.counts = d.counts;
      state.rows = new Map(d.rows.map((r) => [r.id, r]));
      if (d.holiday && d.holiday.now) { const sv = Date.parse(d.holiday.now); if (!isNaN(sv)) { skew = sv - Date.now(); clock(); } }
      const days = d.holiday && d.holiday.days;
      setText("h-xmas", typeof days === "number" ? (days > 0 ? `CHRISTMAS EVE IN ${days} DAYS` : days === 0 ? "CHRISTMAS EVE TODAY" : "CHRISTMAS EVE 24.12.") : "CHRISTMAS EVE: NO DATA");
      renderCounts(); pushStores();
    } catch (e) {
      state.counts = null; setText("h-stores", "STORE ENTITIES: NO DATA"); setText("h-broker", "BROKER: NO DATA", "fb");
    }
  }

  function approve(item, notified) {
    const r = state.rows.get(item.id);
    if (r && r.s === "approved") return false;
    if (r) r.s = "approved";
    else if (item.lon != null) state.rows.set(item.id, { id: item.id, n: item.name, lon: item.lon, lat: item.lat, s: "approved" });
    pushStores();
    if (item.lon != null) pulse(item.lon, item.lat);
    if (notified) addEvent(item);
    renderCounts();
    return true;
  }

  // reconciliation: a Store seen approved in two consecutive broker reads (>= 5 s) without a notification heals
  async function reconcile() {
    try {
      const d = await (await fetch("/api/city/stores?only=approved")).json();
      state.source = d.source;
      if (d.holiday && d.holiday.now) { const sv = Date.parse(d.holiday.now); if (!isNaN(sv)) { skew = sv - Date.now(); clock(); } }
      const now = Date.now();
      for (const r of d.rows) {
        const cur = state.rows.get(r.id);
        if (cur && cur.s === "approved") continue;
        const first = state.seenApproved.get(r.id);
        if (!first) { state.seenApproved.set(r.id, now); continue; }
        if (now - first >= 4500) { approve({ id: r.id, name: r.n, lon: r.lon, lat: r.lat }, false); }
      }
      if (d.source !== "orion-ld") renderCounts();
    } catch (e) { /* the next read retries */ }
  }

  // ---------------------------------------------------------------- pulses (<= 10 features)
  function pulse(lon, lat) {
    state.pulses.push({ lon, lat, t0: performance.now() });
    if (state.pulses.length > 10) state.pulses.shift();
  }
  function pulseFrame(now) {
    const src = map.getSource("pulse"); if (!src) return;
    state.pulses = state.pulses.filter((p) => now - p.t0 < 1400);
    if (!state.pulses.length && !state._pulseDirty) return;
    state._pulseDirty = state.pulses.length > 0;
    src.setData({ type: "FeatureCollection", features: state.pulses.map((p) => {
      const k = Math.max(0, (now - p.t0) / 1400);
      return { type: "Feature", properties: { r: 4 + 44 * (1 - Math.pow(1 - k, 2)), o: 0.7 * (1 - k) },
               geometry: { type: "Point", coordinates: [p.lon, p.lat] } };
    }) });
  }

  // ---------------------------------------------------------------- vehicles (tween between broker reads)
  const DUR = 5000;
  function onPositions(d) {
    const now = performance.now(), seen = new Set();
    const take = (arr, kind) => (arr || []).forEach((a) => {
      const [id, lon, lat, h] = a; seen.add(id);
      const v = state.vehicles.get(id);
      if (!v) { state.vehicles.set(id, { kind, from: [lon, lat], to: [lon, lat], t0: now, h, trail: [[lon, lat]] }); return; }
      if (h != null) v.h = h;
      if (far(v.to, [lon, lat])) { // > 300 m between two reads (measured max 180 m in 11 s on 7 Nov): a GPS jump or a reused id; snap, no tween, no trail
        v.from = v.to = [lon, lat]; v.t0 = now; v.trail = [[lon, lat]]; return;
      }
      v.from = pos(v, now); v.to = [lon, lat];
      v.dur = Math.max(100, Math.min(DUR, now - v.t0)); // tween over the measured read interval, so the arrow never lags its data
      v.t0 = now;
      const last = v.trail[v.trail.length - 1];
      if (!last || last[0] !== lon || last[1] !== lat) { v.trail.push([lon, lat]); if (v.trail.length > (kind === "ship" ? 3 : 10)) v.trail.shift(); }
    });
    take(d.buses, "bus"); take(d.ships, "ship");
    for (const id of [...state.vehicles.keys()]) if (!seen.has(id)) state.vehicles.delete(id);
    const c = d.counts || {};
    setText("h-buses", d.buses ? `${fmt.format(d.buses.length)} BUSES` : "BUSES: NO DATA");
    setText("h-ships", d.ships ? `${fmt.format(d.ships.length)} SHIPS` : "SHIPS: NO DATA");
    const w = d.weather;
    setText("h-wx", w && typeof w.temp === "number" ? `${w.temp.toFixed(1)} °C ${(w.wtype || "").toUpperCase()}` : "WEATHER: NO DATA");
    if (d.source && d.source !== "broker") setText("h-buses", `${fmt.format((d.buses || []).length)} BUSES (CACHE)`);
    void c;
  }
  function far(a, b) {
    const dx = (a[0] - b[0]) * 55.3, dy = (a[1] - b[1]) * 111.3; // km at 60.45 N
    return dx * dx + dy * dy > 0.09;
  }
  function pos(v, now) {
    const k = Math.max(0, Math.min(1, (now - v.t0) / (v.dur || DUR))); // clamped: a clock that steps back must not extrapolate
    return [v.from[0] + (v.to[0] - v.from[0]) * k, v.from[1] + (v.to[1] - v.from[1]) * k];
  }
  let lastVeh = 0, lastTrail = 0;
  function vehFrame(now) {
    if (now - lastVeh < 50) return; lastVeh = now; // <= 20 Hz
    const bus = [], ship = [];
    for (const [id, v] of state.vehicles) {
      const p = pos(v, now);
      (v.kind === "ship" ? ship : bus).push({ type: "Feature", properties: { h: v.h }, geometry: { type: "Point", coordinates: p } });
    }
    map.getSource("buses").setData({ type: "FeatureCollection", features: bus });
    map.getSource("ships").setData({ type: "FeatureCollection", features: ship });
    if (now - lastTrail < 250) return; lastTrail = now; // trails at 4 Hz
    const f = [];
    for (const v of state.vehicles.values()) {
      const pts = [...v.trail.slice(0, -1), pos(v, now)];
      for (let i = pts.length - 1, age = 0; i > 0; i--, age++)
        if (!far(pts[i - 1], pts[i])) f.push({ type: "Feature", properties: { age, k: v.kind }, geometry: { type: "LineString", coordinates: [pts[i - 1], pts[i]] } });
    }
    map.getSource("trails").setData({ type: "FeatureCollection", features: f });
  }

  function loop(now) {
    if (map && map.getSource("buses")) {
      if (state.vehOn) vehFrame(now);
      pulseFrame(now);
      beaconFrame(now);
      if (state.drift && !state.flying && now - state.lastTouch > 8000 && !map.isMoving()) {
        const dt = state._lt ? Math.max(0, Math.min(100, now - state._lt)) : 16;
        map.setBearing(map.getBearing() + dt / 1000);
      }
    }
    state._lt = now;
    requestAnimationFrame(loop);
  }

  // ---------------------------------------------------------------- SSE
  function stream() {
    const es = new EventSource("/api/city/stream");
    es.addEventListener("hello", (e) => { const d = JSON.parse(e.data); (d.recent || []).forEach(addEvent); });
    es.addEventListener("positions", (e) => onPositions(JSON.parse(e.data)));
    es.addEventListener("store", (e) => {
      const it = JSON.parse(e.data);
      if (!approve(it, true)) addEvent(it);
    });
  }

  // ---------------------------------------------------------------- camera
  function land() {
    state.flying = false; state.landed = true; state.drift = !REDUCE; state.view = "turku";
    state.landedAt = performance.now(); state.nextHarbour = state.landedAt + 25000; state.returnAt = 0;
    showDots();
    setTimeout(() => $("s1").classList.add("on"), 200);
    setTimeout(() => $("s2").classList.add("on"), 2000);
  }
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  // Pre-warm: step the camera through the zooms of the descent under an opaque cover, waiting for each zoom's tiles
  // (cap 1.5 s per step), so the visible flight never passes a zoom whose tiles have not arrived.
  async function prewarm() {
    const zs = [2, 4, 6, 8, 10, 12, 13.5, 15.2];
    for (const z of zs) {
      const k = (z - EUROPE.zoom) / (TURKU.zoom - EUROPE.zoom), kc = Math.min(1, k * 2.2);
      map.jumpTo({ zoom: z, pitch: TURKU.pitch * k, bearing: TURKU.bearing * k,
                   center: [EUROPE.center[0] + (TURKU.center[0] - EUROPE.center[0]) * kc,
                            EUROPE.center[1] + (TURKU.center[1] - EUROPE.center[1]) * kc] });
      const t0 = performance.now();
      await wait(200);
      while (!map.areTilesLoaded() && performance.now() - t0 < 1500) await wait(50);
    }
    state.warmed = true;
  }
  async function fly() {
    state.flying = true; state.drift = false; state.landed = false; state.view = "turku"; state.returnAt = 0;
    $("s1").classList.remove("on"); $("s2").classList.remove("on");
    $("ctitle").classList.add("on");
    if (!state.warmed) {
      $("ccover").classList.add("on");
      await prewarm();
    }
    map.jumpTo(EUROPE);
    $("ccover").classList.remove("on");
    setTimeout(() => {
      setTimeout(() => $("ctitle").classList.remove("on"), 1800);
      map.flyTo({ ...TURKU, duration: 7000, curve: 1.42, easing: (t) => 1 - Math.pow(1 - t, 3), essential: true });
      map.once("moveend", land);
    }, 1500);
  }

  // act two: the harbour move, and back
  function harbour() {
    if (!map || state.flying) return;
    state.view = "harbour"; state.harbourAt = performance.now();
    state.returnAt = state.harbourAt + 9000 + 20000; state.nextHarbour = state.harbourAt + 60000;
    map.easeTo({ ...HARBOUR, duration: REDUCE ? 0 : 9000, easing: easeInOutCubic, essential: true });
  }
  function toTurku() {
    if (!map || state.flying) return;
    state.view = "turku"; state.returnAt = 0;
    map.easeTo({ ...TURKU, duration: REDUCE ? 0 : 9000, easing: easeInOutCubic, essential: true });
  }
  // live page: 25 s after landing with nobody touching the map, go to the harbour; back 20 s after arriving; every 60 s
  function autoCamera() {
    if (P.get("hold") === "1" || REDUCE || !state.landed || state.flying) return;
    const now = performance.now();
    if (state.lastTouch > state.landedAt && now - state.lastTouch < 25000) {
      state.nextHarbour = state.lastTouch + 25000; state.returnAt = 0; return;
    }
    if (state.view === "turku" && now >= state.nextHarbour) harbour();
    else if (state.view === "harbour" && (!state.returnAt || now >= state.returnAt)) toTurku();
  }

  async function init() {
    clock(); setInterval(clock, 15000);
    const style = prepStyle(await getStyle());
    const start = INTRO ? EUROPE : TURKU;
    map = new maplibregl.Map({
      container: "cmap", style, ...start, maxPitch: 70, attributionControl: false,
      pixelRatio: Math.min(window.devicePixelRatio || 1, 1.5), canvasContextAttributes: { antialias: false },
    });
    window.__city = { map, state, harbour, turku: toTurku };
    if (INTRO) $("ccover").classList.add("on");
    map.on("zoom", () => { if (map.getZoom() > 11) showDots(); });
    for (const ev of ["pointerdown", "wheel", "touchstart"]) map.getCanvasContainer().addEventListener(ev, () => { state.lastTouch = performance.now(); }, { passive: true });
    map.on("load", async () => {
      addLayers();
      await loadStores();
      stream();
      setInterval(reconcile, 5000);
      fetch("/api/city/vehicles").then((r) => r.json()).then(onPositions).catch(() => {});
      requestAnimationFrame(loop);
      window.__city.ready = true;
      setInterval(autoCamera, 1000);
      // returns a promise that resolves once the pre-warm is done (the recorder drives the clock until it does)
      window.__city.start = () => (INTRO ? fly() : (land(), Promise.resolve()));
      if (P.get("hold") !== "1") window.__city.start(); // ?hold=1: the recorder starts the fly-in on its first frame
    });
    addEventListener("keydown", (e) => {
      if (e.target.closest && e.target.closest("input,textarea,button")) return;
      if ((e.key === "r" || e.key === "R" || e.code === "Space") && !REDUCE) { e.preventDefault(); fly(); }
      if (e.key === "h" || e.key === "H") { state.lastTouch = 0; state.view === "harbour" ? toTurku() : harbour(); }
    });
  }

  // ---------------------------------------------------------------- judge drawer
  $("judge-open").addEventListener("click", async () => {
    $("judge").hidden = false; $("city").classList.add("has-judge");
    try {
      const d = await (await fetch("/api/city/judge")).json();
      $("judge-curl").textContent = d.curl;
      $("judge-ent").textContent = d.entity ? JSON.stringify(d.entity, null, 2) : "no data: the broker did not answer";
    } catch (e) { $("judge-ent").textContent = "no data"; }
  });
  $("judge-close").addEventListener("click", () => { $("judge").hidden = true; $("city").classList.remove("has-judge"); });

  init();
})();
