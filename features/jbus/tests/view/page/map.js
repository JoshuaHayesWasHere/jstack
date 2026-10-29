/* The probe of the homes map: what the map of `#/` draws, as test_view_page_map.py reads it, and
   each element that says a wrong fact and shows on the first screen, and the role of each panel's
   card the page draws. With `__tap`, it taps that first. With `__looked`, a time in ms, the user last
   looked then, so the since card has something to say. */
window.__errs = [];
if (window.__looked != null) localStorage.setItem("jbus.since.looked", String(window.__looked));
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
    map: (function (m) { return !m.hidden && m.getBoundingClientRect().height > 0; })(document.getElementById("stack")),
    panels: all("#desk [data-part], #ov-tail [data-part]").filter(function (el) {
      var b = el.getBoundingClientRect();
      return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) && b.width > 0 && b.height > 0;
    }).map(function (el) { return el.getAttribute("data-part").split(":")[0]; }).filter(function (name, n, all) { return all.indexOf(name) === n; }),
    wrong: all("[data-wrong]").filter(seen).map(function (el) { return el.getAttribute("data-wrong"); }),
    groups: all("#prog .pgg .pgh").map(text),
    /* The map's words and the page's height as they would be with no matrix over the map: the
       matrix is the board's, and a page no taller than the screen is the screen's height. */
    words: ["header", "main"].map(function (q) { return (text(document.querySelector(q)).match(/\S+/g) || []).length; }).reduce(function (a, b) { return a + b; }, 0) - (text(document.getElementById("matrix")).match(/\S+/g) || []).length,
    high: Math.max(document.documentElement.clientHeight, document.documentElement.scrollHeight - (function (m) { var mx = m.firstElementChild, high = m.getBoundingClientRect().height; return high ? Math.round(high + parseFloat(getComputedStyle(mx).marginBottom)) : 0; })(document.getElementById("matrix"))), line: (function (one) { return one ? one.getBoundingClientRect().height : 0; })(document.querySelector("#map-ql li")) };
  var pre = document.createElement("pre");
  pre.id = "probe";
  pre.textContent = JSON.stringify(out);
  (window.top === window ? document : window.top.document).body.appendChild(pre);
}, window.__at); });
