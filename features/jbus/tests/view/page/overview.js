/* The probe of the overview, `#/` at a desk or on a phone: each part of each region, as
   test_view_page_overview.py reads it. It waits until every part has said something other than
   that it is asking, or until `__at` ms have passed, then reads each part's box, its words and
   what in it is cut with no way to open it, the board's box, and the header, shut and with its
   menu open. */
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
     inside its part is a link or a button that opens the rest, or at a desk has a title. A
     phone has no pointer to hover with, so there a title opens nothing. */
  var touch = window.innerWidth <= 640;
  function opens(el, part) {
    for (var n = el; n && n !== part.parentNode; n = n.parentNode) if (n.getAttribute && ((!touch && n.hasAttribute("title")) || /^(A|BUTTON|SUMMARY)$/.test(n.tagName))) return true;
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
  var IDS = ["tri", "readat", "helpme", "hmenu", "homes", "pick", "theme"];
  function header() { return IDS.map(function (id) { var el = document.getElementById(id); return { id: id, text: text(el), label: el.getAttribute("aria-label") || "", expanded: el.getAttribute("aria-expanded") || "", shown: !!el.getClientRects().length, box: box(el) }; }); }
  function lines(el) { var r = document.createRange(); r.selectNodeContents(el); var tops = {}; [].forEach.call(r.getClientRects(), function (b) { tops[Math.round(b.top)] = 1; }); return { text: text(el), lines: Object.keys(tops).length }; }
  function read() {
    var parts = all("[data-part]").filter(function (p) { return p.getClientRects().length; });
    return {
      errors: window.__errs,
      high: window.innerHeight,
      wide: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      parts: parts.map(function (p) { return { name: p.getAttribute("data-part"), region: p.closest("[data-region]") ? p.closest("[data-region]").getAttribute("data-region") : "", box: box(p), text: text(p), cut: cut(p) }; }),
      board: box(document.getElementById("pipeline")),
      header: header(),
      stamp: getComputedStyle(document.querySelector(".hdr .brand"), "::after").content,
      homes: all("[data-part='pipeline:homes'] [data-home]").map(function (a) { return { home: a.getAttribute("data-home"), text: text(a), href: a.getAttribute("href"), box: box(a), bar: all(".seg-bar i", a).map(function (i) { return i.className; }), ago: lines(a.querySelector(".ago")) }; }),
      legend: all("[data-part='pipeline:homes'] .ehl-k > span").map(function (k) { var s = getComputedStyle(k.querySelector("i")); return { text: text(k), cls: k.querySelector("i").className, paint: s.backgroundColor + " " + s.backgroundImage }; }),
      regions: all("[data-region]").map(function (r) { return { name: r.getAttribute("data-region"), box: box(r) }; })
    };
  }
  /* The board's own section is drawn only once the board has answered: Every home on a phone,
     the board's columns at a desk. The part that holds Every home is there, empty, before that. */
  (function wait() {
    var parts = all("[data-part]"), ready = parts.length && !parts.some(asking) && document.querySelector(touch ? "[data-role=homes]" : "[data-role=cards]");
    if (!ready && Date.now() - started < window.__at) { setTimeout(wait, 200); return; }
    var pre = document.createElement("pre");
    pre.id = "probe";
    var seen = read(), menu = document.getElementById("hmenu");
    if (menu.getClientRects().length) { menu.click(); seen.opened = header(); seen.openedBox = box(document.querySelector(".hdr")); menu.click(); }
    pre.textContent = JSON.stringify(seen);
    (window.top === window ? document : window.top.document).body.appendChild(pre);
  })();
});
