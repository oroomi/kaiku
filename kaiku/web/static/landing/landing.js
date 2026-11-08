(function () {
  "use strict";
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------- dotted dome (Canvas 2D) ---------- */
  var cv = $("#dome");
  if (cv && cv.getContext) {
    var ctx = cv.getContext("2d"), W = 0, H = 0, dpr = 1, visible = true, t0 = performance.now();
    var TILT = 0.42, dots = [], LATS = 28, DOTS = 1400;
    // dots on latitude rings, count per ring proportional to its circumference
    (function () {
      var rings = [], total = 0, i, lat, c;
      for (i = 1; i <= LATS; i++) { lat = (i / (LATS + 1)) * Math.PI / 2; c = Math.cos(lat); rings.push([lat, c]); total += c; }
      rings.forEach(function (r) {
        var n = Math.max(6, Math.round(DOTS * r[1] / total));
        for (var k = 0; k < n; k++) dots.push([r[0], (k / n) * Math.PI * 2 + r[0] * 3]);
      });
    })();
    var size = function () {
      var r = cv.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = r.width; H = r.height;
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    // the sphere centre sits below the canvas top by R, so only the cap shows
    var proj = function (lat, lon, spin, R, cx, cy) {
      var cl = Math.cos(lat), x = cl * Math.sin(lon + spin), z = cl * Math.cos(lon + spin), y = Math.sin(lat);
      var y2 = y * Math.cos(TILT) - z * Math.sin(TILT), z2 = y * Math.sin(TILT) + z * Math.cos(TILT);
      return [cx + x * R, cy - y2 * R, z2];
    };
    var draw = function (now) {
      var el = (now - t0) / 1000, spin = (el / 90) * Math.PI * 2;
      var R = Math.min(W * 0.49, 640), cx = W / 2, cy = R + 6;
      ctx.clearRect(0, 0, W, H);
      ctx.lineWidth = 1; ctx.strokeStyle = "rgba(0,0,0,.12)";
      var lat, lon, p, started, i, j;
      for (i = 1; i <= 8; i++) {
        lat = (i / 9) * Math.PI / 2; ctx.beginPath(); started = false;
        for (j = 0; j <= 96; j++) { p = proj(lat, (j / 96) * Math.PI * 2, 0, R, cx, cy); if (p[2] > 0) { started ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); started = true; } else started = false; }
        ctx.stroke();
      }
      for (i = 0; i < 16; i++) {
        lon = (i / 16) * Math.PI * 2 + spin; ctx.beginPath(); started = false;
        for (j = 0; j <= 40; j++) { p = proj((j / 40) * Math.PI / 2, lon, 0, R, cx, cy); if (p[2] > 0) { started ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); started = true; } else started = false; }
        ctx.stroke();
      }
      ctx.fillStyle = "#000";
      for (i = 0; i < dots.length; i++) {
        p = proj(dots[i][0], dots[i][1], spin, R, cx, cy);
        if (p[2] <= 0.02 || p[1] > H + 4) continue;
        ctx.globalAlpha = Math.min(1, 0.3 + p[2]);
        ctx.beginPath(); ctx.arc(p[0], p[1], 0.7 + p[2] * 1.2, 0, 6.2832); ctx.fill();
      }
      ctx.globalAlpha = 1;
      // one cyan dot sweeps along the top arc every 8 s (fixed to the viewer, not to the spin)
      var ph = (el % 8) / 8, a = -1.2 + ph * 2.4, k, tail, q, g, cl = Math.cos(1.0), yy = Math.sin(1.0);
      for (k = 12; k >= 0; k--) {
        tail = a - k * 0.022;
        q = [cx + cl * Math.sin(tail) * R, cy - (yy * Math.cos(TILT) - cl * Math.cos(tail) * Math.sin(TILT)) * R];
        ctx.fillStyle = "rgba(34,211,238," + (k === 0 ? 1 : 0.25 * (1 - k / 13)) + ")";
        ctx.beginPath(); ctx.arc(q[0], q[1], k === 0 ? 5 : 3.4 * (1 - k / 16), 0, 6.2832); ctx.fill();
        if (k === 0) {
          g = ctx.createRadialGradient(q[0], q[1], 0, q[0], q[1], 24);
          g.addColorStop(0, "rgba(34,211,238,.55)"); g.addColorStop(1, "rgba(34,211,238,0)");
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(q[0], q[1], 24, 0, 6.2832); ctx.fill();
        }
      }
    };
    var loop = function (now) { if (visible) draw(now); requestAnimationFrame(loop); };
    size(); draw(performance.now());
    window.addEventListener("resize", function () { size(); draw(performance.now()); });
    if (!reduce) {
      if ("IntersectionObserver" in window) new IntersectionObserver(function (e) { visible = e[0].isIntersecting; }).observe(cv);
      requestAnimationFrame(loop);
    }
  }

  var nav = $(".nav"); var onS = function () { nav.classList.toggle("is-solid", window.scrollY > 60); }; window.addEventListener("scroll", onS, { passive: true }); onS();

  /* ---------- FAQ: one open at a time ---------- */
  $$("#faqlist details").forEach(function (d) {
    d.addEventListener("toggle", function () {
      if (d.open) $$("#faqlist details").forEach(function (o) { if (o !== d) o.open = false; });
    });
  });

  /* ---------- GSAP ---------- */
  if (reduce || !window.gsap || !window.ScrollTrigger) return;
  var gsap = window.gsap, ST = window.ScrollTrigger;
  gsap.registerPlugin(ST);

  // hero cards pop in one by one, then float slowly
  var order = [".hc--mail", ".hc--wa", ".hc--call", ".hc--ok", ".hc--pub"].map(function (s) { return $(s); });
  gsap.set(order, { opacity: 0, y: 24 });
  order.forEach(function (el, i) {
    var tl = gsap.timeline({ delay: 0.5 + i * 0.18 });
    tl.to(el, { opacity: 1, y: 0, duration: 0.8, ease: "power3.out" });
    tl.to(el, { y: i % 2 ? 7 : -7, duration: 3, ease: "sine.inOut", yoyo: true, repeat: -1 }, ">");
  });

  // section copy fades up at 20 percent visible
  $$(".rv, .ft2-text").forEach(function (el) {
    gsap.from(el, { opacity: 0, y: 36, duration: 0.9, ease: "power3.out", scrollTrigger: { trigger: el, start: "top 80%", once: true } });
  });

  // the pinned feature: six cards slide up and stack while the block is pinned
  var mm = gsap.matchMedia();
  mm.add("(min-width: 821px)", function () {
    var sec = $(".ft2"), pin = $(".ft2-pin"), cards = $$(".ft2 .card");
    if (!sec || !pin || !cards.length) return;
    sec.classList.add("is-pinned");
    var step = 72;
    gsap.set(cards, { y: function () { return window.innerHeight; } });
    var tl = gsap.timeline({
      scrollTrigger: { trigger: sec, start: "top top", end: "+=2600", pin: pin, scrub: 0.6, invalidateOnRefresh: true, anticipatePin: 1 }
    });
    cards.forEach(function (c, i) {
      tl.to(c, { y: i * step, duration: 1, ease: "power2.out" }, i);
    });
    tl.to({}, { duration: 0.6 });
    return function () { sec.classList.remove("is-pinned"); gsap.set(cards, { clearProps: "all" }); };
  });
  mm.add("(max-width: 820px)", function () {
    $$(".ft2 .card").forEach(function (c) {
      gsap.from(c, { opacity: 0, y: 40, duration: 0.7, ease: "power3.out", scrollTrigger: { trigger: c, start: "top 88%", once: true } });
    });
  });
  window.addEventListener("load", function () { ST.refresh(); });

  /* ---------- rotating subject in the headline ---------- */
  var rot = $(".rot");
  if (rot && !reduce && window.gsap) {
    var rwords = (rot.getAttribute("data-words") || "").split("|").filter(Boolean);
    var rw = $(".rot__w", rot), ri = 0;
    var rmeasure = function (txt) { var c = rw.cloneNode(true); c.textContent = txt; c.style.position = "absolute"; c.style.visibility = "hidden"; c.style.whiteSpace = "nowrap"; rot.appendChild(c); var px = c.getBoundingClientRect().width; rot.removeChild(c); return px; };
    rot.style.width = rmeasure(rwords[0]) + "px";
    var rswap = function () {
      ri = (ri + 1) % rwords.length;
      var next = rwords[ri], nw = rmeasure(next);
      gsap.timeline()
        .to(rw, { y: "-0.5em", opacity: 0, duration: 0.38, ease: "power2.in" })
        .add(function () { rw.textContent = next; })
        .to(rot, { width: nw, duration: 0.42, ease: "power2.inOut" })
        .fromTo(rw, { y: "0.5em", opacity: 0 }, { y: 0, opacity: 1, duration: 0.42, ease: "power2.out" }, "<0.05");
    };
    setInterval(rswap, 2600);
    window.addEventListener("resize", function () { rot.style.width = rmeasure(rw.textContent) + "px"; });
  }
})();
