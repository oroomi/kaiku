/* Live Turku map: businesses from /api/room/state, updates via /api/events (SSE), no layer re-render. */
(function () {
  var embed = /[?&]embed=1/.test(location.search);
  if (embed) document.getElementById('mapwrap').classList.add('embed');
  var STATE = {}, answered = 0, unknown = 0, known = 0, pulses = [];
  var elU = document.getElementById('c-unknown'), elA = document.getElementById('c-answered'),
      elC = document.getElementById('conn'), elL = document.getElementById('latest');
  var COL = { amber: '#ffd27a', green: '#9fe0b5', cyan: '#8fd3e8', white: '#eef6f9' };

  /* ---- dark restyle of OpenFreeMap positron: invert lightness, tint toward the Horizon teal ---- */
  function parseColor(s) {
    var m, c;
    if ((m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(s))) {
      var h = m[1].length === 3 ? m[1].replace(/./g, '$&$&') : m[1];
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 1];
    }
    if ((m = /^rgba?\(([^)]+)\)$/i.exec(s))) { c = m[1].split(',').map(parseFloat); return [c[0], c[1], c[2], c.length > 3 ? c[3] : 1]; }
    if ((m = /^hsla?\(([^)]+)\)$/i.exec(s))) {
      c = m[1].split(',').map(parseFloat);
      var H = c[0] / 360, S = c[1] / 100, L = c[2] / 100, q = L < .5 ? L * (1 + S) : L + S - L * S, p = 2 * L - q;
      var f = function (t) { t = (t + 1) % 1; return t < 1 / 6 ? p + (q - p) * 6 * t : t < .5 ? q : t < 2 / 3 ? p + (q - p) * (2 / 3 - t) * 6 : p; };
      return [f(H + 1 / 3) * 255, f(H) * 255, f(H - 1 / 3) * 255, c.length > 3 ? c[3] : 1];
    }
    if (s === 'transparent') return [0, 0, 0, 0];
    return null;
  }
  function dark(s) {
    var c = parseColor(s.trim());
    if (!c) return s;
    var l = (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255, inv = 1 - l; // 0 dark .. 1 light
    var t = 0.06 + inv * 0.45;                                                  // map to 4.5%..34% lightness
    var r = Math.round((12 + 70 * t * 1.7) * .8 + 6), g = Math.round(20 + 105 * t * 1.7 * .85), b = Math.round(24 + 125 * t * 1.7 * .85);
    return 'rgba(' + Math.min(r, 255) + ',' + Math.min(g, 255) + ',' + Math.min(b, 255) + ',' + c[3] + ')';
  }
  function walk(v) {
    if (typeof v === 'string') return parseColor(v) ? dark(v) : v;
    if (Array.isArray(v)) return v.map(walk);
    if (v && typeof v === 'object' && v.stops) { v.stops = v.stops.map(function (s) { return [s[0], walk(s[1])]; }); return v; }
    return v;
  }
  function darken(style) {
    style.layers.forEach(function (l) {
      var pt = l.paint || {};
      Object.keys(pt).forEach(function (k) {
        if (/-color$/.test(k) && k.indexOf('text') !== 0) pt[k] = walk(pt[k]);
        else if (k === 'text-color') pt[k] = 'rgba(238,246,249,.62)';
        else if (k === 'text-halo-color') pt[k] = 'rgba(12,20,24,.85)';
      });
    });
    return style;
  }

  var map = new maplibregl.Map({
    container: 'map', center: [22.2666, 60.4518], zoom: 14.6, attributionControl: false,
    style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#0c1418' } }],
             glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf' }
  });
  /* attribution lives in its own strip (#mattr) so it never overlaps the legend */
  var styleReady = fetch('https://tiles.openfreemap.org/styles/positron').then(function (r) { return r.json(); })
    .then(function (s) { return new Promise(function (res) { map.setStyle(darken(s), { diff: false }); map.once('style.load', res); }); })
    .catch(function () { /* offline: dots on the dark background */ });
  var loaded = new Promise(function (res) { map.on('load', res); });
  var ready = styleReady.then(function () { return loaded; });
  var dataP = null;

  function fcFrom(list) {
    return { type: 'FeatureCollection', features: list.map(function (b) {
      return { type: 'Feature', id: b.id, properties: { id: b.id, n: b.n, s: b.s, a: b.a || '' }, geometry: { type: 'Point', coordinates: [b.lon, b.lat] } };
    }) };
  }
  var DONE = ['any', ['boolean', ['feature-state', 'done'], false], ['==', ['get', 's'], 'answered']];
  var PAINT = ['case', ['boolean', ['feature-state', 'done'], false], COL.green,
    ['==', ['get', 's'], 'answered'], COL.green, ['==', ['get', 's'], 'known'], COL.white, COL.amber];

  function addLayers(list) {
    if (map.getSource('biz')) return;
    map.addSource('biz', { type: 'geojson', data: fcFrom(list), promoteId: 'id' });
    map.addSource('pulse', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'biz-glow', type: 'circle', source: 'biz', paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, ['case', DONE, 12, 6], 17, ['case', DONE, 28, 16]], 'circle-color': PAINT, 'circle-opacity': ['case', DONE, .35, .16], 'circle-blur': 1 } });
    map.addLayer({ id: 'biz-dot', type: 'circle', source: 'biz', paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, ['case', DONE, 4.5, 2.6], 17, ['case', DONE, 10, 7]], 'circle-color': PAINT,
      'circle-stroke-width': 1, 'circle-stroke-color': 'rgba(9,11,13,.7)' } });
    map.addLayer({ id: 'pulse', type: 'circle', source: 'pulse', paint: {
      'circle-radius': ['get', 'r'], 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-width': 2.5,
      'circle-stroke-color': COL.cyan, 'circle-stroke-opacity': ['get', 'o'] } });
    map.addLayer({ id: 'biz-label', type: 'symbol', source: 'biz', minzoom: 16, layout: {
      'text-field': ['get', 'n'], 'text-font': ['Noto Sans Regular'], 'text-size': 11, 'text-offset': [0, 1.1], 'text-anchor': 'top', 'text-optional': true },
      paint: { 'text-color': 'rgba(238,246,249,.7)', 'text-halo-color': 'rgba(12,20,24,.9)', 'text-halo-width': 1 } });
  }

  function counts() { elU.textContent = unknown; elA.textContent = answered; }
  function esc(t) { var d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
  function pushLatest(name, ans) {
    if (!elL) return;
    var li = document.createElement('li');
    li.innerHTML = '<span class="nm">' + esc(name) + '</span><span class="an">' + esc('Christmas Eve: ' + ({ suljettu: 'closed', normaalisti: 'as usual' }[ans] || ans)) + '</span>';
    elL.insertBefore(li, elL.firstChild);
    while (elL.children.length > 6) elL.removeChild(elL.lastChild);
  }

  /* pulse animation: one tiny source, only active while a pulse lives */
  var raf = null;
  function tick() {
    var now = performance.now();
    pulses = pulses.filter(function (p) { return now - p.t0 < 1600; });
    var feats = pulses.map(function (p) {
      var k = (now - p.t0) / 1600;
      return { type: 'Feature', properties: { r: 6 + k * 34, o: 1 - k }, geometry: { type: 'Point', coordinates: p.c } };
    });
    var s = map.getSource('pulse'); if (s) s.setData({ type: 'FeatureCollection', features: feats });
    raf = pulses.length ? requestAnimationFrame(tick) : null;
  }
  function pulse(c) { pulses.push({ c: c, t0: performance.now() }); if (!raf) raf = requestAnimationFrame(tick); }

  function turnGreen(id, ans, name, lonlat, announce) {
    var st = STATE[id];
    if (st && st.s !== 'answered') { unknown -= st.s === 'unknown' ? 1 : 0; answered += 1; st.s = 'answered'; st.a = ans; }
    else if (st) st.a = ans;
    if (map.getSource('biz')) map.setFeatureState({ source: 'biz', id: id }, { done: true });
    counts();
    if (announce) { pushLatest(name || (st && st.n) || id, ans); if (lonlat) pulse(lonlat); }
  }

  function loadState() {
    return fetch('/api/room/state').then(function (r) { return r.json(); }).then(function (s) {
      STATE = {}; s.businesses.forEach(function (b) { STATE[b.id] = b; });
      answered = s.counts.answered; unknown = s.counts.unknown; known = s.counts.known; counts();
      if (elL) { elL.innerHTML = ''; s.latest.slice(0, 6).reverse().forEach(function (l) { pushLatest(l.name, l.answer); }); }
      var src = document.getElementById('legend-src');
      if (src && s.meta.fallback) src.textContent = 'Businesses: fictional placeholder (OpenStreetMap was unreachable). Holiday hours: unknown. Answers: from the room (demo).';
      return ready.then(function () {
        if (map.getSource('biz')) { map.getSource('biz').setData(fcFrom(s.businesses)); } else { addLayers(s.businesses); }
      });
    });
  }

  var es = null, backoff = 1000, retryT = null;
  function onEvent(m) {
    var e; try { e = JSON.parse(m.data); } catch (x) { return; }
    var d = e.detail || {};
    if (!d.map) return;
    if (d.reset) { loadState().then(function () { map.getSource('biz') && Object.keys(STATE).forEach(function (id) { map.removeFeatureState({ source: 'biz', id: id }); }); }).catch(function () {}); return; }
    var ll = d.lon != null ? [d.lon, d.lat] : null;
    if (e.step === 'decide') { if (ll) pulse(ll); }
    else if (e.step === 'apply') turnGreen(e.business_id, d.answer || '', d.name, null, true);
  }
  /* SSE is optional: the dots come from /api/room/state; if the stream is down we retry with backoff and poll state meanwhile */
  function connect() {
    clearTimeout(retryT);
    try { es = new EventSource('/api/events'); } catch (x) { retry(); return; }
    es.onopen = function () { backoff = 1000; elC.className = 'mono live on'; elC.innerHTML = '<i></i>live'; loadState().catch(function () {}); };
    es.onerror = function () { elC.className = 'mono live'; elC.innerHTML = '<i></i>reconnecting'; if (es) { es.close(); es = null; } retry(); };
    es.addEventListener('kaiku', onEvent);
  }
  function retry() { clearTimeout(retryT); retryT = setTimeout(connect, backoff); backoff = Math.min(backoff * 2, 30000); }
  function loadStateRetry(n) { loadState().catch(function () { setTimeout(function () { loadStateRetry(n + 1); }, Math.min(1000 * (n + 1), 10000)); }); }
  loadStateRetry(0);
  connect();
  window.__kaikuMap = map;
  /* resync after a dropped connection so counts never drift */
  setInterval(function () { fetch('/api/room/state').then(function (r) { return r.json(); }).then(function (s) { answered = s.counts.answered; unknown = s.counts.unknown; counts(); if (!es || es.readyState !== 1) loadState().catch(function () {}); }).catch(function () {}); }, 5000);
})();
