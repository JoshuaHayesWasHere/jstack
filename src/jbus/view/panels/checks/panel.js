/* The repo's checks on GitHub: its card of what runs, waits and failed, and the drawer of runs. */
/* A check is one run of the repo's workflow on GitHub. What runs, waits for a runner and
   failed is the server's to say (`tally` in panel.py): `S.checks.now` names the runs. These
   are the words GitHub has for a run that ended badly. */
var FAILED = { failure: 1, timed_out: 1, startup_failure: 1 };
var CHECKS = [["running", "running"], ["waiting", "waiting for a runner"], ["failed", "failed"]];
function runStats() {
  var by = {}, waited = [], runs = S.checks.runs, now = {};
  runs.forEach(function (r) {
    by[r.state] = (by[r.state] || 0) + 1;
    if (ms(r.started) > ms(r.created)) waited.push(r);
  });
  CHECKS.forEach(function (c) { now[c[0]] = (S.checks.now[c[0]] || []).map(function (at) { return runs[at]; }).filter(Boolean); });
  var worst = waited.slice().sort(function (a, b) { return (ms(b.started) - ms(b.created)) - (ms(a.started) - ms(a.created)); })[0] || null;
  return { by: by, waited: waited, worst: worst, now: now, ended: Object.keys(FAILED).reduce(function (n, k) { return n + (by[k] || 0); }, 0) };
}
function branches(runs) {
  var seen = {}, names = runs.map(function (r) { return r.branch || "no branch"; }).filter(function (n) { return seen[n] ? false : (seen[n] = true); });
  return names.slice(0, 2).join(", ") + (names.length > 2 ? " +" + (names.length - 2) : "");
}
function checksSay(rs) { return CHECKS.map(function (c) { return rs.now[c[0]].length + " " + c[1]; }).join(", "); }
/* The runner units of this machine as systemd lists them. One that is not active is said on
   the card: the view knows it is stopped, so it is a fact and not a blind spot. */
function stoppedRunners() { return S.checks.runners.filter(function (u) { return u.active !== "active"; }); }
function stoppedSay(units) { return units.map(function (u) { return u.unit.replace(/\.service$/, "") + " " + u.active; }).join(", "); }
function runnerList() {
  var c = S.checks;
  if (!c.runners_read) return '<p class="src">systemd did not answer, so the runners of this machine are not known.</p>';
  if (!c.runners.length) return '<p class="src">systemd lists no unit <code>actions-runner-*</code> on this machine.</p>';
  return '<ul class="clean steps">' + c.runners.map(function (u) {
    return '<li><span class="t"></span><span><code>' + esc(u.unit) + '</code></span><span class="d"><span class="chip ' + (u.active === "active" ? "ok" : "user") + '">' + esc(u.active) + (u.sub ? ", " + esc(u.sub) : "") + '</span></span></li>';
  }).join("") + '</ul>';
}
function gantt(branch) {
  var runs = S.checks.runs; if (!runs.length) return '<p class="src">No run to draw.</p>';
  var t0 = ms(runs[0].created), t1 = Math.max.apply(null, runs.map(function (r) { return ms(r.updated) || NOW; }).concat([t0 + 1])), W = 1000, rh = 5, gp = 2, Hh = runs.length * (rh + gp) + gp;
  function x(t) { return (t - t0) / (t1 - t0) * W; }
  var rects = runs.map(function (r, i) {
    var c = ms(r.created), s = ms(r.started) || c, u = ms(r.updated) || s, y = gp + i * (rh + gp), f = branch && r.branch !== branch ? " faint" : "", end = r.state === "in_progress" ? t1 : u, out = "";
    if (s > c) out += '<rect class="q' + f + '" x="' + x(c).toFixed(1) + '" y="' + y + '" width="' + Math.max(3, x(s) - x(c)).toFixed(1) + '" height="' + rh + '"><title>' + esc(r.branch) + ': waited ' + dur(s - c) + ' for a runner</title></rect>';
    out += '<rect class="' + esc(r.state) + f + '" x="' + x(s).toFixed(1) + '" y="' + y + '" width="' + Math.max(4, x(end) - x(s)).toFixed(1) + '" height="' + rh + '"><title>' + esc(r.branch) + ': ' + esc(r.state) + ', started ' + hm(s, true) + '</title></rect>';
    return out;
  }).join("");
  return '<svg class="gantt" viewBox="0 0 ' + W + ' ' + Hh + '" preserveAspectRatio="none" height="' + Hh + '" role="img" aria-label="Check runs from ' + hm(t0) + ' to ' + hm(t1) + ', one row for each run, amber is time waiting for a runner">' + rects + '</svg>' +
    '<div class="axis"><span>' + hm(t0) + '</span><span>' + hm(t1) + '</span></div>' +
    '<div class="key"><span><i class="sw q"></i>waited for a runner</span><span><i class="sw success"></i>success</span><span><i class="sw cancelled"></i>cancelled</span><span><i class="sw failure"></i>failure</span><span><i class="sw in_progress"></i>in progress</span></div>';
}
function dChecks() {
  var rs = runStats(), w = rs.worst, c = S.checks, bad = c.error || rs.now.failed.length;
  var at = { running: ["started", "started"], waiting: ["created", "asked for"], failed: ["updated", "ended"] }, title = { running: "Running", waiting: "Waiting for a runner", failed: "Failed, and not run again since" };
  return head("Under the line", "CI checks on GitHub") +
    '<div class="now' + (bad ? " e-op" : "") + '"><span class="tag">Now</span><span class="big">' + (c.error ? esc(c.error) : checksSay(rs)) + '</span>' +
    '<span class="src">A check is one run of the workflow of ' + (S.repo ? '<code>' + esc(S.repo) + '</code>' : "the repo") + ' on GitHub, which a push to a branch or a pull request starts. A branch counts as failed, once, while the newest run of one of its workflows failed. A run held for an approval or by another run is in neither count.</span></div>' + note("live") +
    CHECKS.map(function (k) {
      var runs = rs.now[k[0]];
      return '<h3>' + runs.length + " " + title[k[0]].toLowerCase() + '</h3>' + (runs.length ? '<ul class="clean steps">' + runs.map(function (r) {
        var t = ms(r[at[k[0]][0]]);
        return '<li><span class="t">' + (t == null ? "" : hm(t)) + '</span><span>' + link(r.url, r.branch || "no branch") + ' <span class="src">' + esc(r.name) + '</span></span><span class="d">' + (t == null ? "" : at[k[0]][1] + " " + dur(NOW - t) + " ago") + '</span></li>';
      }).join("") + '</ul>' : '<p class="src">None.</p>');
    }).join("") +
    '<h3>Runners on this machine</h3>' + runnerList() +
    '<h3>The last ' + c.runs.length + ' runs</h3>' + gantt(null) +
    '<p class="src" style="margin-top:10px">Of these, ' + rs.waited.length + ' waited for a runner, ' + (rs.by.cancelled || 0) + ' were cancelled, ' + rs.ended + ' ended in failure and ' + (rs.by.success || 0) + ' passed. ' + (w ? 'The longest wait for a runner was ' + dur(ms(w.started) - ms(w.created)) + ', by <code>' + esc(w.branch) + '</code> at ' + hm(ms(w.created), true) + '. ' : "") +
    'Asked of GitHub once a minute' + (ms(c.at) == null ? "" : ", last at " + hm(ms(c.at), true)) + '. <code>checks.json</code>: ' + c.green + ' of ' + c.commits + ' commits of main green.</p>';
}
panel({
  card: function () {
    var rs = runStats(), off = stoppedRunners();
    return { at: 40, e: S.checks.error || rs.now.failed.length || off.length ? "op" : rs.now.running.length + rs.now.waiting.length ? "msg" : "dim", cls: " wide", tag: "CI checks on GitHub", st: lv(),
      val: (S.checks.error ? '<small class="bad">' + esc(S.checks.error) + '</small>' : CHECKS.map(function (c) { var runs = rs.now[c[0]]; return '<span class="ck' + (runs.length ? "" : " zero") + '"><span>' + runs.length + " " + c[1] + '</span>' + (runs.length ? ' <small>' + esc(branches(runs)) + '</small>' : "") + '</span>'; }).join(" ")) +
        (off.length ? ' <span class="ck"><span>' + plural(off.length, "runner", "runners") + ' not active</span> <small>' + esc(stoppedSay(off)) + '</small></span>' : ""),
      viz: "", label: "The repo's checks on GitHub: " + (S.checks.error || checksSay(rs)) + (off.length ? ", runners not active: " + stoppedSay(off) : "") };
  },
  drawer: dChecks
});
