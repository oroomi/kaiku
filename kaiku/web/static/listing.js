/* ON FONECTA NOW: what Connect publishes today, read from the Yext sandbox entity (GET /api/listing/{id}).
   Every value on screen comes from that call. A missing field is a warn "no data" line that links to its suggestion card;
   a value a pending suggestion would change gets a faint "Kaiku suggests ..." note. Vanilla JS, no build step. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var host = $("l-body"); if (!host) return;
  var BIZ = ($("home") && $("home").getAttribute("data-biz")) || "furry-paw";
  var DAYS = [["mon", "Mon"], ["tue", "Tue"], ["wed", "Wed"], ["thu", "Thu"], ["fri", "Fri"], ["sat", "Sat"], ["sun", "Sun"]];
  var data = null, items = [], err = false;
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function nb(s) { return String(s).replace(/(\d)-(\d)/g, "$1⁠-⁠$2"); }
  function hm(t) { var p = String(t).split(":"), h = parseInt(p[0], 10); return p[1] && parseInt(p[1], 10) ? h + ":" + p[1] : String(h); }
  function hrs(p) { return p === "closed" ? "closed" : (p || []).map(function (s) { return hm(s.start) + "-" + hm(s.end); }).join(", "); }
  function dm(d) { return parseInt(d.slice(8), 10) + "." + parseInt(d.slice(5, 7), 10) + "."; }
  function pend(i) { return i.kind !== "no_change" && !{ approved: 1, edited: 1, applied: 1, declined: 1, info: 1 }[i.status || "proposed"]; }
  function of(kind) { return items.filter(function (i) { return i.kind === kind && pend(i); }); }
  function link(i, label) { return '<a class="l-go" href="#sg-' + esc(i.id) + '" data-go="' + esc(i.id) + '">' + esc(label || "see suggestion") + "</a>"; }
  function none(card, what) { return '<span class="l-none">no data</span>' + (card ? " " + link(card, what || "see suggestion") : ""); }
  function row(k, v) { return '<div class="l-row"><span class="mono l-k">' + k + '</span><div class="l-v">' + v + "</div></div>"; }
  function suggests(t) { return '<p class="l-note">Kaiku suggests ' + nb(esc(t)) + "</p>"; }

  /* the dates a pending holiday suggestion would set: date -> proposed hours text */
  function holidayPlans() {
    var out = {};
    items.filter(function (i) { return pend(i) && { holiday_hours: 1, conflict: 1, period: 1 }[i.kind]; }).forEach(function (i) {
      if (i.kind === "period" && Array.isArray(i.proposed)) i.proposed.forEach(function (m) { if (m.date && m.kind !== "no_change") out[m.date] = out[m.date] || { text: hrs(m.proposed == null ? "closed" : m.proposed), card: i }; });
      else if (i.holiday_date && i.proposed) out[i.holiday_date] = { text: hrs(i.proposed), card: i };
    });
    return out;
  }
  function render() {
    if (err && !data) { host.innerHTML = '<p class="empty">The listing could not be read right now.</p>'; return; }
    if (!data) return;
    var d = data, h = [], plans = holidayPlans(), descC = of("description")[0], revC = of("review");
    h.push(row("NAME", d.name ? esc(d.name) : none()));
    h.push(row("ADDRESS", d.address ? esc(d.address.text) : none()));
    h.push(row("CATEGORY", d.categories && d.categories.length ? d.categories.map(function (c) { return '<span class="l-tag mono">' + esc(c) + "</span>"; }).join(" ") : none()));
    h.push(row("PHONE", d.phone ? esc(d.phone) : none()));
    h.push(row("WEBSITE", d.website ? esc(d.website) : none()));
    h.push(row("HOURS", '<div class="l-hours">' + DAYS.map(function (x) {
      var t = d.hours_text && d.hours_text[x[0]];
      return '<span class="mono l-d">' + x[1] + "</span><span>" + (t ? nb(esc(t)) : '<span class="l-none">no data</span>') + "</span>";
    }).join("") + "</div>"));
    var rows = d.holiday_hours || [], known = {};
    var hh = rows.map(function (r) {
      known[r.date] = 1; var p = plans[r.date];
      return '<span class="mono l-d">' + dm(r.date) + "</span><span>" + nb(esc(r.text)) + (p && p.text !== r.text ? ' <span class="l-note">Kaiku suggests ' + nb(esc(p.text)) + "</span>" : "") + "</span>";
    });
    var firstPlan = null;
    Object.keys(plans).sort().forEach(function (dt) {
      if (known[dt]) return; firstPlan = firstPlan || plans[dt];
      hh.push('<span class="mono l-d">' + dm(dt) + '</span><span><span class="l-none">no data</span> <span class="l-note">Kaiku suggests ' + nb(esc(plans[dt].text)) + "</span></span>");
    });
    h.push(row("HOLIDAYS", hh.length ? '<div class="l-hours">' + hh.join("") + "</div>" + (firstPlan ? "<p class=\"l-link\">" + link(firstPlan.card, "see suggestion") + "</p>" : "") : none()));
    var dtxt = d.description ? '<span class="l-desc">' + esc(d.description) + "</span>" : none(descC, "see suggestion");
    h.push(row("DESCRIPTION", dtxt + (descC && typeof descC.proposed === "string" && d.description ? suggests(descC.proposed) : "")));
    var rv = d.reviews;
    h.push(row("REVIEWS", rv == null ? none() : rv.count ? esc(rv.count + (rv.count === 1 ? " review" : " reviews") + (rv.average != null ? ", average " + rv.average : "")) : '<span class="l-plain">No reviews yet</span>') +
      (revC.length ? '<p class="l-note">' + revC.length + (revC.length === 1 ? " reply is" : " replies are") + " waiting " + link(revC[0], "see suggestion") + "</p>" : ""));
    var html = h.join("");
    if (html !== lastHtml) { lastHtml = html; host.innerHTML = html; }   /* same payload: no repaint */
    if (d.entity_id) $("l-src").textContent = "WHAT CONNECT PUBLISHES TODAY · YEXT SANDBOX " + String(d.entity_id).toUpperCase();
    $("l-read").textContent = "READ " + readAt(d.read_at) + " FROM THE SANDBOX ENTITY";
  }
  var lastHtml = "";
  function readAt(iso) {
    try { return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Europe/Helsinki", hour12: false }).format(new Date(iso)); } catch (e) { return ""; }
  }
  var busy = false;
  function load(fresh) {
    if (busy && !fresh) return; busy = true;
    fetch("/api/listing/" + encodeURIComponent(BIZ) + (fresh ? "?fresh=1" : "")).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (j) { data = j; err = false; }).catch(function () { err = true; })
      .then(function () { busy = false; render(); });
  }
  host.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-go]"); if (!a) return;
    e.preventDefault();
    var el = document.getElementById("sg-" + a.getAttribute("data-go")); if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
  });
  window.addEventListener("kaiku:feed", function (m) { items = m.detail || []; render(); });
  window.addEventListener("kaiku:refresh", function (m) { load(!!(m.detail && m.detail.fresh)); });
  load(); setInterval(function () { if (!document.hidden) load(); }, 10000);
})();
