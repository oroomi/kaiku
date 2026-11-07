/* Kaiku owner home: the hero (listing score, GET /api/score) and the SUGGESTIONS widget (GET /api/feed, Accept / Suggest a change).
   Vanilla JS, no build step. The chat lives in chat.js, ON FONECTA NOW in listing.js; they talk through window events. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var home = $("home"); if (!home || !$("arc-track")) return;
  var BIZ = home.getAttribute("data-biz") || "furry-paw";
  var DAYS = [["mon", "Mon"], ["tue", "Tue"], ["wed", "Wed"], ["thu", "Thu"], ["fri", "Fri"], ["sat", "Sat"], ["sun", "Sun"]];
  var ORDER = ["detect", "suggest", "contact", "decide", "apply", "learn"];
  function jget(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function nb(s) { return String(s).replace(/(\d)-(\d)/g, "$1⁠-⁠$2"); }   /* 9-13 never breaks across lines */
  function hm(t) { var p = String(t).split(":"), h = parseInt(p[0], 10); return p[1] && parseInt(p[1], 10) ? h + ":" + p[1] : String(h); }
  /* proposed -> "9-13", "closed", "6 dates", or "" */
  function hoursOf(p) {
    if (p == null) return "";
    if (p === "closed" || (Array.isArray(p) && !p.length)) return "closed";
    if (!Array.isArray(p)) return "";
    if (p[0] && p[0].date) return p.length + " dates";
    return p.map(function (s) { return hm(s.start) + "-" + hm(s.end); }).join(", ");
  }
  var DECIDED = { approved: 1, edited: 1, applied: 1 };

  /* ---------- state ---------- */
  var biz = null, items = [], evs = {}, steps = {}, chainRunning = false, chainTimer = 0, chatBusy = false, sc = null, loaded = false;

  /* ---------- hero: the listing score ---------- */
  var track = $("arc-track"), fill = $("arc-fill"), dot = $("dot"), halo = $("dot-halo");
  var LEN = track.getTotalLength(), arc = { t: 0, target: 0 };
  function place(t) {
    var p = track.getPointAtLength(LEN * Math.max(0, Math.min(1, t)));
    dot.setAttribute("cx", p.x); dot.setAttribute("cy", p.y); halo.setAttribute("cx", p.x); halo.setAttribute("cy", p.y);
    fill.setAttribute("stroke-dashoffset", 1 - Math.max(0.001, t));
  }
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var shownN = 0, numTarget = 0;
  function loop(ts) {
    requestAnimationFrame(loop);
    if ((chainRunning || chatBusy || !sc) && !reduce) { arc.t = 0.5 - 0.5 * Math.cos(ts / 2400 * Math.PI * 2); place(arc.t); }
    else if (Math.abs(arc.target - arc.t) > 0.002) { arc.t += (arc.target - arc.t) * 0.06; place(arc.t); }
    if (sc && shownN !== numTarget) {   /* the big number follows the dot */
      shownN += (numTarget - shownN) * 0.12; if (Math.abs(numTarget - shownN) < 0.5) shownN = numTarget;
      $("score-n").textContent = String(Math.round(shownN));
    }
  }
  var HOL = { "12-24": "Christmas", "12-25": "Christmas", "12-26": "Christmas", "12-31": "New Year's Eve", "01-01": "New Year", "01-06": "Epiphany" };
  function dm(date) { return parseInt(date.slice(8), 10) + "." + parseInt(date.slice(5, 7), 10) + "."; }
  function whenOf(list) {
    var d = list.map(function (i) { return i.holiday_date; }).filter(Boolean).sort()[0];
    return d ? (HOL[d.slice(5)] || dm(d)) : "";
  }
  function pendingItems() { return items.filter(function (i) { return i.kind !== "no_change" && (i.status || "proposed") !== "approved" && i.status !== "declined" && i.status !== "edited" && i.status !== "applied" && i.status !== "info"; }); }
  function paint() {
    var name = (biz && biz.name) || "Furry Paw Vet Clinic", en;
    if (!sc) { $("headline").textContent = nb(name + ": reading the listing."); return; }
    var pend = (sc.pending || []).length, list = pendingItems();
    if (!pend) en = name + ": nothing to fix.";
    else { var w = whenOf(list); en = name + ": " + pend + (pend === 1 ? " thing" : " things") + " to fix" + (w ? " before " + w : "") + "."; }
    $("headline").textContent = nb(en);
    arc.target = Math.max(0, Math.min(100, sc.score)) / 100; numTarget = sc.score;
    if (reduce) { shownN = numTarget; $("score-n").textContent = String(numTarget); }
    $("big-cap").textContent = (sc.label_en || "").toUpperCase() + " · " + sc.checks_ok + " OF " + sc.checks_total + " CHECKS";
    $("score-n").setAttribute("title", "Listing score " + sc.score + " of 100. " + sc.checks.map(function (c) { return (c.ok ? "ok: " : "fix: ") + c.label_en; }).join("; "));
    var du = evs.decide_url && pend ? evs.decide_url : "";
    $("decide-row").hidden = !du; if (du) $("decide-go").href = du;
  }
  var scoreBusy = false;
  function loadScore(fresh) {
    if (scoreBusy && !fresh) return Promise.resolve(); scoreBusy = true;
    return jget("/api/score/" + encodeURIComponent(BIZ) + (fresh ? "?fresh=1" : "")).then(function (j) { sc = j; paint(); window.dispatchEvent(new CustomEvent("kaiku:score", { detail: j })); })
      .catch(function () { /* keep the last score on screen */ }).then(function () { scoreBusy = false; });
  }

  /* ---------- suggestions widget ---------- */
  var SRC = { lastyear: "last year", google: "Google", peers: "peers", website: "website", yext: "Yext", regular: "regular hours" };
  var KIND = { holiday_hours: "Holiday hours", conflict: "Conflict", period: "Period", no_change: "No change", description: "Description", review: "Review" };
  function statusOf(i) {
    if (DECIDED[i.status]) return ["approved", "approved"];
    if (i.status === "declined") return ["declined", "declined"];
    if (i.kind === "no_change" || i.status === "info") return ["info", "info"];
    return ["proposed", "proposed"];
  }
  function card(i) {
    var st = statusOf(i), text = typeof i.proposed === "string" && i.proposed !== "closed" ? i.proposed : "";
    var h = i.kind === "no_change" ? "no change" : text ? "" : hoursOf(i.proposed);
    var seen = {}, src = (i.reasons || []).map(function (r) { return r.source; }).filter(function (s) { if (!s || seen[s]) return false; seen[s] = 1; return true; })
      .map(function (s) { return esc(SRC[s] || String(s).replace(/_/g, " ")); });
    var conf = i.confidence != null ? '<span class="mono sg-conf">' + Math.round(i.confidence * 100) + " % sure</span>" : "";
    var acts = st[0] === "proposed" ? '<div class="sg-acts"><button type="button" class="sg-accept" data-act="accept">Accept</button><button type="button" class="sg-change" data-act="change">Suggest a change</button></div>' : "";
    return '<article class="sg" data-kind="' + esc(i.kind) + '" data-status="' + st[0] + '" data-id="' + esc(i.id) + '" id="sg-' + esc(i.id) + '">' +
      '<div class="sg-top"><span class="mono sg-kind">' + esc(KIND[i.kind] || String(i.kind).replace(/_/g, " ")) + '</span><span class="mono sg-st st-' + st[0] + '">' + st[1] + "</span></div>" +
      "<h3>" + nb(esc(i.title_en || "")) + "</h3>" + (i.text_en ? '<p class="sg-text">' + nb(esc(i.text_en)) + "</p>" : "") +
      (text ? '<blockquote class="sg-quote">' + nb(esc(text)) + "</blockquote>" : "") +
      '<div class="sg-meta">' + (h ? '<span class="mono sg-hours">' + nb(esc(h)) + "</span>" : "") + conf + "</div>" +
      (src.length ? '<p class="mono sg-src">' + src.join(" · ") + "</p>" : "") + acts + "</article>";
  }
  function renderSuggestions() {
    var busy = {};   /* keep a card's "working" state across the 10 s refresh */
    Array.prototype.forEach.call(document.querySelectorAll(".sg.working"), function (el) { busy[el.getAttribute("data-id")] = 1; });
    $("sug-grid").innerHTML = items.map(card).join("");
    Object.keys(busy).forEach(function (id) { var el = document.querySelector('.sg[data-id="' + id.replace(/"/g, "") + '"]'); if (el) setWorking(el, true); });
    $("sug-empty").hidden = !(loaded && !items.length);
    $("sug-count").textContent = items.length ? items.length + (items.length === 1 ? " item" : " items") : "";
    window.dispatchEvent(new CustomEvent("kaiku:feed", { detail: items }));
  }
  function setWorking(el, on) {
    el.classList.toggle("working", on);
    Array.prototype.forEach.call(el.querySelectorAll("button"), function (b) { b.disabled = on; });
    var a = el.querySelector(".sg-accept"); if (a) a.textContent = on ? "Saving..." : "Accept";
  }
  $("sug-grid").addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("button[data-act]"); if (!b) return;
    var el = b.closest(".sg"), id = el.getAttribute("data-id"), i = items.filter(function (x) { return x.id === id; })[0];
    if (b.getAttribute("data-act") === "accept") {
      setWorking(el, true);
      window.dispatchEvent(new CustomEvent("kaiku:accept", { detail: { id: id, item: i, done: function () { setWorking(el, false); } } }));
    } else {
      window.dispatchEvent(new CustomEvent("kaiku:change", { detail: { id: id, item: i } }));
    }
  });
  var feedBusy = false;
  /* the first paint asks without the network signals (fast); the full feed follows and replaces it */
  function loadFeed(quick) {
    if (feedBusy) return Promise.resolve(); feedBusy = true;
    return jget("/api/feed/" + encodeURIComponent(BIZ) + (quick ? "?network=0" : "")).then(function (f) { items = f.suggestions || []; })
      .catch(function () { /* keep what is on screen */ })
      .then(function () { feedBusy = false; loaded = true; renderSuggestions(); paint(); });
  }
  function changed() { loadFeed(); loadScore(true); window.dispatchEvent(new CustomEvent("kaiku:refresh", { detail: { fresh: true } })); }

  /* ---------- chain events: step tracking, the decision link, and the contact ladder lines for the chat ---------- */
  var seenEv = {}, ladder = [];
  function pick(d, keys) { for (var i = 0; i < keys.length; i++) if (typeof d[keys[i]] === "string" && d[keys[i]].trim()) return d[keys[i]].trim(); return ""; }
  function chanOf(e, d) {
    var c = String(d.channel || "").toLowerCase();
    if (/^(email|whatsapp|call)$/.test(c)) return c;
    var t = (e.title_en || "").toLowerCase();
    return /^call|phon/.test(t) ? "call" : /email/.test(t) ? "email" : /whatsapp/.test(t) ? "whatsapp" : "";
  }
  function hhmm(ts) {
    try { return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Helsinki", hour12: false }).format(new Date(ts)); } catch (e) { return ""; }
  }
  function addEvent(e) {
    if (e.id != null) { if (seenEv[e.id]) return false; seenEv[e.id] = 1; }
    if (e.business_id && e.business_id !== BIZ) return false;
    if (e.suggestion_id && ORDER.indexOf(e.step) >= 0) steps[e.step] = e.suggestion_id;
    var d = e.detail || {};
    if ((e.step === "decide" || e.step === "contact") && d.decide_url) evs.decide_url = d.decide_url;
    if (e.step === "contact" && !d.degraded && d.phase !== "waiting") {   /* degraded = nothing left the building */
      var c = chanOf(e, d);
      if (c) { ladder.push({ ch: c, at: hhmm(e.ts), ts: Date.parse(e.ts) || 0 }); return true; }
    }
    return false;
  }
  function sendLadder() {
    ladder.sort(function (a, b) { return a.ts - b.ts; });
    var txt = ladder.map(function (x) { return (x.ch === "call" ? "CALL" : x.ch.toUpperCase() + " SENT") + " " + x.at; }).join(" · ");
    window.dispatchEvent(new CustomEvent("kaiku:sysline", { detail: { id: "ladder", text: txt } }));
  }
  var scheduled = 0;
  function onEvent(e, live) {
    var isLadder = addEvent(e);
    if (isLadder && !scheduled) scheduled = setTimeout(function () { scheduled = 0; sendLadder(); }, 80);
    if (live) {
      if (e.step === "detect") { chainRunning = true; clearTimeout(chainTimer); chainTimer = setTimeout(function () { chainRunning = false; }, 60000); }
      if (e.step === "learn" || (e.detail && e.detail.error)) { chainRunning = false; clearTimeout(chainTimer); }
      if (e.step === "suggest" || e.step === "decide" || e.step === "apply" || e.step === "learn") { loadFeed(); if (e.step === "apply" || e.step === "decide" || e.step === "learn") { loadScore(true); window.dispatchEvent(new CustomEvent("kaiku:refresh", { detail: { fresh: true } })); } }
    }
  }
  jget("/api/events/recent?limit=200&business=" + encodeURIComponent(BIZ)).then(function (l) { l.forEach(function (e) { onEvent(e, false); }); }).catch(function () {})
    .then(function () {
      if (!window.EventSource) return;
      var es = new EventSource("/api/events?replay=1&last=60");
      es.addEventListener("kaiku", function (m) { var e = JSON.parse(m.data); onEvent(e, Date.now() - new Date(e.ts).getTime() < 20000); });
    });

  /* ---------- the chat widget talks to us ---------- */
  window.addEventListener("kaiku:busy", function (m) { chatBusy = !!(m.detail && m.detail.on); });
  window.addEventListener("kaiku:decided", function () { changed(); setTimeout(changed, 2500); });

  /* ---------- boot ---------- */
  jget("/api/business/" + encodeURIComponent(BIZ)).then(function (b) { biz = b; paint(); }).catch(function () {});
  loadScore(); loadFeed(true).then(function () { return loadFeed(); });
  setInterval(function () { if (!document.hidden) { loadFeed(); loadScore(); } }, 10000);
  place(0); requestAnimationFrame(loop); paint();
})();
