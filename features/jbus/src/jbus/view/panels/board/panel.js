var BOARD_KIND = { crew: ["C", "crewmate"], reviewer: ["R", "reviewer"], scout: ["S", "scout"] };
var BOARD_HEALTH = { moving: ["Working", ""], quiet: ["Quiet", "ask"], hung: ["Hung", "bad"], waiting: ["Waiting on you", "ask"], ended: ["Idle, with work open", "ask"], rest: ["At rest", ""], none: ["No home thread", ""], unknown: ["Not known", ""] };
var BOARD_STYLE = '<style>' +
  '.bd-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 400px), 1fr)); gap: 12.5px; margin-top: 12.5px; }' +
  '.bd-card { min-width: 0; border: 1.5px solid var(--hair); border-top: 5px solid var(--ink-3); border-radius: 10px; background: var(--surface); padding: 6px 12px 8px; }' +
  '.bd-card.ask { border-top-color: var(--due); } .bd-card.bad { border-top-color: var(--missed); }' +
  '.dw .bd-h { text-transform: none; letter-spacing: normal; color: var(--ink); font-weight: 800; display: flex; flex-wrap: wrap; gap: 2px 10px; align-items: baseline; margin: 0; font-size: 18px; }' +
  '.dw .bd-h .bd-hs { font-size: 15px; font-weight: 400; color: var(--ink-2); }' +
  '.bd-h .ask { color: var(--due); font-weight: 700; } .bd-h .bad { color: var(--missed); font-weight: 700; }' +
  '.bd-sum { display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0 4px; font-size: 15px; color: var(--ink-2); }' +
  '.bd-sum span { border-radius: 1249px; box-shadow: inset 0 0 0 1px var(--hair); padding: 0 8px; white-space: nowrap; }' +
  '.bd-sum b { color: var(--ink); }' +
  '.bd-w { display: grid; grid-template-columns: 22px minmax(0, 1fr) auto auto; gap: 2px 10px; align-items: center; padding: 4px 0; border-top: 1px solid var(--hair); }' +
  '.bd-k { width: 22px; height: 22px; border-radius: 6px; background: var(--sunk); color: var(--ink-2); font-size: 13px; font-weight: 800; display: inline-flex; align-items: center; justify-content: center; }' +
  '.bd-s { min-width: 0; text-align: left; background: none; border: 0; padding: 0; cursor: pointer; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }' +
  '.bd-s:hover { text-decoration: underline; }' +
  '.bd-st { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; font-size: 15px; white-space: nowrap; }' +
  '.bd-st .bd-sw { color: var(--ink-2); } .bd-st .ask { color: var(--due); font-weight: 700; } .bd-st .bad { color: var(--missed); font-weight: 700; }' +
  '.bd-dots { display: inline-flex; gap: 3px; } .bd-dots i { display: block; flex: none; width: 12px; height: 6px; border-radius: 3px; background: var(--hair); }' +
  '.bd-dots i.bd-was { background: var(--ink-3); } .bd-dots i.bd-at { background: var(--brand); width: 18px; }' +
  '.bd-dots.ask i.bd-at { background: var(--due); } .bd-dots.bad i.bd-at { background: var(--missed); }' +
  '.bd-a { font-size: 15px; color: var(--ink-2); font-variant-numeric: tabular-nums; min-width: 3.2em; text-align: right; }' +
  '.bd-goal { margin: 2px 0 6px; font-size: 15px; color: var(--ink-2); }' +
  '.bd-chain { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 2px; margin: 0 0 6px; padding: 0; list-style: none; font-size: 15px; }' +
  '.bd-chain li { display: inline-flex; align-items: center; gap: 4px; min-width: 0; }' +
  '.bd-chain li + li::before { content: "\\2192"; color: var(--ink-3); margin: 0 4px 0 2px; }' +
  '.bd-m { width: 10px; height: 10px; border-radius: 50%; flex: none; box-shadow: inset 0 0 0 2px var(--ink-3); }' +
  '.bd-m.merged { background: var(--ink-3); } .bd-m.working { background: var(--brand); box-shadow: none; } .bd-m.queued { box-shadow: inset 0 0 0 2px var(--brand); } .bd-m.parked { box-shadow: inset 0 0 0 2px var(--hair); }' +
  '.bd-chain .merged .bd-cs, .bd-chain .parked .bd-cs { color: var(--ink-2); } .bd-chain .working .bd-cs { font-weight: 700; }' +
  '.bd-cs { max-width: 22ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }' +
  '.bd-done { margin: 0; padding: 4px 0 0; border-top: 1px solid var(--hair); font-size: 15px; color: var(--ink-2); }' +
  '.bd-done b { color: var(--ink); }' +
  '.bd-ml { background: none; border: 0; padding: 0; cursor: pointer; color: var(--ink); text-decoration: underline; font-size: 15px; }' +
  '@media (max-width: 640px) { .bd-ml { min-height: 44px; } }' +
  '.bd-none { font-size: 15px; color: var(--ink-2); padding: 4px 0; border-top: 1px solid var(--hair); margin: 0; }' +
  '@media (max-width: 640px) { .bd-w { grid-template-columns: 22px minmax(0, 1fr) auto; } .bd-st { grid-column: 2 / 4; flex-direction: row; justify-content: space-between; align-items: center; } .bd-a { grid-row: 1; grid-column: 3; } .bd-s { min-height: 44px; } }' +
  '</style>';
function boardWorker(w, stages) {
  var at = 0, k = BOARD_KIND[w.kind] || ["?", w.kind], v = ms(w.since), tone = w.tone ? " " + w.tone : "";
  stages.forEach(function (s, n) { if (s.key === w.stage) at = n; });
  var name = stages[at].name;
  var dots = stages.map(function (s, n) { return '<i class="' + (n < at ? "bd-was" : n === at ? "bd-at" : "") + '"></i>'; }).join("");
  return '<li class="bd-w" data-stage="' + esc(w.stage) + '" data-kind="' + esc(w.kind) + '">' +
    '<span class="bd-k" title="' + esc(k[1]) + '" aria-label="' + esc(k[1]) + '">' + k[0] + '</span>' +
    '<button type="button" class="bd-s" data-open="' + esc(w.open) + '" title="' + esc(w.slug) + '">' + esc(w.slug) + (w.pr ? ' <span class="src">' + esc(w.pr) + '</span>' : "") + '</button>' +
    '<span class="bd-st"><span class="bd-dots' + tone + '" role="img" aria-label="stage ' + (at + 1) + ' of ' + stages.length + ': ' + esc(name) + '">' + dots + '</span>' +
    '<span><b class="' + esc(w.tone) + '">' + esc(name) + '</b>' + (w.state && w.state !== name ? ' <span class="bd-sw">&middot; ' + esc(w.state) + '</span>' : "") + '</span></span>' +
    '<span class="bd-a" title="' + (v == null ? "no time kept" : "on this stage since " + esc(day(v))) + '">' + (v == null ? "&ndash;" : short(NOW - v)) + '</span></li>';
}
var BOARD_MARK = { merged: "merged", working: "in progress", queued: "queued", planned: "planned", parked: "parked" };
function boardStep(c) {
  var said = BOARD_MARK[c.mark] || c.mark;
  return '<li class="' + esc(c.mark) + '" title="' + esc(c.slug + ": " + c.line + " (" + said + ")") + '"><i class="bd-m ' + esc(c.mark) + '" role="img" aria-label="' + esc(said) + '"></i><span class="bd-cs">' + esc(c.line) + '</span>' + (c.prs.length ? ' <span class="src">' + esc(c.prs.join(" ")) + '</span>' : "") + '</li>';
}
function boardCard(h, stages) {
  var health = BOARD_HEALTH[h.health] || [h.health, ""], tone = h.workers.some(function (w) { return w.tone === "bad"; }) || health[1] === "bad" ? "bad" : h.waits || health[1] === "ask" ? "ask" : "";
  var count = {};
  h.workers.forEach(function (w) { count[w.stage] = (count[w.stage] || 0) + 1; });
  var sum = stages.filter(function (s) { return count[s.key]; }).map(function (s) { return '<span><b>' + count[s.key] + '</b> ' + esc(s.name.toLowerCase()) + '</span>'; }).join("");
  var since = ms(h.since);
  return '<section class="bd-card ' + tone + '" aria-label="' + esc(h.name ? "home " + h.name : "root home") + '">' +
    '<h3 class="bd-h">' + esc(h.name || "root") + ' <span class="bd-hs"><span class="' + health[1] + '">' + esc(health[0]) + (since == null ? "" : " " + short(NOW - since)) + '</span> &middot; ' + plural(h.workers.length, "worker", "workers") + (h.waits ? ' &middot; <span class="ask">' + plural(h.waits, "waits", "wait") + ' on you</span>' : "") + '</span></h3>' +
    (h.goal ? '<p class="bd-goal"><b>Goal</b> ' + esc(h.goal) + '</p>' : "") +
    (h.chain.length ? '<ol class="bd-chain" aria-label="the plan, in order">' + h.chain.map(boardStep).join("") + '</ol>' : "") +
    (sum ? '<div class="bd-sum" aria-label="workers by stage">' + sum + '</div>' : "") +
    (h.workers.length ? '<ol class="clean">' + h.workers.map(function (w) { return boardWorker(w, stages); }).join("") + '</ol>' : '<p class="bd-none">No worker at work</p>') +
    (h.merged.length ? '<p class="bd-done"><b>Merged today ' + h.merged.length + '</b> ' + h.merged.map(function (w) { return '<button type="button" class="bd-ml" data-open="' + esc(w.open) + '">' + esc(w.slug) + '</button>' + (w.pr ? ' ' + esc(w.pr) : ""); }).join(", ") + '</p>' : "") +
    '</section>';
}
function dBoard(arg, d) {
  var all = d.homes.reduce(function (n, h) { return n + h.workers.length; }, 0), merged = d.homes.reduce(function (n, h) { return n + h.merged.length; }, 0);
  return BOARD_STYLE + head("Homes", "Every home and its workers") +
    '<p class="src" style="margin:10px 0 0">' + plural(d.homes.length, "home", "homes") + ', ' + plural(all, "worker", "workers") + ' at work, ' + merged + ' merged today. The chain is each home\'s plan, in order. The bar is the process, ' + esc(d.stages.map(function (s) { return s.name; }).join(" \u203a ")) + ', and the time is how long on the stage.</p>' +
    '<div class="bd-grid">' + d.homes.map(function (h) { return boardCard(h, d.stages); }).join("") + '</div>';
}
panel({
  title: "Every home and its workers",
  wide: true,
  drawer: dBoard,
  gloss: { board: ["Homes", "Each home of the project as one card: its crews (C), reviewers (R) and scouts (S), each on one of seven stages, briefed, running, PR open, in review, fixing, green and merged, with how long it has been on it."] }
});
