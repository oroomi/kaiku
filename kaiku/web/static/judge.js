/* Kaiku judge view: the live event feed, broker status, and the Yext read-back line. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var rows = $("rows"); if (!rows) return;
  var LABEL = { detect: "DETECT", suggest: "SUGGEST", contact: "CONTACT", decide: "DECIDE", apply: "APPLY", learn: "LEARN", broker: "BROKER" };
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function hhmmss(ts) { var d = new Date(ts); if (isNaN(d)) return ""; var p = function (n) { return (n < 10 ? "0" : "") + n; }; return p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds()); }
  function jget(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  function hrs(h) { return h === "closed" || !h || !h.length ? "closed" : h.map(function (s) { return parseInt(s.start, 10) + "-" + parseInt(s.end, 10); }).join(", "); }

  function extra(e) {
    var d = e.detail || {}, h = "";
    if (d.decide_url && (e.step === "contact" || d.phase === "waiting")) {
      h += '<small><a href="' + esc(d.decide_url) + '" target="_blank" rel="noopener" data-pilot="decide-link">Open the decision link (owner view)</a></small>';
    }
    if (e.step === "decide" && d.via) h += "<small>via " + esc(d.via) + "</small>";
    if (e.step === "apply" && d.where_it_shows && d.where_it_shows.length) {
      h += "<small>" + d.where_it_shows.filter(function (p) { return p.kind === "named"; }).map(function (p) { return esc(p.name); }).join(", ") + (d.verified ? " (sandbox, read back)" : " (sandbox)") + "</small>";
    }
    return h;
  }
  function readback(e) {
    var d = e.detail || {};
    if (!d.hours && d.yext_status !== "ok") return;
    var day = (e.title_en.match(/\((\d+\.\d+\.)\)/) || [])[1] || "";
    $("readback-t").textContent = (d.yext_status === "ok" ? (d.verified ? "Read back and verified at " : "Written, not read back, at ") : "Not written, ") + hhmmss(e.ts) + ": " +
      (d.entity || "SinceAI07") + (d.environment ? " (" + d.environment + ")" : "") + (day ? ", " + day : "") + (d.hours ? " " + hrs(d.hours) : "") + ".";
  }
  function add(e, live) {
    $("rows-empty").hidden = true;
    var err = e.detail && e.detail.error;
    Array.prototype.forEach.call(rows.querySelectorAll(".row.cur"), function (r) { r.classList.remove("cur"); });
    var li = document.createElement("li");
    li.className = "row" + (err ? " err" : "") + (live && !err && e.step !== "learn" ? " cur" : "");
    li.setAttribute("data-step", e.step);
    li.innerHTML = '<span class="dot"></span><span class="lab">' + (LABEL[e.step] || e.step) + '</span><span class="ttl">' + esc(e.title_en) + extra(e) + "</span><time>" + hhmmss(e.ts) + "</time>";
    rows.appendChild(li);
    if (e.step === "apply") readback(e);
  }
  var conn = $("conn");
  var es = new EventSource("/api/events?replay=1&last=40"), replaying = true;
  es.addEventListener("kaiku", function (m) { var e = JSON.parse(m.data); add(e, !replaying || Date.now() - new Date(e.ts).getTime() < 20000); });
  es.onopen = function () { conn.className = "mono live on"; conn.lastChild.textContent = "live"; setTimeout(function () { replaying = false; }, 400); };
  es.onerror = function () { conn.className = "mono live"; conn.lastChild.textContent = "reconnecting"; };

  function chip(id, text, ok) { var c = $(id); c.querySelector("b").textContent = text; c.className = "chip" + (ok ? " ok" : ""); }
  jget("/api/status").then(function (s) {
    chip("st-broker", s.broker === "orion-ld" ? "Orion-LD" : "fallback", s.broker === "orion-ld");
    chip("st-wa", s.whatsapp_configured ? "in use" : "not in use", s.whatsapp_configured);
    chip("st-yext", s.yext_entity, true);
  }).catch(function () { chip("st-broker", "no data", false); });
})();
