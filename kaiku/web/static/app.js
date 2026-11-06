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
  var biz = null;
  function renderBusiness(b) {
    if (!b) return;
    biz = b; paint();
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
  function stepsDone() { return Object.keys(seenSteps).filter(function (s) { return seenSteps[s] && ORDER.indexOf(s) >= 0; }).length; }

  /* ---------- before / after hero: one plain English headline, the Finnish line under it ---------- */
  var HOL = { "12-24": ["jouluaattona", "Christmas Eve"], "12-25": ["joulupäivänä", "Christmas Day"], "12-26": ["tapaninpäivänä", "Boxing Day"],
              "12-31": ["uudenvuodenaattona", "New Year's Eve"], "01-01": ["uudenvuodenpäivänä", "New Year's Day"], "11-08": ["isänpäivänä", "Father's Day"] };
  function dayInfo(date) {
    var h = HOL[date.slice(5)], d = parseInt(date.slice(8), 10) + "." + parseInt(date.slice(5, 7), 10) + ".";
    return { fi: h ? h[0] : d, en: h ? h[1] : d, d: d };
  }
  function spanEn(h) { return h.length ? span(h) : "closed"; }
  function regularFor(date) {
    if (!biz) return null;
    var wd = (new Date(date + "T12:00:00Z").getUTCDay() + 6) % 7;
    return biz.regular_hours[DAYS[wd][0]] || [];
  }
  function lastYearFor(date) {
    if (!biz) return null;
    var e = (biz.last_year_exceptions || []).filter(function (x) { return x.date.slice(5) === date.slice(5) && x.date.slice(0, 4) < date.slice(0, 4); })[0];
    return e ? (e.hours === "closed" ? [] : e.hours) : null;
  }
  var appliedFor = null;
  var applied = null;   // hours the owner approved (from the apply event), overrides the proposal
  function caps(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  function paint() {
    var date = (current && current.holiday_date) || $("date").value, di = dayInfo(date), reg = regularFor(date);
    var name = (biz && biz.name) || "Furry Paw Vet Clinic";
    var kind = current ? current.kind : null, hrs = null, finished = false, isDone = false;
    if (current) {
      hrs = (applied && appliedFor === current.id ? applied : null) || (current.kind === "closed" ? [] : current.proposed);
      isDone = current.status === "approved" || current.status === "edited" || current.status === "applied";
      finished = isDone || current.status === "declined";
    } else {
      hrs = lastYearFor(date);
    }
    var oldV = reg ? spanEn(reg) : "–", newEl = $("ba-new"), oldEl = $("ba-old");
    $("ba-old-v").textContent = oldV; oldEl.className = "ba-old" + (isDone ? " struck" : ""); oldEl.hidden = kind === "no_change";
    var en, fi, nv;
    if (kind === "no_change") {
      nv = "no change"; en = name + " keeps its regular hours on " + di.en + ". Nothing to change.";
      fi = caps(di.fi) + " " + name + " noudattaa tavallisia aukioloaikoja. Ei muutosta.";
    } else if (hrs) {
      nv = hrs.length ? span(hrs) : "closed";
      var verbEn = hrs.length ? "open " + span(hrs) : "closed", verbFi = hrs.length ? "auki klo " + span(hrs) : "suljettu";
      if (isDone) {
        en = name + " is " + verbEn + " on " + di.en + ". Saved to Connect, owner approved.";
        fi = caps(di.fi) + " " + name + " on " + verbFi + ". Tallennettu Connectiin, omistaja hyväksyi.";
      } else {
        en = name + " is " + (current ? "" : "likely ") + verbEn + " on " + di.en + ". Google still says " + oldV + ".";
        fi = caps(di.fi) + " " + name + " on " + (current ? "" : "todennäköisesti ") + verbFi + ". Google näyttää yhä " + (reg && reg.length ? span(reg) : "suljettu") + ".";
      }
    } else {
      nv = "ready"; en = "Run the chain to see what Kaiku proposes for " + di.en + " (" + di.d + ")."; fi = "Käynnistä ketju: Kaiku ehdottaa aukioloajat " + di.fi + " (" + di.d + ").";
    }
    var nb = function (t) { return t.replace(/(\d)-(\d)/g, "$1\u2060-\u2060$2"); };
    $("headline").textContent = nb(en); $("fi-line").textContent = nb(fi);
    $("ba-new-v").textContent = nv; newEl.className = "ba-new" + (current ? " live" : " idle");
    var du = current && current.decide_url, row = $("decide-row");
    row.hidden = !(du && !finished); if (du) $("decide-go").href = du;
  }
  function setCap(t) { $("big-cap").textContent = t; }

  var current = null;   // latest suggestion
  var seenSteps = {};
  function showSuggestion(s, finished) {
    if (!s) return;
    current = s;
    $("sentence").textContent = s.message_fi || "";
    $("gloss").textContent = s.message_en || "";
    var pct = Math.round(s.confidence * 100);
    paint();
    if (finished) {
      setCap(pct + " % sure \u00b7 " + pct + " % varma");
      arc.running = false; arc.target = s.confidence;
    } else {
      setCap(pct + " % sure \u00b7 " + stepsDone() + "/6 steps");
    }
  }
  function resetRun() {
    seenSteps = {}; current = null; applied = null; rows.innerHTML = ""; $("rows-empty").hidden = false;
    paint(); setCap("Scanning \u00b7 0/6 steps");
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
    if (live && !arc.running && (e.step === "detect" || (e.step === "broker" && e.detail && e.detail.kind === "missing"))) { setRunning(true); }
    $("rows-empty").hidden = true;
    var err = e.detail && e.detail.error;
    markDone();
    var li = document.createElement("li");
    li.className = "row" + (err ? " err" : "") + (live && !err && e.step !== "learn" ? " cur" : "");
    li.setAttribute("data-step", e.step);
    li.innerHTML = '<span class="dot"></span><span class="lab">' + (LABEL[e.step] || e.step) + '</span><span class="ttl">' + esc(e.title_en) +
      '<small lang="fi">' + esc(e.title_fi) + '</small>' + extra(e) + '</span><time>' + hhmmss(e.ts) + '</time>';
    rows.appendChild(li);
    if (e.step === "apply" && e.detail && e.detail.hours) { applied = e.detail.hours === "closed" ? [] : e.detail.hours; appliedFor = e.suggestion_id; if (current) paint(); }
    if (!live) return;
    seenSteps[e.step] = true;
    if (e.suggestion_id && (e.step === "suggest")) {
      jget("/api/suggestions/" + e.suggestion_id).then(function (s) { showSuggestion(s, false); }).catch(function () {});
    }
    if (e.step === "decide" && e.detail && e.detail.phase === "waiting") { delete seenSteps.decide; $("run").textContent = "Waiting for the owner"; }
    if (e.step === "apply" || (e.step === "decide" && e.detail && e.detail.phase === "decided")) {
      if (e.suggestion_id) jget("/api/suggestions/" + e.suggestion_id).then(function (s) { showSuggestion(s, !arc.running); }).catch(function () {});
    }
    if (arc.running) setCap((current ? Math.round(current.confidence * 100) + " % sure \u00b7 " : "") + stepsDone() + "/6 steps");
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
  $("date").addEventListener("change", function () { if (!arc.running) { current = null; applied = null; paint(); setCap("Ready"); arc.target = 0; } });
  $("st-toggle").addEventListener("click", function () {
    var o = $("statusbar").classList.toggle("open"); $("st-toggle").setAttribute("aria-expanded", o ? "true" : "false");
  });
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
    if (l.length) {
      var fin = ["applied", "declined", "expired"].indexOf(l[0].status) >= 0;
      seenSteps = fin ? { detect: 1, suggest: 1, contact: 1, decide: 1, apply: 1, learn: 1 } : { detect: 1, suggest: 1, contact: 1 };
      showSuggestion(l[0], l[0].status === "applied" || l[0].status === "declined");
    }
  }).catch(function () {});
  place(0);
  arc.raf = requestAnimationFrame(loop);
  connect();
})();
