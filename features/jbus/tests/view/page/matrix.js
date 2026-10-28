window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("load", function () { setTimeout(function () {
  var all = function (sel, el) { return [].slice.call((el || document).querySelectorAll(sel)); };
  var text = function (el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : ""; };
  var board = document.getElementById("pipeline"), out = { errors: window.__errs, seen: [] };
  function read(step) {
    var m = board.querySelector("[data-role=matrix]"), box = m && m.getBoundingClientRect();
    var cols = board.querySelector("[data-role=cards]"), top = cols && cols.getBoundingClientRect().top;
    out.seen.push({
      step: step, hash: location.hash,
      heads: all("thead th", m).map(text),
      homes: all("tbody tr", m).map(function (r) {
        return { home: r.getAttribute("data-home"), head: text(r.querySelector("th")), cells: all("td", r).map(function (td) {
          var a = td.querySelector("a");
          return { text: text(td), href: a ? a.getAttribute("href") : "", dots: all(".mx-dots i", td).map(function (i) { return i.className; }) };
        }) };
      }),
      chains: text(board.querySelector("[data-role=chains]")),
      above: !!(box && top && box.bottom <= top),
      stages: all("[data-stage]", cols).map(function (c) { return { key: c.getAttribute("data-stage"), slugs: all(".pl-c", c).map(function (b) { return b.getAttribute("data-bpick"); }) }; }),
      chips: all("[data-role=chips] button[aria-pressed=true]", board).map(text)
    });
  }
  var steps = [
    function () { read("first"); board.querySelector('[data-bcell="jview/check"]').click(); },
    function () { read("cell"); board.querySelector('[data-bcell="root/stacked"]').click(); },
    function () { read("cell2"); document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })); },
    function () { read("esc"); board.querySelector('[data-bcell="root/stacked"]').click(); },
    function () { read("again"); board.querySelector('[data-bcell="root/stacked"]').click(); },
    function () { read("twice"); history.back(); },
    function () { read("back"); board.querySelector('[data-bcell="jview/check"]').click(); },
    function () { var b = document.createElement("button"); b.setAttribute("data-open", "help"); document.body.appendChild(b); b.click(); b.remove(); },
    function () { document.getElementById("dw-close").click(); },
    function () { read("shut"); board.querySelector('[data-bcell="root/stacked"]').click(); },
    function () { read("over"); document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })); },
    function () {
      read("drawn");
      var pre = document.createElement("pre"); pre.id = "probe"; pre.textContent = JSON.stringify(out);
      (window.top === window ? document : window.top.document).body.appendChild(pre);
    }
  ];
  (function next(n) { steps[n](); if (n + 1 < steps.length) setTimeout(function () { next(n + 1); }, 500); })(0);
}, window.__at); });
