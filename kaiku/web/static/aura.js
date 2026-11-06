/* Aura: live Turku from the NGSI-LD broker. Vanilla JS + MapLibre. Positions are tweened in place; no full re-render. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var pad = function (n) { return (n < 10 ? "0" : "") + n; };
  var hhmmss = function (ts) { var d = new Date(ts); return isNaN(d) ? "" : pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds()); };
  var jget = function (u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); };
  var jpost = function (u, b) { return fetch(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) }).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || r.status); return j; }); }); };
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (typeof maplibregl === "undefined") { $("map").innerHTML = '<p style="padding:90px 20px">The map library did not load.</p>'; return; }

  var map = new maplibregl.Map({ container: "map", style: "https://tiles.openfreemap.org/styles/dark", center: [22.2666, 60.4518], zoom: window.innerWidth < 700 ? 11.6 : 12.4, attributionControl: false });
  map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: "Föli, Fintraffic, Open-Meteo CC BY 4.0" }), "bottom-left");
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

  function arrow(color) { // cyan arrow pointing up, rotated by icon-rotate
    var s = 40, c = document.createElement("canvas"); c.width = c.height = s; var x = c.getContext("2d");
    x.translate(s / 2, s / 2); x.beginPath(); x.moveTo(0, -13); x.lineTo(9, 11); x.lineTo(0, 6); x.lineTo(-9, 11); x.closePath();
    x.fillStyle = color; x.shadowColor = color; x.shadowBlur = 8; x.fill(); x.lineWidth = 1.5; x.strokeStyle = "rgba(6,34,44,.9)"; x.stroke();
    return x.getImageData(0, 0, s, s);
  }
  function diamond(color) {
    var s = 44, c = document.createElement("canvas"); c.width = c.height = s; var x = c.getContext("2d");
    x.translate(s / 2, s / 2); x.beginPath(); x.moveTo(0, -15); x.lineTo(10, 0); x.lineTo(0, 15); x.lineTo(-10, 0); x.closePath();
    x.fillStyle = color; x.shadowColor = color; x.shadowBlur = 8; x.fill(); x.lineWidth = 1.5; x.strokeStyle = "rgba(40,24,0,.9)"; x.stroke();
    return x.getImageData(0, 0, s, s);
  }
  var empty = function () { return { type: "FeatureCollection", features: [] }; };
  var cur = { buses: {}, ships: {} }, from = { buses: {}, ships: {} }, to = { buses: {}, ships: {} }, tweenStart = 0, TWEEN = 4500;
  var ready = false, pendingBrief = null, geofences = [];

  map.on("load", function () {
    map.addImage("aura-bus", arrow("#8fd3e8")); map.addImage("aura-ship", diamond("#ffd27a"));
    map.addSource("fences", { type: "geojson", data: empty() });
    map.addLayer({ id: "fences-fill", type: "fill", source: "fences", paint: { "fill-color": "#8fd3e8", "fill-opacity": ["case", ["==", ["get", "pending"], 1], 0.1, 0.16] } });
    map.addLayer({ id: "fences-line", type: "line", source: "fences", paint: { "line-color": "#8fd3e8", "line-width": 1.6, "line-dasharray": [2, 2] } });
    map.addSource("biz", { type: "geojson", data: empty() });
    map.addLayer({ id: "biz", type: "circle", source: "biz", paint: { "circle-radius": 2.5, "circle-color": "#9fe0b5", "circle-opacity": 0.7 } });
    map.addSource("ships", { type: "geojson", data: empty() });
    map.addLayer({ id: "ships", type: "symbol", source: "ships", layout: { "icon-image": "aura-ship", "icon-rotate": ["get", "h"], "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-size": 0.7 } });
    map.addSource("buses", { type: "geojson", data: empty() });
    map.addLayer({ id: "buses", type: "symbol", source: "buses", layout: { "icon-image": "aura-bus", "icon-rotate": ["get", "h"], "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-size": 0.62 } });
    ready = true;
    if (pendingBrief) applyBrief(pendingBrief);
    jget("/api/aura/businesses").then(function (b) {
      if (!b.items.length) return;
      map.getSource("biz").setData({ type: "FeatureCollection", features: b.items.map(function (i) { return { type: "Feature", geometry: { type: "Point", coordinates: [i[0], i[1]] }, properties: { n: i[2] } }; }) });
    }).catch(function () {});
    ["buses", "ships"].forEach(function (l) {
      map.on("click", l, function (e) {
        var p = e.features[0].properties;
        new maplibregl.Popup({ closeButton: false, offset: 10 }).setLngLat(e.lngLat).setHTML('<div style="color:#06222c;font:13px Inter,sans-serif"><b>' + esc(p.t) + "</b><br>" + esc(p.d) + "</div>").addTo(map);
      });
      map.on("mouseenter", l, function () { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", l, function () { map.getCanvas().style.cursor = ""; });
    });
    loadSubs();
  });

  /* ---------- positions: broker delta, tweened ---------- */
  function applyBrief(b) {
    var t = {};
    ["buses", "ships"].forEach(function (k) {
      from[k] = {}; to[k] = {};
      Object.keys(cur[k]).forEach(function (id) { from[k][id] = cur[k][id]; });
      (b[k] || []).forEach(function (r) {
        var meta = k === "buses" ? { t: "Line " + r[4], d: "Destination " + (r[5] || "-") + (r[6] != null ? ", " + Math.round(r[6] / 60) + " min late" : "") } : { t: r[4] || "Ship", d: "AIS, " + r[0].split(":").pop() };
        to[k][r[0]] = { lon: r[1], lat: r[2], h: r[3] == null ? 0 : r[3], t: meta.t, d: meta.d };
        if (!from[k][r[0]]) from[k][r[0]] = to[k][r[0]];
      });
    });
    tweenStart = performance.now();
    if (reduce) tweenStart -= TWEEN;
    renderStats(b);
  }
  function tick(now) {
    requestAnimationFrame(tick);
    if (!ready) return;
    var f = Math.min(1, (now - tweenStart) / TWEEN);
    ["buses", "ships"].forEach(function (k) {
      var feats = [], out = {};
      Object.keys(to[k]).forEach(function (id) {
        var a = from[k][id], b = to[k][id];
        var p = { lon: a.lon + (b.lon - a.lon) * f, lat: a.lat + (b.lat - a.lat) * f, h: b.h, t: b.t, d: b.d };
        out[id] = p;
        feats.push({ type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat] }, properties: { h: p.h, t: p.t, d: p.d } });
      });
      cur[k] = out;
      if (f < 1 || !cur["_done" + k]) { map.getSource(k).setData({ type: "FeatureCollection", features: feats }); cur["_done" + k] = f >= 1; }
    });
  }
  requestAnimationFrame(tick);

  function renderStats(b) {
    var c = b.counts || {}, w = b.weather;
    $("n-ent").textContent = c.entities != null ? c.entities : 0;
    $("l-bus").innerHTML = "Buses <b>" + (c.buses || 0) + "</b>";
    $("l-ship").innerHTML = "ships <b>" + (c.ships || 0) + "</b>";
    var wf = "Turku <b>no data</b>", we = "Turku no data";
    if (w && w.temp != null) {
      var t = String(w.temp.toFixed ? w.temp.toFixed(1) : w.temp), ms = w.wind_ms != null ? Math.round(w.wind_ms) : null;
      wf = "Turku <b>" + t + " °C</b>" + (ms != null ? ", wind <b>" + ms + " m/s</b>" : "");
      we = "Turku " + String(w.temp) + " °C" + (ms != null ? ", wind " + ms + " m/s" : "") + (w.wtype ? ", " + w.wtype : "");
    }
    $("l-wx").innerHTML = wf;
    var fb = b.source !== "broker";
    $("src-mode").className = "src mono " + (fb ? "off" : "on");
    $("src-mode").textContent = fb ? "Fallback cache, broker not answering" : "Read from the Orion-LD broker";
  }

  /* ---------- SSE ---------- */
  function connect() {
    var es = new EventSource("/api/aura/stream");
    es.addEventListener("hello", function (m) { JSON.parse(m.data).recent.forEach(function (n) { addNote(n, false); }); });
    es.addEventListener("positions", function (m) { var b = JSON.parse(m.data); if (ready) applyBrief(b); else { pendingBrief = b; renderStats(b); } });
    es.addEventListener("notification", function (m) { addNote(JSON.parse(m.data), true); loadSubs(); });
    es.onerror = function () { $("src-mode").className = "src mono off"; $("src-mode").textContent = "Connection lost, reconnecting"; };
  }
  connect();

  /* ---------- notifications ---------- */
  function addNote(n, fresh) {
    var ul = $("feed"); var e = ul.querySelector(".empty"); if (e) e.remove();
    var li = document.createElement("li"); if (fresh) li.className = "new";
    li.innerHTML = '<time>' + hhmmss(n.ts) + "</time>" + esc(n.title_en) + (n.others ? " (+" + n.others + ")" : "");
    ul.insertBefore(li, ul.firstChild);
    while (ul.children.length > 12) ul.lastChild.remove();
    if (fresh) setTimeout(function () { li.classList.remove("new"); }, 6000);
  }

  /* ---------- geofences ---------- */
  function circle(c, r, props) {
    var pts = [], dLat = r / 111320, dLon = r / (111320 * Math.cos(c[1] * Math.PI / 180));
    for (var i = 0; i <= 48; i++) { var a = i / 48 * 2 * Math.PI; pts.push([c[0] + dLon * Math.cos(a), c[1] + dLat * Math.sin(a)]); }
    return { type: "Feature", geometry: { type: "Polygon", coordinates: [pts] }, properties: props };
  }
  function drawFences() {
    if (!ready) return;
    var fs = geofences.map(function (p) { return circle(p.geo_center, p.geo_radius_m, { pending: p._pending ? 1 : 0 }); });
    map.getSource("fences").setData({ type: "FeatureCollection", features: fs });
  }

  /* ---------- subscriptions ---------- */
  var proposal = null, active = [];
  function loadSubs() {
    jget("/api/aura/subscriptions").then(function (r) {
      active = r.items; $("sub-count").textContent = active.length;
      $("subs").innerHTML = active.map(function (s) {
        return '<li><span>' + esc(s.description_en) + '<small>sent ' + (s.times_sent || 0) + '</small></span><button data-del="' + esc(s.subscription_id) + '" type="button">Delete</button></li>';
      }).join("");
      geofences = active.slice(); if (proposal) geofences.push(Object.assign({ _pending: true }, proposal)); drawFences();
    }).catch(function () {});
  }
  $("subs").addEventListener("click", function (e) {
    var id = e.target.getAttribute && e.target.getAttribute("data-del"); if (!id) return;
    fetch("/api/aura/subscriptions/" + encodeURIComponent(id), { method: "DELETE" }).then(loadSubs);
  });
  setInterval(loadSubs, 20000);

  function showProposal(p, fi, en) {
    proposal = p;
    $("proposal").hidden = !p;
    if (!p) { $("ask-gloss").textContent = en || ""; $("ask-gloss").style.color = ""; $("ask-text").placeholder = fi || ""; return; }
    $("prop-en").textContent = en;
    $("prop-tech").textContent = "Subscription · Vehicle[" + p.entity_type + "] · geoQ near;maxDistance==" + p.geo_radius_m + " · watchedAttributes location";
    map.flyTo({ center: p.geo_center, zoom: p.geo_radius_m > 1000 ? 12.6 : 14.2, duration: reduce ? 0 : 1200 });
    loadSubs();
  }
  $("ask").addEventListener("submit", function (e) {
    e.preventDefault();
    var t = $("ask-text").value.trim(); if (!t) return;
    $("ask-go").disabled = true; $("ask-gloss").textContent = "Aura is thinking...";
    jpost("/api/aura/ask", { text: t }).then(function (r) {
      $("ask-gloss").textContent = r.proposal ? "Aura proposes, you decide." : r.explanation_en;
      showProposal(r.proposal, r.explanation_en, r.explanation_en);
    }).catch(function (err) { $("ask-gloss").textContent = "The assistant did not answer."; })
      .then(function () { $("ask-go").disabled = false; });
  });
  $("prop-ok").addEventListener("click", function () {
    if (!proposal) return; $("prop-ok").disabled = true;
    jpost("/api/aura/subscriptions/" + proposal.id + "/approve").then(function () {
      proposal = null; $("proposal").hidden = true; $("ask-text").value = "";
      $("ask-gloss").textContent = "Subscription created in the broker. Notifications appear below."; loadSubs();
    }).catch(function () { $("ask-gloss").textContent = "Could not create the subscription."; })
      .then(function () { $("prop-ok").disabled = false; });
  });
  $("prop-no").addEventListener("click", function () {
    if (!proposal) return; var id = proposal.id;
    fetch("/api/aura/subscriptions/" + id + "/reject", { method: "POST" }); proposal = null; $("proposal").hidden = true; loadSubs();
  });
})();
