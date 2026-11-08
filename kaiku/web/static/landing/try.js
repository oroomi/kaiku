(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var forms = [$("#f-email"), $("#f-phone")];
  var state = $("#state"), live = $("#live"), ok = $("#ok"), ev = $("#ev");
  var timer = null, es = null, busyUntil = 0, paused = false, submitting = false;

  function setDisabled(on) {
    forms.forEach(function (f) {
      Array.prototype.forEach.call(f.querySelectorAll("input,button"), function (el) { el.disabled = on; });
    });
  }
  function showState(t) { state.textContent = t || ""; state.hidden = !t; }
  function showMsg(f, t) { var m = $(".msg", f); m.textContent = t || ""; m.hidden = !t; }
  function clearMsgs() { forms.forEach(function (f) { showMsg(f, ""); }); }

  function countdown(sec) {
    clearInterval(timer);
    busyUntil = Date.now() + sec * 1000;
    setDisabled(true);
    function tick() {
      var left = Math.ceil((busyUntil - Date.now()) / 1000);
      if (left <= 0) { clearInterval(timer); showState(""); if (!paused) setDisabled(false); return; }
      showState("Kaiku is with someone else right now. Try again in about " + left + " seconds.");
    }
    tick();
    timer = setInterval(tick, 500);
  }

  function hhmm(ts) {
    var d = new Date(ts);
    if (isNaN(d)) return "";
    return d.toLocaleTimeString("fi-FI", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  function startFeed() {
    if (!window.EventSource || es) return;
    es = new EventSource("/api/events?replay=1&last=12");
    es.addEventListener("kaiku", function (m) {
      var e; try { e = JSON.parse(m.data); } catch (x) { return; }
      var li = document.createElement("li");
      var t = document.createElement("time"); t.textContent = hhmm(e.ts);
      var s = document.createElement("span"); s.textContent = e.title_en || e.title_fi || "";
      li.appendChild(t); li.appendChild(s);
      ev.insertBefore(li, ev.firstChild);
      while (ev.children.length > 12) ev.removeChild(ev.lastChild);
    });
  }

  function submit(door, f) {
    return function (e) {
      e.preventDefault();
      if (submitting) return;
      clearMsgs();
      var body = { door: door, email: f.elements.email.value.trim(), phone: "", own_number: false };
      if (door === "phone") { body.phone = f.elements.phone.value.trim(); body.own_number = f.elements.own.checked; }
      submitting = true; setDisabled(true);
      fetch("/api/try", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { s: r.status, j: j }; }); })
        .then(function (o) {
          submitting = false;
          if (o.s === 200 && o.j.ok) {
            ok.textContent = "Sent. The proposal from Kaiku is on its way to your inbox. Decide there, or do nothing and watch what happens next." +
              (door === "phone" ? " If you do not decide within a minute, WhatsApp follows, then the call." : "");
            live.hidden = false; ev.innerHTML = ""; startFeed();
            countdown(o.j.seconds_locked || 150);
            live.scrollIntoView({ behavior: "smooth", block: "nearest" });
            return;
          }
          var msg = (typeof o.j.detail === "string" && o.j.detail) || "Something went wrong. Please try again.";
          if (o.s === 503) { paused = true; showState(msg); setDisabled(true); return; }
          if (o.s === 409 && o.j.seconds_left) { countdown(o.j.seconds_left); return; }
          setDisabled(false); showMsg(f, msg);
        })
        .catch(function () { submitting = false; setDisabled(false); showMsg(f, "Could not reach Kaiku. Check your connection and try again."); });
    };
  }
  $("#f-email").addEventListener("submit", submit("email", $("#f-email")));
  $("#f-phone").addEventListener("submit", submit("phone", $("#f-phone")));

  fetch("/api/try/status").then(function (r) { return r.json(); }).then(function (s) {
    if (s.paused) { paused = true; showState("Try-it is paused during the live final. Come to the stand instead."); setDisabled(true); }
    else if (s.busy && s.seconds_left > 0) countdown(s.seconds_left);
  }).catch(function () {});
})();
