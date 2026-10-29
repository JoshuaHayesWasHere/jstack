function busNow(tag, o, own) {
  var big = o.outbox == null ? plural(o.failed_wakes, "failed wake", "failed wakes") : plural(o.outbox, "body", "bodies") + ' in the outbox';
  var post = o.outbox == null ? "" : 'Last POST ' + (ms(o.posted) == null ? "never" : day(ms(o.posted))) + '. ';
  return '<div class="now e-' + (o.failed_wakes || o.last_error ? "op" : "ok") + '"><span class="tag">' + tag + '</span><span class="big">' + big + '</span>' +
    '<span class="src">' + (o.last_error ? "Last error: " + esc(o.last_error) + ". " : "") + (o.outbox == null ? "" : plural(o.failed_wakes, "failed post", "failed posts") + '. ') + post + own + '</span></div>';
}
var LAST_EVENTS = 10;
function dBus(arg) {
  var b = S.bus, lc = { user: "user", quiet: "plain" };
  function kinds(l) {
    var ks = Object.keys(b.today).filter(function (k) { return (b.loudness[k] || "none") === l; }).sort(function (x, y) { return b.today[y] - b.today[x]; });
    return ks.length ? ks.map(function (k) { return '<span class="chip ' + (lc[l] || "gap") + '"><b>' + b.today[k] + '</b> ' + esc(k) + '</span>'; }).join("") : '<span class="src">none</span>';
  }
  if (arg === "events") return head("Under the line", "The last " + b.events.length + " events") + '<ul class="clean steps">' + b.events.slice().reverse().map(eventRow).join("") + '</ul>';
  var last = b.events.slice(-LAST_EVENTS).reverse();
  return head("Under the line", "The bus") +
    busNow("Home thread", b, "The wakes of the one list. The count is from <code>status.json</code>." + (b.since ? " Wakes fail since " + day(ms(b.since)) + "." : "")) +
    (b.blocking ? busNow("Outbox, second target", b.blocking, "What blocks: each item as it opens, its one reminder and the hourly refresh, posted to the address jbus-relay fans out. Its outbox holds whole bodies.") : "") +
    '<h3>Sent today, by kind and loudness</h3>' +
    '<span class="tag">user: a kind that may wake the home thread</span><div class="wrap">' + kinds("user") + '</div>' +
    '<span class="tag">quiet: a kind that is in the log only</span><div class="wrap">' + kinds("quiet") + '</div>' +
    '<h3>The last ' + last.length + ' events</h3><ul class="clean steps">' + last.map(eventRow).join("") + '</ul>' +
    (b.events.length > last.length ? '<p style="margin-top:7.5px">' + openBtn("bus:events", "The last " + b.events.length + " events") + '</p>' : "") +
    '<p class="src" style="margin-top:7.5px">From <code>events.jsonl</code>. <code>sent.json</code> keeps ' + num(b.sent) + ' keys. <code>stall.json</code> holds ' + b.stalls + '.</p>';
}
panel({
  gloss: { bus: ["Bus", "The wakes a pass sends to the homes. A failed wake is a send that did not go out."] },
  drawer: dBus
});
