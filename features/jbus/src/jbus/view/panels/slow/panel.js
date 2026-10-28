var SLOW_NAME = { check: "Check", review: "Review", rebase: "Rebase", you: "You" };
var SLOW_SAYS = { check: "in check", review: "in review", rebase: "to rebase", you: "wait on you" };
var SLOW_CHECK = { failing: ["failing check", "failing checks"], waiting: ["check running or queued", "checks running or queued"], passed: ["passed check waiting for jmerge", "passed checks waiting for jmerge"], stacked: ["stacked row merging after its parent", "stacked rows merging after their parents"] };
(function () {
  var css = document.createElement("style");
  css.textContent =
    ".sl-s { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }" +
    ".sl-c { min-width: 0; border-top: 3px solid var(--hair); padding-top: 3px; }" +
    ".sl-c.busy { border-top-color: var(--due); }" +
    ".sl-c a, .sl-c span.sl-in { display: grid; color: var(--ink); text-decoration: none; min-height: 40px; }" +
    ".sl-n { font-size: 13px; letter-spacing: .06em; text-transform: uppercase; color: var(--ink-2); }" +
    ".sl-v { font-size: 17px; overflow-wrap: anywhere; } .sl-v b { font-size: 22px; line-height: 1.1; }" +
    ".sl-a { font-size: 15px; color: var(--ink-2); overflow-wrap: anywhere; }" +
    ".sl-m { margin: 8px 0 0; font-size: 15px; color: var(--ink-2); display: flex; flex-wrap: wrap; gap: 2px 16px; } .sl-m b { color: var(--ink); }" +
    "@media (max-width: 640px) { .sl-s { grid-template-columns: repeat(2, minmax(0, 1fr)); } .sl-c a, .sl-c span.sl-in { min-height: 44px; } }";
  document.head.appendChild(css);
})();
function slowRoom() { return PROJECT ? S && S.room : STACK && STACK.machine.room; }
function slowWait(s) { var v = s.oldest && ms(s.oldest.since); return v == null ? null : NOW - v; }
function slowTop(stages) {
  return stages.filter(function (s) { return s.rows; }).sort(function (a, b) { return (slowWait(b) || 0) - (slowWait(a) || 0); })[0] || null;
}
function slowRows(s) {
  if (s.key === "you") return plural(s.rows, "waits", "wait") + " on you";
  var rows = plural(s.rows, "row", "rows") + " " + SLOW_SAYS[s.key];
  if (!s.cause) return rows;
  var n = s.checks[s.cause];
  return plural(n, SLOW_CHECK[s.cause][0], SLOW_CHECK[s.cause][1]) + " of " + rows;
}
function slowAge(s) { var w = slowWait(s); return w == null ? (s.rows ? "no time kept" : "none") : "oldest " + short(w); }
function slowChecks(s) { return s.checks ? '<span class="sl-a">' + s.checks.failing + " failing, " + s.checks.waiting + " running or queued, " + s.checks.passed + " passed, " + s.checks.stacked + " stacked</span>" : ""; }
function slowSlots(t) {
  if (!t.total) return "Test slots: <b>not known</b>";
  if (!t.read) return "Test slots: <b>not known</b> of " + t.total;
  return "Test slots: <b>" + t.used + " of " + t.total + "</b> held" + (t.waiting ? ", " + plural(t.waiting, "thread waits", "threads wait") + (ms(t.since) == null ? "" : " (oldest " + short(NOW - ms(t.since)) + ")") : "");
}
function slowLoad(r) {
  if (!r) return "Load: <b>not known</b>";
  return "Load: <b>" + (r.load[0] == null ? "not known" : r.load[0] + " of " + r.cores + " cores") + "</b>" + (r.answer === "wait" ? ", no room: " + esc(r.why) : r.answer === "go" ? ", room to launch" : "");
}
function slowSay(g) {
  var top = slowTop(g.stages), t = g.slots, full = t.read && t.total && t.used >= t.total;
  var bits = [];
  if (top) bits.push("<b>" + esc(slowRows(top)) + "</b>" + (slowWait(top) == null ? "" : ", the oldest for " + short(slowWait(top))));
  if (full) bits.push("<b>every test slot is held</b>");
  return bits.length ? "Slowed by " + bits.join(", and ") + "." : "Nothing waits at a stage, and a test slot is free.";
}
function slowCell(s) {
  var inner = '<span class="sl-n">' + SLOW_NAME[s.key] + '</span><span class="sl-v"><b>' + s.rows + '</b> ' + esc(SLOW_SAYS[s.key]) + '</span>' + slowChecks(s) + '<span class="sl-a">' + esc(slowAge(s)) + '</span>';
  var to = s.oldest && s.oldest.open;
  return '<li class="sl-c' + (s.rows ? " busy" : "") + '" data-stage="' + esc(s.key) + '">' + (to ? '<a href="' + esc(linkOf(to)) + '" title="The oldest: ' + esc(s.oldest.what) + (STACK && STACK.projects.length > 1 ? ' in ' + esc(s.oldest.project) : "") + '">' + inner + '</a>' : '<span class="sl-in">' + inner + '</span>') + '</li>';
}
function slowBody(g) {
  return '<ul class="sl-s">' + g.stages.map(slowCell).join("") + '</ul>' +
    '<p class="sl-m"><span>' + slowSlots(g.slots) + '</span><span>' + slowLoad(slowRoom()) + '</span></p>';
}
function slowBusy(g) { return g.stages.some(function (s) { return s.rows; }) || (g.slots.read && g.slots.total && g.slots.used >= g.slots.total); }
function slowTile() {
  var check = STACK && STACK.slow && STACK.slow.stages.filter(function (s) { return s.key === "check"; })[0];
  if (!check) return "";
  var c = check.checks, none = Math.max(0, check.rows - c.failing - c.waiting - c.passed - c.stacked), own = check.rows - c.stacked;
  var segs = [["failing", c.failing, "failing"], ["waiting", c.waiting, "running or queued"], ["passed", c.passed, "passed"], ["norun", none, "no run"]];
  var bar = own ? '<span class="seg-bar" role="img" aria-label="' + esc(segs.map(function (g) { return g[1] + " " + g[2]; }).join(", ")) + '">' + segs.filter(function (g) { return g[1]; }).map(function (g) { return '<i class="' + g[0] + '" style="flex:' + g[1] + ' 0 0" title="' + g[1] + " " + g[2] + '"></i>'; }).join("") + '</span>' : "";
  var said = segs.filter(function (g) { return g[1]; }).map(function (g) { return (g[0] === "failing" ? '<b class="alarm">' : "<b>") + g[1] + "</b> " + g[2]; }).join(" &middot; ");
  return '<a class="tile' + (c.failing ? " bad" : "") + '" data-role="in-check" href="#/?stage=check' + themed() + '"><span class="tag" data-gloss="card:in-check">In check</span><span class="tile-n">' + own + (c.stacked ? ' <small>+ ' + c.stacked + ' stacked</small>' : "") + '</span>' + bar + '<span class="tile-s">' + (said || "nothing in check") + '</span></a>';
}
var SLOW_GROUPS = 6;
function slowRail() {
  var v = STACK && STACK.glance && STACK.glance.verdict;
  if (!v) return "";
  var top = Math.max.apply(null, v.groups.map(function (g) { return g.count; }).concat([1])), ci = { failed: 0, error: 0, running: 0, waiting: 0 };
  STACK.projects.forEach(function (p) { var k = p.health && p.health.checks; if (k) Object.keys(ci).forEach(function (n) { ci[n] += k[n] || 0; }); });
  var bad = ci.failed + ci.error, one = STACK.projects.length === 1 ? STACK.projects[0].name : "";
  var line = (bad ? '<b class="alarm">' + bad + '</b> failing' : "none failing") + ", " + ci.running + " running, " + ci.waiting + " queued";
  return '<section class="ovc" data-role="slowed" aria-labelledby="ovc-slow"><h2 class="ovc-h" id="ovc-slow"><span class="tag" data-gloss="card:slowed">Slowed by</span></h2>' +
    (v.groups.length ? '<ul class="clean">' + v.groups.slice(0, SLOW_GROUPS).map(function (g) {
      var since = ms(g.since);
      return '<li class="gr' + (g.kind === "failing" ? " failing" : "") + '"><span title="' + esc(g.text + (g.head ? ", the first: " + g.head : "") + (since == null ? "" : ", the oldest for " + short(NOW - since))) + '">' + esc(g.text) + '</span><i><u style="width:' + Math.max(4, Math.round(100 * g.count / top)) + '%"></u></i><b>' + g.count + '</b></li>';
    }).join("") + '</ul>' : '<p class="ovc-s">Nothing holds the work back.</p>') +
    (v.groups.length > SLOW_GROUPS ? '<p class="ovc-s">and ' + plural(v.groups.length - SLOW_GROUPS, "smaller group", "smaller groups") + ': ' + esc(v.groups.slice(SLOW_GROUPS).map(function (g) { return g.text + " " + g.count; }).join(", ")) + '</p>' : "") +
    '<p class="ovc-f">CI: ' + (one ? '<a href="' + esc(href(one, "checks")) + '">' + line + '</a>' : line) + '</p></section>';
}
function slowMachine() {
  if (!STACK || !STACK.slow) return "";
  var r = slowRoom();
  return '<section class="ovc" data-role="machine" aria-label="The machine"><p class="ovc-s"><span class="tag" data-gloss="card:machine">Machine</span> ' + slowLoad(r) + ' &middot; ' + slowSlots(STACK.slow.slots) + '</p></section>';
}
function dSlow(arg, data) {
  var g = data.slow;
  return head("The line", "What slows us") + '<div class="now' + (slowBusy(g) ? " e-op" : "") + '"><span class="tag">Now</span><span class="big">' + slowSay(g) + '</span></div>' + slowBody(g) +
    '<p class="src" style="margin-top:10px">A row waits at a stage from when it came to it. Check is the step Check: of its rows, failing counts those with a check that failed, running or queued those whose check runs or waits for a runner, passed those whose checks passed and that wait for jmerge, each by the latest run of each check, as jmerge reads them, and stacked those that merge after their parent row, whatever their own checks say. The first line names the largest of the four. You is what Needs you lists. Test slots are the full lane of <code>jgauge test-slot</code>, where a thread runs its check command, read from the kernel&#39;s list of held locks. Load is the room&#39;s.</p>';
}
panel({
  title: "What slows us",
  drawer: dSlow,
  parts: { tile: slowTile, rail: slowRail, machine: slowMachine },
  adds: {
    task: function (t) { return t.step === "check" || t.step === "rebase" || t.who === "rev" ? openBtn("slow", "What slows the line") : ""; }
  },
  gloss: {
    "in-check": ["In check", "How many rows are at the step Check, with the rows stacked on a parent row counted apart, since they merge after it whatever their own checks say. The bar and the line under it split the rest by the latest run of each check: failing, running or queued, passed and waiting for jmerge, and no run yet."],
    slowed: ["Slowed by", "The groups of rows that do not move, as the verdict counts them, each with how many rows it holds and how long the first has waited, the longest bar the largest group. Under them, the projects' CI checks: how many fail, run and wait for a runner."],
    machine: ["The machine", "The machine's load against its cores, whether it has room to launch one more thread, and how many of its test slots are held."],
    slow: ["What slows us", "How many rows wait at each stage, check, review, rebase and you, with how long the oldest has waited, the rows in check split into failing, running or queued, passed, and stacked on a parent row, how many of the machine's test slots are held, and the machine's load. Its first line names the stage whose oldest row has waited longest."]
  }
});
