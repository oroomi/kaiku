/* Kaiku core UI: the header date label on every page. The chat lives in chat.js, the live events in judge.js. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  /* header date label: every page has #today, only the home drives the rest */
  var ttToday = "";
  function loadToday() {
    var el = $("today"); if (!el) return Promise.resolve();
    return fetch("/api/today").then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (t) { var q = t.date.split("-"); el.textContent = "Today: " + parseInt(q[2], 10) + "." + parseInt(q[1], 10) + "." + q[0]; el.title = "Demo clock (time travel)"; if ($("tt-date") && t.date) { $("tt-date").value = t.date; ttToday = t.date; } })
      .catch(function () { el.hidden = true; });
  }
  loadToday();
})();
