/* The probe the page test adds to the page: it counts the words on the first screen, the view's
   and the shell's apart, measures
   what a thumb can hit and what is cut off, opens every drawer, picks a row in the drawer of the
   queue as a flow, answers the gates it is told to, one by one or as a batch, and writes what it
   found into a pre the browser prints. In a frame, which is how the test gets a screen as narrow as a phone,
   the pre goes into the page that holds the frame. */
window.__errs = [];
/* Each change to the page, from the start: when, and the part it is in, the nearest element
   with an id, or a row of every project by its key. */
window.__changes = [];
new MutationObserver(function (records) {
  records.forEach(function (r) {
    var el = r.target.nodeType === 1 ? r.target : r.target.parentElement;
    while (el && !el.id && !(el.getAttribute && el.getAttribute("data-key"))) el = el.parentElement;
    var key = el && el.getAttribute("data-key");
    window.__changes.push({ at: Math.round(performance.now()), part: !el ? "" : key ? el.parentElement.id + ":" + key : el.id });
  });
}).observe(document, { childList: true, subtree: true, characterData: true });
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("unhandledrejection", function (e) {
  window.__errs.push("rejection: " + String(e.reason && e.reason.message || e.reason));
});
/* A walk the test asks for, 2.5 s after the page loads: one step each 0.5 s, and what the page
   shows after each. A step is `open:<target>`, tapped where a person would, in the drawer when
   one is open; `back` and `forward`, the browser's; `esc`; `arrow`, the drawer's back arrow;
   `close`; `crumb:<n>`, the nth link of the drawer's breadcrumbs; `hash:<address>`; `tap:<selector>`,
   a click on what the page drew; `key:<key>:<selector>`, the key pressed on what the selector
   finds, focused first, or with no selector on what has the focus; `focus:<selector>`, the focus
   put there as a keyboard would; `hover:<selector>`, the pointer moved onto it; `cancel`, the
   close request a phone's back gesture sends; `cancel-hard`, the second one in a row, which
   cannot be refused and shuts the drawer; or `look`. After each it writes down what the page
   shows, with the open toggletip, `tip`, and the peek, `peek`. */
window.__walked = [];
window.addEventListener("load", function () { if (window.__walk) setTimeout(function () {
  function text(el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : ""; }
  function raw(el) { return el ? el.textContent.replace(/\s+/g, " ").trim() : ""; }
  function step(n) {
    if (n >= window.__walk.length) return;
    var w = window.__walk[n], drawer = document.getElementById("drawer"), how = w.split(":")[0], what = w.slice(how.length + 1);
    if (how === "open") {
      var b = document.createElement("button"); b.setAttribute("data-open", what);
      (drawer.open ? document.getElementById("dw") : document.body).appendChild(b); b.click(); b.remove();
    } else if (how === "back") history.back();
    else if (how === "forward") history.forward();
    else if (how === "esc") (document.activeElement || document.body).dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    else if (how === "arrow") document.getElementById("dw-back").click();
    else if (how === "close") document.getElementById("dw-close").click();
    else if (how === "crumb") document.querySelectorAll("#dw .crumbs a")[+what].click();
    else if (how === "hash") location.hash = what;
    else if (how === "tap") document.querySelector(what).click();
    else if (how === "key") {
      var key = what.split(":")[0], on = what.slice(key.length + 1), el = on ? document.querySelector(on) : document.activeElement || document.body;
      if (on) el.focus();
      el.dispatchEvent(new KeyboardEvent("keydown", { key: key, bubbles: true, cancelable: true }));
    }
    else if (how === "focus") document.querySelector(what).focus();
    else if (how === "hover") document.querySelector(what).dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    else if (how === "cancel") drawer.dispatchEvent(new Event("cancel", { cancelable: true }));
    else if (how === "cancel-hard") { drawer.dispatchEvent(new Event("cancel")); drawer.close(); }
    setTimeout(function () {
      var focus = document.activeElement;
      window.__walked.push({ step: w, hash: location.hash, open: drawer.open, title: drawer.open ? text(document.getElementById("dw-title")) : "",
        back: drawer.open ? text(document.getElementById("dw-back")) : "", crumbs: Array.prototype.map.call(document.querySelectorAll(drawer.open ? "#dw .crumbs a" : "#title .crumbs a"), function (a) { return [text(a), a.getAttribute("href")]; }),
        notice: drawer.open ? text(document.querySelector("#dw .now")) : text(document.getElementById("none")), focus: focus ? focus.getAttribute("data-open") || focus.getAttribute("data-tip") || (focus.hasAttribute("data-fold") ? "fold:" + focus.getAttribute("data-fold") : focus.hasAttribute("data-hide") ? "hide:" + focus.getAttribute("data-hide") : "") || focus.id : "",
        said: drawer.open ? text(document.getElementById("dw")) : "", tip: text(document.getElementById("tip")), peek: text(document.getElementById("peek")),
        expanded: Array.prototype.map.call(document.querySelectorAll('[data-tip][aria-expanded="true"]'), function (b) { return b.getAttribute("data-tip"); }),
        acc: raw(document.querySelector("#needs .acc")), nsaid: raw(document.getElementById("nsaid")),
        rows: Array.prototype.map.call(document.querySelectorAll('[data-tip][aria-expanded="true"]'), function (b) { var r = b.closest("[data-key]"); return r ? r.getAttribute("data-key") : ""; }),
        changes: window.__changes.length });
      step(n + 1);
    }, 500);
  }
  step(0);
}, 2500); });
/* A tap the test asks for, on what `__tap` selects, a moment after the page loads. */
window.addEventListener("load", function () { if (window.__tap) setTimeout(function () { var el = document.querySelector(window.__tap); if (el) el.click(); else window.__errs.push("nothing to tap: " + window.__tap); }, 3000); });
window.addEventListener("load", function () { setTimeout(function () {
  var vh = window.innerHeight, vw = window.innerWidth, drawer = document.getElementById("drawer");
  function seen(el) {
    if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
    var b = el.getBoundingClientRect();
    return b.width > 0 && b.height > 0 && b.top < vh && b.bottom > 0 && b.left < vw && b.right > 0;
  }
  function words(root) {
    var n = 0, walk = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT);
    while (walk.nextNode()) {
      var node = walk.currentNode, p = node.parentElement;
      if (!p || /^(SCRIPT|STYLE|TITLE|TEMPLATE|TEXTAREA|PRE)$/.test(p.tagName) || drawer.contains(p)) continue;
      var found = node.textContent.match(/\S+/g) || [];
      if (!found.length || !p.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
      var range = document.createRange(); range.selectNodeContents(node);
      var rects = range.getClientRects(), shown = false;
      for (var i = 0; i < rects.length; i++) { var b = rects[i]; if (b.width > 0 && b.height > 0 && b.top < vh && b.bottom > 0 && b.left < vw && b.right > 0) shown = true; }
      if (shown) n += found.length;
    }
    return n;
  }
  function all(q, root) { return Array.prototype.slice.call((root || document).querySelectorAll(q)); }
  function text(el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : ""; }
  function written(el) { return el.textContent.replace(/\s+/g, " ").trim(); }
  function shown(el) { return el.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true }); }
  function box(el) { var b = el.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)]; }
  /* Each thing to tap that is under 44px one way, and each thing that runs past the screen or
     holds more than it shows. */
  function small(root) {
    return all("button, a[href]", root).filter(shown).filter(function (el) { var b = el.getBoundingClientRect(); return b.width < 43.5 || b.height < 43.5; })
      .map(function (el) { var b = el.getBoundingClientRect(); return (el.className || el.tagName) + " " + written(el).slice(0, 30) + " " + Math.round(b.width) + "x" + Math.round(b.height); });
  }
  function cut(root) {
    return all("*", root).filter(shown).filter(function (el) {
      var b = el.getBoundingClientRect(), hides = getComputedStyle(el).overflowX !== "visible";
      return b.width > 0 && (b.right > vw + 0.5 || b.left < -0.5 || (hides && el.scrollWidth > el.clientWidth + 1));
    }).map(function (el) { return (el.className || el.tagName) + " " + written(el).slice(0, 30); });
  }
  function tag(el) { var st = el && all(".st", el).filter(seen)[0]; return st ? (st.classList.contains("fz") ? "frozen" : "live") : ""; }
  /* What a voice says of it past its name: the description, or the label of one that shows no words. */
  function called(el) { return el.getAttribute("aria-description") || el.getAttribute("aria-label"); }
  function border(el) { return el ? getComputedStyle(el).borderTopStyle : ""; }
  var main = document.querySelector("main"), dead = document.getElementById("dead");
  var out = {
    /* The view's words, and apart from them the shell's: the header. */
    words: words(document.querySelector("main")),
    shell: words(document.querySelector("header")),
    bottom: Math.round(main.getBoundingClientRect().bottom),
    scrollWidth: document.documentElement.scrollWidth,
    width: vw,
    high: vh,
    body: document.body.className,
    background: getComputedStyle(document.body).backgroundColor,
    banner: seen(dead) ? text(dead) : "",
    font: parseFloat(getComputedStyle(document.body).fontSize),
    small: small(document.body),
    cut: cut(document.body),
    /* The shell: the header, with its one switcher and its machine word. */
    header: { box: box(document.querySelector("header")), brand: text(document.querySelector("header .brand")), crumbs: all("#title a").map(function (a) { return [text(a), a.getAttribute("href"), a.getAttribute("aria-current") || ""]; }), where: text(document.getElementById("title")), read: text(document.getElementById("readat")), stale: document.getElementById("readat").classList.contains("stale"),
      pick: all("#pick option").map(function (o) { return [o.value, text(o), o.selected]; }), machine: seen(document.getElementById("mach")) ? { text: text(document.getElementById("mach")), cls: document.getElementById("mach").className, href: document.getElementById("mach").getAttribute("href") } : null },
    /* The Needs you section: its heading, and each row of its two queues. */
    needs: (function (sec) {
      function row(r) {
        return { key: r.getAttribute("data-key"), seen: seen(r), what: written(r.querySelector(".nw")), why: all(".ny", r).map(written), meta: written(r.querySelector(".nm")), box: box(r),
          acts: all(".na .btn", r).map(function (b) { return { text: written(b), tag: b.tagName, href: b.getAttribute("href"), fill: b.classList.contains("fill"), seen: seen(b), box: box(b), border: border(b) }; }), acting: text(r.querySelector(".acc")) };
      }
      return { shown: seen(sec), words: words(sec), text: text(sec), head: text(document.getElementById("needs-h")), count: text(document.querySelector("#needs-h b")), now: all("#nq .nr").map(row), soon: all("#np .nr").map(row), said: text(document.getElementById("nsaid")),
        extra: all("#nx .tok").map(function (t) { return { text: text(t), open: t.getAttribute("data-open"), seen: seen(t), border: border(t) }; }),
        filled: all("button.fill, a.fill").filter(seen).length, focus: document.activeElement ? document.activeElement.id || document.activeElement.tagName : "" };
    })(document.getElementById("needs")),
    /* The line of one project: each row of In progress, the Merged list and the Health line. */
    prog: all("#prog li").map(function (r) { return { key: r.getAttribute("data-key"), seen: seen(r), slug: text(r.querySelector(".pgs")), state: text(r.querySelector(".pgw b")), who: text(r.querySelector(".pgw")), chips: all(".chip", r).map(text), age: text(r.querySelector(".pga")), open: r.querySelector(".pgs").getAttribute("data-open"), box: box(r) }; }),
    merged: { shown: seen(document.getElementById("merged-d")), head: text(document.getElementById("merged-s")), open: document.getElementById("merged-d").open },
    health: { shown: seen(document.getElementById("health")), text: text(document.getElementById("health")), links: all("#health [data-open]").map(function (b) { return [text(b), b.getAttribute("data-open")]; }), unplaced: text(document.getElementById("unplaced")) },
    first: all("[data-open]").filter(function (b) { return !drawer.contains(b) && seen(b); }).map(function (b) { return b.getAttribute("data-open"); }),
    /* Each ? on the page, and each that is in the folded key: the term it explains. */
    tips: all("[data-tip]").filter(function (b) { return !drawer.contains(b) && !b.closest("details") && shown(b); }).map(function (b) { return b.getAttribute("data-tip"); }),
    stack: (function () {
      var view = document.getElementById("stack"), none = document.getElementById("none");
      return { shown: seen(view), title: text(document.getElementById("title")), none: none && seen(none) ? text(none) : "",
        rows: all("#rows .prl").map(function (r) { return { project: r.parentElement.getAttribute("data-key"), seen: seen(r), box: box(r), name: text(r.querySelector(".pn")), dot: r.querySelector(".pd").className, why: text(r.querySelector(".pwhy")), counts: all(".pc", r).map(text), href: r.getAttribute("href"), said: r.getAttribute("aria-description") }; }) };
    })(),
    links: [],
    opened: []
  };
  var queue = all("[data-open]").filter(function (b) { return !drawer.contains(b) && shown(b); }).map(function (b) { return b.getAttribute("data-open"); }), done = {};
  while (queue.length && out.opened.length < 400) {
    var target = queue.shift();
    if (done[target]) continue;
    done[target] = true;
    var from = document.querySelector('main [data-open="' + CSS.escape(target) + '"]'), made = null;
    if (!from) { made = from = document.createElement("button"); made.setAttribute("data-open", target); document.body.appendChild(made); }
    var before = window.__errs.length;
    from.click();
    if (made) made.remove();
    var dw = document.getElementById("dw"), said = dw.innerText;
    out.opened.push({ target: target, open: drawer.open, title: text(document.getElementById("dw-title")), now: text(dw.querySelector(".now")), said: said.replace(/\s+/g, " "), words: (said.match(/\S+/g) || []).length, bad: /NaN|undefined|\[object/.test(said), errors: window.__errs.length - before, tags: all(".st", dw).map(function (s) { return s.classList.contains("fz") ? "frozen" : "live"; }), github: tag(document.getElementById("gh") && document.getElementById("gh").previousElementSibling), box: box(drawer), small: small(dw), cut: cut(dw), tips: all("[data-tip]", dw).map(function (b) { return b.getAttribute("data-tip"); }) });
    all("[data-open]", dw).forEach(function (b) { queue.push(b.getAttribute("data-open")); });
    if (target === "bus") out.links = all("li [data-open]", dw).map(function (b) { return b.getAttribute("data-open"); });
    document.getElementById("dw-close").click();
    out.opened[out.opened.length - 1].closed = !drawer.open;
    drawer.close();
  }
  /* The drawer of the queue as a flow: its columns and where each stands, then a row picked. */
  function flow() {
    var dw = document.getElementById("dw");
    function slugs(q) { return all(q, dw).map(function (r) { return text(r.querySelector(".lb")); }); }
    return { title: text(document.getElementById("dw-title")), chain: text(dw.querySelector(".now .big")), box: box(drawer),
      columns: all(".fc", dw).map(function (c) { return [text(c.querySelector("h3")), all(".fr", c).map(function (r) { return text(r.querySelector(".lb")); })]; }),
      lefts: all(".fc", dw).map(function (c) { return box(c)[0]; }).filter(function (x, i, a) { return a.indexOf(x) === i; }).length,
      borders: all(".fr", dw).map(border).filter(function (x, i, a) { return a.indexOf(x) === i; }), labels: all(".fr", dw).map(function (r) { return called(r); }),
      picked: slugs(".fr.pk"), up: slugs(".fr.up"), down: slugs(".fr.dn"), dim: slugs(".fr.dim").length, said: text(dw.querySelector("p")) };
  }
  if (window.__pick) {
    var way = document.createElement("button"); way.setAttribute("data-open", "flow"); document.body.appendChild(way); way.click(); way.remove();
    out.flow = flow();
    document.querySelector('#dw .fr[data-pick="' + CSS.escape(window.__pick) + '"]').click();
    out.picked = flow();
    function tap(q) { document.querySelector(q).click(); return flow().picked; }
    var row = '#dw .fr[data-pick="' + CSS.escape(window.__pick) + '"]';
    out.taps = [tap(row), tap("#dw .now [data-pick]"), tap("#dw .now [data-pick]"), tap(row)];
    drawer.close();
  }
  /* The gates. Each of `ways` opens one gate, picks a card or types words where it is told to,
     and taps the one button. `batch` ticks every gate that can be ticked and taps the batch's
     button. After each tap the probe waits for the server's answer and reads the drawer. */
  function go(target) { var b = document.createElement("button"); b.setAttribute("data-open", target); document.body.appendChild(b); b.click(); b.remove(); }
  function gate() {
    var dw = document.getElementById("dw");
    return { title: text(document.getElementById("dw-title")), said: text(dw), kv: all("dl.kv dt", dw).map(written),
      cards: all(".opt", dw).map(function (o) { return { name: text(o.querySelector("b")), picked: o.getAttribute("aria-pressed") === "true", marks: all(".om", o).map(written), follows: text(o.querySelector("small")) }; }),
      box: !!document.getElementById("gwords"), will: text(dw.querySelector("#gfoot .will")), buttons: all(".confirm", dw).map(text), links: all("[data-open]", dw).map(function (b) { return b.getAttribute("data-open"); }),
      drawer: box(drawer), small: small(dw), cut: cut(dw) };
  }
  function rows() {
    var dw = document.getElementById("dw");
    return all("li", dw).filter(function (li) { return li.querySelector(".n") && !li.querySelector(".n.zero"); }).map(function (li) {
      return { number: text(li.querySelector(".n")), tick: !!li.querySelector("[data-tick]"), ticked: !!(li.querySelector("[data-tick]") || {}).checked, options: all(".oc", li).map(text), taken: all(".oc.tk", li).map(text), opens: all("[data-open]", li).map(function (b) { return b.getAttribute("data-open"); }), said: text(li) };
    });
  }
  function foot() { var f = document.getElementById("bfoot"); return f ? { line: text(f.querySelector(".will, p")), button: text(f.querySelector("#bsend")), off: f.querySelector("#bsend").disabled } : null; }
  function answer(ways, then) {
    if (!ways.length) return then();
    var w = ways[0], seen = {};
    go("gate:" + w.number);
    seen.opened = gate();
    if (w.option != null) all("#dw .opt")[w.option].click();
    if (w.words) { var typed = document.getElementById("gwords"); typed.value = w.words; typed.dispatchEvent(new Event("input", { bubbles: true })); }
    seen.before = gate();
    document.getElementById("gsend").click();
    setTimeout(function () { seen.after = gate(); out.answered.push(seen); drawer.close(); answer(ways.slice(1), then); }, 900);
  }
  function batch(then) {
    go("you:gate");
    var seen = { rows: rows(), none: foot(), control: text(document.getElementById("tickall")), drawer: box(drawer), small: small(document.getElementById("dw")), cut: cut(document.getElementById("dw")) };
    document.getElementById("tickall").click();
    seen.ticked = rows().filter(function (r) { return r.ticked; }).map(function (r) { return r.number; });
    seen.all = foot();
    document.getElementById("bsend").click();
    setTimeout(function () { seen.after = gate(); out.batch = seen; drawer.close(); then(); }, 900);
  }
  function left(then) { setTimeout(function () { go("you:gate"); out.left = rows().map(function (r) { return r.number; }); drawer.close(); then(); }, 600); }
  function end() {
    var last = window.__task ? "task:" + window.__task : "";
    if (last) go(last);
    setTimeout(function () {
      out.github = text(document.getElementById("gh"));
      out.errors = window.__errs;
      out.changes = window.__changes;
      out.hash = location.hash;
      out.walked = window.__walked;
      out.marked = performance.getEntriesByName("jbus-first-render").length;
      out.nan = /NaN|undefined|\[object/.test(document.body.innerText);
      var pre = document.createElement("pre");
      pre.id = "probe";
      pre.textContent = JSON.stringify(out);
      (window.top === window ? document : window.top.document).body.appendChild(pre);
    }, 1500);
  }
  var told = window.__gates;
  out.answered = [];
  if (!told) end();
  else answer(told.ways || [], function () { (told.batch ? batch : function (then) { then(); })(function () { left(end); }); });
}, window.__at); });
