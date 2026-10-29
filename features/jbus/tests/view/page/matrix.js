window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("load", function () { setTimeout(function () {
  var all = function (sel, el) { return [].slice.call((el || document).querySelectorAll(sel)); };
  var text = function (el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : ""; };
  var board = document.getElementById("main") || document.body, out = { errors: window.__errs, seen: [] };
  function read() {
    var m = board.querySelector("[data-role=matrix]"), box = m && m.getBoundingClientRect();
    var cols = board.querySelector("[data-role=cards]"), top = cols && cols.getBoundingClientRect().top;
    var table = m && m.querySelector("table"), legend = m && m.querySelector(".mx-lg");
    var bar = board.querySelector("[data-role=showing]"), at = bar && bar.getBoundingClientRect();
    var map = document.getElementById("map-c"), under = map && map.getBoundingClientRect();
    out.seen.push({
      hash: location.hash,
      drawn: all('[data-part="pipeline:matrix"]').length,
      overMap: !!(box && box.height && under && under.height && box.bottom <= under.top),
      heads: all("thead th", m).map(text),
      homes: all("tbody tr", m).map(function (r) {
        return { home: r.getAttribute("data-home"), head: text(r.querySelector("th")), cells: all("td", r).map(function (td) {
          var a = td.querySelector("a");
          return { text: text(td), href: a ? a.getAttribute("href") : "", dots: all(".mx-dots i", td).map(function (i) { return i.className; }) };
        }) };
      }),
      chains: text(board.querySelector("[data-role=chains]")),
      above: !!(box && top && box.bottom <= top),
      legend: !!(legend && table && legend.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING),
      stages: all("[data-stage]", cols).map(function (c) { return { key: c.getAttribute("data-stage"), slugs: all(".pl-c", c).map(function (b) { return b.getAttribute("data-bpick"); }) }; }),
      picked: all(".pl-c.pk", cols).map(function (b) { return b.getAttribute("data-bpick"); }),
      cards: all(".pl-c", cols).map(function (b) { return { slug: b.getAttribute("data-bpick"), meta: text(b.querySelector(".pl-m")) }; }),
      chips: all("[data-role=chips] button", board).map(function (b) { return { text: text(b), pressed: b.getAttribute("aria-pressed") === "true" }; }),
      bar: text(bar),
      barSeen: !!(at && at.height && at.top >= 0 && at.bottom <= window.innerHeight)
    });
  }
  // Each step: "cell:<project>/<home>/<stage>" clicks that matrix cell, "chip:<project>/<home>" that
  // home chip, "chain:<slug>" that slug of the Chains line, "esc" presses Escape, "clear" clicks the bar's ✕, "back" goes back, "help" opens the
  // help drawer and "shut" closes it. The page is read before each step and after the last.
  var steps = window.__cells;
  function act(step) {
    if (step.indexOf("cell:") === 0) board.querySelector('[data-bcell="' + step.slice(5) + '"]').click();
    else if (step.indexOf("chain:") === 0) board.querySelector('[data-role=chains] [data-bpick="' + step.slice(6) + '"]').click();
    else if (step === "esc") document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    else if (step === "clear") board.querySelector("[data-role=showing] [data-bclear]").click();
    else if (step === "back") history.back();
    else if (step.indexOf("chip:") === 0) board.querySelector('[data-bhome="' + step.slice(5) + '"]').click();
    else if (step === "help") { var b = document.createElement("button"); b.setAttribute("data-open", "help"); document.body.appendChild(b); b.click(); b.remove(); }
    else if (step === "shut") document.getElementById("dw-close").click();
  }
  (function next(n) {
    read();
    if (n < steps.length) { act(steps[n]); setTimeout(function () { next(n + 1); }, 500); return; }
    var pre = document.createElement("pre"); pre.id = "probe"; pre.textContent = JSON.stringify(out);
    (window.top === window ? document : window.top.document).body.appendChild(pre);
  })(0);
}, window.__at); });
