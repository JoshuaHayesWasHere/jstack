/* The threads that are out: its card of counts, the drawer that lists each by role, and the
   Threads band of a project's row and page. */
var ROLES = [["crew", "crews", "crew"], ["scout", "scouts", "scout"], ["reviewer", "reviewers", "reviewer"], ["home", "homes", "home"], ["other", "other threads", "other thread"]];
function threadsOf(list, role) { return (list || []).filter(function (t) { return t.out && (!role || t.role === role); }); }
function threadsOut(role) { return threadsOf(S.threads, role); }
function are(list, word) { return list.filter(function (t) { return t.live === word; }).length; }
function outSay(list) { return list.length + " out, " + are(list, "quiet") + " quiet, " + are(list, "hung") + " hung"; }
function threadRow(t) { return threadLine(t, t.role !== "other" ? openBtn(threadAt(t), t.title) : '<code>' + esc(t.title) + '</code>'); }
function dThreads(role) {
  var all = S.threads, shown = (all || []).filter(function (t) { return !role || t.role === role; }), out = shown.filter(function (t) { return t.out; }), rest = shown.filter(function (t) { return !t.out; });
  var named = ROLES.filter(function (r) { return r[0] === role; })[0] || ["", "threads", "thread"];
  var h = head("Under the line", (all ? plural(out.length, named[2], named[1]) : "No count of " + named[1]) + " out");
  if (!all) return h + '<div class="now e-op"><span class="tag">Not known</span><span class="big">The last pass left no list of the threads that are out.</span></div>' + note("frozen");
  h += '<div class="now e-' + (are(out, "hung") ? "op" : "ok") + '"><span class="tag">As the last pass saw them</span><span class="big">' + outSay(out) + '</span><span class="src">Out is a thread that is not settled with a turn under way, or one that waits. Quiet is a turn that has written nothing for a while, and hung is one that has for longer, or with a run queued behind it. jbus says it and interrupts nothing.</span></div>' + note("frozen");
  h += '<div class="filters" role="group" aria-label="Show the threads of">' + [["", "all"]].concat(ROLES.slice(0, 3)).map(function (r) {
    return '<button type="button" class="fb" data-open="threads' + (r[0] ? ":" + r[0] : "") + '" aria-pressed="' + (r[0] === (role || "")) + '">' + r[1] + ' <i>' + threadsOut(r[0]).length + '</i></button>';
  }).join("") + '</div>' + added("threads", role).map(function (a) { return '<p style="margin:10px 0 0">' + a.said + '</p>'; }).join("");
  ROLES.forEach(function (r) {
    var mine = out.filter(function (t) { return t.role === r[0]; });
    if (mine.length) h += '<h3>' + mine.length + " " + r[1] + '</h3><ul class="clean rows">' + mine.map(threadRow).join("") + '</ul>';
  });
  if (!out.length) h += '<p class="src">None is out.</p>';
  if (rest.length) h += '<h3>' + rest.length + ' not settled, with no turn under way</h3><ul class="clean rows">' + rest.map(threadRow).join("") + '</ul>';
  return h;
}
/* The band: the threads of today by role, those out first, each with its liveness and when it
   last wrote, and one that ended today dimmed. Those that ended before today, and those of no
   role, are folded into one way to the drawer. A pass that left no list is said as a blind
   spot, never as none. `v.away` is a row of every project, whose ways lead to the project's page. */
function band(v) {
  var all = v.threads, away = v.away ? v.name : "";
  function more(target, label) {
    return away ? '<a class="pl" href="' + esc(href(away, target)) + '" title="' + esc(v.name + ": " + label) + '">' + esc(label) + '</a>' : '<button type="button" class="pl" data-open="' + esc(target) + '">' + esc(label) + '</button>';
  }
  var h = '<div class="thb' + (!all ? " blind" : threadsOf(all).length ? "" : " calm") + '" role="group" aria-label="Threads of ' + esc(v.name) + '"><div class="thh"><b>Threads</b>';
  if (!all) return h + '<span>not known</span><span class="src">the last pass left no list: a blind spot, not none</span>' + fz() + hint("term:threads", "Threads") + '</div></div>';
  var roled = all.filter(function (t) { return t.role !== "other"; }), shown = roled.filter(function (t) { return t.today; });
  var ended = shown.filter(function (t) { return !t.out; }).length, older = roled.length - shown.length, other = all.length - roled.length;
  h += '<span>' + threadsOf(all).length + ' out</span>' + (ended ? '<span class="src">' + ended + ' ended today</span>' : "") + fz() + hint("term:threads", "Threads") + '</div>';
  ROLES.slice(0, 4).forEach(function (r) {
    var mine = shown.filter(function (t) { return t.role === r[0]; }).sort(function (a, b) { return (b.out - a.out) || ((ms(b.updated) || 0) - (ms(a.updated) || 0)); });
    if (mine.length) h += '<div class="thr"><span class="rl">' + ROLE[r[0]][2] + '</span><span class="chs">' + mine.map(function (t) { return threadChip(t, away); }).join("") + '</span></div>';
  });
  if (older || other) h += '<div class="thr"><span class="rl">Folded</span><span class="chs">' + more("threads", (older ? older + " ended before today" : "") + (older && other ? ", " : "") + (other ? other + " of no role" : "")) + '</span></div>';
  return h + '</div>';
}
panel({
  gloss: { threads: ["Threads out", "Threads not settled: a turn is under way, or one waits. Quiet is a turn that has written nothing for a while, and hung one that has for longer. jbus says it and interrupts nothing."] },
  adds: { band: band },
  card: function () {
    var out = threadsOut();
    return { at: 30, e: !S.threads || are(out, "hung") ? "op" : are(out, "quiet") ? "msg" : "ok", tag: "threads", st: fz(), frz: true,
      val: S.threads ? '<b>' + out.length + ' out</b>' + ["quiet", "hung"].map(function (w) { return are(out, w) ? ' <small class="bad" style="flex-basis:auto">' + are(out, w) + " " + w + '</small>' : ""; }).join("") : '<small class="bad">not known</small>', viz: "",
      label: "Threads: " + (S.threads ? outSay(out) : "the last pass left no list of them") };
  },
  drawer: dThreads
});
