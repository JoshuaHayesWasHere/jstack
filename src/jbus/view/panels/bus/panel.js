/* The bus: its card of the outbox, and the drawer of what was sent and the last events.
   The top-level webhook, where the project posts to it beside its own, has its own outbox. */
function busFails(b) { var t = b.top_level; return !!(b.failed_wakes || b.last_error || (t && (t.failed_wakes || t.last_error))); }
function busNow(tag, o, own) {
  return '<div class="now e-' + (o.failed_wakes || o.last_error ? "op" : "ok") + '"><span class="tag">' + tag + '</span><span class="big">' + plural(o.outbox, "event", "events") + ' in the outbox</span>' +
    '<span class="src">' + (o.last_error ? "Last error: " + esc(o.last_error) + ". " : "") + plural(o.failed_wakes, "failed wake", "failed wakes") + '. Last POST ' + (ms(o.posted) == null ? "never" : day(ms(o.posted))) + '. ' + own + '</span></div>';
}
function dBus() {
  var b = S.bus, t = b.top_level, lc = { user: "user", quiet: "plain" };
  function kinds(l) {
    var ks = Object.keys(b.today).filter(function (k) { return (b.loudness[k] || "none") === l; }).sort(function (x, y) { return b.today[y] - b.today[x]; });
    return ks.length ? ks.map(function (k) { return '<span class="chip ' + (lc[l] || "gap") + '"><b>' + b.today[k] + '</b> ' + esc(k) + '</span>'; }).join("") : '<span class="src">none</span>';
  }
  return head("Under the line", "The bus") +
    busNow(t ? "Outbox, own webhook" : "Outbox", b, "The count is from <code>status.json</code>: the outbox itself is never read.") +
    (t ? busNow("Outbox, top-level webhook", t, "What waits on the user, posted to the monitor of every project beside the project's own webhook.") : "") + note("frozen") +
    '<h3>Sent today, by kind and loudness</h3>' +
    '<span class="tag">user: a kind that may start a POST</span><div class="wrap">' + kinds("user") + '</div>' +
    '<span class="tag">quiet: a kind that is in the log only</span><div class="wrap">' + kinds("quiet") + '</div>' +
    '<h3>The last ' + b.events.length + ' events</h3><ul class="clean steps">' + b.events.slice().reverse().map(eventRow).join("") + '</ul>' +
    '<p class="src" style="margin-top:7.5px">From <code>events.jsonl</code>. <code>sent.json</code> keeps ' + num(b.sent) + ' keys. <code>stall.json</code> holds ' + b.stalls + '.</p>';
}
panel({
  card: function () {
    var b = S.bus;
    var t = b.top_level, top = t ? ", top-level webhook: " + t.outbox + " events in its outbox, " + t.failed_wakes + " failed wakes" + (t.last_error ? ", last error: " + t.last_error : "") : "";
    var fails = b.failed_wakes + (t ? t.failed_wakes : 0);
    return { at: 50, e: busFails(b) ? "op" : "ok", tag: "bus", st: fz(), frz: true, val: b.outbox + ' <small>in outbox</small>' + (t ? ' <small>+ ' + t.outbox + ' top-level</small>' : ""),
      viz: new Array(Math.min(b.outbox, 12) + 1).join('<i class="sd" style="background:var(--dim)"></i>') + new Array(Math.min(fails, 6) + 1).join('<i class="dot amber"></i>'),
      label: "The bus: " + b.outbox + " events in the outbox, " + b.failed_wakes + " failed wakes" + top };
  },
  drawer: dBus
});
