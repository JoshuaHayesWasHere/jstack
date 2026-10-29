(function () {
  var css = document.createElement("style");
  css.textContent =
    "body:has(#pipeline:not([hidden])) main { max-width: 1440px; }" +
    "#pipeline { margin-top: 10px; }" +
    ".pl-heads { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }" +
    ".pl-hd { min-width: 0; border: 1.5px solid var(--hair); border-radius: 10px; background: var(--surface); padding: 6px 12px 8px; }" +
    ".pl-hd.hot { border-left: 5px solid var(--due); }" +
    ".pl-hd .tag { display: block; font-size: 13px; letter-spacing: .06em; text-transform: uppercase; color: var(--ink-2); }" +
    ".pl-v { display: block; font-size: 19px; font-weight: 800; line-height: 1.3; overflow-wrap: anywhere; }" +
    ".pl-d { display: block; font-size: 15px; color: var(--ink-2); overflow-wrap: anywhere; }" +
    ".pl-l { font: inherit; font-family: var(--mono); color: var(--ink); background: none; border: 0; padding: 0; cursor: pointer; text-align: left; overflow-wrap: anywhere; text-decoration: underline; text-decoration-color: var(--line); text-underline-offset: 3px; }" +
    ".pl-hm { display: none; font-size: 15px; color: var(--ink); align-self: center; }" +
    ".pl-strip { list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 6px; }" +
    ".pl-st { min-width: 0; display: grid; border: 1.5px solid var(--hair); border-radius: 8px; background: var(--surface); padding: 4px 6px 5px; }" +
    ".pl-st.hot { border-color: var(--due); box-shadow: inset 0 0 0 1px var(--due); }" +
    ".pl-k, .pl-o, .pl-x { font-size: 13px; color: var(--ink-2); overflow-wrap: anywhere; }" +
    ".pl-n { font-size: 22px; font-weight: 800; line-height: 1.1; }" +
    ".pl-bar { display: block; height: 5px; margin: 3px 0 2px; background: var(--sunk); border-radius: 3px; overflow: hidden; }" +
    ".pl-bar i { display: block; height: 100%; background: var(--due); }" +
    ".pl-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }" +
    ".pl-chips button { font: inherit; font-size: 15px; color: var(--ink); background: var(--surface); border: 1.5px solid var(--line); border-radius: 1249px; padding: 1px 12px; cursor: pointer; }" +
    ".pl-chips button[aria-pressed=true] { background: var(--ink); border-color: var(--ink); color: var(--canvas); }" +
    ".pl-board { position: relative; display: grid; gap: 6px; margin-top: 10px; align-items: start; }" +
    ".pl-col { min-width: 0; background: var(--sunk); border: 1.5px solid transparent; border-radius: 8px; padding: 5px; }" +
    ".pl-col.hot { border-color: var(--due); }" +
    ".pl-col h3 { margin: 0 0 5px; font-size: 14px; line-height: 1.3; overflow-wrap: anywhere; } .pl-col h3 span { font-weight: 400; color: var(--ink-2); }" +
    ".pl-board ol { list-style: none; margin: 0; padding: 0; display: grid; gap: 5px; }" +
    ".pl-c { width: 100%; min-width: 0; display: grid; gap: 1px; text-align: left; font: inherit; font-size: 13px; line-height: 1.3; color: var(--ink); background: var(--surface); border: 1.5px solid var(--hair); border-left: 4px solid var(--hair); border-radius: 6px; padding: 3px 6px 4px; cursor: pointer; }" +
    ".pl-c.still { border-left-color: var(--due); }" +
    ".pl-c.pk { border-color: var(--focus); border-left-color: var(--focus); box-shadow: 0 0 0 1.5px var(--focus); }" +
    ".pl-c.up, .pl-c.dn { border-color: var(--focus); box-shadow: 0 0 0 1px var(--focus); }" +
    ".pl-c.dim, .pl-c.dim .pl-m, .pl-c.dim .pl-u { background: var(--canvas); color: var(--ink-3); border-color: var(--hair); font-weight: 400; }" +
    ".pl-c.dim.still { border-left-color: var(--hair); }" +
    ".pl-s { font-family: var(--mono); font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }" +
    ".pl-m, .pl-u { font-size: 13px; color: var(--ink-2); overflow-wrap: anywhere; } .pl-w { overflow-wrap: anywhere; }" +
    "svg.pl-links { position: absolute; left: 0; top: 0; width: 100%; height: 100%; pointer-events: none; }" +
    "svg.pl-links path { fill: none; stroke: var(--focus); stroke-width: 2; }" +
    ".pl-det { border: 1.5px solid var(--hair); border-radius: 10px; background: var(--surface); padding: 0 10px; }" +
    ".pl-det.hot { border-color: var(--due); border-left-width: 5px; }" +
    ".pl-det summary { min-height: 44px; display: flex; flex-wrap: wrap; align-items: center; gap: 0 6px; cursor: pointer; font-weight: 700; }" +
    ".pl-det summary span { font-weight: 400; color: var(--ink-2); }" +
    ".pl-det ol { padding-bottom: 8px; } .pl-det .pl-u { margin: 0 0 8px; }" +
    ".pl-show { display: flex; flex-wrap: wrap; align-items: center; gap: 0 8px; margin: 10px 0 0; padding: 4px 4px 4px 12px; border: 1.5px solid var(--focus); border-radius: 8px; background: var(--surface); font-size: 15px; font-weight: 700; scroll-margin-top: 12px; overflow-wrap: anywhere; }" +
    ".pl-show button { font: inherit; min-width: 44px; min-height: 36px; color: var(--ink); background: none; border: 0; border-radius: 6px; cursor: pointer; }" +
    ".pl-unpl { margin: 10px 0 0; font-size: 15px; color: var(--ink-2); overflow-wrap: anywhere; }" +
    "@media (max-width: 1180px) { .pl-strip, .pl-board.cols { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)) !important; } }" +
    "@media (max-width: 640px) { .pl-heads { grid-template-columns: minmax(0, 1fr); gap: 6px; } .pl-strip { display: none; } .pl-board { gap: 6px; }" +
    " .pl-chips button, .pl-hm { min-height: 44px; } .pl-hm { display: inline-flex; align-items: center; padding: 0 6px; } .pl-c { min-height: 44px; font-size: 15px; } }" +
    "@media (min-width: 641px) and (max-width: 1024px) { #homes { display: none; } } @media (max-width: 1024px) { .pl-hm { display: inline-flex; align-items: center; } }";
  document.head.appendChild(css);
})();

var BOARD = null, BOARD_ASKED = 0, BOARD_ASKING = false, BOARD_FAILED = "", BOARD_PROJECT = "", BOARD_OPEN = {}, BOARD_SCROLL = false;

function boardRows() { return BOARD && BOARD.rows || []; }
function boardKey(project, slug) { return project + "/" + slug; }
function homeKey(project, home) { return project + "/" + home; }
function homeHref(key) { return "#/?home=" + key.split("/").map(encodeURIComponent).join("/"); }
function boardProjects() {
  var seen = {};
  boardRows().forEach(function (r) { seen[r.project] = true; });
  (BOARD.homes || []).forEach(function (h) { seen[h.project] = true; });
  return seen;
}
function homeLabel(project, home) { return (Object.keys(boardProjects()).length > 1 ? project + "\u00b7" : "") + home; }
function homeSaid(key) { var at = key.indexOf("/"); return at < 0 ? key : homeLabel(key.slice(0, at), key.slice(at + 1)); }
function boardOf(home) {
  if (!home) return function () { return true; };
  if (home.indexOf("/") < 0 && !boardProjects()[home]) return function (r) { return r.home === home; };
  return function (r) { return r.project === home || homeKey(r.project, r.home) === home; };
}
function boardAge(since) { var v = ms(since); return v == null ? "no time kept" : short((ms(BOARD.at) || NOW) - v); }
function boardName(key) { var s = (BOARD.stages || []).filter(function (one) { return one.key === key; })[0]; return s ? s.name : key; }
function boardView() { return { home: HASH.home || "", stage: HASH.stage || "", still: HASH.still === "1", pick: HASH.pick || "" }; }
function boardPicked(view) {
  var rows = boardRows().filter(function (r) { return r.slug === view.pick; });
  var project = BOARD_PROJECT || view.home.split("/")[0];
  return rows.filter(function (r) { return r.project === project; })[0] || rows[0] || null;
}

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

function boardPick(slug, project) { return '<button type="button" class="pl-l" data-bpick="' + esc(slug) + '" data-bproj="' + esc(project || "") + '">' + esc(slug) + '</button>'; }

function boardHeads() {
  var stuck = BOARD.stuck, wait = BOARD.longest_wait, long = BOARD.longest, oldest = null;
  if (stuck) boardRows().forEach(function (r) { if (r.stage === stuck.stage && !r.moving && (!oldest || (ms(r.since) || 0) < (ms(oldest.since) || 0))) oldest = r; });
  function head(key, tag, value, said, hot) {
    return '<div class="pl-hd' + (hot ? " hot" : "") + '" data-head="' + key + '"><span class="tag">' + tag + '</span><span class="pl-v">' + value + '</span><span class="pl-d">' + said + '</span></div>';
  }
  return '<div class="pl-heads" data-role="heads">' +
    head("stuck", "Most stuck", stuck && stuck.still ? esc(boardName(stuck.stage)) + ": " + stuck.still + " of " + stuck.count + " not moving" : "Every row is moving",
      oldest ? "Oldest " + boardPick(oldest.slug, oldest.project) + ", " + boardAge(oldest.since) + ": " + esc(oldest.cause) : "", !!(stuck && stuck.still)) +
    head("wait", "Waiting longest", wait ? boardPick(wait.slug, wait.project) + ": " + boardAge(wait.since) + " in " + esc(boardName(wait.stage)) : "No row waits",
      wait ? esc(wait.cause) : "", false) +
    head("chain", "Longest chain", long && long.depth ? long.depth + " deep, " + plural(long.chains, "chain", "chains") : "No row waits on another",
      long && long.head ? "Head " + boardPick(long.head, long.head_project) + " (" + esc(boardName(long.head_stage)) + "): " + esc(long.head_cause) : "", false) +
    '</div>';
}

var MX_WAITS = [["failing", "f", "check failing"], ["waiting", "w", "running or queued"], ["passed", "p", "passed, waits for jmerge"]];

function mxCell(home, key) { return home.cells && home.cells[key] || { count: 0, old: 0, waits: {} }; }

function mxDots(key, c) {
  var dots = [], cap = 30, w = c.waits || {};
  function put(cls, n) { for (var i = 0; i < n && dots.length < cap; i++) dots.push('<i' + (cls ? ' class="' + cls + '"' : "") + '></i>'); }
  if (key === "check") {
    var told = 0;
    MX_WAITS.forEach(function (one) { put(one[1], w[one[0]] || 0); told += w[one[0]] || 0; });
    put("x", c.count - told);
  } else {
    put("", c.count - c.old);
    put("old", c.old);
  }
  return '<span class="mx-dots" aria-hidden="true">' + dots.join("") + (c.count > cap ? '<b>+' + (c.count - cap) + '</b>' : "") + '</span>';
}

function mxSaid(key, c) {
  var w = c.waits || {}, told = 0, parts = [];
  if (key === "check") {
    MX_WAITS.forEach(function (one) { if (w[one[0]]) parts.push(w[one[0]] + " " + one[2]); told += w[one[0]] || 0; });
    if (c.count - told) parts.push(c.count - told + " no check ran");
  } else if (c.old) parts.push(c.old + " an hour or more");
  return parts.length ? ": " + parts.join(", ") : "";
}

function mxCellHref(home, key) { return homeHref(home) + "&stage=" + encodeURIComponent(key) + themed(); }

function mxChains() {
  var long = BOARD.longest, st = BOARD.stacked, words = { failing: "failing", waiting: "running or queued", passed: "passed", stacked: "stacked" };
  var path = long && long.depth > 1 && long.path || [];
  var nodes = path.map(function (slug, n) {
    return (n ? '<span class="mx-ar" aria-hidden="true">◀</span>' : "") + '<button type="button" class="mx-n' + (n ? "" : " hd") + '" data-bpick="' + esc(slug) + '" data-bproj="' + esc(long.head_project) + '">' + esc(slug) + '</button>';
  }).join("");
  var said = [path.length ? long.depth + " deep, " + plural(long.chains, "chain", "chains") : "No row waits on another"];
  if (st && st.rows) {
    var of = Object.keys(words).filter(function (k) { return st.waits && st.waits[k]; }).map(function (k) { return st.waits[k] + " " + words[k]; });
    said.push(plural(st.rows, "stacked row", "stacked rows") + " on " + plural(st.parents, "parent", "parents") + (of.length ? " (" + of.join(", ") + ")" : ""));
  }
  if (path.length) said.push("pick a row to draw its chain");
  return '<div class="mx-ch" data-role="chains"><span class="tag">Chains</span>' + nodes + '<span class="mx-cs">' + esc(said.join(" · ")) + '</span></div>';
}

function boardMatrix(view) {
  var homes = BOARD.homes || [];
  if (!homes.length) return "";
  var many = Object.keys(boardProjects()).length > 1;
  var keys = (BOARD.stages || []).filter(function (s) { return s.key !== "merged" && (s.key !== "scout" || homes.some(function (h) { return mxCell(h, "scout").count; })); });
  var heads = keys.map(function (s) {
    var total = homes.reduce(function (n, h) { return n + mxCell(h, s.key).count; }, 0);
    return '<th scope="col" class="' + (s.key === "check" ? "mx-ck" : "") + '">' + esc(s.name) + '<span class="mx-c">' + total + '</span></th>';
  }).join("");
  var body = homes.map(function (h) {
    var last = h.last && h.last.at ? "last act " + boardAge(h.last.at) : "no act kept";
    var label = swatch(h) + (many ? esc(h.project) + "\u00b7" : "") + '<b>' + esc(h.name) + '</b> ' + h.open;
    var key = homeKey(h.project, h.name), said = homeLabel(h.project, h.name);
    return '<tr data-home="' + esc(key) + '"><th scope="row">' + label + '<span class="mx-la"' + (h.last && h.last.what ? ' title="' + esc(h.last.what) + '"' : "") + '>' + last + '</span></th>' + keys.map(function (s) {
      var c = mxCell(h, s.key);
      if (!c.count) return '<td class="mx-e">·</td>';
      var on = view.home === key && view.stage === s.key;
      return '<td><a class="mx-a' + (on ? " on" : "") + '"' + (on ? ' aria-current="true"' : "") + ' data-bcell="' + esc(key + "/" + s.key) + '" href="' + mxCellHref(key, s.key) + '" aria-label="' + esc(said + ", " + s.name + ": " + plural(c.count, "row", "rows") + mxSaid(s.key, c)) + '"><span class="mx-c">' + c.count + '</span>' + mxDots(s.key, c) + '</a></td>';
    }).join("") + '</tr>';
  }).join("");
  var legend = [["", "under 1 h"], ["old", "1 h or more"]].concat(MX_WAITS.map(function (one) { return [one[1], one[2]]; }), [["x", "no check ran"]]).map(function (one) {
    return '<span><span class="mx-dots"><i' + (one[0] ? ' class="' + one[0] + '"' : "") + '></i></span>' + one[1] + '</span>';
  }).join("");
  return '<section class="mx" data-part="pipeline:matrix" data-role="matrix" aria-label="Every stage, every home"><div class="mx-hd"><span class="tag">Every stage, every home</span><span class="src">a dot per row, filled at 1 h or more · click a cell for its rows</span></div>' +
    '<div class="mx-lg">' + legend + '</div>' +
    '<div class="mx-w"><table><thead><tr><th scope="col" class="mx-hm">home</th>' + heads + '</tr></thead><tbody>' + body + '</tbody></table></div>' + mxChains() + '</section>';
}

var HL_BAR = [["failing", "failing"], ["waiting", "running"], ["passed", "passed"], ["norun", "no run"], ["other", "other stages"]];

function boardHomes() {
  var homes = BOARD && BOARD.homes || [];
  if (!homes.length) return "";
  var drawn = {};
  var lines = homes.map(function (h) {
    var c = mxCell(h, "check"), w = c.waits || {}, told = (w.failing || 0) + (w.waiting || 0) + (w.passed || 0);
    var n = { failing: w.failing || 0, waiting: w.waiting || 0, passed: w.passed || 0, norun: c.count - told, other: h.open - c.count };
    HL_BAR.forEach(function (one) { if (n[one[0]]) drawn[one[0]] = true; });
    var said = HL_BAR.filter(function (one) { return n[one[0]]; }).map(function (one) { return n[one[0]] + " " + one[1]; }).join(", ");
    var bar = '<span class="seg-bar" role="img" aria-label="' + esc(said || "nothing open") + '">' + HL_BAR.filter(function (one) { return n[one[0]]; }).map(function (one) { return '<i class="' + one[0] + '" style="flex:' + n[one[0]] + ' 0 0"></i>'; }).join("") + '</span>';
    var at = h.last && ms(h.last.at), last = at == null ? "none" : short((ms(BOARD.at) || NOW) - at);
    var key = homeKey(h.project, h.name);
    return '<a class="ehl" data-home="' + esc(key) + '" href="' + homeHref(key) + themed() + '"><b>' + esc(homeLabel(h.project, h.name)) + '</b><span class="ehl-n">' + h.open + '</span>' + bar + '<span class="ago">' + last + '</span></a>';
  }).join("");
  return '<section class="ovc" data-role="homes" aria-labelledby="ovc-homes"><h2 class="ovc-h" id="ovc-homes"><span class="tag">Every home</span> <span class="ovc-s ehl-k">' + HL_BAR.filter(function (one) { return drawn[one[0]]; }).map(function (one) { return '<span><i class="' + one[0] + '"></i>' + one[1] + '</span>'; }).join("") + '</span></h2>' + lines + '</section>';
}

function boardStages(view) {
  if (!(BOARD.stages || []).some(function (s) { return s.key === view.stage; })) view.stage = "";
  var all = !view.home && !view.still && !view.stage, mine = boardOf(view.home);
  return (BOARD.stages || []).filter(function (s) { return !view.stage || s.key === view.stage; }).map(function (s) {
    var rows = boardRows().filter(function (r) { return r.stage === s.key && mine(r) && (!view.still || !r.moving); });
    rows.sort(function (a, b) { return (a.moving - b.moving) || ((ms(a.since) || 0) - (ms(b.since) || 0)); });
    var still = rows.filter(function (r) { return !r.moving; }).length;
    var oldest = all ? s.oldest : rows.reduce(function (o, r) { return !o || (ms(r.since) || 0) < (ms(o.since) || 0) ? r : o; }, null);
    return { key: s.key, name: s.name, rows: rows, count: all ? s.count : rows.length, still: all ? s.still : still, oldest: oldest };
  });
}

function boardCols(stages) { return stages.map(function (s) { return "minmax(0, " + (s.count ? "1fr" : ".5fr") + ")"; }).join(" "); }

function boardStrip(stages, hot) {
  return '<ol class="pl-strip" data-role="strip" aria-label="Rows in each stage" style="grid-template-columns: ' + boardCols(stages) + '">' + stages.map(function (s) {
    var age = s.key === "merged" ? "today" : s.oldest ? "oldest " + boardAge(s.oldest.since) : "";
    return '<li class="pl-st' + (s.key === hot ? " hot" : "") + '" data-stage="' + esc(s.key) + '"><span class="pl-k">' + esc(s.name) + '</span> <span class="pl-n">' + s.count + '</span>' +
      (age ? ' <span class="pl-o">' + age + '</span>' : "") +
      (s.count && s.key !== "merged" ? '<span class="pl-bar"><i style="width:' + Math.round(100 * s.still / s.count) + '%"></i></span>' + (s.still ? '<span class="pl-x">' + s.still + ' not moving</span>' : "") : "") + '</li>';
  }).join("") + '</ol>';
}

function boardChips(view) {
  var homes = {}, said = {}, still = 0, mine = boardOf(view.home);
  boardRows().forEach(function (r) {
    var key = homeKey(r.project, r.home);
    homes[key] = (homes[key] || 0) + 1; said[key] = homeLabel(r.project, r.home);
    if (!r.moving && mine(r)) still += 1;
  });
  var named = Object.keys(homes).sort(function (a, b) { return homes[b] - homes[a] || (a < b ? -1 : 1); });
  function chip(attr, value, said, on) { return '<button type="button" id="ph-' + esc(attr === "data-bstill" ? "still" : value || "all") + '" ' + attr + '="' + esc(value) + '" aria-pressed="' + on + '">' + said + '</button>'; }
  return '<div class="pl-chips" data-role="chips" role="group" aria-label="Show the rows of">' +
    chip("data-bhome", "", "All homes " + boardRows().length, !view.home) +
    named.map(function (h) { return chip("data-bhome", h, esc(said[h]) + " " + homes[h], view.home === h); }).join("") +
    chip("data-bstill", "1", "Not moving only " + still, view.still) + '<a class="pl-hm" href="#/homes">Homes map</a></div>';
}

function boardShowing(view) {
  var said = [view.home ? homeSaid(view.home) : "", view.stage ? boardName(view.stage) : ""].filter(Boolean);
  if (!said.length) return "";
  return '<p class="pl-show" data-role="showing" tabindex="-1">Showing ' + esc(said.join(", ")) + ' <button type="button" data-bclear="1" aria-label="Show every home and stage">✕</button></p>';
}

function boardCard(r, marks, on) {
  var how = on ? marks[boardKey(r.project, r.slug)] || "dim" : "";
  var waits = r.waits_on.map(function (w) { return w.slug; });
  return '<li><button type="button" class="pl-c ' + (r.moving ? "mv" : "still") + (how ? " " + how : "") + '" data-bpick="' + esc(r.slug) + '" data-bproj="' + esc(r.project) + '" aria-pressed="' + (how === "pk") + '" title="' + esc(r.slug) + '">' +
    '<span class="pl-s">' + esc(r.slug) + '</span><span class="pl-m">' + esc(homeLabel(r.project, r.home)) + ' · ' + boardAge(r.since) + (r.moving ? "" : ", not moving") + '</span><span class="pl-w">' + esc(r.cause) + '</span>' +
    (waits.length ? '<span class="pl-u">waits on ' + esc(waits.join(", ")) + '</span>' : "") + '</button></li>';
}

function boardCards(stages, hot, marks, on) {
  var phone = NARROW.matches;
  return '<div class="pl-board' + (phone ? "" : " cols") + '" data-role="cards"' + (phone ? "" : ' style="grid-template-columns: ' + boardCols(stages) + '"') + '>' + stages.map(function (s) {
    var age = s.key === "merged" ? "today" : s.oldest ? "oldest " + boardAge(s.oldest.since) : "";
    var list = s.rows.length ? '<ol>' + s.rows.map(function (r) { return boardCard(r, marks, on); }).join("") + '</ol>' : s.count ? '<p class="pl-u">' + plural(s.count, "row", "rows") + ', none drawn</p>' : "";
    if (!phone) return '<section class="pl-col' + (s.key === hot ? " hot" : "") + '" data-stage="' + esc(s.key) + '"><h3>' + esc(s.name) + ' <b>' + s.count + '</b>' + (age ? ' <span>· ' + age + '</span>' : "") + '</h3>' + list + '</section>';
    var marked = on && s.rows.some(function (r) { return marks[boardKey(r.project, r.slug)]; });
    var open = marked || (BOARD_OPEN[s.key] === undefined ? s.key === hot : BOARD_OPEN[s.key]);
    return '<details class="pl-det' + (s.key === hot ? " hot" : "") + '" data-stage="' + esc(s.key) + '"' + (open ? " open" : "") + '><summary>' + esc(s.name) + ' <b>' + s.count + '</b>' +
      (s.still && s.key !== "merged" ? ' <span>· ' + s.still + ' not moving</span>' : "") + (age ? ' <span>· ' + age + '</span>' : "") + '</summary>' + list + '</details>';
  }).join("") + '<svg class="pl-links" aria-hidden="true" focusable="false"></svg></div>';
}

function boardUnplaced() {
  var u = BOARD.unplaced || [];
  if (!u.length) return "";
  return '<p class="pl-unpl"><b>Not in a stage:</b> ' + u.map(function (one) { return '<code>' + esc(one.slug) + '</code> (' + esc(one.cause) + ')'; }).join("; ") + '</p>';
}

function boardLinks() {
  var el = $("pipeline"), svg = el.querySelector("svg.pl-links");
  if (!svg) return;
  var box = svg.parentNode.getBoundingClientRect(), cards = {}, paths = [];
  [].slice.call(el.querySelectorAll(".pl-c.pk, .pl-c.up, .pl-c.dn")).forEach(function (c) {
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

function boardOwns(el) { return !$("pipeline").hidden && $("pipeline").contains(el) || !$("stack").hidden && $("matrix").contains(el); }

function boardWhere(el) {
  if (!el || !el.getAttribute || !boardOwns(el)) return "";
  var cls = el.className.split(" ")[0];
  for (var i = 0, a = ["data-bpick", "data-bproj", "data-bhome", "data-bstill", "data-bcell"], sel = cls ? "." + cls : el.tagName.toLowerCase(), any = false; i < a.length; i++) {
    if (el.hasAttribute(a[i])) { sel += "[" + a[i] + '="' + CSS.escape(el.getAttribute(a[i])) + '"]'; any = true; }
  }
  return any ? sel : "";
}

function boardAsk() {
  BOARD_ASKING = true; BOARD_ASKED = Date.now();
  ask("/panel/pipeline.json").then(function (said) {
    var b = said && said.stages ? said : said && said.data && (said.data);
    if (!b || !b.stages) throw new Error("the board has no stages");
    BOARD = b; BOARD_FAILED = "";
  }, function (e) { BOARD_FAILED = e && e.message || "no answer"; }).then(function () { BOARD_ASKING = false; render(); }, function (e) { BOARD_ASKING = false; BOARD_FAILED = e && e.message || "no answer"; render(); });
}

function boardTab() {
  var t = $("homes");
  t.hidden = !STACK;
  t.setAttribute("href", "#/homes" + (HASH.theme === "light" || HASH.theme === "dark" ? "&theme=" + HASH.theme : ""));
  if (HOMES && !PROJECT && !TRIAGE) t.setAttribute("aria-current", "page"); else t.removeAttribute("aria-current");
}

function boardDraw() {
  boardTab();
  var el = $("pipeline"), mx = $("matrix"), homes = !$("stack").hidden;
  if (!homes) put(mx, "");
  if (el.hidden && !homes) return;
  if (!BOARD_ASKING && (!BOARD || Date.now() - BOARD_ASKED >= POLL_MS)) boardAsk();
  if (!BOARD) {
    put(mx, "");
    if (!el.hidden) put(el, BOARD_FAILED ? '<p class="calm">The board could not be read: ' + esc(BOARD_FAILED) + '. <a href="#/homes">Open the homes map</a></p>' : '<p class="calm">Asking the server for the board</p>');
    return;
  }
  var view = boardView(), had = boardWhere(document.activeElement);
  var matrix = homes ? boardMatrix(view) : "", html = el.hidden ? el.__drawn : boardBoard(view);
  if (el.__drawn !== html || mx.__drawn !== matrix) {
    put(el, html);
    put(mx, matrix);
    var back = had && document.querySelector(had);
    if (back) back.focus({ preventScroll: true });
  }
  var bar = BOARD_SCROLL && el.querySelector("[data-role=showing]");
  BOARD_SCROLL = false;
  if (bar) { bar.scrollIntoView({ block: "start" }); bar.focus({ preventScroll: true }); }
  setTimeout(boardLinks, 0);
}

function boardBoard(view) {
  var picked = boardPicked(view), marks = boardMarks(picked), hot = BOARD.stuck && BOARD.stuck.still ? BOARD.stuck.stage : "", stages = boardStages(view);
  return boardHeads() + boardStrip(stages, hot) + boardChips(view) + boardShowing(view) + boardCards(stages, hot, marks, !!picked) + boardUnplaced();
}

function boardSet(change) {
  var view = boardView();
  Object.keys(change).forEach(function (k) { view[k] = change[k]; });
  HASH.home = view.home; HASH.stage = view.stage; HASH.still = view.still ? "1" : ""; HASH.pick = view.pick;
  history.replaceState(history.state, "", href("", top()));
  boardDraw();
}

document.addEventListener("click", function (e) {
  if (!e.target.closest || !boardOwns(e.target)) return;
  var b = e.target.closest("[data-bpick]");
  if (b) {
    var slug = b.getAttribute("data-bpick"), project = b.getAttribute("data-bproj");
    if ($("pipeline").hidden) { BOARD_PROJECT = project; enter("pushState", { layers: [], back: false }, board(slug, "")); return; }
    var again = b.classList.contains("pl-c") && boardView().pick === slug && BOARD_PROJECT === project;
    BOARD_PROJECT = again ? "" : project;
    boardSet({ pick: again ? "" : slug });
    return;
  }
  var h = e.target.closest("[data-bhome]");
  if (h) { var home = h.getAttribute("data-bhome"); boardSet({ home: home && boardView().home === home ? "" : home }); return; }
  if (e.target.closest("[data-bstill]")) { boardSet({ still: !boardView().still }); return; }
  if (e.target.closest("[data-bclear]")) { boardAll(); return; }
  var cell = e.target.closest("[data-bcell]");
  if (cell && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
    e.preventDefault();
    BOARD_SCROLL = true;
    enter("pushState", { layers: [], back: false, cell: true }, cell.getAttribute("href"));
  }
  var s = e.target.closest("summary");
  if (s && s.parentNode.classList.contains("pl-det")) { BOARD_OPEN[s.parentNode.getAttribute("data-stage")] = !s.parentNode.open; setTimeout(boardLinks, 0); }
});
function boardClear() { if (history.state && history.state.cell) history.back(); else boardAll(); }
function boardAll() {
  if (history.state && history.state.cell) history.replaceState(Object.assign({}, history.state, { cell: false }), "", location.href);
  boardSet({ home: "", stage: "" });
}
document.addEventListener("keydown", function (e) {
  var view = boardView();
  if (e.key !== "Escape" || $("pipeline").hidden || !(view.pick || view.stage || view.home) || drawer.open || typing(e.target)) return;
  e.preventDefault();
  if (view.pick) { BOARD_PROJECT = ""; boardSet({ pick: "" }); return; }
  boardClear();
});
window.addEventListener("resize", function () { if (!$("pipeline").hidden) setTimeout(boardLinks, 0); });

panel({ draw: boardDraw, parts: { homes: boardHomes } });
