/* The probe of the Landed since you looked card: what the card of `#/` says, and everything the page
   keeps in this browser's storage, as test_view_page_since.py reads it. */
window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("load", function () {
  setTimeout(function () {
    var text = function (el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : ""; };
    var line = document.querySelector('[data-role="since"]'), box = line ? line.getBoundingClientRect() : null;
    var kept = {};
    for (var i = 0; i < localStorage.length; i++) kept[localStorage.key(i)] = localStorage.getItem(localStorage.key(i));
    var out = { errors: window.__errs, since: text(line),
      links: [].slice.call(document.querySelectorAll('[data-role="since"] a')).map(function (a) { return [a.innerText, a.getAttribute("href")]; }),
      box: box ? [box.left, box.top, box.width, box.height] : null, wide: window.innerWidth, high: window.innerHeight,
      kept: kept };
    var pre = document.createElement("pre");
    pre.id = "probe";
    pre.textContent = JSON.stringify(out);
    (window.top === window ? document : window.top.document).body.appendChild(pre);
  }, window.__at);
});
