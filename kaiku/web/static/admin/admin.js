/* /admin: the three FIWARE panels load their live page only on click (three WebGL maps at once would stall a laptop). */
(function () {
  "use strict";
  Array.prototype.forEach.call(document.querySelectorAll(".panel[data-src]"), function (panel) {
    var btn = panel.querySelector(".p-load"), frame = panel.querySelector(".p-frame");
    if (!btn || !frame) return;
    btn.addEventListener("click", function () {
      if (panel.querySelector("iframe")) return;
      var f = document.createElement("iframe");
      f.src = panel.getAttribute("data-src");
      f.title = (panel.querySelector("h3") || {}).textContent || "Live view";
      f.setAttribute("loading", "eager");
      frame.textContent = "";
      frame.appendChild(f);
      btn.disabled = true;
      btn.textContent = "Live view loaded";
    });
  });
})();
