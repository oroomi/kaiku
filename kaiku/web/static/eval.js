(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var file = null, lastMapping = null, lastJsonl = "";
  var FIELDS = {id: "business id", name: "business name", category: "category", regular: "regular hours",
    last_year: "last year's hours", date: "holiday date", target: "expected hours (target)", today: "today (fake clock)"};

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function pct(x) { return x == null ? null : Math.round(x * 100) + "%"; }

  function metric(cls, big, label, title) {
    var m = el("div", "ev-m " + (big == null ? "none" : cls));
    var b = el("b", null, big == null ? "no data" : big);
    var s = el("span", "mono", label);
    if (title) m.title = title;
    m.appendChild(b); m.appendChild(s);
    return m;
  }

  function renderMetrics(d) {
    var box = $("ev-metrics"); box.textContent = "";
    var s = d.summary, m = s.metrics;
    var tone = function (v, hi, lo) { return v == null ? "" : v >= hi ? "good" : v >= lo ? "warn" : "bad"; };
    if (s.has_target) {
      box.appendChild(metric(tone(m.exact_match_rate_all, .8, .5), pct(m.exact_match_rate_all), "HIT RATE, ALL ROWS (ASKS COUNT AS MISSES)",
        "Exact match of the hours the customer would end up with, over " + s.rows_scored + " rows that have an expected value."));
      box.appendChild(metric(tone(m.exact_match_rate_answered, .8, .5), pct(m.exact_match_rate_answered), "HIT RATE, ANSWERED ROWS",
        "Same, over rows where Kaiku answered instead of asking."));
      box.appendChild(metric(tone(m.closed_day_accuracy, .8, .5), pct(m.closed_day_accuracy), "CLOSED-DAY ACCURACY",
        "Of the rows whose expected value is closed, how many Kaiku got right."));
      box.appendChild(metric(m.wrong_suggestion_rate === 0 ? "good" : "bad", pct(m.wrong_suggestion_rate), "WRONG ANSWER RATE",
        "Answered with something other than the expected hours."));
    } else {
      box.appendChild(metric("", null, "HIT RATE", "This file has no target / expected column."));
      box.appendChild(metric("", null, "CLOSED-DAY ACCURACY"));
    }
    box.appendChild(metric(s.ask_rate_all_rows > .4 ? "warn" : "good", pct(s.ask_rate_all_rows), "ASK RATE (BELOW " + s.ask_below + ")",
      "Share of all rows where Kaiku asked the owner instead of guessing."));
    box.appendChild(metric("", String(s.rows_run), "ROWS RUN" + (s.rows_with_error ? " (" + s.rows_with_error + " UNREADABLE)" : "")));
  }

  var STATUS = {match: ["MATCH", "t-match"], miss: ["MISS", "t-miss"], ask: ["ASKED, NO ANSWER", "t-ask"],
    no_target: ["NO EXPECTED VALUE", "t-warn"], error: ["COULD NOT READ", "t-warn"]};

  function renderRows(d) {
    var box = $("ev-rows"); box.textContent = "";
    var jsonl = [];
    d.rows.forEach(function (r) {
      var row = el("article", "ev-row " + r.status);
      var r1 = el("div", "ev-r1");
      r1.appendChild(el("span", "ev-biz", r.business));
      r1.appendChild(el("span", "mono ev-when", (r.date || "no date") + (r.holiday ? " · " + r.holiday : "")));
      row.appendChild(r1);
      if (r.status === "error") {
        row.appendChild(el("p", "ev-ans", "Not run"));
        row.appendChild(el("ul", "ev-why")).appendChild(el("li", null, r.error));
      } else {
        row.appendChild(el("p", "ev-ans", r.answer));
        var bd = el("div", "ev-badges");
        var st = STATUS[r.status];
        var t = el("span", "tag " + st[1], st[0]); bd.appendChild(t);
        bd.appendChild(el("span", "tag soft mono", "CONFIDENCE " + r.confidence.toFixed(2)));
        if (r.low_confidence) bd.appendChild(el("span", "tag t-warn mono", "LOW CONFIDENCE GUESS"));
        if (r.target != null) bd.appendChild(el("span", "tag soft mono", "EXPECTED " + (r.target_flat || r.target)));
        row.appendChild(bd);
        var ul = el("ul", "ev-why");
        (r.reasons.length ? r.reasons : ["No reason recorded."]).forEach(function (x) { ul.appendChild(el("li", null, x)); });
        row.appendChild(ul);
        jsonl.push(JSON.stringify(r.suggestion));
      }
      box.appendChild(row);
    });
    lastJsonl = jsonl.join("\n") + "\n";
    var dl = $("ev-dl");
    if (dl.dataset.url) URL.revokeObjectURL(dl.dataset.url);
    dl.href = URL.createObjectURL(new Blob([lastJsonl], {type: "application/x-ndjson"}));
    dl.dataset.url = dl.href;
  }

  function code(t) { return el("code", null, t); }

  function renderMapping(d) {
    var txt = $("ev-maptext"), form = $("ev-remap");
    txt.textContent = ""; form.textContent = ""; form.hidden = true;
    var fields = d.fields || FIELDS;
    if (!d.headers || !d.headers.length) {
      txt.textContent = d.note || "Nested JSON is read by key; no column mapping needed.";
      return;
    }
    var parts = [], m = d.mapping || {};
    Object.keys(FIELDS).forEach(function (k, i) {
      if (i) txt.appendChild(document.createTextNode(m[k] ? ", " : ", "));
      txt.appendChild(document.createTextNode(FIELDS[k] + " "));
      if (m[k]) { txt.appendChild(document.createTextNode("from ")); txt.appendChild(code(m[k])); }
      else txt.appendChild(document.createTextNode("not found"));
    });
    txt.appendChild(document.createTextNode(". If a guess is wrong, choose the right column and run again."));
    Object.keys(FIELDS).forEach(function (k) {
      var lab = el("label"); lab.appendChild(el("span", "mono", FIELDS[k]));
      var sel = el("select"); sel.name = k;
      var o0 = el("option", null, "(none)"); o0.value = ""; sel.appendChild(o0);
      d.headers.forEach(function (h) { var o = el("option", null, h); o.value = h; if (m[k] === h) o.selected = true; sel.appendChild(o); });
      lab.appendChild(sel); form.appendChild(lab);
    });
    var act = el("div", "ev-actions");
    var b = el("button", "primary", "Run again with these columns"); b.type = "submit"; act.appendChild(b);
    form.appendChild(act); form.hidden = false;
  }

  function show(d) {
    $("ev-err").hidden = true;
    $("ev-label").textContent = d.label || "RUN";
    $("ev-sub").textContent = d.kind ? "FORMAT: " + d.kind.toUpperCase() : "";
    renderMetrics(d); renderRows(d); renderMapping(d);
    $("ev-dl-wrap").hidden = false;
  }

  function fail(d) {
    var e = $("ev-err"); e.textContent = d.error || "Something went wrong."; e.hidden = false;
    $("ev-metrics").textContent = ""; $("ev-rows").textContent = ""; $("ev-dl-wrap").hidden = true;
    $("ev-label").textContent = "COULD NOT RUN THIS FILE"; $("ev-sub").textContent = "";
    if (d.headers && d.headers.length) renderMapping(d);
    $("ev-res").scrollIntoView({behavior: "smooth", block: "start"});
  }

  function run(mapping) {
    if (!file) return;
    var btn = $("ev-run"); btn.disabled = true; btn.textContent = "Running...";
    var fd = new FormData(); fd.append("file", file);
    if (mapping) fd.append("mapping", JSON.stringify(mapping));
    fetch("/api/eval/run", {method: "POST", body: fd}).then(function (r) {
      return r.json().catch(function () { return {ok: false, error: "The server answered something unreadable. Try again."}; });
    }).then(function (d) {
      if (d.ok) { lastMapping = d.mapping; show(d); $("ev-res").scrollIntoView({behavior: "smooth", block: "start"}); }
      else fail(d);
    }).catch(function () { fail({error: "Could not reach the server. Check the connection and try again."}); })
      .then(function () { btn.disabled = false; btn.textContent = "Run on this file"; });
  }

  function pick(f) {
    if (!f) return;
    file = f; $("ev-zone-main").textContent = f.name + " (" + Math.max(1, Math.round(f.size / 1024)) + " KB)";
    $("ev-run").disabled = false;
    run(null);
  }

  var zone = $("ev-zone");
  $("ev-file").addEventListener("change", function (e) { pick(e.target.files[0]); });
  ["dragenter", "dragover"].forEach(function (n) { zone.addEventListener(n, function (e) { e.preventDefault(); zone.classList.add("drag"); }); });
  ["dragleave", "drop"].forEach(function (n) { zone.addEventListener(n, function (e) { e.preventDefault(); zone.classList.remove("drag"); }); });
  zone.addEventListener("drop", function (e) { if (e.dataTransfer.files.length) pick(e.dataTransfer.files[0]); });
  $("ev-run").addEventListener("click", function () { run(null); });
  $("ev-remap").addEventListener("submit", function (e) {
    e.preventDefault();
    var m = {}; Array.prototype.forEach.call(e.target.querySelectorAll("select"), function (s) { m[s.name] = s.value; });
    run(m);
  });
  $("ev-sample").addEventListener("click", function () {
    file = null; $("ev-file").value = ""; $("ev-run").disabled = true;
    $("ev-zone-main").textContent = "Drop a file here, or tap to choose";
    show(JSON.parse($("ev-sample-data").textContent));
  });

  show(JSON.parse($("ev-sample-data").textContent));
})();
