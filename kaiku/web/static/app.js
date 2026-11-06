/* Kaiku core UI: the header date on every page; on the home page the status chips and the keyed reset. Vanilla JS, no build step. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  function jget(url, h) { return fetch(url, { headers: h || {} }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  /* header date label: every page has #today */
  function loadToday() {
    var el = $("today"); if (!el) return Promise.resolve();
    return jget("/api/today").then(function (t) { var q = t.date.split("-"); el.textContent = "Today: " + parseInt(q[2], 10) + "." + parseInt(q[1], 10) + "." + q[0]; el.title = "Demo clock (time travel)"; if ($("tt-date") && t.date) $("tt-date").value = t.date; })
      .catch(function () { el.hidden = true; });
  }
  loadToday();
  if (!$("statusbar") || !$("hero")) return;   // not the home page

  /* ---------- status chips ---------- */
  function setChip(id, text, ok) { var c = $(id); c.querySelector("b").textContent = text; c.className = "chip" + (ok ? " ok" : ""); }
  jget("/api/status").then(function (s) {
    setChip("st-broker", s.broker === "orion-ld" ? "Orion-LD" : "fallback", s.broker === "orion-ld");
    $("st-broker").title = s.broker === "orion-ld" ? "FIWARE NGSI-LD context broker Orion-LD is live" : "Orion-LD is not reachable, the in-memory fallback keeps the chain alive";
    setChip("st-wa", s.whatsapp_configured ? "in use" : "not in use", s.whatsapp_configured);
    $("st-wa").title = s.whatsapp_configured ? "WhatsApp in use: the message goes to the owner's phone" : "WhatsApp not in use yet: the decision link is shown instead of a message";
    setChip("st-yext", s.yext_entity, true);
  }).catch(function () { setChip("st-broker", "no data", false); });
  $("st-toggle").addEventListener("click", function () {
    var o = $("statusbar").classList.toggle("open"); $("st-toggle").setAttribute("aria-expanded", o ? "true" : "false");
  });

  /* ---------- keyed reset: the key is never in the HTML, it travels in ?key= and lives in sessionStorage ---------- */
  var rkey = "";
  try {
    var qk = new URLSearchParams(location.search).get("key");
    if (qk) sessionStorage.setItem("kaikuKey", qk);
    rkey = sessionStorage.getItem("kaikuKey") || "";
  } catch (x) { rkey = new URLSearchParams(location.search).get("key") || ""; }
  var hdr = rkey ? { "X-Kaiku-Key": rkey } : {};
  jget("/api/chat/keyed", hdr).then(function (k) { if (k.keyed) $("foot").hidden = false; }).catch(function () {});
  $("reset-foot").addEventListener("click", function () {
    var btn = $("reset-foot"); btn.disabled = true; $("reset-msg").textContent = "Resetting...";
    fetch("/api/reset", { method: "POST", headers: hdr })
      .then(function (r) { if (r.status === 403) throw new Error("key"); return r.json(); })
      .then(function () { try { sessionStorage.removeItem("kaikuChat"); sessionStorage.removeItem("kaikuWeb"); } catch (e) {} location.reload(); })
      .catch(function (err) {
        btn.disabled = false;
        $("reset-msg").textContent = err && err.message === "key" ? "Key needed, open the page with ?key=..." : "Reset failed";
      });
  });
})();
