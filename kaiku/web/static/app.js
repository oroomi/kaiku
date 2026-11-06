/* Kaiku core UI: arc hero, live event strip (SSE), run button. Vanilla JS, no build step. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var LABEL = { detect: "DETECT", suggest: "SUGGEST", contact: "CONTACT", decide: "DECIDE", apply: "APPLY", learn: "LEARN", broker: "BROKER" };
  var ORDER = ["detect", "suggest", "contact", "decide", "apply", "learn"];
  var DAYS = [["mon", "Ma"], ["tue", "Ti"], ["wed", "Ke"], ["thu", "To"], ["fri", "Pe"], ["sat", "La"], ["sun", "Su"]];

  function jget(url) { return fetch(url).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function span(h) { return h.length ? h.map(function (s) { return parseInt(s.start, 10) + "-" + parseInt(s.end, 10); }).join(", ") : "suljettu"; }
  function hhmmss(ts) { var d = new Date(ts); return isNaN(d) ? "" : d.toLocaleTimeString("fi-FI", { hour12: false }); }

  /* ---------- business card ---------- */
  function renderBusiness(b) {
    if (!b) return;
    $("b-name").textContent = b.name; $("b-addr").textContent = b.address; $("b-note").textContent = b.note || "";
    $("b-hours").innerHTML = DAYS.map(function (d) { return "<dt>" + d[1] + "</dt><dd>" + esc(span(b.regular_hours[d[0]] || [])) + "</dd>"; }).join("");
  }

  /* ---------- today ---------- */
  function loadToday() { jget("/api/today").then(function (t) { $("today").textContent = t.label_fi; }).catch(function () { $("today").textContent = "Tänään: no data"; }); }

  /* ---------- arc hero ---------- */
  var track = $("arc-track"), fill = $("arc-fill"), dot = $("dot"), halo = $("dot-halo");
  var LEN = track.getTotalLength();
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
  function setRunning(on) {
    arc.running = on; $("run").disabled = on;
    $("run").textContent = on ? "Chain is running" : "Run the chain";
    if (on) { seenSteps = {}; setBig("&hellip;", "SCANNING"); }
    else if (current) arc.target = current.confidence;
  }

  /* ---------- event strip ---------- */
  var rows = $("rows"), runSid = null;
  function markDone() { Array.prototype.forEach.call(rows.querySelectorAll(".row.cur"), function (r) { r.classList.remove("cur"); }); }
  function addEvent(e, live) {
    $("rows-empty").hidden = true;
    var err = e.detail && e.detail.error;
    markDone();
    var li = document.createElement("li");
    li.className = "row" + (err ? " err" : "") + (live && !err && e.step !== "learn" ? " cur" : "");
    li.setAttribute("data-step", e.step);
    li.innerHTML = '<span class="dot"></span><span class="lab">' + (LABEL[e.step] || e.step) + '</span><span class="ttl">' + esc(e.title_fi) +
      '<small>' + esc(e.title_en) + '</small></span><time>' + hhmmss(e.ts) + '</time>';
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
    } else if (!arc.running && e.step === "detect") { setRunning(true); }
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

  /* ---------- boot ---------- */
  $("rows-empty").hidden = false;
  loadToday();
  jget("/api/business/furry-paw").then(renderBusiness).catch(function () {});
  jget("/api/suggestions?business=furry-paw&limit=1").then(function (l) {
    if (l.length) { seenSteps = { detect: 1, suggest: 1, contact: 1, decide: 1, apply: 1, learn: 1 }; showSuggestion(l[0], l[0].status === "applied" || l[0].status === "declined"); }
  }).catch(function () {});
  place(0);
  arc.raf = requestAnimationFrame(loop);
  connect();
})();
