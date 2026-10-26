// The board, the first screen (`#/`, and `#/flow`): every open row of every project in its stage,
// from `/panel/board.json`. Three headlines, a strip of the stages, then a column of cards for each
// stage; on a phone each stage is a `<details>`. A pick marks what the row waits on and what waits
// on it, links them in one SVG over the columns, and dims the rest. The home, "not moving only" and
// the pick are kept in the address: `#/?home=<home>&still=1&pick=<slug>`.
(function () {
  var css = document.createElement("style");
  css.textContent =
    "body:has(#board:not([hidden])) main { max-width: 1440px; }" +
    "#board { margin-top: 10px; }" +
    ".bd-heads { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }" +
    ".bd-hd { min-width: 0; border: 1.5px solid var(--hair); border-radius: 10px; background: var(--surface); padding: 6px 12px 8px; }" +
    ".bd-hd.hot { border-left: 5px solid var(--due); }" +
    ".bd-hd .tag { display: block; font-size: 13px; letter-spacing: .06em; text-transform: uppercase; color: var(--ink-2); }" +
    ".bd-v { display: block; font-size: 19px; font-weight: 800; line-height: 1.3; overflow-wrap: anywhere; }" +
    ".bd-d { display: block; font-size: 15px; color: var(--ink-2); overflow-wrap: anywhere; }" +
    ".bd-l { font: inherit; font-family: var(--mono); color: var(--ink); background: none; border: 0; padding: 0; cursor: pointer; text-align: left; overflow-wrap: anywhere; text-decoration: underline; text-decoration-color: var(--line); text-underline-offset: 3px; }" +
    ".bd-hm { display: none; font-size: 15px; color: var(--ink); align-self: center; }" +
    ".bd-strip { list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 6px; }" +
    ".bd-st { min-width: 0; display: grid; border: 1.5px solid var(--hair); border-radius: 8px; background: var(--surface); padding: 4px 6px 5px; }" +
    ".bd-st.hot { border-color: var(--due); box-shadow: inset 0 0 0 1px var(--due); }" +
    ".bd-k, .bd-o, .bd-x { font-size: 13px; color: var(--ink-2); overflow-wrap: anywhere; }" +
    ".bd-n { font-size: 22px; font-weight: 800; line-height: 1.1; }" +
    ".bd-bar { display: block; height: 5px; margin: 3px 0 2px; background: var(--sunk); border-radius: 3px; overflow: hidden; }" +
    ".bd-bar i { display: block; height: 100%; background: var(--due); }" +
    ".bd-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }" +
    ".bd-chips button { font: inherit; font-size: 15px; color: var(--ink); background: var(--surface); border: 1.5px solid var(--line); border-radius: 1249px; padding: 1px 12px; cursor: pointer; }" +
    ".bd-chips button[aria-pressed=true] { background: var(--ink); border-color: var(--ink); color: var(--canvas); }" +
    ".bd-board { position: relative; display: grid; gap: 6px; margin-top: 10px; align-items: start; }" +
    ".bd-col { min-width: 0; background: var(--sunk); border: 1.5px solid transparent; border-radius: 8px; padding: 5px; }" +
    ".bd-col.hot { border-color: var(--due); }" +
    ".bd-col h3 { margin: 0 0 5px; font-size: 14px; line-height: 1.3; overflow-wrap: anywhere; } .bd-col h3 span { font-weight: 400; color: var(--ink-2); }" +
    ".bd-board ol { list-style: none; margin: 0; padding: 0; display: grid; gap: 5px; }" +
    ".bd-c { width: 100%; min-width: 0; display: grid; gap: 1px; text-align: left; font: inherit; font-size: 13px; line-height: 1.3; color: var(--ink); background: var(--surface); border: 1.5px solid var(--hair); border-left: 4px solid var(--hair); border-radius: 6px; padding: 3px 6px 4px; cursor: pointer; }" +
    ".bd-c.still { border-left-color: var(--due); }" +
    ".bd-c.pk { border-color: var(--focus); border-left-color: var(--focus); box-shadow: 0 0 0 1.5px var(--focus); }" +
    ".bd-c.up, .bd-c.dn { border-color: var(--focus); box-shadow: 0 0 0 1px var(--focus); }" +
    ".bd-c.dim, .bd-c.dim .bd-m, .bd-c.dim .bd-u { background: var(--canvas); color: var(--ink-3); border-color: var(--hair); font-weight: 400; }" +
    ".bd-c.dim.still { border-left-color: var(--hair); }" +
    ".bd-s { font-family: var(--mono); font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }" +
    ".bd-m, .bd-u { font-size: 13px; color: var(--ink-2); overflow-wrap: anywhere; } .bd-w { overflow-wrap: anywhere; }" +
    "svg.bd-links { position: absolute; left: 0; top: 0; width: 100%; height: 100%; pointer-events: none; }" +
    "svg.bd-links path { fill: none; stroke: var(--focus); stroke-width: 2; }" +
    ".bd-det { border: 1.5px solid var(--hair); border-radius: 10px; background: var(--surface); padding: 0 10px; }" +
    ".bd-det.hot { border-color: var(--due); border-left-width: 5px; }" +
    ".bd-det summary { min-height: 44px; display: flex; flex-wrap: wrap; align-items: center; gap: 0 6px; cursor: pointer; font-weight: 700; }" +
    ".bd-det summary span { font-weight: 400; color: var(--ink-2); }" +
    ".bd-det ol { padding-bottom: 8px; } .bd-det .bd-u { margin: 0 0 8px; }" +
    ".bd-unpl { margin: 10px 0 0; font-size: 15px; color: var(--ink-2); overflow-wrap: anywhere; }" +
    "@media (max-width: 1180px) { .bd-strip, .bd-board.cols { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)) !important; } }" +
    "@media (max-width: 640px) { .bd-heads { grid-template-columns: minmax(0, 1fr); gap: 6px; } .bd-strip { display: none; } .bd-board { gap: 6px; }" +
    " .bd-chips button, .bd-hm { min-height: 44px; } .bd-hm { display: inline-flex; align-items: center; padding: 0 6px; } .bd-c { min-height: 44px; font-size: 15px; } #homes { display: none; } }";
  document.head.appendChild(css);
})();

var BOARD = null, BOARD_ASKED = 0, BOARD_ASKING = false, BOARD_FAILED = "", BOARD_PROJECT = "", BOARD_OPEN = {};
var BOARD_PHONE = window.matchMedia("(max-width: 640px)");

function boardRows() { return BOARD && BOARD.rows || []; }
function boardKey(project, slug) { return project + "/" + slug; }
function boardAge(since) { var v = ms(since); return v == null ? "no time kept" : short((ms(BOARD.at) || NOW) - v); }
function boardName(key) { var s = (BOARD.stages || []).filter(function (one) { return one.key === key; })[0]; return s ? s.name : key; }
function boardView() { return { home: HASH.home || "", still: HASH.still === "1", pick: HASH.pick || "" }; }
function boardPicked(view) {
  var rows = boardRows().filter(function (r) { return r.slug === view.pick; });
  return rows.filter(function (r) { return r.project === BOARD_PROJECT; })[0] || rows[0] || null;
}

// What a pick marks: the row (pk), what it waits on back to the head (up), what waits on it (dn).
function boardMarks(picked) {
  var at = {}, marks = {};
  if (!picked) return marks;
  boardRows().forEach(function (r) { at[boardKey(r.project, r.slug)] = r; });
  function walk(how, cls) {
    var look = how(picked);
    while (look.length) {
      var k = look.pop(), r = at[k];
      if (!r || marks[k]) continue;
      marks[k] = cls;
      look = look.concat(how(r));
    }
  }
  marks[boardKey(picked.project, picked.slug)] = "pk";
  walk(function (r) { return r.waits_on.map(function (w) { return boardKey(w.project, w.slug); }); }, "up");
  walk(function (r) { return r.waited_by.map(function (s) { return boardKey(r.project, s); }); }, "dn");
  return marks;
}

function boardPick(slug, project) { return '<button type="button" class="bd-l" data-bpick="' + esc(slug) + '" data-bproj="' + esc(project || "") + '">' + esc(slug) + '</button>'; }

function boardHeads() {
  var stuck = BOARD.stuck, wait = BOARD.longest_wait, long = BOARD.longest, oldest = null;
  if (stuck) boardRows().forEach(function (r) { if (r.stage === stuck.stage && !r.moving && (!oldest || (ms(r.since) || 0) < (ms(oldest.since) || 0))) oldest = r; });
  function head(key, tag, value, said, hot) {
    return '<div class="bd-hd' + (hot ? " hot" : "") + '" data-head="' + key + '"><span class="tag">' + tag + '</span><span class="bd-v">' + value + '</span><span class="bd-d">' + said + '</span></div>';
  }
  return '<div class="bd-heads" data-role="heads">' +
    head("stuck", "Most stuck", stuck && stuck.still ? esc(boardName(stuck.stage)) + ": " + stuck.still + " of " + stuck.count + " not moving" : "Every row is moving",
      oldest ? "Oldest " + boardPick(oldest.slug, oldest.project) + ", " + boardAge(oldest.since) + ": " + esc(oldest.cause) : "", !!(stuck && stuck.still)) +
    head("wait", "Waiting longest", wait ? boardPick(wait.slug, wait.project) + ": " + boardAge(wait.since) + " in " + esc(boardName(wait.stage)) : "No row waits",
      wait ? esc(wait.cause) : "", false) +
    head("chain", "Longest chain", long && long.depth ? long.depth + " deep, " + plural(long.chains, "chain", "chains") : "No row waits on another",
      long && long.head ? "Head " + boardPick(long.head, long.head_project) + " (" + esc(boardName(long.head_stage)) + "): " + esc(long.head_cause) : "", false) +
    '</div>';
}

// Each stage as the filter leaves it: its rows, not moving first and then the oldest, its count and
// its oldest. With no filter, the count and the oldest are the server's (merged counts today's).
function boardStages(view) {
  var all = !view.home && !view.still;
  return (BOARD.stages || []).map(function (s) {
    var rows = boardRows().filter(function (r) { return r.stage === s.key && (!view.home || r.home === view.home) && (!view.still || !r.moving); });
    rows.sort(function (a, b) { return (a.moving - b.moving) || ((ms(a.since) || 0) - (ms(b.since) || 0)); });
    var still = rows.filter(function (r) { return !r.moving; }).length;
    var oldest = all ? s.oldest : rows.reduce(function (o, r) { return !o || (ms(r.since) || 0) < (ms(o.since) || 0) ? r : o; }, null);
    return { key: s.key, name: s.name, rows: rows, count: all ? s.count : rows.length, still: all ? s.still : still, oldest: oldest };
  });
}

function boardCols(stages) { return stages.map(function (s) { return "minmax(0, " + (s.count ? "1fr" : ".5fr") + ")"; }).join(" "); }

function boardStrip(stages, hot) {
  return '<ol class="bd-strip" data-role="strip" aria-label="Rows in each stage" style="grid-template-columns: ' + boardCols(stages) + '">' + stages.map(function (s) {
    var age = s.key === "merged" ? "today" : s.oldest ? "oldest " + boardAge(s.oldest.since) : "";
    return '<li class="bd-st' + (s.key === hot ? " hot" : "") + '" data-stage="' + esc(s.key) + '"><span class="bd-k">' + esc(s.name) + '</span> <span class="bd-n">' + s.count + '</span>' +
      (age ? ' <span class="bd-o">' + age + '</span>' : "") +
      (s.count && s.key !== "merged" ? '<span class="bd-bar"><i style="width:' + Math.round(100 * s.still / s.count) + '%"></i></span>' + (s.still ? '<span class="bd-x">' + s.still + ' not moving</span>' : "") : "") + '</li>';
  }).join("") + '</ol>';
}

function boardChips(view) {
  var homes = {}, still = 0;
  boardRows().forEach(function (r) { homes[r.home] = (homes[r.home] || 0) + 1; if (!r.moving && (!view.home || r.home === view.home)) still += 1; });
  var named = Object.keys(homes).sort(function (a, b) { return homes[b] - homes[a] || (a < b ? -1 : 1); });
  function chip(attr, value, said, on) { return '<button type="button" ' + attr + '="' + esc(value) + '" aria-pressed="' + on + '">' + said + '</button>'; }
  return '<div class="bd-chips" data-role="chips" role="group" aria-label="Show the rows of">' +
    chip("data-bhome", "", "All homes " + boardRows().length, !view.home) +
    named.map(function (h) { return chip("data-bhome", h, esc(h) + " " + homes[h], view.home === h); }).join("") +
    chip("data-bstill", "1", "Not moving only " + still, view.still) + '<a class="bd-hm" href="#/homes">Homes map</a></div>';
}

function boardCard(r, marks, on) {
  var how = on ? marks[boardKey(r.project, r.slug)] || "dim" : "";
  var waits = r.waits_on.map(function (w) { return w.slug; });
  return '<li><button type="button" class="bd-c ' + (r.moving ? "mv" : "still") + (how ? " " + how : "") + '" data-bpick="' + esc(r.slug) + '" data-bproj="' + esc(r.project) + '" aria-pressed="' + (how === "pk") + '" title="' + esc(r.slug) + '">' +
    '<span class="bd-s">' + esc(r.slug) + '</span><span class="bd-m">' + esc(r.home) + ' · ' + boardAge(r.since) + (r.moving ? "" : ", not moving") + '</span><span class="bd-w">' + esc(r.cause) + '</span>' +
    (waits.length ? '<span class="bd-u">waits on ' + esc(waits.join(", ")) + '</span>' : "") + '</button></li>';
}

function boardCards(stages, hot, marks, on) {
  var phone = BOARD_PHONE.matches;
  return '<div class="bd-board' + (phone ? "" : " cols") + '" data-role="cards"' + (phone ? "" : ' style="grid-template-columns: ' + boardCols(stages) + '"') + '>' + stages.map(function (s) {
    var age = s.key === "merged" ? "today" : s.oldest ? "oldest " + boardAge(s.oldest.since) : "";
    var list = s.rows.length ? '<ol>' + s.rows.map(function (r) { return boardCard(r, marks, on); }).join("") + '</ol>' : s.count ? '<p class="bd-u">' + plural(s.count, "row", "rows") + ', none drawn</p>' : "";
    if (!phone) return '<section class="bd-col' + (s.key === hot ? " hot" : "") + '" data-stage="' + esc(s.key) + '"><h3>' + esc(s.name) + ' <b>' + s.count + '</b>' + (age ? ' <span>· ' + age + '</span>' : "") + '</h3>' + list + '</section>';
    var marked = on && s.rows.some(function (r) { return marks[boardKey(r.project, r.slug)]; });
    var open = marked || (BOARD_OPEN[s.key] === undefined ? s.key === hot : BOARD_OPEN[s.key]);
    return '<details class="bd-det' + (s.key === hot ? " hot" : "") + '" data-stage="' + esc(s.key) + '"' + (open ? " open" : "") + '><summary>' + esc(s.name) + ' <b>' + s.count + '</b>' +
      (s.still && s.key !== "merged" ? ' <span>· ' + s.still + ' not moving</span>' : "") + (age ? ' <span>· ' + age + '</span>' : "") + '</summary>' + list + '</details>';
  }).join("") + '<svg class="bd-links" aria-hidden="true" focusable="false"></svg></div>';
}

function boardUnplaced() {
  var u = BOARD.unplaced || [];
  if (!u.length) return "";
  return '<p class="bd-unpl"><b>Not in a stage:</b> ' + u.map(function (one) { return '<code>' + esc(one.slug) + '</code> (' + esc(one.cause) + ')'; }).join("; ") + '</p>';
}

// The links of a pick: one path from each marked row to each marked row it waits on.
function boardLinks() {
  var el = $("board"), svg = el.querySelector("svg.bd-links");
  if (!svg) return;
  var box = svg.parentNode.getBoundingClientRect(), cards = {}, paths = [];
  [].slice.call(el.querySelectorAll(".bd-c.pk, .bd-c.up, .bd-c.dn")).forEach(function (c) {
    if (c.offsetParent) cards[boardKey(c.getAttribute("data-bproj"), c.getAttribute("data-bpick"))] = c.getBoundingClientRect();
  });
  boardRows().forEach(function (r) {
    var from = cards[boardKey(r.project, r.slug)];
    if (!from) return;
    r.waits_on.forEach(function (w) {
      var to = cards[boardKey(w.project, w.slug)];
      if (!to) return;
      var fy = from.top + from.height / 2 - box.top, ty = to.top + to.height / 2 - box.top, d;
      if (Math.abs(from.left - to.left) < 4) {
        var x = from.left - box.left + 2, bend = Math.max(12, Math.min(40, Math.abs(ty - fy) / 4));
        d = "M" + x + " " + fy + " C" + (x - bend) + " " + fy + " " + (x - bend) + " " + ty + " " + x + " " + ty;
      } else {
        var right = to.left > from.left, fx = (right ? from.right : from.left) - box.left, tx = (right ? to.left : to.right) - box.left, mid = (fx + tx) / 2;
        d = "M" + fx + " " + fy + " C" + mid + " " + fy + " " + mid + " " + ty + " " + tx + " " + ty;
      }
      paths.push('<path d="' + d + '"/>');
    });
  });
  svg.setAttribute("viewBox", "0 0 " + box.width + " " + box.height);
  svg.innerHTML = paths.join("");
}

function boardWhere(el) {
  if (!el || !el.getAttribute || !$("board").contains(el)) return "";
  var cls = el.className.split(" ")[0];
  for (var i = 0, a = ["data-bpick", "data-bproj", "data-bhome", "data-bstill"], sel = "." + cls, any = false; i < a.length; i++) {
    if (el.hasAttribute(a[i])) { sel += "[" + a[i] + '="' + CSS.escape(el.getAttribute(a[i])) + '"]'; any = true; }
  }
  return any ? sel : "";
}

function boardAsk() {
  BOARD_ASKING = true; BOARD_ASKED = Date.now();
  ask("/panel/board.json").then(function (said) {
    var b = said && said.stages ? said : said && said.data && (said.data.stages ? said.data : said.data.board);
    if (!b || !b.stages) throw new Error("the board has no stages");
    BOARD = b; BOARD_FAILED = "";
  }, function (e) { BOARD_FAILED = e && e.message || "no answer"; }).then(function () { BOARD_ASKING = false; boardDraw(); }, function (e) { BOARD_ASKING = false; BOARD_FAILED = e && e.message || "no answer"; boardDraw(); });
}

function boardTab() {
  var t = $("homes");
  t.hidden = !STACK;
  t.setAttribute("href", "#/homes" + (HASH.theme === "light" || HASH.theme === "dark" ? "&theme=" + HASH.theme : ""));
  if (HOMES && !PROJECT && !TRIAGE) t.setAttribute("aria-current", "page"); else t.removeAttribute("aria-current");
}

function boardDraw() {
  boardTab();
  var el = $("board");
  if (el.hidden) return;
  if (!BOARD_ASKING && (!BOARD || Date.now() - BOARD_ASKED >= POLL_MS)) boardAsk();
  if (!BOARD) {
    put(el, BOARD_FAILED ? '<p class="calm">The board could not be read: ' + esc(BOARD_FAILED) + '. <a href="#/homes">Open the homes map</a></p>' : '<p class="calm">Asking the server for the board</p>');
    return;
  }
  var view = boardView(), picked = boardPicked(view), marks = boardMarks(picked), hot = BOARD.stuck && BOARD.stuck.still ? BOARD.stuck.stage : "";
  var stages = boardStages(view), had = boardWhere(document.activeElement);
  var html = boardHeads() + boardStrip(stages, hot) + boardChips(view) + boardCards(stages, hot, marks, !!picked) + boardUnplaced();
  if (el.__drawn !== html) {
    put(el, html);
    var back = had && el.querySelector(had);
    if (back) back.focus({ preventScroll: true });
  }
  setTimeout(boardLinks, 0);
}

function boardSet(change) {
  var view = boardView(), keep = [];
  Object.keys(change).forEach(function (k) { view[k] = change[k]; });
  if (view.home) keep.push("home=" + encodeURIComponent(view.home));
  if (view.still) keep.push("still=1");
  if (view.pick) keep.push("pick=" + encodeURIComponent(view.pick));
  Object.keys(HASH).forEach(function (k) { if (["home", "still", "pick", "theme"].indexOf(k) < 0) keep.push(k + "=" + encodeURIComponent(HASH[k])); });
  if (HASH.theme === "light" || HASH.theme === "dark") keep.push("theme=" + HASH.theme);
  HASH.home = view.home; HASH.still = view.still ? "1" : ""; HASH.pick = view.pick;
  history.replaceState(history.state, "", (/^#\/flow/.test(location.hash) ? "#/flow" : "#/") + (keep.length ? "?" + keep.join("&") : ""));
  boardDraw();
}

document.addEventListener("click", function (e) {
  var el = $("board");
  if (el.hidden || !e.target.closest || !el.contains(e.target)) return;
  var b = e.target.closest("[data-bpick]");
  if (b) {
    var slug = b.getAttribute("data-bpick"), project = b.getAttribute("data-bproj");
    var again = b.classList.contains("bd-c") && boardView().pick === slug && BOARD_PROJECT === project;
    BOARD_PROJECT = again ? "" : project;
    boardSet({ pick: again ? "" : slug });
    return;
  }
  var h = e.target.closest("[data-bhome]");
  if (h) { var home = h.getAttribute("data-bhome"); boardSet({ home: home && boardView().home === home ? "" : home }); return; }
  if (e.target.closest("[data-bstill]")) { boardSet({ still: !boardView().still }); return; }
  var s = e.target.closest("summary");
  if (s && s.parentNode.classList.contains("bd-det")) { BOARD_OPEN[s.parentNode.getAttribute("data-stage")] = !s.parentNode.open; setTimeout(boardLinks, 0); }
});
document.addEventListener("keydown", function (e) {
  if (e.key !== "Escape" || $("board").hidden || !boardView().pick || drawer.open || typing(e.target)) return;
  e.preventDefault();
  BOARD_PROJECT = "";
  boardSet({ pick: "" });
});
BOARD_PHONE.addEventListener("change", function () { boardDraw(); });
window.addEventListener("resize", function () { if (!$("board").hidden) setTimeout(boardLinks, 0); });

panel({ draw: boardDraw });
