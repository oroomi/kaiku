/* Kaiku owner home: the hero (headline, arc, before/after), the SUGGESTIONS widget (GET /api/feed) and the conversation THREAD (events + web chat).
   Vanilla JS, no build step. The chat widget itself lives in chat.js and talks to this file through window events. */
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
  var biz = null, items = [], evs = {}, steps = {}, chainRunning = false, chainTimer = 0, chatBusy = false;

  /* ---------- hero ---------- */
  var track = $("arc-track"), fill = $("arc-fill"), dot = $("dot"), halo = $("dot-halo");
  var LEN = track.getTotalLength(), arc = { t: 0, target: 0 };
  function place(t) {
    var p = track.getPointAtLength(LEN * Math.max(0, Math.min(1, t)));
    dot.setAttribute("cx", p.x); dot.setAttribute("cy", p.y); halo.setAttribute("cx", p.x); halo.setAttribute("cy", p.y);
    fill.setAttribute("stroke-dashoffset", 1 - Math.max(0.001, t));
  }
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  function loop(ts) {
    requestAnimationFrame(loop);
    if ((chainRunning || chatBusy) && !reduce) { arc.t = 0.5 - 0.5 * Math.cos(ts / 2400 * Math.PI * 2); place(arc.t); }
    else if (Math.abs(arc.target - arc.t) > 0.002) { arc.t += (arc.target - arc.t) * 0.08; place(arc.t); }
  }
  var HOL = { "12-24": "Christmas Eve", "12-25": "Christmas Day", "12-26": "Boxing Day", "12-31": "New Year's Eve", "01-01": "New Year's Day", "01-06": "Epiphany", "11-08": "Father's Day" };
  function dayLabel(date) { return HOL[date.slice(5)] || (parseInt(date.slice(8), 10) + "." + parseInt(date.slice(5, 7), 10) + "."); }
  function dm(date) { return parseInt(date.slice(8), 10) + "." + parseInt(date.slice(5, 7), 10) + "."; }
  function regularFor(date) {
    if (!biz || !biz.regular_hours) return null;
    var wd = (new Date(date + "T12:00:00Z").getUTCDay() + 6) % 7;
    var h = biz.regular_hours[DAYS[wd][0]] || [];
    return hoursOf(h.length ? h : "closed");
  }
  function lead() {
    var act = items.filter(function (i) { return i.kind !== "no_change"; });
    return act.filter(function (i) { return i.kind === "holiday_hours" || i.kind === "conflict"; })[0] || act[0] || null;
  }
  function idsOf(i) { return [i.id, i.suggestion_id].filter(Boolean); }
  function stepCount(i) { var n = 0; ORDER.forEach(function (s) { if (steps[s] && i && idsOf(i).indexOf(steps[s]) >= 0) n++; }); return n; }
  function setCap(t) { $("big-cap").textContent = t; }
  function paint() {
    var name = (biz && biz.name) || "Furry Paw Vet Clinic", L = lead(), nc = items.filter(function (i) { return i.kind === "no_change"; })[0];
    var oldEl = $("ba-old"), newEl = $("ba-new"), en, nv, oldV = "–", done = false;
    if (L) {
      var date = L.holiday_date || "", st = L.status || "proposed", hrs = hoursOf(L.proposed);
      var reg = date ? regularFor(date) : null;
      done = !!DECIDED[st]; oldV = reg || "–";
      var when = date ? dayLabel(date) : L.title_en;
      if (st === "declined") { nv = "no change"; en = name + " keeps its regular hours on " + when + ". The owner said no thanks."; }
      else if (hrs === "closed") { nv = "closed"; en = name + " is closed on " + when + (done ? ". Saved to Connect, owner approved." : ". Everywhere Connect publishes still says " + oldV + "."); }
      else if (hrs && L.kind !== "period") { nv = hrs; en = name + " is open " + hrs + " on " + when + (done ? ". Saved to Connect, owner approved." : ". Everywhere Connect publishes still says " + oldV + "."); }
      else { nv = hrs || "ready"; en = name + ": " + (L.title_en || "a suggestion is ready") + "."; }
      var pct = Math.round((L.confidence || 0) * 100), n = stepCount(L);
      setCap(pct + " % sure" + (n ? " · " + n + "/6 steps" : "")); arc.target = L.confidence || 0;
      var du = evs.decide_url && !done && st !== "declined" ? evs.decide_url : "";
      $("decide-row").hidden = !du; if (du) $("decide-go").href = du;
      newEl.className = "ba-new live";
    } else if (nc) {
      nv = "no change"; en = name + " keeps its regular hours" + (nc.holiday_date ? " on " + dayLabel(nc.holiday_date) : "") + ". Nothing to change.";
      oldEl.hidden = true; setCap("No change needed"); arc.target = nc.confidence || 0; newEl.className = "ba-new live"; $("decide-row").hidden = true;
    } else {
      nv = "ready"; en = items.length || !loaded ? name + ": checking the next holiday." : name + ": nothing to suggest right now.";
      setCap("READY"); arc.target = 0; newEl.className = "ba-new idle"; $("decide-row").hidden = true;
    }
    if (L) oldEl.hidden = false;
    $("ba-old-v").textContent = oldV; oldEl.className = "ba-old" + (done ? " struck" : "");
    $("headline").textContent = nb(en); $("ba-new-v").textContent = nv;
  }

  /* ---------- suggestions widget ---------- */
  var loaded = false;
  var SRC = { lastyear: "last year", google: "Google", peers: "peers", website: "website", yext: "Yext", regular: "regular hours" };
  var KIND = { holiday_hours: "Holiday hours", conflict: "Conflict", period: "Period", no_change: "No change", description: "Description", review: "Review" };
  function statusOf(i) {
    if (DECIDED[i.status]) return ["approved", "approved"];
    if (i.status === "declined") return ["declined", "declined"];
    if (i.kind === "no_change" || i.status === "info") return ["info", "info"];
    return ["proposed", "proposed"];
  }
  function card(i) {
    var st = statusOf(i), h = i.kind === "no_change" ? "no change" : hoursOf(i.proposed);
    var seen = {}, src = (i.reasons || []).map(function (r) { return r.source; }).filter(function (s) { if (!s || seen[s]) return false; seen[s] = 1; return true; })
      .map(function (s) { return esc(SRC[s] || String(s).replace(/_/g, " ")); });
    var conf = i.confidence != null ? '<span class="mono sg-conf">' + Math.round(i.confidence * 100) + " % sure</span>" : "";
    return '<article class="sg" data-kind="' + esc(i.kind) + '" data-status="' + st[0] + '" data-id="' + esc(i.id) + '">' +
      '<div class="sg-top"><span class="mono sg-kind">' + esc(KIND[i.kind] || String(i.kind).replace(/_/g, " ")) + '</span><span class="mono sg-st st-' + st[0] + '">' + st[1] + "</span></div>" +
      "<h3>" + nb(esc(i.title_en || "")) + "</h3>" + (i.text_en ? '<p class="sg-text">' + nb(esc(i.text_en)) + "</p>" : "") +
      '<div class="sg-meta">' + (h ? '<span class="mono sg-hours">' + nb(esc(h)) + "</span>" : "") + conf + "</div>" +
      (src.length ? '<p class="mono sg-src">' + src.join(" · ") + "</p>" : "") + "</article>";
  }
  function renderSuggestions() {
    $("sug-grid").innerHTML = items.map(card).join("");
    $("sug-empty").hidden = !(loaded && !items.length);
    $("sug-count").textContent = items.length ? items.length + (items.length === 1 ? " item" : " items") : "";
  }
  var feedBusy = false;
  /* the first paint asks without the network signals (fast); the full feed follows and replaces it */
  function loadFeed(quick) {
    if (feedBusy) return Promise.resolve(); feedBusy = true;
    return jget("/api/feed/" + encodeURIComponent(BIZ) + (quick ? "?network=0" : "")).then(function (f) { items = f.suggestions || []; })
      .catch(function () { /* keep what is on screen */ })
      .then(function () { feedBusy = false; loaded = true; renderSuggestions(); paint(); });
  }

  /* ---------- conversation thread ---------- */
  var CH = { email: "EMAIL", whatsapp: "WHATSAPP", call: "CALL", web: "WEB", voice: "WEB" };
  var seenEv = {}, ents = [], web = [];
  try { web = JSON.parse(sessionStorage.getItem("kaikuWeb") || "[]"); } catch (e) { web = []; }
  function saveWeb() { try { sessionStorage.setItem("kaikuWeb", JSON.stringify(web.slice(-60))); } catch (e) {} }
  function pick(d, keys) { for (var i = 0; i < keys.length; i++) if (typeof d[keys[i]] === "string" && d[keys[i]].trim()) return d[keys[i]].trim(); return ""; }
  function chanOf(e, d) {
    var c = String(d.channel || (d.decision && d.decision.via) || d.via || "").toLowerCase();
    if (CH[c]) return c;
    var t = (e.title_en || "").toLowerCase();
    return /^call|phon/.test(t) ? "call" : /email/.test(t) ? "email" : /whatsapp/.test(t) ? "whatsapp" : "";
  }
  function toEntry(e) {
    var d = e.detail || {}, ts = Date.parse(e.ts) || 0, c = chanOf(e, d);
    if (e.step === "contact") {
      var m = pick(d, ["message_en", "message", "text", "body"]);
      if (!m && d.degraded) return null;                      /* nothing left the building: not a message */
      return { id: e.id, ts: ts, who: "kaiku", ch: c || "whatsapp", text: m || e.title_en };
    }
    if (e.step === "decide") {
      if (d.phase === "waiting") return null;
      return { id: e.id, ts: ts, who: "owner", ch: c || "web", text: pick(d, ["answer", "reply", "text", "message"]) || e.title_en, decide: true };
    }
    if (e.step === "apply") return { id: e.id, ts: ts, who: "kaiku", ch: "", text: pick(d, ["receipt", "message_en", "text"]) || e.title_en, apply: true };
    return null;
  }
  function addEvent(e) {
    if (e.id != null) { if (seenEv[e.id]) return; seenEv[e.id] = 1; }
    if (e.business_id && e.business_id !== BIZ) return;
    if (e.suggestion_id && ORDER.indexOf(e.step) >= 0) { steps[e.step] = e.suggestion_id; }
    if (e.step === "decide" && e.detail && e.detail.decide_url) evs.decide_url = e.detail.decide_url;
    if (e.step === "contact" && e.detail && e.detail.decide_url) evs.decide_url = e.detail.decide_url;
    var en = toEntry(e); if (en) ents.push(en);
    return en;
  }
  function render() {
    var all = ents.concat(web.map(function (w) { return { ts: w.ts, who: w.role === "user" ? "owner" : "kaiku", ch: "web", text: w.text }; }));
    all.forEach(function (x, i) { x._i = i; });
    all.sort(function (a, b) { return a.ts - b.ts || a._i - b._i; });
    /* a chat-made decision is already in the thread as the owner's WEB message */
    all = all.filter(function (x) { return !(x.decide && x.ch === "web" && all.some(function (w) { return !w.decide && w.ch === "web" && w.who === "owner" && Math.abs(w.ts - x.ts) < 90000; })); });
    var log = $("thread-log"), near = log.scrollHeight - log.scrollTop - log.clientHeight < 60, n = log.querySelectorAll(".tb").length;
    var last = "web";
    all.forEach(function (x) { if (x.ch) last = x.ch; else x.ch = last; });
    var html = all.map(function (x) {
      return '<div class="tb ' + (x.who === "owner" ? "tb-o" : "tb-k") + '"><span class="mono tb-ch">' + (x.who === "owner" ? "Owner · " : "Kaiku · ") + (CH[x.ch] || "WEB") +
        '</span><div class="b">' + nb(esc(x.text)) + "</div></div>";
    }).join("");
    log.innerHTML = (all.length ? "" : '<p class="empty" id="thread-empty">Nothing sent yet.</p>') + html;
    if (all.length !== n && (near || n === 0)) log.scrollTop = log.scrollHeight;
  }

  /* ---------- events: initial list, then live ---------- */
  var scheduled = 0;
  function later() { if (scheduled) return; scheduled = setTimeout(function () { scheduled = 0; render(); paint(); }, 60); }
  function onEvent(e, live) {
    addEvent(e); later();
    if (live) {
      if (e.step === "detect") { chainRunning = true; clearTimeout(chainTimer); chainTimer = setTimeout(function () { chainRunning = false; }, 60000); }
      if (e.step === "learn" || (e.detail && e.detail.error)) { chainRunning = false; clearTimeout(chainTimer); }
      if (e.step === "suggest" || e.step === "decide" || e.step === "apply" || e.step === "learn") loadFeed();
    }
  }
  jget("/api/events/recent?limit=200&business=" + encodeURIComponent(BIZ)).then(function (l) { l.forEach(function (e) { onEvent(e, false); }); }).catch(function () {})
    .then(function () {
      if (!window.EventSource) return;
      var es = new EventSource("/api/events?replay=1&last=60");
      es.addEventListener("kaiku", function (m) { var e = JSON.parse(m.data); onEvent(e, Date.now() - new Date(e.ts).getTime() < 20000); });
    });

  /* ---------- the chat widget talks to us ---------- */
  window.addEventListener("kaiku:chat", function (m) {
    var d = m.detail || {};
    if (d.replay) { if (web.length) return; }
    web.push({ ts: Date.now(), role: d.role, text: d.text }); saveWeb(); render();
  });
  window.addEventListener("kaiku:busy", function (m) { chatBusy = !!(m.detail && m.detail.on); });
  window.addEventListener("kaiku:decided", function () { loadFeed(); setTimeout(loadFeed, 1500); });

  /* ---------- boot ---------- */
  jget("/api/business/" + encodeURIComponent(BIZ)).then(function (b) { biz = b; paint(); }).catch(function () {});
  loadFeed(true).then(function () { return loadFeed(); });
  setInterval(function () { if (!document.hidden) loadFeed(); }, 10000);
  place(0); requestAnimationFrame(loop); paint(); render();
})();
