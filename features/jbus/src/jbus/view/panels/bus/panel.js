function busNow(tag, o, own) {
  return '<div class="now e-' + (o.failed_wakes || o.last_error ? "op" : "ok") + '"><span class="tag">' + tag + '</span><span class="big">' + plural(o.outbox, "event", "events") + ' in the outbox</span>' +
    '<span class="src">' + (o.last_error ? "Last error: " + esc(o.last_error) + ". " : "") + plural(o.failed_wakes, "failed wake", "failed wakes") + '. Last POST ' + (ms(o.posted) == null ? "never" : day(ms(o.posted))) + '. ' + own + '</span></div>';
}
var LAST_EVENTS = 10;
function dBus(arg) {
  var b = S.bus, t = b.top_level, lc = { user: "user", quiet: "plain" };
  function kinds(l) {
    var ks = Object.keys(b.today).filter(function (k) { return (b.loudness[k] || "none") === l; }).sort(function (x, y) { return b.today[y] - b.today[x]; });
    return ks.length ? ks.map(function (k) { return '<span class="chip ' + (lc[l] || "gap") + '"><b>' + b.today[k] + '</b> ' + esc(k) + '</span>'; }).join("") : '<span class="src">none</span>';
  }
  if (arg === "events") return head("Under the line", "The last " + b.events.length + " events") + '<ul class="clean steps">' + b.events.slice().reverse().map(eventRow).join("") + '</ul>';
  var last = b.events.slice(-LAST_EVENTS).reverse();
  return head("Under the line", "The bus") +
    busNow(t ? "Outbox, own route" : "Outbox", b, "The count is from <code>status.json</code>, with any route the project no longer takes: the outbox itself is never read." + (b.stranded ? " " + plural(b.stranded, "event waits", "events wait") + " in a route the project no longer takes, and the next pass moves them." : "") + (b.since ? " Wakes fail since " + day(ms(b.since)) + "." : "")) +
    (t ? busNow("Outbox, top-level webhook", t, "What waits on the user, posted to the monitor of every project beside the project's own webhook.") : "") +
    (b.blocking ? busNow("Outbox, second target", b.blocking, "What blocks: each item as it opens, its one reminder and the hourly refresh, posted to the webhook jbus-relay fans out. Its outbox holds whole bodies.") : "") +
    '<h3>Sent today, by kind and loudness</h3>' +
    '<span class="tag">user: a kind that may start a POST</span><div class="wrap">' + kinds("user") + '</div>' +
    '<span class="tag">quiet: a kind that is in the log only</span><div class="wrap">' + kinds("quiet") + '</div>' +
    '<h3>The last ' + last.length + ' events</h3><ul class="clean steps">' + last.map(eventRow).join("") + '</ul>' +
    (b.events.length > last.length ? '<p style="margin-top:7.5px">' + openBtn("bus:events", "The last " + b.events.length + " events") + '</p>' : "") +
    '<p class="src" style="margin-top:7.5px">From <code>events.jsonl</code>. <code>sent.json</code> keeps ' + num(b.sent) + ' keys. <code>stall.json</code> holds ' + b.stalls + '.</p>';
}
panel({
  gloss: { bus: ["Bus outbox", "Events a pass wrote to send to the Chef and has not sent yet. A failed wake is a send that did not go out."] },
  drawer: dBus
});
