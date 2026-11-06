/* Kaiku voice: hold space or the orb, speak, release. STT -> brain -> TTS, with captions and a spotlight.
   The browser only talks to /api/voice/*; no key ever reaches it. Vanilla JS, no build step. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var root = $("kv"); if (!root) return;
  var orb = $("kv-orb"), muteBtn = $("kv-mute"), cap = $("kv-cap");
  var PENDING = "kaiku_voice_pending", HIST = "kaiku_voice_hist", MUTE = "kaiku_voice_mute";
  var st = { state: "idle", rec: null, chunks: [], stream: null, t0: 0, idle: 0, audio: new Audio(), unlocked: false, muted: false,
             spot: null, spotTimer: 0, hideTimer: 0, an: null, raf: 0, ctx: null, gen: 0 };
  st.audio.preload = "auto"; st.audio.setAttribute("playsinline", "");
  try { st.muted = localStorage.getItem(MUTE) === "1"; } catch (e) {}
  muteBtn.setAttribute("aria-pressed", st.muted ? "true" : "false");

  function setState(s) { st.state = s; root.setAttribute("data-state", s); orb.setAttribute("aria-pressed", s === "listening" ? "true" : "false"); }
  function show(you, ai, keep) {
    clearTimeout(st.hideTimer);
    $("kv-you").textContent = you || ""; $("kv-ai").textContent = ai || "";
    $("kv-you-l").hidden = $("kv-you").hidden = !you; $("kv-ai-l").hidden = $("kv-ai").hidden = !ai;
    cap.hidden = !(you || ai);
    if (!keep) st.hideTimer = setTimeout(function () { if (st.state === "idle") cap.hidden = true; }, 9000);
  }
  function hist() { try { return JSON.parse(sessionStorage.getItem(HIST) || "[]"); } catch (e) { return []; } }
  function pushHist(role, text) { try { var h = hist(); h.push({ role: role, text: text }); sessionStorage.setItem(HIST, JSON.stringify(h.slice(-6))); } catch (e) {} }

  /* ---------- audio unlock (iOS Safari needs a play() inside a user gesture) ---------- */
  var SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
  function unlock() {
    if (st.unlocked) return; st.unlocked = true;
    try { st.audio.src = SILENT; var p = st.audio.play(); if (p && p.catch) p.catch(function () { st.unlocked = false; }); } catch (e) {}
    try { st.ctx = st.ctx || new (window.AudioContext || window.webkitAudioContext)(); if (st.ctx.state === "suspended") st.ctx.resume(); } catch (e) {}
  }

  /* ---------- spotlight ---------- */
  function clearSpot() { clearTimeout(st.spotTimer); cancelAnimationFrame(st.spotRaf); if (st.spot) { st.spot.classList.remove("on"); st.spotEl = null; } }
  function placeSpot() {
    if (!st.spotEl || !st.spot) return;
    var r = st.spotEl.getBoundingClientRect(), pad = 8;
    st.spot.style.left = (r.left - pad) + "px"; st.spot.style.top = (r.top - pad) + "px";
    st.spot.style.width = (r.width + pad * 2) + "px"; st.spot.style.height = (r.height + pad * 2) + "px";
    st.spotRaf = requestAnimationFrame(placeSpot);
  }
  function spotlight(sel) {
    var el = null; try { el = document.querySelector(sel); } catch (e) {}
    if (!el || !/^\[data-pilot=/.test(sel)) return false;   /* only data-pilot targets, never model-written css */
    if (!st.spot) { st.spot = document.createElement("div"); st.spot.className = "kv-spot"; st.spot.setAttribute("aria-hidden", "true"); document.body.appendChild(st.spot); }
    clearSpot(); st.spotEl = el;
    el.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    placeSpot(); requestAnimationFrame(function () { st.spot.classList.add("on"); });
    st.spotTimer = setTimeout(clearSpot, 8000);
    return true;
  }

  /* ---------- actions ---------- */
  function applyActions(actions, text) {
    actions = actions || [];
    var nav = actions.filter(function (a) { return a.type === "navigate" && typeof a.url === "string" && a.url.charAt(0) === "/"; })[0];
    if (nav && location.pathname !== nav.url.split("#")[0].split("?")[0]) {
      /* another page: remember what to say and do, the next page picks it up */
      try { sessionStorage.setItem(PENDING, JSON.stringify({ at: Date.now(), text: text, actions: actions.filter(function (a) { return a !== nav; }) })); } catch (e) {}
      location.href = nav.url; return true;
    }
    actions.forEach(function (a) {
      if (a.type === "spotlight") spotlight(a.selector);
      if (a.type === "run_chain") document.dispatchEvent(new CustomEvent("kaiku:run_chain", { detail: a }));
    });
    return false;
  }

  /* ---------- speaking ---------- */
  function speakBrowser(text) {
    if (!("speechSynthesis" in window)) return Promise.resolve();
    return new Promise(function (res) {
      var u = new SpeechSynthesisUtterance(text); u.lang = /[äö]|\b(on|ja|ei|klo|auki)\b/i.test(text) ? "fi-FI" : "en-US"; u.onend = u.onerror = res; speechSynthesis.speak(u);
    });
  }
  function speak(text) {
    if (st.muted) return Promise.resolve();
    return fetch("/api/voice/tts", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text: text }) })
      .then(function (r) { if (!r.ok) throw new Error("tts " + r.status); return r.blob(); })
      .then(function (b) {
        return new Promise(function (res) {
          var url = URL.createObjectURL(b); st.audio.src = url;
          st.audio.onended = st.audio.onerror = function () { URL.revokeObjectURL(url); res(); };
          var p = st.audio.play();
          if (p && p.catch) p.catch(function () { res(); });   /* blocked autoplay: the caption already carries the answer */
        });
      })
      .catch(function () { return speakBrowser(text); });
  }
  function deliver(text, actions, you) {
    show(you, text, true);
    setState("speaking");
    var left = applyActions(actions, text);
    if (left) return;
    speak(text).then(function () { setState("idle"); show(you, text, false); });
  }

  /* ---------- the turn ---------- */
  function ask(text) {
    setState("thinking"); show(text, "", true);
    $("kv-ai-l").hidden = false; $("kv-ai").textContent = "Mietin…";
    var gen = ++st.gen;
    pushHist("user", text);
    return fetch("/api/voice/ask", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: text, page: location.pathname, lang: "auto", history: hist().slice(0, -1) }) })
      .then(function (r) { if (!r.ok) throw new Error("ask " + r.status); return r.json(); })
      .then(function (j) { if (gen !== st.gen) return; pushHist("assistant", j.text); deliver(j.text, j.actions, text); })
      .catch(function () { setState("error"); show(text, "Could not reach Kaiku.", false); setTimeout(function () { setState("idle"); }, 2500); });
  }
  function transcribe(blob) {
    setState("thinking"); show("", "", true); $("kv-you-l").hidden = false; $("kv-you").hidden = false; cap.hidden = false; $("kv-you").textContent = "Kuuntelen…";
    return fetch("/api/voice/stt", { method: "POST", headers: { "content-type": blob.type || "audio/webm" }, body: blob })
      .then(function (r) { if (!r.ok) throw new Error("stt " + r.status); return r.json(); })
      .then(function (j) {
        if (!j.text) { setState("idle"); show("", "I heard nothing.", false); return; }
        return ask(j.text);
      })
      .catch(function () { setState("error"); show("", "I could not transcribe that.", false); setTimeout(function () { setState("idle"); }, 2500); });
  }

  /* ---------- push to talk ---------- */
  function pickMime() {
    var c = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
    if (!window.MediaRecorder) return "";
    for (var i = 0; i < c.length; i++) if (MediaRecorder.isTypeSupported(c[i])) return c[i];
    return "";
  }
  function meter(stream) {
    try {
      st.ctx = st.ctx || new (window.AudioContext || window.webkitAudioContext)();
      var src = st.ctx.createMediaStreamSource(stream), an = st.ctx.createAnalyser(); an.fftSize = 256; src.connect(an);
      var buf = new Uint8Array(an.frequencyBinCount);
      (function tick() { an.getByteTimeDomainData(buf); var m = 0; for (var i = 0; i < buf.length; i++) m = Math.max(m, Math.abs(buf[i] - 128)); root.style.setProperty("--lvl", (m / 128).toFixed(2)); st.raf = requestAnimationFrame(tick); })();
    } catch (e) {}
  }
  function getStream() {
    if (st.stream && st.stream.active) return Promise.resolve(st.stream);
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return Promise.reject(new Error("nomic"));
    return navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }).then(function (s) { st.stream = s; return s; });
  }
  function releaseMicLater() { clearTimeout(st.idle); st.idle = setTimeout(function () { if (st.stream) { st.stream.getTracks().forEach(function (t) { t.stop(); }); st.stream = null; } }, 30000); }

  var holding = false;
  function start() {
    if (holding || st.state === "thinking") return;
    holding = true; unlock(); clearSpot(); st.gen++;
    try { st.audio.pause(); } catch (e) {} if ("speechSynthesis" in window) speechSynthesis.cancel();
    clearTimeout(st.idle);
    getStream().then(function (stream) {
      if (!holding) { releaseMicLater(); return; }
      st.chunks = []; var mt = pickMime();
      st.rec = mt ? new MediaRecorder(stream, { mimeType: mt }) : new MediaRecorder(stream);
      st.rec.ondataavailable = function (e) { if (e.data && e.data.size) st.chunks.push(e.data); };
      st.rec.onstop = function () {
        cancelAnimationFrame(st.raf); root.style.setProperty("--lvl", "0");
        var dur = Date.now() - st.t0, blob = new Blob(st.chunks, { type: (st.rec && st.rec.mimeType) || mt || "audio/webm" });
        releaseMicLater();
        if (dur < 400 || blob.size < 800) { setState("idle"); show("", "Hold and speak.", false); return; }
        transcribe(blob);
      };
      st.t0 = Date.now(); st.rec.start(); setState("listening"); show("", "", true); cap.hidden = false; $("kv-you-l").hidden = false; $("kv-you").hidden = false; $("kv-you").textContent = "Kuuntelen…"; meter(stream);
    }).catch(function () {
      holding = false; setState("error"); show("", "Microphone is not available.", false); setTimeout(function () { setState("idle"); }, 2500);
    });
  }
  function stop() {
    if (!holding) return; holding = false;
    if (st.rec && st.rec.state === "recording") st.rec.stop();
  }

  orb.addEventListener("pointerdown", function (e) { e.preventDefault(); try { orb.setPointerCapture(e.pointerId); } catch (x) {} start(); });
  orb.addEventListener("pointerup", stop); orb.addEventListener("pointercancel", stop);
  orb.addEventListener("contextmenu", function (e) { e.preventDefault(); });
  orb.addEventListener("keydown", function (e) { if (e.code === "Enter") { e.preventDefault(); if (!e.repeat) start(); } });
  orb.addEventListener("keyup", function (e) { if (e.code === "Enter") stop(); });
  function typing(t) { return t && (/^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(t.tagName) || t.isContentEditable); }
  document.addEventListener("keydown", function (e) {
    if (e.code === "Space" && !e.repeat && !typing(e.target) && !e.metaKey && !e.ctrlKey) { e.preventDefault(); start(); }
    if (e.code === "Escape") { clearSpot(); st.gen++; try { st.audio.pause(); } catch (x) {} setState("idle"); }
  });
  document.addEventListener("keyup", function (e) { if (e.code === "Space") stop(); });
  window.addEventListener("blur", stop);

  muteBtn.addEventListener("click", function () {
    st.muted = !st.muted; muteBtn.setAttribute("aria-pressed", st.muted ? "true" : "false");
    try { localStorage.setItem(MUTE, st.muted ? "1" : "0"); } catch (e) {}
    if (st.muted) { try { st.audio.pause(); } catch (e) {} if ("speechSynthesis" in window) speechSynthesis.cancel(); }
  });

  /* ---------- resume after a page change ---------- */
  try {
    var p = JSON.parse(sessionStorage.getItem(PENDING) || "null"); sessionStorage.removeItem(PENDING);
    if (p && Date.now() - p.at < 20000) {
      show("", p.text, true); setState("speaking");
      setTimeout(function () { applyActions(p.actions, p.text); }, 350);
      speak(p.text).then(function () { setState("idle"); show("", p.text, false); });
    }
  } catch (e) {}

  /* hook for demos and tests: KaikuVoice.say("Kaiku, what is wrong with Furry Paw?") runs the same turn as speech would */
  window.KaikuVoice = { say: function (t) { unlock(); return ask(t); }, spotlight: spotlight, clear: clearSpot };
})();
