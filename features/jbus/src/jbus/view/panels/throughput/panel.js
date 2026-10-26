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
function dThroughput(arg, data) {
  var t = data.throughput;
  return head("Throughput", "Merges by day") +
    '<div class="now' + (t.read ? "" : " e-op") + '"><span class="tag">The last ' + t.days.length + ' days</span><span class="big">' + plural(t.total, "merge", "merges") + '</span>' +
    '<span class="src">' + (t.read ? 'Pull requests GitHub has as merged, counted by the day of your zone, today up to now. GitHub asked at ' + hm(ms(t.at)) + '.' : 'Not known: ' + esc(t.error) + '.') + '</span></div>' +
    tpBars(t.days);
}
panel({
  title: "Throughput",
  drawer: dThroughput,
  reads: "server",
  gloss: { throughput: ["Throughput", "How many pull requests merged on each of the last seven days, and their total, as GitHub counts them."] },
});
