/* The probe of the glance band: what the band at the top of `#/` draws, as test_view_page_glance.py
   reads it, and the time the page keeps of when the user last looked. Before the page's own scripts
   run, it puts `__looked` in that store, and with `__hidden` the page starts in a tab the user does
   not see. `__flip` is two times in ms: the tab is hidden at the first and shown again at the
   second. */
window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("unhandledrejection", function (e) { window.__errs.push("rejection: " + String(e.reason && e.reason.stack || e.reason)); });
(function () {
  var KEY = "jbus.glance.looked", hidden = !!window.__hidden;
  if (window.__looked != null) localStorage.setItem(KEY, String(window.__looked));
  Object.defineProperty(document, "visibilityState", { configurable: true, get: function () { return hidden ? "hidden" : "visible"; } });
  Object.defineProperty(document, "hidden", { configurable: true, get: function () { return hidden; } });
  function turn(to) { hidden = to; document.dispatchEvent(new Event("visibilitychange")); }
  if (window.__flip) {
    setTimeout(function () { turn(true); }, window.__flip[0]);
    setTimeout(function () { turn(false); }, window.__flip[1]);
  }
  window.addEventListener("load", function () {
    setTimeout(function () {
      var all = function (sel, el) { return [].slice.call((el || document).querySelectorAll(sel)); };
      var text = function (el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : null; };
      var band = document.querySelector('#cards [data-role="glance"]');
      var out = {
        errors: window.__errs,
        cards: document.getElementById("cards").innerHTML.trim(),
        band: band && {
          calm: text(band.querySelector('[data-role="calm"]')),
          head: text(band.querySelector(".gl-h")),
          since: text(band.querySelector(".gl-since")),
          moving: text(band.querySelector(".gl-m")),
          tiers: all(".gl-t", band).map(function (t) {
            var more = t.querySelector(".gl-more a");
            return { head: text(t.querySelector("h3")), rows: all(".gl-r", t).map(function (r) { return r.getAttribute("data-kind") + ":" + text(r.querySelector(".gl-s code")); }),
              more: text(more), href: more && more.getAttribute("href") };
          }),
        },
        stamp: localStorage.getItem(KEY),
      };
      var pre = document.createElement("pre");
      pre.id = "probe";
      pre.textContent = JSON.stringify(out);
      (window.top === window ? document : window.top.document).body.appendChild(pre);
    }, window.__at);
  });
})();
