(function () {
  "use strict";
  var root = document.getElementById("dc");
  if (!root) return;
  var token = root.dataset.token, sid = root.dataset.sid;
  // English by default; Finnish (with English glosses) when the page says data-lang="fi".
  var FI = root.dataset.lang === "fi";
  var T_FI = {
    thanks: ["Kiitos. Päivitän tiedot nyt.", "Thank you. I am updating the details now."],
    thanksNo: ["Kiitos. En muuta mitään.", "Thank you. I will change nothing."],
    waiting: ["Odotan, että tiedot päivittyvät...", "Waiting for the details to update..."],
    seen: ["Päivitämme tietosi kaikkialle.", "We'll update your information everywhere."],
    sent: ["Lähetetty", "Sent"],
    bad: ["Tarkista ajat: alkamisen pitää olla ennen päättymistä.", "Check the times: the start must be before the end."],
    fail: ["Jokin meni vikaan. Yritä uudelleen.", "Something went wrong. Try again."],
    done_approve: ["Hyväksytty", "Approved"], done_edit: ["Muokattu", "Edited"], done_decline: ["Ei kiitos", "Declined"],
    chips: [["Olemme auki normaalisti", "We are open as usual"], ["Ajat ovat väärin", "The times are wrong"],
            ["Emme tiedä vielä", "We do not know yet"], ["Ei koske meitä", "Does not concern us"]],
    gloss: ["Tap send.", "Reason (optional). Tap one, then send."]
  };
  var T_EN = {
    thanks: ["Thank you. I am updating the details now.", ""],
    thanksNo: ["Thank you. I will change nothing.", ""],
    waiting: ["Waiting for the details to update...", ""],
    seen: ["We'll update your information everywhere.", ""],
    sent: ["Sent", ""],
    bad: ["Check the times: the start must be before the end.", ""],
    fail: ["Something went wrong. Try again.", ""],
    done_approve: ["Approved", ""], done_edit: ["Edited", ""], done_decline: ["Declined", ""],
    chips: [["We are open as usual", ""], ["The times are wrong", ""], ["We do not know yet", ""], ["Does not concern us", ""]],
    gloss: ["Tap send.", "Reason (optional). Tap one, then send."]
  };
  var T = FI ? T_FI : T_EN;
  function both(p) { return p[1] ? p[0] + " (" + p[1] + ")" : p[0]; }
  window.KAIKU_DECIDE_I18N = T;
  var $ = function (id) { return document.getElementById(id); };
  var reason = null, closed = false, scope = "same", busy = false;

  var tl = $("today");
  if (tl) {
    fetch("/api/today").then(function (r) { return r.json(); }).then(function (t) {
      var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t.date || "");
      if (m) tl.textContent = parseInt(m[3], 10) + "." + parseInt(m[2], 10) + "." + m[1];
      else tl.hidden = true;
    }).catch(function () { tl.hidden = true; });
  }

  /* the last question: how do you want me to reach you next time? One tap, one line back. */
  var chrow = $("ch-row");
  if (chrow) {
    var CH_GOT = { email: ["Selvä, sähköposti. Aloitan siitä ensi kerralla.", "Got it, email it is. I'll start there next time."],
                   whatsapp: ["Selvä, WhatsApp. Aloitan siitä ensi kerralla.", "Got it, WhatsApp it is. I'll start there next time."],
                   call: ["Selvä, puhelu. Aloitan siitä ensi kerralla.", "Got it, a call it is. I'll start there next time."] };
    [].forEach.call(chrow.querySelectorAll("[data-channel]"), function (b) {
      b.addEventListener("click", function () {
        var ch = b.dataset.channel;
        [].forEach.call(chrow.querySelectorAll("button"), function (x) { x.disabled = true; });
        fetch("/api/decide/" + encodeURIComponent(token) + "/channel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel: ch }) })
          .then(function (r) { if (!r.ok) throw new Error("fail"); return r.json(); })
          .then(function (j) {
            [].forEach.call(chrow.querySelectorAll("button"), function (x) { x.disabled = false; x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
            var g = $("ch-got"); g.textContent = j.message || (FI ? CH_GOT[ch][0] : CH_GOT[ch][1]); g.hidden = false;
          })
          .catch(function () {
            [].forEach.call(chrow.querySelectorAll("button"), function (x) { x.disabled = false; });
            var g = $("ch-got"); g.textContent = both(T.fail); g.hidden = false;
          });
      });
    });
  }

  var was = $("was");
  if (was) { var t = T["done_" + was.dataset.act]; if (t) was.textContent = both(t); }
  if (!$("form")) return;

  var chips = $("reasons");
  T.chips.forEach(function (c) {
    var b = document.createElement("button");
    b.type = "button"; b.className = "chip"; b.setAttribute("aria-pressed", "false");
    b.textContent = c[0]; if (c[1]) b.title = c[1]; b.setAttribute("aria-label", both(c));
    b.addEventListener("click", function () {
      var on = b.getAttribute("aria-pressed") !== "true";
      [].forEach.call(chips.children, function (x) { x.setAttribute("aria-pressed", "false"); });
      b.setAttribute("aria-pressed", on ? "true" : "false");
      reason = on ? c[0] : null;
      $("r-gloss").textContent = on ? (c[1] || c[0]) + ". " + T.gloss[0] : T.gloss[1];
    });
    chips.appendChild(b);
  });

  function toggle(which) {
    var map = { edit: ["b-edit", "d-edit"], decline: ["b-decline", "d-decline"] };
    Object.keys(map).forEach(function (k) {
      var open = k === which && $(map[k][1]).hidden;
      $(map[k][1]).hidden = !open;
      $(map[k][0]).setAttribute("aria-expanded", open ? "true" : "false");
    });
  }
  $("b-edit").addEventListener("click", function () { toggle("edit"); });
  $("b-decline").addEventListener("click", function () { toggle("decline"); });
  $("c-closed").addEventListener("click", function () {
    closed = !closed;
    this.setAttribute("aria-pressed", closed ? "true" : "false");
    $("t-start").disabled = $("t-end").disabled = closed;
  });
  $("perm").addEventListener("change", function () { $("scope").hidden = !this.checked; });
  [].forEach.call(document.querySelectorAll("[data-scope]"), function (b) {
    b.addEventListener("click", function () {
      scope = b.dataset.scope;
      [].forEach.call(document.querySelectorAll("[data-scope]"), function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
    });
  });

  function submit(body) {
    if (busy) return;
    var s = $("t-start").value, e = $("t-end").value;
    if (body.action === "edit" && !closed && (!s || !e || s >= e)) {
      var er = $("e-err"); er.textContent = both(T.bad); er.hidden = false; return;
    }
    busy = true;
    [].forEach.call(root.querySelectorAll("button"), function (b) { b.disabled = true; });
    body.standing_permission = $("perm").checked; body.scope = scope;
    fetch("/api/decide/" + encodeURIComponent(token), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return [r.ok, j, r.status]; }); })
      .then(function (x) {
        if (x[2] === 410) { expired(); return; }
        if (!x[0]) throw new Error("fail");
        thanks(x[1]);
      })
      .catch(function () {
        busy = false;
        [].forEach.call(root.querySelectorAll("button"), function (b) { b.disabled = false; });
        var er = $("e-err"); er.textContent = both(T.fail); er.hidden = false;
        $("d-edit").hidden = false;
      });
  }
  $("b-approve").addEventListener("click", function () { submit({ action: "approve" }); });
  $("s-edit").addEventListener("click", function () {
    submit({ action: "edit", edited: closed ? "closed" : [{ start: $("t-start").value, end: $("t-end").value }] });
  });
  $("s-decline").addEventListener("click", function () { submit({ action: "decline", reason_chip: reason }); });

  function expired() {
    $("form").hidden = true; $("permbox").hidden = true;
    $("expired-live").hidden = false;
    $("expired-live").scrollIntoView({ block: "nearest" });
  }

  function thanks(res) {
    var no = res.next === "skip";
    $("form").hidden = true; $("permbox").hidden = true;
    var th = $("thanks"); th.hidden = false;
    var cq = $("chpref"); if (cq) { cq.hidden = false; [].forEach.call(cq.querySelectorAll("button"), function (x) { x.disabled = false; }); }
    $("th-fi").textContent = no ? T.thanksNo[0] : T.thanks[0];
    $("th-en").textContent = no ? T.thanksNo[1] : T.thanks[1]; $("th-en").hidden = !$("th-en").textContent;
    th.scrollIntoView({ block: "nearest" });
    if (no) return;
    var vis = $("vis");
    vis.innerHTML = '<div class="pend"><i></i><span>' + T.waiting[0] + '</span></div>' + (T.waiting[1] ? '<p class="gl" style="margin:6px 0 0 16px">' + T.waiting[1] + "</p>" : "");
    var es = new EventSource("/api/events?replay=1&last=50");
    es.addEventListener("kaiku", function (m) {
      var e; try { e = JSON.parse(m.data); } catch (_) { return; }
      if (e.suggestion_id !== sid || e.step !== "apply" || (e.detail && e.detail.error)) return;
      vis.innerHTML = '<div class="seen">' + T.seen[0] + '</div>' + (T.seen[1] ? '<p class="gl" style="margin:6px 0 0">' + T.seen[1] + "</p>" : "");
      es.close();
    });
  }
})();
