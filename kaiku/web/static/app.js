/* Kaiku core UI: arc hero, live event strip (SSE), run button. Vanilla JS, no build step. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  /* header date label: every page has #today, only the home drives the rest */
  function loadToday() {
    var el = $("today"); if (!el) return;
    fetch("/api/today").then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (t) { el.textContent = t.label_fi; el.title = t.label_en; })
      .catch(function () { el.hidden = true; });
  }
  loadToday();
  if (!$("hero") || !$("arc-track") || !$("run") || !$("rows") || !$("reset")) return;  // not the home page: nothing to drive
  var LABEL = { detect: "DETECT", suggest: "SUGGEST", contact: "CONTACT", decide: "DECIDE", apply: "APPLY", learn: "LEARN", broker: "BROKER" };
  var ORDER = ["detect", "suggest", "contact", "decide", "apply", "learn"];
  var DAYS = [["mon", "Ma"], ["tue", "Ti"], ["wed", "Ke"], ["thu", "To"], ["fri", "Pe"], ["sat", "La"], ["sun", "Su"]];

  function jget(url) { return fetch(url).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function span(h) { return h.length ? h.map(function (s) { return parseInt(s.start, 10) + "-" + parseInt(s.end, 10); }).join(", ") : "suljettu"; }
  function hhmmss(ts) { var d = new Date(ts); if (isNaN(d)) return ""; var p = function (n) { return (n < 10 ? "0" : "") + n; }; return p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds()); }

  /* ---------- business card ---------- */
  function renderBusiness(b) {
    if (!b) return;
    $("b-name").textContent = b.name; $("b-addr").textContent = b.address; $("b-note").textContent = b.note || "";
    $("b-hours").innerHTML = DAYS.map(function (d) { return "<dt>" + d[1] + "</dt><dd>" + esc(span(b.regular_hours[d[0]] || [])) + "</dd>"; }).join("");
  }

  /* ---------- arc hero ---------- */
  var track = $("arc-track"), fill = $("arc-fill"), dot = $("dot"), halo = $("dot-halo");
  var LEN = track.getTotalLength();
  var rows = $("rows");
  var arc = { t: 0, running: false, done: 0, raf: 0, target: null };
  function place(t) {
    var p = track.getPointAtLength(LEN * Math.max(0, Math.min(1, t)));
    dot.setAttribute("cx", p.x); dot.setAttribute("cy", p.y); halo.setAttribute("cx", p.x); halo.setAttribute("cy", p.y);
    fill.setAttribute("stroke-dashoffset", 1 - Math.max(0.001, t));
  }
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  function loop(ts) {
    arc.raf = requestAnimationFrame(loop);
    if (arc.running) {
      var sweep = reduce ? arc.done / 6 : 0.5 - 0.5 * Math.cos(ts / 2400 * Math.PI * 2);
      arc.t = sweep; place(sweep);
    } else if (arc.target != null) {
      arc.t += (arc.target - arc.t) * 0.08;
      if (Math.abs(arc.target - arc.t) < 0.002) { arc.t = arc.target; arc.target = null; }
      place(arc.t);
    }
  }
  function setBig(html, cap) { $("big").innerHTML = html; $("big-cap").textContent = cap; }
  function stepsDone() { return Object.keys(seenSteps).filter(function (s) { return seenSteps[s] && ORDER.indexOf(s) >= 0; }).length; }

  var current = null;   // latest suggestion
  var seenSteps = {};
  function showSuggestion(s, finished) {
    if (!s) return;
    current = s;
    $("sentence").textContent = s.message_fi || "";
    $("gloss").textContent = s.message_en || "";
    var pct = Math.round(s.confidence * 100);
    if (finished) {
      setBig("5/5<small>steps</small>", pct + " % CONFIDENCE");
      var n = stepsDone();
      if (n >= 6) setBig(pct + "<small>%</small>", "CONFIDENCE, 6/6 STEPS");
      arc.running = false; arc.target = s.confidence;
    } else {
      setBig(pct + "<small>%</small>", "CONFIDENCE, " + stepsDone() + "/6 STEPS");
    }
  }
  function resetRun() {
    seenSteps = {}; current = null; rows.innerHTML = ""; $("rows-empty").hidden = false;
    setBig("&hellip;", "SCANNING, 0/6 STEPS");
    $("sentence").textContent = "Kaiku tarkistaa aukioloajat."; $("gloss").textContent = "Kaiku is checking the opening hours.";
  }
  function setRunning(on) {
    arc.running = on; $("run").disabled = on;
    $("run").textContent = on ? "Chain is running" : "Run the chain";
    if (on) { resetRun(); }
    else if (current) arc.target = current.confidence;
  }

  /* ---------- event strip ---------- */
  var runSid = null;
  function markDone() { Array.prototype.forEach.call(rows.querySelectorAll(".row.cur"), function (r) { r.classList.remove("cur"); }); }
  function extra(e) {
    var d = e.detail || {}, h = "";
    if (d.decide_url && (e.step === "contact" || d.phase === "waiting")) {
      h += '<small><a href="' + esc(d.decide_url) + '" target="_blank" rel="noopener" data-pilot="decide-link">Avaa päätöslinkki (omistajan näkymä)</a> <i>Open the decision link (owner view)</i></small>';
    }
    if (e.step === "apply" && d.where_it_shows && d.where_it_shows.length) {
      h += '<small>' + d.where_it_shows.filter(function (p) { return p.kind === "named"; }).map(function (p) { return esc(p.name); }).join(", ") +
        (d.verified ? " (sandbox, luettu takaisin / read back)" : " (sandbox)") + '</small>';
    }
    return h;
  }
  function addEvent(e, live) {
    if (live && e.step === "detect" && !arc.running) { setRunning(true); }
    $("rows-empty").hidden = true;
    var err = e.detail && e.detail.error;
    markDone();
    var li = document.createElement("li");
    li.className = "row" + (err ? " err" : "") + (live && !err && e.step !== "learn" ? " cur" : "");
    li.setAttribute("data-step", e.step);
    li.innerHTML = '<span class="dot"></span><span class="lab">' + (LABEL[e.step] || e.step) + '</span><span class="ttl">' + esc(e.title_fi) +
      '<small>' + esc(e.title_en) + '</small>' + extra(e) + '</span><time>' + hhmmss(e.ts) + '</time>';
    rows.appendChild(li);
    rows.scrollTop = rows.scrollHeight;
    if (!live) return;
    seenSteps[e.step] = true;
    if (e.suggestion_id && (e.step === "suggest")) {
      jget("/api/suggestions/" + e.suggestion_id).then(function (s) { showSuggestion(s, false); }).catch(function () {});
    }
    if (e.step === "decide" && e.detail && e.detail.phase === "waiting") { delete seenSteps.decide; }
    if (arc.running) $("big-cap").textContent = (current ? Math.round(current.confidence * 100) + " % CONFIDENCE, " : "") + stepsDone() + "/6 STEPS";
    if (err || e.step === "learn") {
      setRunning(false);
      if (e.suggestion_id) jget("/api/suggestions/" + e.suggestion_id).then(function (s) { showSuggestion(s, !err); }).catch(function () {});
    }
  }
  function connect() {
    var es = new EventSource("/api/events?replay=1&last=12"), replaying = true;
    es.addEventListener("kaiku", function (m) {
      var e = JSON.parse(m.data);
      var age = Date.now() - new Date(e.ts).getTime();
      addEvent(e, !replaying || age < 20000);
    });
    es.onopen = function () { $("conn").className = "mono live on"; $("conn").lastChild.textContent = "live"; setTimeout(function () { replaying = false; }, 400); };
    es.onerror = function () { $("conn").className = "mono live"; $("conn").lastChild.textContent = "reconnecting"; };
  }
  $("conn").innerHTML = "<i></i><span>connecting</span>";

  /* ---------- run ---------- */
  $("run").addEventListener("click", function () {
    var date = $("date").value;
    setRunning(true);
    fetch("/api/run?business=furry-paw&date=" + date, { method: "POST" }).then(function (r) { return r.json(); })
      .then(function (j) { runSid = j.suggestion_id; })
      .catch(function () { setRunning(false); setBig("!", "COULD NOT START"); });
  });

  /* ---------- status strip + reset ---------- */
  function setChip(id, text, ok) { var c = $(id); c.querySelector("b").textContent = text; c.className = "chip" + (ok ? " ok" : ""); }
  function loadStatus() {
    return jget("/api/status").then(function (s) {
      setChip("st-broker", s.broker === "orion-ld" ? "Orion-LD" : "varakäsittelijä", s.broker === "orion-ld");
      $("st-broker").title = s.broker === "orion-ld" ? "FIWARE NGSI-LD context broker Orion-LD is live" : "Orion-LD is not reachable, the in-memory fallback keeps the chain alive";
      setChip("st-wa", s.whatsapp_configured ? "käytössä" : "ei käytössä", s.whatsapp_configured);
      $("st-wa").title = s.whatsapp_configured ? "WhatsApp in use: the message goes to the owner's phone" : "WhatsApp not in use yet: the decision link is shown instead of a message";
      setChip("st-yext", s.yext_entity, true);
    }).catch(function () { if ($("st-broker")) setChip("st-broker", "no data", false); });
  }
  var rkey = "";  /* the reset key is never in the HTML: it only travels in ?key= and lives in sessionStorage */
  try {
    var qk = new URLSearchParams(location.search).get("key");
    if (qk) sessionStorage.setItem("kaikuKey", qk);
    rkey = sessionStorage.getItem("kaikuKey") || "";
  } catch (x) { rkey = new URLSearchParams(location.search).get("key") || ""; }
  $("reset").addEventListener("click", function () {
    var btn = $("reset"); btn.disabled = true; $("reset-msg").textContent = "Nollataan... / resetting...";
    fetch("/api/reset", { method: "POST", headers: rkey ? { "X-Kaiku-Key": rkey } : {} })
      .then(function (r) { if (r.status === 403) throw new Error("key"); return r.json(); }).then(function () { location.reload(); })
      .catch(function (err) {
        btn.disabled = false;
        $("reset-msg").textContent = err && err.message === "key" ? "Avain puuttuu, avaa sivu ?key=... / key needed, open the page with ?key=..." : "Nollaus epäonnistui / reset failed";
      });
  });

  /* ---------- boot ---------- */
  loadStatus();
  $("rows-empty").hidden = false;
  jget("/api/business/furry-paw").then(renderBusiness).catch(function () {});
  jget("/api/suggestions?business=furry-paw&limit=1").then(function (l) {
    if (l.length) { seenSteps = { detect: 1, suggest: 1, contact: 1, decide: 1, apply: 1, learn: 1 }; showSuggestion(l[0], l[0].status === "applied" || l[0].status === "declined"); }
  }).catch(function () {});
  place(0);
  arc.raf = requestAnimationFrame(loop);
  connect();
})();
