function threadsOf(list, role) { return (list || []).filter(function (t) { return t.out && (!role || t.role === role); }); }
function threadsOut(role) { return threadsOf(S.threads, role); }
function are(list, word) { return list.filter(function (t) { return t.live === word; }).length; }
function outSay(list) { return list.length + " out, " + are(list, "quiet") + " quiet, " + are(list, "hung") + " hung"; }
function threadRow(t) { return threadLine(t, t.role !== "other" ? openBtn(threadAt(t), t.title) : '<code>' + esc(t.title) + '</code>'); }
function dThreads(role) {
  var all = S.threads, shown = (all || []).filter(function (t) { return !role || t.role === role; }), out = shown.filter(function (t) { return t.out; }), rest = shown.filter(function (t) { return !t.out; });
  var named = S.roles.filter(function (r) { return r.name === role; })[0] || { name: "", many: "threads", one: "thread" };
  var h = head("Under the line", (all ? plural(out.length, named.one, named.many) : "No count of " + named.many) + " out");
  if (!all) return h + '<div class="now e-op"><span class="tag">Not known</span><span class="big">The last pass left no list of the threads that are out.</span></div>';
  h += '<div class="now e-' + (are(out, "hung") ? "op" : "ok") + '"><span class="tag">As the last pass saw them</span><span class="big">' + outSay(out) + '</span><span class="src">Out is a thread that is not settled with a turn under way, or one that waits. Quiet is a turn that has written nothing for a while, and hung is one that has for longer, or with a run queued behind it. jbus says it and interrupts nothing.</span></div>';
  h += '<div class="filters" role="group" aria-label="Show the threads of">' + [{ name: "", many: "all" }].concat(S.roles.slice(0, 3)).map(function (r) {
    return '<button type="button" class="fb" data-open="threads' + (r.name ? ":" + r.name : "") + '" aria-pressed="' + (r.name === (role || "")) + '">' + r.many + ' <i data-gloss="count:threads">' + threadsOut(r.name).length + '</i></button>';
  }).join("") + '</div>' + added("threads", role).map(function (a) { return '<p style="margin:10px 0 0">' + a.said + '</p>'; }).join("");
  S.roles.forEach(function (r) {
    var mine = out.filter(function (t) { return t.role === r.name; });
    if (mine.length) h += '<h3>' + mine.length + " " + r.many + '</h3><ul class="clean rows">' + mine.map(threadRow).join("") + '</ul>';
  });
  if (!out.length) h += '<p class="src">None is out.</p>';
  if (rest.length) h += '<h3>' + rest.length + ' not settled, with no turn under way</h3><ul class="clean rows">' + rest.map(threadRow).join("") + '</ul>';
  return h;
}
panel({
  gloss: { threads: ["Threads out", "Threads not settled: a turn is under way, or one waits. Quiet is a turn that has written nothing for a while, and hung one that has for longer. jbus says it and interrupts nothing."] },
  drawer: dThreads
});
