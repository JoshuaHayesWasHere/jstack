function tpWeekday(d) {
  var p = d.split("-");
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][new Date(Date.UTC(+p[0], p[1] - 1, +p[2])).getUTCDay()];
}
function tpBars(days) {
  var top = Math.max.apply(null, days.map(function (d) { return d.merged; }).concat([1])), last = days.length - 1;
  return '<ol class="clean" role="list" aria-label="Merges by day, oldest first" style="display:grid;grid-template-columns:repeat(' + days.length + ',minmax(0,1fr));gap:2px;align-items:end;margin:12px 0 4px;padding:0">' + days.map(function (d, i) {
    var tall = Math.round(d.merged / top * 120), name = (i === last ? "today" : tpWeekday(d.day)) + " " + d.day.slice(5);
    return '<li title="' + esc(d.day) + ': ' + esc(plural(d.merged, "merge", "merges")) + '" aria-label="' + esc(name + ": " + plural(d.merged, "merge", "merges")) + '" style="display:flex;flex-direction:column;align-items:center;justify-content:end;min-width:0">' +
      '<span style="font-variant-numeric:tabular-nums;color:' + (d.merged ? "var(--ink)" : "var(--ink-3)") + '">' + d.merged + '</span>' +
      '<span style="width:min(100%,40px);height:' + Math.max(tall, 1) + 'px;margin-top:3px;border-radius:4px 4px 0 0;background:' + (d.merged ? "var(--brand)" : "var(--hair)") + '"></span>' +
      '<span class="src" style="border-top:1.5px solid var(--line);align-self:stretch;text-align:center;padding-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(i === last ? "today" : tpWeekday(d.day)) + '<br>' + esc(d.day.slice(5)) + '</span></li>';
  }).join("") + '</ol>';
}
var TP_WAITING = "GitHub has not answered yet", TP_AGAIN_MS = 2000, TP_TRIES = 6;
function tpFetch(name, then, tries) {
  ask("/panel/throughput.json?project=" + encodeURIComponent(name)).then(function (a) {
    var t = a.data.throughput, n = tries || 1;
    if (!t.read && t.error === TP_WAITING && n < TP_TRIES) setTimeout(function () { tpFetch(name, then, n + 1); }, TP_AGAIN_MS);
    else then(t);
  }, function () { then({ read: false, error: "the view server did not answer" }); });
}
function dThroughput(arg, data) {
  var t = data.throughput, mine = turn;
  if (!t.read && t.error === TP_WAITING) {
    tpFetch(PROJECT, function (said) { if (mine === turn && drawer.open) $("dw").innerHTML = tpDrawn(said); }, 2);
    return head("Throughput", "Merges by day") + '<p class="src" style="margin-top:var(--space-8)">Asking GitHub for the merges of each day: it has not answered yet.</p>';
  }
  return tpDrawn(t);
}
function tpDrawn(t) {
  return head("Throughput", "Merges by day") +
    '<div class="now' + (t.read ? "" : " e-op") + '"><span class="tag">The last ' + t.days.length + ' days</span><span class="big">' + plural(t.total, "merge", "merges") + '</span>' +
    '<span class="src">' + (t.read ? 'Pull requests GitHub has as merged, counted by the day of your zone, today up to now. GitHub asked at ' + hm(ms(t.at)) + '.' : 'Not known: ' + esc(t.error) + '.') + '</span></div>' +
    tpBars(t.days);
}
var TP_ASKED = null;
function tpAsk() {
  if (TP_ASKED || !STACK || !STACK.projects.length) return;
  TP_ASKED = {};
  STACK.projects.forEach(function (p) { tpFetch(p.name, function (t) { TP_ASKED[p.name] = t; render(); }); });
}
function tpPerDay() {
  tpAsk();
  if (!TP_ASKED) return "";
  var names = STACK.projects.map(function (p) { return p.name; }), said = names.map(function (n) { return TP_ASKED[n]; });
  var tag = '<span class="tag" data-gloss="card:perday">Merged per day</span>', one = names.length === 1 ? href(names[0], "throughput") : "";
  if (said.some(function (t) { return !t; })) return '<section class="ovc" data-role="perday"><h2 class="ovc-h">' + tag + '</h2><p class="ovc-s">Asking GitHub for the merges of each day.</p></section>';
  var read = said.filter(function (t) { return t.read; }), by = {}, order = [];
  read.forEach(function (t) { t.days.forEach(function (d) { if (!(d.day in by)) { by[d.day] = 0; order.push(d.day); } by[d.day] += d.merged; }); });
  order.sort();
  if (!read.length) return '<section class="ovc" data-role="perday"><h2 class="ovc-h">' + tag + '</h2><p class="ovc-s">Not known: ' + esc(said[0].error || "GitHub did not answer") + '.</p></section>';
  var top = Math.max.apply(null, order.map(function (d) { return by[d]; }).concat([1])), total = order.reduce(function (n, d) { return n + by[d]; }, 0);
  var bars = '<span class="days" role="img" aria-label="' + esc(order.map(function (d) { return d + ": " + by[d]; }).join(", ")) + '">' + order.map(function (d) {
    return '<i' + (by[d] ? "" : ' class="zero"') + ' title="' + esc(d + ": " + plural(by[d], "merge", "merges")) + '" style="height:' + (by[d] ? Math.max(3, Math.round(60 * by[d] / top)) : 1) + 'px"></i>';
  }).join("") + '</span>';
  var line = "<b>" + total + "</b> over the last " + order.length + " days, today up to now" + (read.length < said.length ? ", " + (said.length - read.length) + " of " + said.length + " projects not known" : "");
  return '<section class="ovc" data-role="perday"><h2 class="ovc-h">' + tag + ' <b>' + by[order[order.length - 1]] + '</b> <span class="ovc-s">today</span></h2>' + bars + '<p class="ovc-s">' + (one ? '<a href="' + esc(one) + '">' + line + '</a>' : line) + '</p></section>';
}
panel({
  title: "Throughput",
  parts: { perday: tpPerDay },
  drawer: dThroughput,
  reads: "server",
  gloss: {
    throughput: ["Throughput", "How many pull requests merged on each of the last seven days, and their total, as GitHub counts them."],
    perday: ["Merged per day", "The card under the matrix: how many pull requests merged on each of the last seven days in every project, as GitHub counts them, asked when the page loads, and again while GitHub has not answered yet. A day with none is drawn as a hairline."]
  },
});
