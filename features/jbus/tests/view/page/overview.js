/* The probe of the desk overview, `#/` at a desk: each part of each region, as
   test_view_page_overview.py reads it. It waits until every part has said something other than
   that it is asking, or until `__at` ms have passed, then reads each part's box, its words and
   what in it is cut with no title and no way to open it. */
window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("unhandledrejection", function (e) { window.__errs.push("rejection: " + String(e.reason && e.reason.stack || e.reason)); });
window.addEventListener("load", function () {
  var all = function (sel, el) { return [].slice.call((el || document).querySelectorAll(sel)); };
  var text = function (el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : ""; };
  var started = Date.now();
  function box(el) { var b = el.getBoundingClientRect(); return { top: b.top, bottom: b.bottom, left: b.left, right: b.right }; }
  function asking(el) { return /^Asking/.test(text(el)); }
  /* Something is cut where its box hides what it holds. It may be, where it or what holds it
     inside its part has a title, or is a link or a button that opens the rest. */
  function opens(el, part) {
    for (var n = el; n && n !== part.parentNode; n = n.parentNode) if (n.getAttribute && (n.hasAttribute("title") || /^(A|BUTTON|SUMMARY)$/.test(n.tagName))) return true;
    return false;
  }
  function cut(part) {
    return all("*", part).filter(function (el) {
      var s = getComputedStyle(el), b = el.getBoundingClientRect();
      if (!b.width || s.visibility === "hidden") return false;
      var hides = /hidden|clip/.test(s.overflowX + s.overflowY) || s.textOverflow === "ellipsis" || s.webkitLineClamp !== "none";
      return hides && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1) && !opens(el, part);
    }).map(function (el) { return (el.className || el.tagName) + " " + text(el).slice(0, 40); });
  }
  function read() {
    var parts = all("[data-part]").filter(function (p) { return p.getClientRects().length; });
    return {
      errors: window.__errs,
      high: window.innerHeight,
      wide: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      parts: parts.map(function (p) { return { name: p.getAttribute("data-part"), region: p.closest("[data-region]") ? p.closest("[data-region]").getAttribute("data-region") : "", box: box(p), text: text(p), cut: cut(p) }; }),
      chains: (function (c) { return c ? { box: box(c), text: text(c) } : null; })(document.querySelector("[data-role=chains]")),
      regions: all("[data-region]").map(function (r) { return { name: r.getAttribute("data-region"), box: box(r) }; })
    };
  }
  (function wait() {
    var parts = all("[data-part]"), ready = parts.length && !parts.some(asking) && document.querySelector("[data-role=matrix]");
    if (!ready && Date.now() - started < window.__at) { setTimeout(wait, 200); return; }
    var pre = document.createElement("pre");
    pre.id = "probe";
    pre.textContent = JSON.stringify(read());
    (window.top === window ? document : window.top.document).body.appendChild(pre);
  })();
});
