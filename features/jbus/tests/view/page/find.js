/* The probe of the Find drawer, as test_view_page_find.py reads it: it taps Find on the first
   screen, types `__type` into the box as a person would, and reads the drawer: where the focus
   is, what it says, each match, and whatever runs past the screen. */
window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("unhandledrejection", function (e) { window.__errs.push("rejection: " + String(e.reason && e.reason.stack || e.reason)); });
window.addEventListener("load", function () {
  var all = function (sel, el) { return [].slice.call((el || document).querySelectorAll(sel)); };
  var text = function (el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : ""; };
  setTimeout(function () { document.querySelector('#prog-t [data-open="find"]').click(); }, 2500);
  setTimeout(function () {
    window.__focus = document.activeElement ? document.activeElement.id : "";
    var q = document.getElementById("find-q");
    window.__type.split("").forEach(function (c) { q.value += c; q.dispatchEvent(new Event("input", { bubbles: true })); });
  }, 3500);
  setTimeout(function () {
    var vw = document.documentElement.clientWidth, dw = document.getElementById("dw");
    var out = { errors: window.__errs, hash: location.hash, focus: window.__focus, open: document.getElementById("drawer").open,
      title: text(document.getElementById("dw-title")), said: text(document.getElementById("find-n")),
      found: all("#find-l li").map(text),
      cut: all("*", dw).filter(function (el) { var b = el.getBoundingClientRect(); return b.width > 0 && (b.right > vw + 0.5 || b.left < -0.5); }).map(function (el) { return el.tagName + " " + text(el).slice(0, 30); }),
      wide: [dw.scrollWidth, dw.clientWidth], page: [document.documentElement.scrollWidth, vw] };
    var pre = document.createElement("pre");
    pre.id = "probe";
    pre.textContent = JSON.stringify(out);
    (window.top === window ? document : window.top.document).body.appendChild(pre);
  }, window.__at);
});
