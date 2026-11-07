/* /fiware: every figure is fetched when the page loads (and the events by SSE). Read-only. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var root = document.querySelector(".fw"); if (!root) return;
  var EID = root.getAttribute("data-entity");
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function p2(n) { return (n < 10 ? "0" : "") + n; }
  function clock(d) { d = d || new Date(); return p2(d.getHours()) + ":" + p2(d.getMinutes()) + ":" + p2(d.getSeconds()); }
  function stamp(id) { var e = $(id); if (e) e.textContent = "read at " + clock(); }
  function jget(u) { return fetch(u, { headers: { Accept: "application/json" } }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  function offline(id, msg) { var e = $(id); if (!e) return; e.hidden = !msg; e.textContent = msg || ""; }
  var OFFLINE = "broker offline, fallback store in use";
  var states = { s1: "", s2: "" };

  // 1. the five datasetIds
  var rawJson = "";
  function renderEntity(d) {
    stamp("r1");
    offline("off1", d.broker_offline ? OFFLINE : "");
    var t = $("ds-table");
    if (!d.instances || !d.instances.length) {
      t.innerHTML = '<p class="empty">' + esc(d.message || "no data") + "</p>";
      rawJson = d.entity ? JSON.stringify(d.entity, null, 2) : "no data";
    } else {
      var h = '<div class="tr th" role="row"><span>datasetId</span><span>value</span><span>observedAt</span></div>';
      d.instances.forEach(function (r) {
        var label = r.is_default ? "default" : r.source;
        h += '<div class="tr' + (r.is_default ? " truth" : "") + '" role="row"><span class="src">' + esc(label) + "</span>" +
          '<span class="val">' + (r.date ? esc(r.date) + " " : "") + esc(r.hours) + (r.is_default ? '<span class="tag">THE TRUTH</span>' : "") +
          "<small>" + (r.datasetId ? esc(r.datasetId) : "no datasetId: the default instance") + (r.note ? " | " + esc(r.note) : "") + "</small></span>" +
          '<span class="obs">' + esc(r.observedAt || "no data") + "</span></div>";
      });
      t.innerHTML = h;
      rawJson = JSON.stringify(d.entity, null, 2);
    }
    states.s1 = d.broker_offline ? "broker offline, fallback store in use" : (d.source === "orion-ld" ? "Orion-LD live" : "no data");
    hero();
    if ($("raw").getAttribute("data-open")) $("raw").textContent = rawJson;
  }
  $("raw-toggle").addEventListener("click", function () {
    var r = $("raw"), open = r.hidden;
    r.hidden = !open; r.setAttribute("data-open", open ? "1" : "");
    this.setAttribute("aria-expanded", open ? "true" : "false");
    this.textContent = open ? "Hide raw NGSI-LD JSON" : "Show raw NGSI-LD JSON";
    if (open) r.textContent = rawJson || "no data";
  });
  function loadEntity() {
    return jget("/api/fiware/entity?id=" + encodeURIComponent(EID) + "&attrs=holidayHours,holidayHoursStatus,name").then(renderEntity)
      .catch(function () { stamp("r1"); $("ds-table").innerHTML = '<p class="empty">no data (the proxy did not answer)</p>'; });
  }

  // 2. subscriptions + events
  function loadSubs() {
    return jget("/api/fiware/subscriptions").then(function (d) {
      stamp("r2");
      offline("off2", d.broker_offline ? OFFLINE : "");
      var ul = $("subs");
      if (!d.items.length) { ul.innerHTML = '<li class="empty">' + esc(d.broker_offline ? "no data while the broker is offline" : "no subscriptions in the broker") + "</li>"; return; }
      ul.innerHTML = d.items.map(function (s) {
        var on = s.status === "active";
        return "<li><b>" + esc(s.name) + '</b><span class="st' + (on ? "" : " off") + '">' + esc(s.status) + "</span>" +
          "<small>watches " + esc((s.watched || []).join(", ") || "all attributes") + " &rarr; " + esc(s.endpoint || "no endpoint") + "</small></li>";
      }).join("");
    }).catch(function () { stamp("r2"); $("subs").innerHTML = '<li class="empty">no data</li>'; });
  }
  var evs = $("evs"), seen = {};
  function addEv(e, fresh) {
    if (e.step !== "broker" || seen[e.id]) return;
    seen[e.id] = 1;
    $("evs-empty").hidden = true;
    var li = document.createElement("li");
    li.className = fresh ? "new" : "";
    li.innerHTML = '<span class="dot"></span><span>' + esc(e.title_en) + "</span><time>" + clock(new Date(e.ts)) + "</time>";
    evs.appendChild(li);
    while (evs.children.length > 10) evs.removeChild(evs.firstChild);
    if (fresh) loadEntity();   // a write just happened: re-read the table
  }
  function startEvents() {
    jget("/api/fiware/events?limit=10").then(function (d) { d.items.forEach(function (e) { addEv(e, false); }); }).catch(function () {});
    if (!window.EventSource) return;
    var conn = $("conn"), es = new EventSource("/api/events");
    es.addEventListener("kaiku", function (m) { try { addEv(JSON.parse(m.data), true); } catch (x) { /* ignore */ } });
    es.onopen = function () { conn.className = "mono live on"; conn.lastChild.textContent = "live"; };
    es.onerror = function () { conn.className = "mono live"; conn.lastChild.textContent = "reconnecting"; };
  }

  // 3. MCP
  function loadMcp() {
    return jget("/api/fiware/mcp").then(function (d) {
      stamp("r3");
      offline("off3", d.error || "");
      $("tools").innerHTML = d.tools.length ? d.tools.map(function (t) {
        return "<li><b>" + esc(t.name) + "</b>" + (t.read_only ? "" : '<span class="w">WRITES PROPOSAL</span>') + "<small>" + esc(t.about) + "</small></li>";
      }).join("") : '<li class="empty">no data</li>';
      if (d.call) $("mcp-call").textContent = "tools/call " + d.call.tool + " " + JSON.stringify(d.call.arguments);
      $("mcp-out").textContent = d.example ? JSON.stringify(d.example, null, 2) : "no data";
    }).catch(function () { stamp("r3"); $("mcp-out").textContent = "no data"; });
  }

  // 4 + 5. Aura counts and broker version
  function loadAura() {
    return jget("/api/aura/status").then(function (d) {
      stamp("r4"); stamp("r5");
      var c = d.counts || {};
      $("c-bus").textContent = c.buses == null ? "no data" : c.buses;
      $("c-ship").textContent = c.ships == null ? "no data" : c.ships;
      $("c-wx").textContent = c.weather == null ? "no data" : (c.weather ? "observed" : "no data");
      $("aura-cap").textContent = d.last_polled ? "Captured " + d.last_polled + " (source: " + d.source + ")." : "Source: " + d.source + ".";
      $("ver").textContent = d.broker && d.broker !== "down" ? "Orion-LD " + d.broker : "broker down, no data";
    }).catch(function () { stamp("r4"); stamp("r5"); ["c-bus", "c-ship", "c-wx"].forEach(function (i) { $(i).textContent = "no data"; }); $("ver").textContent = "no data"; });
  }

  function hero() {
    var e = $("hero-state"); if (e) e.textContent = states.s1 ? "BROKER: " + states.s1 : "";
  }

  loadEntity(); loadSubs(); loadMcp(); loadAura(); startEvents();
})();
