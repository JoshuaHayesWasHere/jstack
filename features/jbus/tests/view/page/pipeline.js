window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("unhandledrejection", function (e) { window.__errs.push("rejection: " + String(e.reason)); });
window.addEventListener("load", function () { setTimeout(function () {
  var all = function (sel, el) { return [].slice.call((el || document).querySelectorAll(sel)); };
  var text = function (el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : ""; };
  var seen = function (el) { return el.checkVisibility({ checkVisibilityCSS: true }); };
  var words = function (el) { return el && seen(el) ? (text(el).match(/\S+/g) || []).length : 0; };
  var board = document.getElementById("board");
  function card(c) { return { slug: c.getAttribute("data-bpick"), cls: c.className, text: c.textContent.replace(/\s+/g, " "), pressed: c.getAttribute("aria-pressed") }; }
  function read() {
    var heads = all("[data-head]", board), cols = all("[data-stage]", board.querySelector("[data-role=cards]"));
    var marks = all(".bd-c", board).filter(function (c) { return /\b(pk|up|dn)\b/.test(c.className); });
    return {
      hash: location.hash, shown: seen(board), map: seen(document.getElementById("stack")),
      layout: board.querySelector(".bd-col") ? "columns" : board.querySelector("details.bd-det") ? "details" : "",
      heads: heads.map(function (h) { var b = h.getBoundingClientRect(); return { key: h.getAttribute("data-head"), text: text(h), value: text(h.querySelector(".bd-v")), top: Math.round(b.top), left: Math.round(b.left) }; }),
      strip: all("[data-role=strip] [data-stage]", board).filter(seen).map(function (s) { return { key: s.getAttribute("data-stage"), text: text(s), hot: s.classList.contains("hot") }; }),
      chips: all("[data-role=chips] button", board).map(function (b) { return { text: text(b), pressed: b.getAttribute("aria-pressed") }; }),
      stages: cols.map(function (c) { return { key: c.getAttribute("data-stage"), hot: c.classList.contains("hot"), open: c.tagName === "DETAILS" ? c.open : null, head: text(c.querySelector("h3, summary")), cards: all(".bd-c", c).map(card) }; }),
      marked: marks.map(function (c) { return c.getAttribute("data-bpick"); }).sort(),
      picked: all(".bd-c.pk", board).map(function (c) { return c.getAttribute("data-bpick"); }),
      dimmed: all(".bd-c.dim", board).length,
      links: all("svg.bd-links path", board).length,
      unplaced: text(board.querySelector(".bd-unpl")),
      words: { heads: words(board.querySelector("[data-role=heads]")), strip: words(board.querySelector("[data-role=strip]")) },
      wide: { width: window.innerWidth, page: document.documentElement.scrollWidth, board: board.scrollWidth, inside: board.clientWidth },
      homes: (function (t) { return t ? { hidden: t.hidden, current: t.getAttribute("aria-current") || "" } : null; })(document.getElementById("homes")),
      header: Math.round(document.querySelector("header").getBoundingClientRect().height)
    };
  }
  var out = { errors: window.__errs, before: read() };
  var target = window.__pick && board.querySelector('.bd-c[data-bpick="' + window.__pick + '"]');
  if (target) target.click();
  setTimeout(function () {
    out.picked = read();
    if (window.__tap) { var chip = board.querySelector(window.__tap); if (chip) chip.click(); }
    else document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    setTimeout(function () {
      out.after = read();
      out.errors = window.__errs;
      var pre = document.createElement("pre");
      pre.id = "probe";
      pre.textContent = JSON.stringify(out);
      (window.top === window ? document : window.top.document).body.appendChild(pre);
    }, 400);
  }, 400);
}, window.__at); });
