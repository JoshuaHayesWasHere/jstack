/* The bus: its card of the outbox, and the drawer of what was sent and the last events. */
function dBus() {
  var b = S.bus, lc = { user: "user", quiet: "plain" };
  function kinds(l) {
    var ks = Object.keys(b.today).filter(function (k) { return (b.loudness[k] || "none") === l; }).sort(function (x, y) { return b.today[y] - b.today[x]; });
    return ks.length ? ks.map(function (k) { return '<span class="chip ' + (lc[l] || "gap") + '"><b>' + b.today[k] + '</b> ' + esc(k) + '</span>'; }).join("") : '<span class="src">none</span>';
  }
  return head("Under the line", "The bus") +
    '<div class="now e-' + (b.failed_wakes || b.last_error ? "op" : "ok") + '"><span class="tag">Outbox</span><span class="big">' + plural(b.outbox, "event", "events") + ' in the outbox</span>' +
    '<span class="src">' + (b.last_error ? "Last error: " + esc(b.last_error) + ". " : "") + plural(b.failed_wakes, "failed wake", "failed wakes") + '. Last POST ' + (ms(b.posted) == null ? "never" : day(ms(b.posted))) + '. The count is from <code>status.json</code>: the outbox itself is never read.</span></div>' + note("frozen") +
    '<h3>Sent today, by kind and loudness</h3>' +
    '<span class="tag">user: a kind that may start a POST</span><div class="wrap">' + kinds("user") + '</div>' +
    '<span class="tag">quiet: a kind that is in the log only</span><div class="wrap">' + kinds("quiet") + '</div>' +
    '<h3>The last ' + b.events.length + ' events</h3><ul class="clean steps">' + b.events.slice().reverse().map(eventRow).join("") + '</ul>' +
    '<p class="src" style="margin-top:7.5px">From <code>events.jsonl</code>. <code>sent.json</code> keeps ' + num(b.sent) + ' keys. <code>stall.json</code> holds ' + b.stalls + '.</p>';
}
panel({
  card: function () {
    var b = S.bus;
    return { at: 50, e: b.failed_wakes || b.last_error ? "op" : "ok", tag: "bus", st: fz(), frz: true, val: b.outbox + ' <small>in outbox</small>',
      viz: new Array(Math.min(b.outbox, 12) + 1).join('<i class="sd" style="background:var(--dim)"></i>') + new Array(Math.min(b.failed_wakes, 6) + 1).join('<i class="dot amber"></i>'),
      label: "The bus: " + b.outbox + " events in the outbox, " + b.failed_wakes + " failed wakes" };
  },
  drawer: dBus
});
