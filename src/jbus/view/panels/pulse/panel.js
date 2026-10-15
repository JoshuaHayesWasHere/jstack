/* Is the bus alive: the drawer with every source and its age. The bus is the machine's, so it
   has no card of a project: the machine's row in the sidebar opens this drawer. */
function sourceList() {
  return '<ul class="clean rows">' + S.sources.map(function (s) {
    var at = ms(s.at);
    return '<li><code><b>' + esc(s.name) + '</b></code> ' + (s.state === "missing" || s.state === "unreadable" ? gap(s.state) : (at == null ? gap("no time") : dur(NOW - at) + ' old <span class="src">(' + day(at) + ')</span>') + (s.state === "stale" ? " " + gap("stale") : "")) + ' ' +
      (stopped || gone ? (s.by === "jbus" ? fz() : lv()) : '<span class="chip plain">' + (s.by === "jbus" ? "jbus writes it" : s.by === "session" ? "a session's status line writes it" : "the server reads it itself") + '</span>') + '</li>';
  }).join("") + '</ul>';
}
function dPulse() {
  var p = S.jbus, st = p.status, end = ms(p.last_end), h = head("Is the bus alive", stopped ? "jbus has not passed" : "jbus is passing");
  h += '<div class="now e-' + (stopped ? "op" : "ok") + '">';
  if (stopped) h += '<span class="tag">Stopped</span><span class="big">' + esc(p.why || "no pass") + '. The last pass ended ' + (end == null ? "never" : day(end) + ", " + dur(NOW - end) + " ago") + '.</span><p>Nothing is launched, merged or sent until jbus passes again. Each token stands where the last pass saw it.</p>';
  else h += '<span class="tag">Now</span><span class="big">' + (p.pass.running ? "A pass is running since " + hm(ms(p.pass.started), true) : "Last pass " + hm(ms(p.pass.started), true) + " to " + hm(end, true) + (p.pass.seconds == null ? "" : ", " + p.pass.seconds + " s")) + '</span>';
  h += '<span class="chip ' + (st.last_error ? "user" : "ok") + '">' + (st.last_error ? "last error: " + esc(st.last_error) : "no error") + '</span> <span class="chip plain">' + plural(st.failed_wakes, "failed wake", "failed wakes") + '</span> ' +
    Object.keys(st.streaks).map(function (k) { return '<span class="chip user">' + esc(k) + ': ' + st.streaks[k] + ' in a row</span>'; }).join(" ") +
    '<p class="src" style="margin:10px 0 0">systemd says: ' + esc(p.said) + '. Timer ' + esc(p.timer.enabled || "unknown") + ', last trigger ' + esc(p.timer.last_trigger || "unknown") + '. Stopped is the timer not active, or no pass in ' + p.quiet + ' s.</p></div>';
  if (p.code && p.code.stale) h += '<div class="now e-op" style="margin-top:15px"><span class="tag">The view server</span><span class="big">' + (ms(p.code.started) == null ? "Now" : "Started " + day(ms(p.code.started))) + ': the view runs older code than is on disk.</span><p>' + (p.code.error ? esc(p.code.error) + '. It keeps serving, and tries the code again at each check.' : 'It ends by itself once the code on disk starts, and its unit starts it again.') + '</p></div>';
  h += '<dl class="kv" style="margin-top:15px"><dt>sign-in</dt><dd>' + (st.sign_in ? esc(st.sign_in) : "expires " + (ms(st.token_expires) == null ? "unknown" : day(ms(st.token_expires)))) + '</dd><dt>sweep</dt><dd>' + esc(st.sweep || "none") + '</dd><dt>main</dt><dd><code>' + esc(S.main.sha.slice(0, 7) || "unknown") + '</code>' + (ms(S.main.at) == null ? "" : ", moved " + day(ms(S.main.at))) + '</dd><dt>repo</dt><dd>' + esc(S.repo || "not known") + '</dd></dl>';
  h += '<h3>Each source and its age</h3><p class="src">What jbus writes stands as the last pass left it. What the server reads itself is as it is now. Stale is an answer of GitHub that the server could not renew.</p>' + sourceList();
  h += '<h3>Where the rest is</h3><p>' + openBtn("bus", "The bus") + ' ' + openBtn("room", "Machine room") + ' ' + openBtn("checks", "CI checks on GitHub") + '</p>';
  return h;
}
panel({
  gloss: { jbus: ["jbus", "The timer that passes about once a minute: it reads each project's queue, launches, merges and sends events. Passing is its timer running and the last pass ended in time. One jbus serves every project of this machine."], homes: ["Homes", "The homes of this machine that are not on the bus: each has a home-id and no project in jbus's config, so jbus launches, merges and tells nothing for it. A home's start adds its repo, and jbus project add does by hand. The pass says the list each time it changes."] },
  drawer: dPulse
});
