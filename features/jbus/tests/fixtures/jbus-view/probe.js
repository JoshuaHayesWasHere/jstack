/* The probe that the page test adds to the page. It counts the words on the first screen, the
   view's words and the shell's words apart. It measures how big each tap target is and what is cut
   off. It opens every drawer, and answers the gates it is told to, one by one or as a batch. Then
   it writes what it found into a pre that the browser prints. In a frame, which is how the test
   gets a screen as narrow as a phone, the pre goes into the page that holds the frame. */
window.__errs = [];
/* Record each change to the page from the start: when it came, and the part it is in. The part
   is the nearest element with an id, or a row of every project by its key. What the probe itself
   adds while `__quiet` is set is no change of the page. */
window.__changes = [];
window.__quiet = false;
new MutationObserver(function (records) {
  if (window.__quiet) return;
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
/* A walk that the test asks for, 2.5 s after the page loads. It takes one step each 0.5 s and
   records what the page shows after each step. `open:<target>` taps where a person would, in the
   drawer when one is open. `back` and `forward` move through the browser's history. `esc` presses
   Escape. `arrow` taps the drawer's back arrow. `close` taps the drawer's close button. `crumb:<n>`
   taps the nth link of the drawer's breadcrumbs. `hash:<address>` sets the page's hash to the
   address. `tap:<selector>` clicks on what the page drew. `key:<key>:<selector>` focuses what the
   selector finds and presses the key on it, or, with no selector, presses the key on what has the
   focus. `focus:<selector>` puts the focus there as a keyboard would. `hover:<selector>` moves the
   pointer onto it. `cancel` sends the close request that a phone's back gesture sends.
   `cancel-hard` sends a second one in a row, which the page cannot refuse and which shuts the
   drawer. `look` does nothing but look. After each step, the walk writes down what the page shows,
   with the peek, `peek`. */
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
        notice: drawer.open ? text(document.querySelector("#dw .now")) : text(document.getElementById("none")), focus: focus ? focus.getAttribute("data-open") || focus.id : "",
        said: drawer.open ? text(document.getElementById("dw")) : "", peek: text(document.getElementById("peek")),
        acc: raw(document.querySelector("#desk .acc, #needs .acc")), accept: raw(document.querySelector("#desk [data-accept]")),
        details: raw(document.querySelector("#desk [data-details]")), nsaid: raw(document.getElementById("nsaid")),
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
  /* The text the first screen shows of `root`, one string for each run of text. Outside the
     drawer that leaves the drawer out; inside it, the first screen is what the drawer shows. */
  function texts(root) {
    var found = [], walk = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT);
    var inside = drawer.contains(root || document.body), clip = inside ? drawer.getBoundingClientRect() : { top: 0, bottom: vh, left: 0, right: vw };
    var top = Math.max(0, clip.top), bottom = Math.min(vh, clip.bottom), left = Math.max(0, clip.left), right = Math.min(vw, clip.right);
    while (walk.nextNode()) {
      var node = walk.currentNode, p = node.parentElement;
      if (!p || /^(SCRIPT|STYLE|TITLE|TEMPLATE|TEXTAREA|PRE)$/.test(p.tagName) || (!inside && drawer.contains(p))) continue;
      if (!/\S/.test(node.textContent) || !p.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
      var range = document.createRange(); range.selectNodeContents(node);
      var rects = range.getClientRects(), shown = false;
      for (var i = 0; i < rects.length; i++) { var b = rects[i]; if (b.width > 0 && b.height > 0 && b.top < bottom && b.bottom > top && b.left < right && b.right > left) shown = true; }
      if (shown) found.push(node.textContent.replace(/\s+/g, " ").trim());
    }
    return found;
  }
  function words(root) { return texts(root).reduce(function (n, one) { return n + one.split(" ").length; }, 0); }
  function all(q, root) { return Array.prototype.slice.call((root || document).querySelectorAll(q)); }
  function text(el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : ""; }
  function written(el) { return el.textContent.replace(/\s+/g, " ").trim(); }
  function shown(el) { return el.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true }); }
  function box(el) { var b = el.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)]; }
  /* Find each thing to tap that is under 44px one way, and each thing that runs past the screen
     or holds more than it shows. */
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
  /* What a screen reader says of it after its name: the description, or the label of one that
     shows no words. */
  function called(el) { return el.getAttribute("aria-description") || el.getAttribute("aria-label"); }
  function border(el) { return el ? getComputedStyle(el).borderTopStyle : ""; }
  /* The colours of the two states that ask for a look, due and missed, and their tints, as the
     browser computes them for this page and its scheme. */
  var TONES = (function () {
    var i = document.createElement("i"), found = {};
    window.__quiet = true;
    document.body.appendChild(i);
    ["due", "due-tint", "missed", "missed-tint"].forEach(function (name) { i.style.color = "var(--" + name + ")"; found[getComputedStyle(i).color] = name.split("-")[0]; });
    i.remove();
    setTimeout(function () { window.__quiet = false; }, 0);
    return found;
  })();
  /* Each shown element of `root` that paints due or missed: as its background, a border, an SVG
     fill or stroke, or the colour of its own words. With it, the words it holds, which are what
     say the state to someone who does not see the colour. A swatch of a legend, `.key`, is told
     by the words of its entry, and is marked `key`: it names a colour and claims no state. */
  function paints(root) {
    var inside = drawer.contains(root);
    return all("*", root).filter(function (el) {
      return (inside || !drawer.contains(el)) && el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) && el.getBoundingClientRect().width > 0;
    }).map(function (el) {
      var cs = getComputedStyle(el), own = Array.prototype.some.call(el.childNodes, function (n) { return n.nodeType === 3 && /\S/.test(n.textContent); });
      var hues = [cs.backgroundColor, cs.fill, cs.stroke, own ? cs.color : ""];
      ["Top", "Right", "Bottom", "Left"].forEach(function (side) { if (parseFloat(cs["border" + side + "Width"]) > 0) hues.push(cs["border" + side + "Color"]); });
      var tones = hues.map(function (c) { return TONES[c]; }).filter(Boolean);
      if (!tones.length) return null;
      var entry = el.closest(".key > *"), said = ((entry || el).innerText === undefined ? el.textContent : (entry || el).innerText).replace(/\s+/g, " ").trim();
      return { tone: tones.indexOf("missed") >= 0 ? "missed" : "due", what: (el.getAttribute("class") || el.tagName) + " " + said.slice(0, 40), words: (said.match(/\S+/g) || []).length, key: !!entry };
    }).filter(Boolean);
  }
  var main = document.querySelector("main"), dead = document.getElementById("dead");
  var out = {
    /* The view's words, and apart from them the words of the shell, which is the header. */
    words: words(document.querySelector("main")),
    shell: words(document.querySelector("header")),
    /* The first screen's text, the header's and the view's, and what the page paints due or
       missed anywhere outside the drawer. */
    screen: texts(document.body),
    paints: paints(document.body),
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
    /* The Needs you section: its heading, each row of its one list, shown or folded, and the
       control that unfolds the rest. */
    needs: (function (sec) {
      function row(r) {
        return { key: r.getAttribute("data-key"), seen: seen(r), what: written(r.querySelector(".nw")), why: all(".ny", r).map(written), meta: r.querySelector(".nm") ? written(r.querySelector(".nm")) : "", ahead: written(r.querySelector(".nd")), box: box(r),
          acts: all(".na .btn, .nf .btn", r).map(function (b) { return { text: written(b), tag: b.tagName, href: b.getAttribute("href"), fill: b.classList.contains("fill"), seen: seen(b), box: box(b), border: border(b) }; }), acting: text(r.querySelector(".acc")) };
      }
      return { shown: seen(sec), words: words(sec), text: text(sec), head: text(document.getElementById("needs-h")), count: text(document.querySelector("#needs-h b")), now: all("#nq .nr").map(row), fold: (function (b) { return b && shown(b) ? { text: text(b), expanded: b.getAttribute("aria-expanded") } : null; })(document.querySelector("#nfold [data-fold]")), said: text(document.getElementById("nsaid")),
        extra: all("#nx .tok").map(function (t) { return { text: text(t), open: t.getAttribute("data-open"), seen: seen(t), border: border(t) }; }),
        filled: all("button.fill, a.fill").filter(seen).length, focus: document.activeElement ? document.activeElement.id || document.activeElement.tagName : "" };
    })(document.getElementById("needs")),
    /* The line of one project: each row of In progress, the Merged list and the Health line. */
    prog: all("#prog li").map(function (r) { return { key: r.getAttribute("data-key"), seen: seen(r), slug: text(r.querySelector(".pgs")), state: text(r.querySelector(".pgw b")), who: text(r.querySelector(".pgw")), chips: all(".chip", r).map(text), age: text(r.querySelector(".pga")), open: r.querySelector(".pgs").getAttribute("data-open"), box: box(r) }; }),
    merged: { shown: seen(document.getElementById("merged-d")), head: text(document.getElementById("merged-s")), open: document.getElementById("merged-d").open },
    health: { shown: seen(document.getElementById("health")), text: text(document.getElementById("health")), links: all("#health [data-open]").map(function (b) { return [text(b), b.getAttribute("data-open")]; }), unplaced: text(document.getElementById("unplaced")) },
    first: all("[data-open]").filter(function (b) { return !drawer.contains(b) && seen(b); }).map(function (b) { return b.getAttribute("data-open"); }),
    /* The homes map of every project: each card, then each line of the quiet ones, in the page's
       order, with the lines of what is wrong apart from the cards under `machine`. */
    stack: (function () {
      var view = document.getElementById("stack"), none = document.getElementById("none");
      return { shown: seen(view), title: text(document.getElementById("title")), none: none && seen(none) ? text(none) : "",
        machine: all("#map-m .wl").map(text),
        rows: all("#map-c > [data-key], #map-ql > [data-key]").map(function (r) {
          var name = r.querySelector(".cn, b"), root = r.querySelector(".hm.root, a");
          return { project: r.getAttribute("data-key"), seen: seen(r), box: box(r), name: text(name), quiet: r.parentElement.id === "map-ql", tone: (r.querySelector(".card") || r).className,
            why: all(".wl", r).map(text).join(", "), counts: text(root.querySelector(".ct, span")), href: name.closest("a").getAttribute("href") };
        }) };
    })(),
    /* The board of every project, the first screen. */
    board: { shown: seen(document.getElementById("pipeline")) || seen(document.getElementById("desk")) },
    links: [],
    opened: []
  };
  /* The drawer a link of the Needs you list opens: the path after the project, `#/demo/gate/6`
     opens `gate:6`. A row folded under its control counts, since the control opens it. */
  function linked(a) {
    var segs = a.getAttribute("href").replace(/^#\//, "").split("&")[0].split("/").map(decodeURIComponent);
    return segs.length > 1 ? segs.slice(1).join(":") : "";
  }
  var queue = all("[data-open]").filter(function (b) { return !drawer.contains(b) && shown(b); }).map(function (b) { return b.getAttribute("data-open"); })
    .concat(all("#needs:not([hidden]) #nq a[href^='#/']").map(linked).filter(Boolean)), done = {};
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
    var links = all(".dw-h .crumbs a", drawer), tag = drawer.querySelector(".dw-h .tag");
    out.opened.push({ target: target, open: drawer.open, title: text(document.getElementById("dw-title")), now: text(dw.querySelector(".now")), said: said.replace(/\s+/g, " "), words: (said.match(/\S+/g) || []).length, bad: /NaN|undefined|\[object/.test(said), errors: window.__errs.length - before, fresh: seen(document.getElementById("dw-fresh")) ? text(document.getElementById("dw-fresh")) : "", box: box(drawer), small: small(dw), cut: cut(dw),
      first: words(drawer), crumb: links.length ? box(links[links.length - 1]) : null, tag: tag && seen(tag) ? box(tag) : null, paints: paints(drawer) });
    all("[data-open]", dw).forEach(function (b) { queue.push(b.getAttribute("data-open")); });
    if (target === "bus") out.links = all("li [data-open]", dw).map(function (b) { return b.getAttribute("data-open"); });
    document.getElementById("dw-close").click();
    out.opened[out.opened.length - 1].closed = !drawer.open;
    drawer.close();
  }
  /* Answer the gates. Each of `ways` opens one gate, picks a card or types words where the test
     tells it to, and taps the one button. `batch` ticks every gate that can be ticked and taps
     the batch's button. After each tap, the probe waits for the server's answer and reads the
     drawer. */
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
  /* With `__hops`, each thing to tap on the first screen, tapped once from where the page
     started: what it opened, and the drawer's words when it opened one. A link is followed by
     its address and a button is tapped where the page drew it, so each starts from the same page. */
  function hops(then) {
    var from = location.hash, goes = [];
    all("[data-open], a[href^='#']").filter(function (el) { return !drawer.contains(el) && seen(el); }).forEach(function (el) {
      var to = el.getAttribute("data-open") || el.getAttribute("href");
      if (goes.indexOf(to) < 0) goes.push(to);
    });
    out.hops = [];
    (function hop(n) {
      if (n >= goes.length) return then();
      var real = goes[n].charAt(0) === "#" ? null : all('[data-open="' + CSS.escape(goes[n]) + '"]').filter(function (el) { return !drawer.contains(el); })[0];
      if (goes[n].charAt(0) === "#") location.hash = goes[n]; else if (real) real.click(); else go(goes[n]);
      setTimeout(function () {
        out.hops.push({ to: goes[n], hash: location.hash, open: drawer.open, title: drawer.open ? text(document.getElementById("dw-title")) : "", said: drawer.open ? text(document.getElementById("dw")) : "" });
        if (drawer.open) { document.getElementById("dw-close").click(); drawer.close(); }
        if (location.hash !== from) location.hash = from;
        setTimeout(function () { hop(n + 1); }, 500);
      }, 500);
    })(0);
  }
  var told = window.__gates;
  out.answered = [];
  if (window.__hops) hops(end);
  else if (!told) end();
  else answer(told.ways || [], function () { (told.batch ? batch : function (then) { then(); })(function () { left(end); }); });
}, window.__at); });
