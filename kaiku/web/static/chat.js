/* Kaiku owner chat: one conversation. Plain words in, plain words out. Vanilla JS, no build step. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var root = $("chat"); if (!root) return;
  var BIZ = root.getAttribute("data-biz") || "furry-paw", thread = $("chat-log"), msg = $("msg"), form = $("composer");
  var SID = "";
  try { SID = sessionStorage.getItem("kaikuChat") || ""; if (!SID) { SID = "s" + Math.random().toString(36).slice(2, 10); sessionStorage.setItem("kaikuChat", SID); } } catch (e) { SID = "s" + Date.now(); }
  var KEY = "";
  try { var qk = new URLSearchParams(location.search).get("key"); if (qk) sessionStorage.setItem("kaikuKey", qk); KEY = sessionStorage.getItem("kaikuKey") || ""; } catch (e) { KEY = new URLSearchParams(location.search).get("key") || ""; }
  function hdr() { return KEY ? { "X-Kaiku-Key": KEY } : {}; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function jget(u, h) { return fetch(u, { headers: h || {} }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }

  /* ---------- rendering ---------- */
  var shown = {};   /* suggestion id -> element */
  function tagFor() { return ""; }   /* the status lives on the suggestion cards, the conversation carries words only */
  function nb(s) { return s.replace(/(\d)-(\d)/g, "$1\u2060-\u2060$2"); }   /* 9-13 never breaks across lines */
  function bubble(m, animate) {
    var el = document.createElement("div");
    var cls = m.role === "user" ? "msg-u" : "msg-k" + (m.kind === "intro" ? " intro" : "") + (m.kind === "note" ? " note" : "");
    el.className = cls;
    if (!animate) el.style.animation = "none";
    el.innerHTML = '<div class="b">' + nb(esc(m.text)) + (m.kind === "suggestion" || m.kind === "note" ? tagFor(m) : "") + "</div>";
    if (m.suggestion_id) { el.setAttribute("data-sid", m.suggestion_id); el._m = m; shown[m.suggestion_id] = el; }
    return el;
  }
  function setStatus(sid, status) {
    var el = shown[sid]; if (!el || !el._m) return;
    el._m.status = status;
    var b = el.querySelector(".b"), t = b.querySelector(".tg"); if (t) t.remove();
    b.insertAdjacentHTML("beforeend", tagFor(el._m));
  }
  function toEnd() { requestAnimationFrame(function () { thread.scrollTop = thread.scrollHeight; }); }
  function tell(role, text, replay) { try { window.dispatchEvent(new CustomEvent("kaiku:chat", { detail: { role: role, text: text, replay: !!replay } })); } catch (e) {} }
  function busyEv(on) { try { window.dispatchEvent(new CustomEvent("kaiku:busy", { detail: { on: on } })); } catch (e) {} }
  function add(m, animate, noScroll) { inviteOff(); var el = bubble(m, animate !== false); thread.appendChild(el); if (!noScroll) toEnd(); return el; }
  function typing(on) {
    var t = $("typing");
    if (on && !t) { t = document.createElement("div"); t.id = "typing"; t.className = "msg-k typing"; t.innerHTML = '<div class="b"><i></i><i></i><i></i></div>'; thread.appendChild(t); toEnd(); }
    if (!on && t) t.remove();
  }

  /* ---------- opening: the chat starts EMPTY (an invitation, no bubbles). Only what this session already said is restored ---------- */
  var first = true, loading = false;
  var INVITE = '<p class="invite">Nothing to type yet. Accept a suggestion above and I will talk you through it, or tell me what changed in your own words.<small>Text here, or hold space and talk</small></p>';
  function inviteOn() { if (!thread.querySelector(".invite") && !thread.querySelector(".msg-k,.msg-u")) thread.insertAdjacentHTML("beforeend", INVITE); }
  function inviteOff() { var i = thread.querySelector(".invite"); if (i) i.remove(); }
  function load() {
    if (loading || !first) return Promise.resolve(); loading = true;
    return jget("/api/chat/open?business=" + encodeURIComponent(BIZ) + "&session=" + encodeURIComponent(SID)).then(function (j) {
      first = false;
      var ms = j.messages || [];
      ms.forEach(function (m) { add(m, false, true); if (m.kind === "chat") tell(m.role === "user" ? "user" : "kaiku", m.text, true); });
      if (!ms.length) inviteOn(); else toEnd();
      if (j.focus) { root.classList.add("ctx"); focusEv(j.focus); }
    }).catch(function () { first = false; inviteOn(); }).then(function () { loading = false; });
  }
  function focusEv(id) { try { window.dispatchEvent(new CustomEvent("kaiku:focus", { detail: { id: id || "" } })); } catch (e) {} }
  function reduce() { return window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches; }

  /* ---------- sending ---------- */
  var busy = false;
  function send(text, fromVoice) {
    text = (text || "").trim(); if (!text || busy) return Promise.resolve("");
    busy = true; 
    add({ role: "user", kind: "chat", text: text }); tell("user", text); msg.value = ""; typing(true); busyEv(true);
    return fetch("/api/chat", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ business_id: BIZ, message: text, session: SID }) })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (j) {
        typing(false); add({ role: "kaiku", kind: "chat", text: j.reply }); tell("kaiku", j.reply);
        Object.keys(j.statuses || {}).forEach(function (k) { setStatus(k, j.statuses[k]); });
        focusEv(j.focus); root.classList.toggle("ctx", !!j.focus);
        try { window.dispatchEvent(new CustomEvent("kaiku:decided")); } catch (e) {}
        return j.reply;
      })
      .catch(function () { typing(false); var t = "That did not go through. Please say it again."; add({ role: "kaiku", kind: "chat", text: t }); tell("kaiku", t); return t; })
      .then(function (r) { busyEv(false); busy = false; if (!fromVoice) msg.focus({ preventScroll: true }); return r; });
  }
  form.addEventListener("submit", function (e) { e.preventDefault(); send(msg.value); });
  window.kaikuChatAsk = function (t) { return send(t, true); };   /* the voice orb hands its transcript to the chat */


  /* ---------- the cards talk to the chat: Accept, Suggest a change, and the contact-ladder system line ---------- */
  function post(u, body) {
    return fetch(u, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }
  /* one smooth scroll that lands with the chat panel at the top of the screen (it is exactly one screen tall, see owner.css),
   so its first message and the input are both visible; no second scroll, focus never scrolls */
  function toChat() {
    var r = root.getBoundingClientRect();
    if (Math.abs(r.top - 14) < 8) return;
    root.scrollIntoView({ behavior: reduce() ? "auto" : "smooth", block: "start" });
  }
  function kaikuSays(t) { if (!t) return; add({ role: "kaiku", kind: "chat", text: t }); tell("kaiku", t); }
  /* Accept hands over: nothing is written, Kaiku's proposal appears here and the card is the focus */
  window.addEventListener("kaiku:accept", function (m) {
    var d = m.detail || {}; if (!d.id || busy) { if (d.done) d.done(); return; }
    busy = true; typing(true); busyEv(true); toChat();
    post("/api/suggestions/" + encodeURIComponent(d.id) + "/accept", { business_id: BIZ, session: SID })
      .then(function (j) { typing(false); kaikuSays(j.reply); if (j.ok) { root.classList.add("ctx"); focusEv(j.focus); } })
      .catch(function () { typing(false); kaikuSays("That did not go through. Please try again."); })
      .then(function () { busyEv(false); busy = false; if (d.done) d.done(); setTimeout(function () { try { msg.focus({ preventScroll: true }); } catch (e) {} }, 400); });
  });
  window.addEventListener("kaiku:change", function (m) {
    var d = m.detail || {}; if (!d.id) return;
    toChat(); typing(true);
    setTimeout(function () { try { msg.focus({ preventScroll: true }); } catch (e) {} }, reduce() ? 0 : 600);
    post("/api/suggestions/" + encodeURIComponent(d.id) + "/change", { business_id: BIZ, session: SID })
      .then(function (j) { typing(false); kaikuSays(j.reply); root.classList.add("ctx"); focusEv(j.focus); })
      .catch(function () { typing(false); /* nothing pending to change: stay quiet */ });
  });
  window.addEventListener("kaiku:discard", function (m) {
    var d = m.detail || {}; if (!d.id) return;
    post("/api/suggestions/" + encodeURIComponent(d.id) + "/discard", { business_id: BIZ, session: SID })
      .then(function (j) { if (d.done) d.done(!!j.ok); if (j.ok) { kaikuSays(j.reply); root.classList.remove("ctx"); focusEv(""); } })
      .catch(function () { if (d.done) d.done(false); })
      .then(function () { try { window.dispatchEvent(new CustomEvent("kaiku:decided")); } catch (e) {} });
  });
  var sys = null;
  function placeSys() {
    if (!sys) return;
    if (sys.parentNode !== thread || thread.firstChild !== sys) thread.insertBefore(sys, thread.firstChild);
  }
  window.addEventListener("kaiku:sysline", function (m) {
    var t = (m.detail && m.detail.text) || ""; if (!t) return;
    if (!sys) { sys = document.createElement("div"); sys.className = "sys mono"; sys.setAttribute("data-pilot", "ladder"); }
    sys.textContent = t; placeSys();
  });

  /* ---------- demo drawer: only for the key holder ---------- */
  function initDrawer() {
    jget("/api/chat/keyed", hdr()).then(function (k) {
      if (!k.keyed) return;
      return fetch("/owner/drawer", { headers: hdr() }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); }).then(function (html) {
        $("drawer-host").innerHTML = html; wireDrawer();
        var b = $("demo-btn"); b.hidden = false;
        b.addEventListener("click", function () { openDrawer(true); });
        $("today").hidden = false;
        if (location.hash === "#drawer") openDrawer(true);
      });
    }).catch(function () {});
  }
  function openDrawer(on) {
    document.body.classList.toggle("drawer-open", on);
    $("drawer").hidden = !on; $("drawer-back").hidden = !on; $("demo-btn").setAttribute("aria-expanded", on ? "true" : "false");
    if (on) $("drawer-close").focus();
  }
  function note(t) { $("d-msg").textContent = t; }
  function addDays(iso, n) { var d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
  function dayDiff(a, b) { return Math.round((new Date(b + "T12:00:00Z") - new Date(a + "T12:00:00Z")) / 86400000); }
  function travel(iso) { return fetch("/api/timetravel?date=" + iso, { method: "POST" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(loadToday); }
  function loadToday() {
    return jget("/api/today").then(function (t) { var q = t.date.split("-"); $("today").textContent = "Today: " + parseInt(q[2], 10) + "." + parseInt(q[1], 10) + "." + q[0]; if ($("tt-date")) $("tt-date").value = t.date; }).catch(function () {});
  }
  function wireDrawer() {
    $("drawer-close").addEventListener("click", function () { openDrawer(false); });
    $("drawer-back").addEventListener("click", function () { openDrawer(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !$("drawer").hidden) openDrawer(false); });
    loadToday();
    $("tt-date").addEventListener("change", function () {
      var v = $("tt-date").value; if (!v) return;
      travel(v).then(function () { note("Time travel: today is now " + v.split("-").reverse().join(".")); }).catch(function () { note("Time travel failed"); });
    });
    $("run").addEventListener("click", function () {
      var date = $("date").value, btn = $("run"); btn.disabled = true; note("Running the chain...");
      jget("/api/today").then(function (t) {
        var d = dayDiff(t.date, date), target = d < 0 ? addDays(date, -6) : d > 21 ? addDays(date, -7) : null;
        return target ? travel(target) : null;
      }).catch(function () { return null; })
        .then(function () { return fetch("/api/run?business=" + BIZ + "&date=" + date, { method: "POST" }); })
        .then(function (r) { return r.json(); })
        .then(function () { note("The chain is running. Kaiku's new suggestion appears in the chat."); openDrawer(false); poll(12); })
        .catch(function () { note("Could not start the chain"); })
        .then(function () { btn.disabled = false; });
    });
    function dcNote(t) { $("dc-msg").textContent = t; }
    function dcShow(j) { dcNote(j && j.set ? "Set: " + [j.email, j.phone].filter(Boolean).join(", ") : "Using the owner's own."); }
    fetch("/api/demo/contact", { headers: hdr() }).then(function (r) { return r.json(); }).then(dcShow).catch(function () {});
    $("dc-save").addEventListener("click", function () {
      var body = JSON.stringify({ email: $("dc-email").value, phone: $("dc-phone").value });
      fetch("/api/demo/contact", { method: "POST", headers: Object.assign({ "Content-Type": "application/json" }, hdr()), body: body })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || "Could not save"); return j; }); })
        .then(function (j) { $("dc-email").value = ""; $("dc-phone").value = ""; dcShow(j); })
        .catch(function (e) { dcNote(e.message); });
    });
    $("dc-clear").addEventListener("click", function () {
      fetch("/api/demo/contact", { method: "DELETE", headers: hdr() }).then(function (r) { return r.json(); })
        .then(function (j) { $("dc-email").value = ""; $("dc-phone").value = ""; dcShow(j); }).catch(function () { dcNote("Could not clear"); });
    });
    $("reset").addEventListener("click", function () {
      var b = $("reset"); b.disabled = true; note("Resetting...");
      fetch("/api/reset", { method: "POST", headers: hdr() })
        .then(function (r) { if (r.status === 403) throw new Error("key"); return r.json(); })
        .then(function () { try { sessionStorage.removeItem("kaikuChat"); sessionStorage.removeItem("kaikuWeb"); } catch (e) {} location.reload(); })
        .catch(function (err) { b.disabled = false; note(err && err.message === "key" ? "Key needed, open the page with ?key=..." : "Reset failed"); });
    });
  }

  /* new suggestions (a chain run from the drawer, a WhatsApp tap) show up as new bubbles */
  var pollTimer = 0;
  function poll() { /* new suggestions show up as cards (owner.js polls the feed); the chat stays quiet until the owner talks */ }

  load(); initDrawer();
})();
