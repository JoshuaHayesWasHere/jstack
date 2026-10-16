function busFails(b) { return [b, b.top_level, b.blocking].some(function (o) { return !!(o && (o.failed_wakes || o.last_error)); }); }
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
    (t ? busNow("Outbox, top-level webhook", t, "What waits on the user, posted to the monitor of every project beside the project's own webhook.") : "") +
    (b.blocking ? busNow("Outbox, second target", b.blocking, "What blocks: each item as it opens, its one reminder and the hourly refresh, posted to the webhook jbus-relay fans out. Its outbox holds whole bodies.") : "") + note("frozen") +
    '<h3>Sent today, by kind and loudness</h3>' +
    '<span class="tag">user: a kind that may start a POST</span><div class="wrap">' + kinds("user") + '</div>' +
    '<span class="tag">quiet: a kind that is in the log only</span><div class="wrap">' + kinds("quiet") + '</div>' +
    '<h3>The last ' + b.events.length + ' events</h3><ul class="clean steps">' + b.events.slice().reverse().map(eventRow).join("") + '</ul>' +
    '<p class="src" style="margin-top:7.5px">From <code>events.jsonl</code>. <code>sent.json</code> keeps ' + num(b.sent) + ' keys. <code>stall.json</code> holds ' + b.stalls + '.</p>';
}
panel({
  gloss: { bus: ["Bus outbox", "Events a pass wrote to send to the Chef and has not sent yet. A failed wake is a send that did not go out."] },
  card: function () {
    var b = S.bus;
    var t = b.top_level, top = t ? ", top-level webhook: " + t.outbox + " events in its outbox, " + t.failed_wakes + " failed wakes" + (t.last_error ? ", last error: " + t.last_error : "") : "";
    var g = b.blocking, second = g ? ", second target: " + g.outbox + " bodies in its outbox, " + g.failed_wakes + " failed wakes" + (g.last_error ? ", last error: " + g.last_error : "") : "";
    var fails = b.failed_wakes + (t ? t.failed_wakes : 0) + (g ? g.failed_wakes : 0);
    return { at: 50, sum: "bus " + b.outbox + " in outbox", e: busFails(b) ? "op" : "ok", tag: "bus", st: fz(), frz: true, val: b.outbox + ' <small>in outbox</small>' + (t ? ' <small>+ ' + t.outbox + ' top-level</small>' : "") + (g ? ' <small>+ ' + g.outbox + ' second target</small>' : ""),
      viz: new Array(Math.min(b.outbox, 12) + 1).join('<i class="sd" style="background:var(--dim)"></i>') + new Array(Math.min(fails, 6) + 1).join('<i class="dot amber"></i>'),
      label: "The bus: " + b.outbox + " events in the outbox, " + b.failed_wakes + " failed wakes" + top + second };
  },
  drawer: dBus
});
