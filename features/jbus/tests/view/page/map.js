/* The probe of the homes map: what the map of `#/` draws, as test_view_page_map.py reads it, and
   each element that says a wrong fact and shows on the first screen. With `__tap`, it taps that first. */
window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("unhandledrejection", function (e) { window.__errs.push("rejection: " + String(e.reason && e.reason.stack || e.reason)); });
window.addEventListener("load", function () {
  if (window.__tap) setTimeout(function () { document.querySelector(window.__tap).click(); }, 2500);
  setTimeout(function () {
  var vh = window.innerHeight;
  var all = function (sel, el) { return [].slice.call((el || document).querySelectorAll(sel)); };
  var text = function (el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : ""; };
  var seen = function (el) {
    if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
    var b = el.getBoundingClientRect();
    return b.width > 0 && b.height > 0 && b.top >= 0 && b.bottom <= vh;
  };
  var line = function (l) {
    return { home: l.getAttribute("data-home"), text: text(l), health: text(l.querySelector(".hh")),
      flags: all(".hf", l).map(text), age: text(l.querySelector(".ha")) };
  };
  var card = function (c) {
    var name = c.querySelector(".cn");
    return { project: c.getAttribute("data-key"), href: name.getAttribute("href"), tone: c.querySelector(".card").className,
      homes: all(".hm", c).map(line), wrong: all(".wl", c).map(text) };
  };
  var out = { errors: window.__errs, hash: location.hash,
    bar: { text: text(document.getElementById("needs")), count: text(document.querySelector("#needs-h b")),
      go: (document.querySelector("#needs .go") || { getAttribute: function () { return null; } }).getAttribute("href"),
      list: seen(document.getElementById("nq")) },
    cards: all("#map-c > [data-key]").map(card),
    quiet: all("#map-q li").map(function (l) { return { project: l.getAttribute("data-key"), text: text(l), href: l.querySelector("a").getAttribute("href") }; }),
    machine: all("#map-m .wl").map(text),
    wrong: all("[data-wrong]").filter(seen).map(function (el) { return el.getAttribute("data-wrong"); }),
    groups: all("#prog .pgg .pgh").map(text),
    words: ["header", "main"].map(function (q) { return (text(document.querySelector(q)).match(/\S+/g) || []).length; }).reduce(function (a, b) { return a + b; }, 0),
    high: document.documentElement.scrollHeight, line: (function (one) { return one ? one.getBoundingClientRect().height : 0; })(document.querySelector("#map-ql li")) };
  var pre = document.createElement("pre");
  pre.id = "probe";
  pre.textContent = JSON.stringify(out);
  (window.top === window ? document : window.top.document).body.appendChild(pre);
}, window.__at); });
