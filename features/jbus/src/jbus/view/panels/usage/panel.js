var USAGE = null;
function mt(n) { return n >= 1e6 ? (n / 1e6).toFixed(2) + "M" : num(n); }
function usageSay(u) {
  if (!u.known) return esc(u.said);
  return mt(u.total) + " tokens in " + plural(u.calls, "call", "calls") + ", peak context " + num(u.peak_context) + (u.first ? ", " + day(ms(u.first)) + " to " + day(ms(u.last)) : "");
}
function usageTask(slug) { return USAGE && USAGE.tasks.filter(function (u) { return u.slug === slug; })[0]; }
function homesSay() {
  var homes = USAGE.homes;
  if (!homes.length) return "No home is out.";
  return "Peak context of each home: " + homes.map(function (u) {
    return '<code>' + esc(u.title) + '</code> ' + (u.known ? num(u.peak_context) : esc(u.said));
  }).join(", ") + ".";
}
function usageFill() {
  if (!USAGE) return;
  [].forEach.call(document.querySelectorAll("[data-usage-task]"), function (s) { var u = usageTask(s.getAttribute("data-usage-task")); s.innerHTML = u ? usageSay(u) : "not known: the task is not open"; });
  [].forEach.call(document.querySelectorAll("[data-usage-homes]"), function (s) { s.innerHTML = homesSay(); });
}
function usageAsk() {
  if (gone) return;
  ask("/panel/" + encodeURIComponent("usage") + ".json" + QUERY).then(function (a) { USAGE = a.data.usage; usageFill(); }, function () {
    if (USAGE) return;
    [].forEach.call(document.querySelectorAll("[data-usage-task], [data-usage-homes]"), function (s) { s.textContent = "not known: the view server did not answer"; });
  });
}
function usageLine(inner) { if (USAGE) setTimeout(usageFill); usageAsk(); return inner; }
function figures(u) {
  return '<dl class="kv"><dt>calls</dt><dd>' + num(u.calls) + '</dd><dt>input</dt><dd>' + num(u.tokens_in) + '</dd><dt>cache write</dt><dd>' + num(u.cache_write) + '</dd><dt>cache read</dt><dd>' + num(u.cache_read) + '</dd><dt>output</dt><dd>' + num(u.tokens_out + u.out_floor) + (u.out_floor ? ' <span class="src">of which ' + num(u.out_floor) + ' a floor</span>' : "") + '</dd><dt>total</dt><dd><b>' + num(u.total) + '</b></dd><dt>peak context</dt><dd>' + num(u.peak_context) + '</dd><dt>first</dt><dd>' + (u.first ? day(ms(u.first)) : "none") + '</dd><dt>last</dt><dd>' + (u.last ? day(ms(u.last)) : "none") + '</dd></dl>';
}
function dUsage(arg, data) {
  var all = data.usage, u = all.tasks.filter(function (t) { return t.slug === arg; })[0], h;
  USAGE = all;
  var from = '<p class="src" style="margin-top:12.5px">From <code>~/.claude/projects</code>' + (all.newest ? ", the newest transcript read written " + day(ms(all.newest)) + ", " + dur(NOW - ms(all.newest)) + " ago" : "") + '. Counted as <code>jgauge session</code> counts one transcript, read when this drawer opened.</p>';
  if (u) {
    h = head("Usage", arg, true) + '<div class="now' + (u.known ? "" : " e-op") + '"><span class="tag">The threads of its worktree</span><span class="big">' + usageSay(u) + '</span><span class="src">The crewmate and each reviewer launched into its worktree, whose transcripts are under <code>' + esc(u.folder) + '</code>' + (u.unread ? ", " + plural(u.unread, "transcript", "transcripts") + " that could not be read left out" : "") + '.</span></div>' + from;
    if (u.known) h += '<h3>All of them</h3>' + figures(u) + '<h3>' + plural(u.sessions.length, "session", "sessions") + ', oldest first</h3><ul class="clean rows">' + u.sessions.map(function (s) { return '<li>' + usageSay({ known: true, total: s.total, calls: s.calls, peak_context: s.peak_context, first: s.first, last: s.last }) + '</li>'; }).join("") + '</ul>';
    return h;
  }
  h = head("Usage", "Tokens and context") + from;
  h += '<h3>Homes</h3><p class="src">Each is the session of the main checkout that started with its thread.</p><ul class="clean rows">' + (all.homes.length ? all.homes.map(function (o) { return '<li><code>' + esc(o.title) + '</code><br>' + usageSay(o) + '</li>'; }).join("") : '<li class="src">No home is out.</li>') + '</ul>';
  h += '<h3>Tasks</h3><ul class="clean rows">' + all.tasks.map(function (t) { return '<li class="' + (t.slug === arg ? "hit" : "") + '">' + openBtn("usage:" + t.slug, t.slug) + '<br>' + usageSay(t) + '</li>'; }).join("") + '</ul>';
  return h;
}
panel({
  title: "Usage",
  reads: "server",
  drawer: dUsage,
  adds: {
    task: function (t) { return usageLine('Usage: <span data-usage-task="' + esc(t.slug) + '">asking the server</span> ' + openBtn("usage:" + t.slug, "usage")); },
    threads: function (role) { return role && role !== "home" ? "" : usageLine('<span data-usage-homes>Asking the server for the homes\' context.</span> ' + openBtn("usage", "usage")); }
  }
});
