/* The probe the page test adds to the page: it counts the words on the first screen, measures
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
   a click on what the page drew; `cancel`, the close request a phone's back gesture sends;
   `cancel-hard`, the second one in a row, which cannot be refused and shuts the drawer; or `look`. */
window.__walked = [];
window.addEventListener("load", function () { if (window.__walk) setTimeout(function () {
  function text(el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : ""; }
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
    else if (how === "cancel") drawer.dispatchEvent(new Event("cancel", { cancelable: true }));
    else if (how === "cancel-hard") { drawer.dispatchEvent(new Event("cancel")); drawer.close(); }
    setTimeout(function () {
      var focus = document.activeElement;
      window.__walked.push({ step: w, hash: location.hash, open: drawer.open, title: drawer.open ? text(document.getElementById("dw-title")) : "",
        back: drawer.open ? text(document.getElementById("dw-back")) : "", crumbs: Array.prototype.map.call(document.querySelectorAll(drawer.open ? "#dw .crumbs a" : "#title .crumbs a"), function (a) { return [text(a), a.getAttribute("href")]; }),
        notice: drawer.open ? text(document.querySelector("#dw .now")) : text(document.getElementById("none")), focus: focus ? focus.getAttribute("data-open") || focus.id : "" });
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
  function words() {
    var n = 0, walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
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
  function border(el) { return el ? getComputedStyle(el).borderTopStyle : ""; }
  var main = document.querySelector("main"), dead = document.getElementById("dead");
  var out = {
    words: words(),
    bottom: Math.round(main.getBoundingClientRect().bottom),
    scrollWidth: document.documentElement.scrollWidth,
    width: vw,
    high: vh,
    body: document.body.className,
    background: getComputedStyle(document.body).backgroundColor,
    banner: seen(dead) ? text(dead) : "",
    halves: all(".half", dead).filter(seen).map(function (h) { return [tag(h), all("code", h).map(text)]; }),
    font: parseFloat(getComputedStyle(document.body).fontSize),
    strip: box(document.getElementById("vitals")),
    band: box(document.getElementById("you")),
    bus: (function (viz) { return viz ? [all(".sd", viz).filter(seen).length, all(".dot.amber", viz).filter(seen).length] : [0, 0]; })(document.querySelector('#vitals [data-open="bus"] .viz')),
    meters: all('#vitals [data-open="room"] .mb').filter(seen).length,
    small: small(document.body),
    cut: cut(document.body),
    cards: all("#vitals .vit").map(function (c) { return { tag: c.querySelector(".tag").textContent, val: text(c.querySelector(".val")), label: c.getAttribute("aria-label"), open: c.getAttribute("data-open"), state: tag(c), border: border(c), seen: seen(c), box: box(c), valbox: box(c.querySelector(".val")) }; }),
    /* The shell: the header, the sidebar of every project, and the machine, drawn once. */
    header: { box: box(document.querySelector("header")), brand: text(document.querySelector("header .brand")), crumbs: all("#title a").map(function (a) { return [text(a), a.getAttribute("href"), a.getAttribute("aria-current") || ""]; }), where: text(document.getElementById("title")), read: text(document.getElementById("readat")) },
    side: { box: box(document.getElementById("side")), items: all("#side .sp").map(function (a) { var d = a.querySelector(".hd"); return { name: text(a.querySelector(".nm")), count: text(a.querySelector(".n")), dot: d ? d.className.replace(/^hd ?/, "") || "ok" : "", tip: a.title, href: a.getAttribute("href"), current: a.getAttribute("aria-current") || "", seen: seen(a), box: box(a) }; }) },
    machine: all("#machine .mi").map(function (c) { return { tag: text(c.querySelector(".tag")), val: text(c.querySelector(".val")), tip: c.title, open: c.getAttribute("data-open"), seen: seen(c), box: box(c) }; }),
    folded: all("#line .folded [data-open]").map(function (b) { return [text(b), b.getAttribute("data-open"), seen(b)]; }),
    count: text(document.querySelector("#you .youn")),
    tiles: all("#you .yg").map(function (y) { return { seen: seen(y.querySelector(".tok")), text: text(y.querySelector(".tok")), open: y.querySelector(".tok").getAttribute("data-open"), state: tag(y), border: border(y.querySelector(".tok")) }; }),
    line: tag(document.getElementById("filters")),
    calm: seen(document.getElementById("calm")),
    lanes: all("#line .lane").map(function (l) {
      return { name: text(l.querySelector(".laneh b")), open: l.querySelector(".laneh").getAttribute("data-open"), count: +text(l.querySelector(".n")), seen: seen(l.querySelector(".laneh")), box: box(l),
        tokens: all(".tok", l).map(function (t) { return { slug: text(t.querySelector(".lb")), open: t.getAttribute("data-open"), who: t.getAttribute("data-who"), live: (function (m) { return m ? m.className.replace("mk lv-", "") : ""; })(t.querySelector('.mk[class*="lv-"]')), long: !!t.querySelector(".mk.long"), again: !!t.querySelector(".mk.rep"), shape: !!t.querySelector(".sh"), seen: seen(t), shown: shown(t), box: box(t), border: border(t), blocks: text(t.querySelector(".bn")), blocked: text(t.parentElement.querySelector(".bk")), blocker: (t.parentElement.querySelector("button.bk") || t).getAttribute("data-open"), mark: !!t.parentElement.querySelector(".mk.blk"), wrap: t.parentElement.className, label: t.getAttribute("aria-label") }; }),
        dots: all(".md", l).map(function (d) { return { open: d.getAttribute("data-open"), seen: seen(d) }; }),
        lines: all(".fl", l).map(function (f) {
          return { name: written(f.querySelector(".flh b")), count: +written(f.querySelector(".flh i")), named: shown(f.querySelector(".flh")),
            tokens: all(".tok", f).filter(shown).map(function (t) { return [text(t.querySelector(".lb"))].concat(all(".bk", t.parentElement).map(text)); }),
            more: all(".pl", f).filter(shown).map(function (b) { return [text(b), b.getAttribute("data-open")]; }),
            waves: all(".wv", f).filter(shown).map(function (w) { return [+text(w.querySelector("b")), all(".qd", w).map(function (d) { return d.getAttribute("title"); })]; }),
            dots: all(".qd", f).filter(shown).map(function (d) { return { open: d.getAttribute("data-open"), label: d.getAttribute("aria-label"), words: text(d), off: d.classList.contains("off"), border: border(d) }; }) };
        }) };
    }),
    first: all("[data-open]").filter(function (b) { return !drawer.contains(b) && seen(b); }).map(function (b) { return b.getAttribute("data-open"); }),
    stack: (function () {
      var view = document.getElementById("stack"), none = document.getElementById("none");
      return { shown: seen(view), title: text(document.getElementById("title")), none: none && seen(none) ? text(none) : "",
        total: text(document.querySelector("#wtotal")),
        waits: all("#yrows .yrow").map(function (r) { return { project: r.getAttribute("data-key"), count: +text(r.querySelector(".pj .n")), seen: seen(r), quiet: text(r.querySelector(".quiet")),
          tokens: all(".tok", r).map(function (t) { return { text: text(t), href: t.getAttribute("href"), tip: t.title }; }) }; }),
        rows: all("#rows .proj").map(function (r) { return { project: r.getAttribute("data-key"), seen: seen(r), box: box(r), head: text(r.querySelector(".pjh")), opens: r.querySelector("h2 a").getAttribute("href"),
          chips: all(".hc", r).map(text), cells: all(".rcell", r).map(function (c) { return [text(c), c.getAttribute("href")]; }), empty: text(r.querySelector(".empty-q")) }; }) };
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
    out.opened.push({ target: target, open: drawer.open, title: text(document.getElementById("dw-title")), now: text(dw.querySelector(".now")), said: said.replace(/\s+/g, " "), words: (said.match(/\S+/g) || []).length, bad: /NaN|undefined|\[object/.test(said), errors: window.__errs.length - before, tags: all(".st", dw).map(function (s) { return s.classList.contains("fz") ? "frozen" : "live"; }), github: tag(document.getElementById("gh") && document.getElementById("gh").previousElementSibling), box: box(drawer), small: small(dw), cut: cut(dw) });
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
      borders: all(".fr", dw).map(border).filter(function (x, i, a) { return a.indexOf(x) === i; }), labels: all(".fr", dw).map(function (r) { return r.getAttribute("aria-label"); }),
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
    all("#filters [data-filter]").forEach(function (b) { if (b.getAttribute("data-filter") === "user") b.click(); });
    out.filtered = { tokens: all("#line .tok.off").length, dots: all("#line .qd.off").length };
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
