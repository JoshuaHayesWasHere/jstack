function ciSeries(n, c) {
  var W = 300, H = 44, P = 4, pts = n.series.map(function (s, i) { return { i: i, v: s.value, day: s.day }; }).filter(function (p) { return p.v != null; });
  var t0 = ms(c.from), t1 = ms(c.to), top = Math.max.apply(null, pts.map(function (p) { return p.v; }).concat([1e-9]));
  function x(i) { return P + i / Math.max(n.series.length - 1, 1) * (W - 2 * P); }
  function y(v) { return H - P - v / top * (H - 2 * P); }
  var line = pts.map(function (p) { return x(p.i).toFixed(1) + "," + y(p.v).toFixed(1); }).join(" ");
  var marks = c.marks.map(function (m) {
    var at = ms(m.at); if (at == null || at < t0 || at > t1) return "";
    var mx = (P + (at - t0) / (t1 - t0) * (W - 2 * P)).toFixed(1);
    return '<line x1="' + mx + '" x2="' + mx + '" y1="0" y2="' + H + '" stroke="currentColor" stroke-dasharray="2 2" opacity=".6"><title>' + esc(m.label) + ' merged ' + day(at) + '</title></line>';
  }).join("");
  if (!pts.length) return '<span class="src">no day with data</span>';
  return '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + esc(n.name) + ' by day, highest ' + top.toFixed(1) + '">' +
    marks + '<polyline fill="none" stroke="currentColor" stroke-width="1.5" points="' + line + '"/>' +
    pts.map(function (p) { return '<circle cx="' + x(p.i).toFixed(1) + '" cy="' + y(p.v).toFixed(1) + '" r="2"><title>' + esc(p.day) + ': ' + p.v.toFixed(1) + '</title></circle>'; }).join("") + '</svg>';
}
function ciRow(n, c) {
  var chip = n.met === false ? '<span class="chip user">missed</span>' : n.met ? '<span class="chip ok">met</span>' : '<span class="chip plain">no data</span>';
  return '<li><b>' + esc(n.name) + '</b> ' + chip +
    '<br><span class="big">' + esc(n.shown) + '</span> <span class="src">held to ' + esc(n.target) + (n.hosted ? '; hosted ' + esc(n.hosted) : '') + '</span>' +
    '<br>' + ciSeries(n, c) +
    '<br><span class="src">' + esc(n.how) + ' (n = ' + n.n + ').</span></li>';
}
function dCi(arg, data) {
  var c = data.ci;
  if (!c.read) return head("CI", "The nine targets") + '<p class="src">Not known: <code>ci.jsonl</code> is not kept. Run <code>jbus ci</code>.</p>';
  var missed = c.numbers.filter(function (n) { return n.met === false; }).length;
  return head("CI", "The nine targets") +
    '<div class="now' + (missed ? " e-op" : "") + '"><span class="tag">The last ' + c.days + ' days</span><span class="big">' + (missed ? plural(missed, "target", "targets") + " missed" : "no target missed") + '</span>' +
    '<span class="src">Counted from ' + plural(c.jobs, "job", "jobs") + ' in <code>ci.jsonl</code>, job level only: a run is never a count. Local and hosted runners are counted apart, the local runner is the one a target holds. A job cancelled while it waited is counted. Written by <code>jbus ci</code>, to ' + hm(ms(c.to), true) + '.</span></div>' +
    '<h3>Targets, and each by day</h3><p class="src">A dashed line is the day a change merged: ' + (c.marks.length ? c.marks.map(function (m) { return esc(m.label) + ' (' + esc(m.project) + ') ' + day(ms(m.at)); }).join(", ") : 'none of the changes has merged yet') + '.</p>' +
    '<ul class="clean rows">' + c.numbers.map(function (n) { return ciRow(n, c); }).join("") + '</ul>';
}
panel({
  title: "CI",
  drawer: dCi,
  wide: true,
  gloss: { ci: ["CI targets", "Nine numbers that say whether CI is getting faster and more honest, each held to a target and drawn by day. Read from ci.jsonl, which jbus ci writes."] },
});
