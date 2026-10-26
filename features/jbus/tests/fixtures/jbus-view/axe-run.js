/* The axe run that the page test adds to the page, after axe itself (`axe.min.js` beside this
   file, which the test reads and the view never serves). A moment after the page loads, it runs
   axe over the view, with WCAG 2.2's target size on. Then it opens every drawer that the view,
   each link of a Needs you row and each drawer name, and runs axe over each one. It also puts
   the focus on everything that takes it, as a keyboard would, and measures the ring each one
   draws. It writes what it found into a pre that the browser prints. When the page is in a
   frame, the pre goes into the page that holds the frame, as the probe does. */
window.addEventListener("load", function () { setTimeout(function () {
  var drawer = document.getElementById("drawer"), found = [], rings = [], looked = [], errors = [];
  window.addEventListener("error", function (e) { errors.push(String(e.message)); });
  function all(q, root) { return Array.prototype.slice.call((root || document).querySelectorAll(q)); }
  function shown(el) { return el.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true }); }
  /* Focus each thing a key can reach, in turn. Its ring, an outline or a shadow, must show. */
  function ring(root, where) {
    all('a[href], button:not([disabled]), input, textarea, select, summary, [tabindex]:not([tabindex="-1"])', root).filter(shown).forEach(function (el) {
      if (!drawer.open && drawer.contains(el)) return;
      el.focus();
      if (document.activeElement !== el) return;
      var st = getComputedStyle(el), width = st.outlineStyle === "none" ? 0 : parseFloat(st.outlineWidth);
      if (width < 2 && st.boxShadow === "none") rings.push(where + ": " + (el.id || el.getAttribute("data-open") || el.getAttribute("data-tip") || el.className || el.tagName));
      el.blur();
    });
  }
  /* A rule of WCAG 2.2 at level A or AA fails the run at any impact; any other rule fails it
     when axe calls it serious or critical. */
  var WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"];
  function check(where, context) {
    return axe.run(context, { resultTypes: ["violations"], rules: { "target-size": { enabled: true } } }).then(function (r) {
      looked.push(where);
      r.violations.forEach(function (v) {
        var wcag = v.tags.some(function (t) { return WCAG.indexOf(t) >= 0; });
        if (!wcag && v.impact !== "serious" && v.impact !== "critical") return;
        found.push({ where: where, rule: v.id, impact: v.impact, nodes: v.nodes.slice(0, 5).map(function (n) { return n.target.join(" ") + " " + (n.failureSummary || "").replace(/\s+/g, " ").slice(0, 160); }) });
      });
    });
  }
  function open(target) { var b = document.createElement("button"); b.setAttribute("data-open", target); document.body.appendChild(b); b.click(); b.remove(); }
  /* The drawer a link of the Needs you list opens: the path after the project, `#/demo/gate/6`
     opens `gate:6`. A row folded under its control counts, since the control opens it. */
  function linked(a) {
    var segs = a.getAttribute("href").replace(/^#\//, "").split("&")[0].split("/").map(decodeURIComponent);
    return segs.length > 1 ? segs.slice(1).join(":") : "";
  }
  var queue = all("[data-open]").filter(function (b) { return !drawer.contains(b) && shown(b); }).map(function (b) { return b.getAttribute("data-open"); })
    .concat(all("#needs:not([hidden]) #nq a[href^='#/']").map(linked).filter(Boolean));
  var done = {};
  if (drawer.open) queue = all("#dw [data-open]").map(function (b) { return b.getAttribute("data-open"); });
  function next() {
    while (queue.length) {
      var target = queue.shift();
      if (done[target]) continue;
      done[target] = true;
      if (drawer.open) { document.getElementById("dw-close").click(); drawer.close(); }
      open(target);
      if (!drawer.open) continue;
      all("#dw [data-open]").forEach(function (b) { queue.push(b.getAttribute("data-open")); });
      ring(drawer, target);
      return check(target, "#drawer").then(next);
    }
    return Promise.resolve();
  }
  /* The first stop of the Tab key, and how it shows once it has the focus. */
  var stops = all('a[href], button:not([disabled]), input, textarea, select, summary, [tabindex]:not([tabindex="-1"])').filter(function (el) { return !drawer.contains(el); });
  var skip = null;
  if (stops.length) {
    stops[0].focus();
    var b = stops[0].getBoundingClientRect();
    skip = { cls: stops[0].className, text: stops[0].textContent.trim(), href: stops[0].getAttribute("href"), seen: stops[0].checkVisibility({ checkOpacity: true }) && b.width > 1 && b.height > 1 && b.top >= 0 };
    stops[0].blur();
  }
  var first = drawer.open ? location.hash : "view";
  if (drawer.open) ring(drawer, first); else ring(document, first);
  check(first, document).then(next).catch(function (e) { errors.push(String(e && e.message || e)); }).then(function () {
    var pre = document.createElement("pre");
    pre.id = "probe";
    pre.textContent = JSON.stringify({ skip: skip, violations: found, rings: rings, looked: looked, errors: errors, theme: document.documentElement.getAttribute("data-theme") || "" });
    (window.top === window ? document : window.top.document).body.appendChild(pre);
  });
}, window.__at); });
