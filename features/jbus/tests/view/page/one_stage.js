window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("load", function () { setTimeout(function () {
  var all = function (sel, el) { return [].slice.call((el || document).querySelectorAll(sel)); };
  var said = function (el) { return el ? el.textContent.replace(/\s+/g, " ").trim() : null; };
  var bar = all(".dw p.src").map(said).filter(function (t) { return /The bar is the process/.test(t); })[0];
  var out = {
    errors: window.__errs,
    help: all("dl.gloss dt").map(said),
    help_stages: all("[data-stages] dt .sn").map(said),
    bar: bar ? bar.replace(/^.*The bar is the process, /, "").replace(/, and the time.*$/, "").split(" › ") : [],
    workers: all(".bd-w").map(function (w) {
      return { slug: w.querySelector(".bd-s").getAttribute("title"), kind: w.getAttribute("data-kind"), stage: said(w.querySelector(".bd-st b")) };
    }),
    homes: all(".bd-card").map(function (c) { return { home: c.getAttribute("aria-label"), state: said(c.querySelector(".bd-hs > span")) }; }),
    rows: all("li.pg").map(function (r) { return { key: r.getAttribute("data-key"), stage: said(r.querySelector(".pgw b")) }; })
  };
  fetch("/panel/pipeline.json?project=demo").then(function (a) { return a.json(); }).then(function (a) {
    out.pipeline = { stages: a.data.stages.map(function (s) { return s.name; }), rows: a.data.rows.map(function (r) { return { slug: r.slug, stage: r.stage }; }), keys: a.data.stages.map(function (s) { return s.key; }) };
  }, function (e) { out.pipeline = { error: String(e) }; }).then(function () {
    var pre = document.createElement("pre");
    pre.id = "probe";
    pre.textContent = JSON.stringify(out);
    (window.top === window ? document : window.top.document).body.appendChild(pre);
  });
}, window.__at); });
