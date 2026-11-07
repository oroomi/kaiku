/* /console: contact box, listing score line, Run the chain and Reset, on the same endpoints as the drawer. Vanilla JS. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var KEY = new URLSearchParams(location.search).get("key") || "";
  var BIZ = "furry-paw", DATE = "2026-12-24";
  function hdr() { return KEY ? { "X-Kaiku-Key": KEY } : {}; }
  function jget(u, h) { return fetch(u, { headers: h || {} }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  function note(t) { $("d-msg").textContent = t; }
  $("c-judge").href = "/judge?key=" + encodeURIComponent(KEY);

  function dcNote(t) { $("dc-msg").textContent = t; }
  function dcShow(j) { dcNote(j && j.set ? "Set: " + [j.email, j.phone].filter(Boolean).join(", ") : "Using the owner's own."); }
  function wipe() { $("dc-email").value = ""; $("dc-phone").value = ""; }
  jget("/api/demo/contact", hdr()).then(dcShow).catch(function () { dcNote("Could not read the contact"); });
  $("dc-save").addEventListener("click", function () {
    fetch("/api/demo/contact", { method: "POST", headers: Object.assign({ "Content-Type": "application/json" }, hdr()), body: JSON.stringify({ email: $("dc-email").value, phone: $("dc-phone").value }) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || "Could not save"); return j; }); })
      .then(function (j) { wipe(); dcShow(j); }).catch(function (e) { dcNote(e.message); });
  });
  $("dc-clear").addEventListener("click", function () {
    fetch("/api/demo/contact", { method: "DELETE", headers: hdr() }).then(function (r) { return r.json(); })
      .then(function (j) { wipe(); dcShow(j); }).catch(function () { dcNote("Could not clear"); });
  });

  function score() {
    jget("/api/score/" + BIZ + "?quick=1").then(function (s) {
      $("c-score").textContent = "Listing score " + s.score + " of 100, " + s.checks_ok + " of " + s.checks_total + " checks" + (s.label_en ? ", " + String(s.label_en).toLowerCase() : "") + ".";
    }).catch(function () { $("c-score").textContent = "Score: no data"; });
  }
  score();

  function addDays(iso, n) { var d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
  function dayDiff(a, b) { return Math.round((new Date(b + "T12:00:00Z") - new Date(a + "T12:00:00Z")) / 86400000); }
  $("run").addEventListener("click", function () {
    var btn = $("run"); btn.disabled = true; note("Running the chain...");
    jget("/api/today").then(function (t) {
      var d = dayDiff(t.date, DATE), target = d < 0 ? addDays(DATE, -6) : d > 21 ? addDays(DATE, -7) : null;
      return target ? fetch("/api/timetravel?date=" + target, { method: "POST" }) : null;
    }).catch(function () { return null; })
      .then(function () { return fetch("/api/run?business=" + BIZ + "&date=" + DATE, { method: "POST" }); })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function () { note("The chain is running. Watch it on the judge view."); setTimeout(score, 4000); })
      .catch(function () { note("Could not start the chain"); })
      .then(function () { btn.disabled = false; });
  });
  $("reset").addEventListener("click", function () {
    var b = $("reset"); b.disabled = true; note("Resetting...");
    fetch("/api/reset", { method: "POST", headers: hdr() })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function () { note("Reset done. Today is 17.12.2026."); score(); window.dispatchEvent(new CustomEvent("kaiku:refresh", { detail: { fresh: true } })); })
      .catch(function () { note("Reset failed"); })
      .then(function () { b.disabled = false; });
  });
})();
