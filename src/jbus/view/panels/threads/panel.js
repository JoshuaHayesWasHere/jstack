/* The threads that are out: its card of counts, and the drawer that lists each by role. */
var ROLES = [["crew", "crews", "crew"], ["scout", "scouts", "scout"], ["reviewer", "reviewers", "reviewer"], ["home", "homes", "home"], ["other", "other threads", "other thread"]];
function threadsOut(role) { return (S.threads || []).filter(function (t) { return t.out && (!role || t.role === role); }); }
function are(list, word) { return list.filter(function (t) { return t.live === word; }).length; }
function outSay(list) { return list.length + " out, " + are(list, "quiet") + " quiet, " + are(list, "hung") + " hung"; }
function threadRow(t) {
  var c = ms(t.created), u = ms(t.updated), more = [];
  if (t.queued) more.push(plural(t.queued, "run waits", "runs wait") + " behind it");
  if (t.pending) more.push(plural(t.pending, "request waits", "requests wait") + " for an answer");
  if (t.page) more.push("it holds a page that waits on you");
  return '<li><span class="chip ' + LIVE[t.live] + '">' + esc(t.live) + '</span> ' + (t.role === "crew" && (TASK[t.slug] || ENDED[t.slug]) ? taskBtn(t.slug) : '<code>' + esc(t.title) + '</code>') + ' <span class="src">' + esc(t.status) + '</span><br><span class="src">' +
    (c == null ? "no start kept" : "started " + day(c) + ", " + dur(NOW - c) + " ago") + ", " + (u == null ? "no write kept" : "last wrote " + day(u) + ", " + dur(NOW - u) + " ago") + (more.length ? ", " + esc(more.join(", ")) : "") + '</span></li>';
}
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
panel({
  card: function () {
    var out = threadsOut();
    return { at: 30, e: !S.threads || are(out, "hung") ? "op" : are(out, "quiet") ? "msg" : "ok", tag: "threads", st: fz(), frz: true,
      val: S.threads ? '<b>' + out.length + ' out</b>' + ["quiet", "hung"].map(function (w) { return are(out, w) ? ' <small class="bad" style="flex-basis:auto">' + are(out, w) + " " + w + '</small>' : ""; }).join("") : '<small class="bad">not known</small>', viz: "",
      label: "Threads: " + (S.threads ? outSay(out) : "the last pass left no list of them") };
  },
  drawer: dThreads
});
