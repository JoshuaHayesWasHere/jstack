var NOTICEMARK = { "new": "user", taken: "ok", dropped: "plain" };
function noticedNew() { return (S.noticed || []).filter(function (r) { return r.mark === "new"; }); }
function noticedRow(r) {
  var t = ms(r.seen_at), mark = r.mark === "taken" ? "taken by " + r.row : r.mark;
  return '<li>' + taskBtn(r.slug) + ' <span class="chip ' + (NOTICEMARK[r.mark] || "gap") + '">' + esc(mark) + '</span> ' +
    '<span class="src">' + (t == null ? "a time not kept" : short(NOW - t) + " ago") + ', ' + esc(r.section) + '</span>' +
    '<br>' + esc(r.text) +
    (r.mark === "dropped" ? '<br><span class="src">Dropped' + (r.why ? ": " + esc(r.why) : "") + (r.by ? ", by " + esc(r.by) : "") + '.</span>'
      : r.mark === "taken" ? '<br><span class="src">Taken by ' + esc(r.row) + (r.by ? ", by " + esc(r.by) : "") + '.</span>' : "") + '</li>';
}
function dNoticed() {
  var all = S.noticed || [], fresh = noticedNew().length, older = S.noticed_older || 0;
  var h = head("Noticed", plural(fresh, "new line", "new lines") + " of " + (all.length + older) + ", newest first");
  h += '<p class="src" style="margin-top:15px">From <code>noticed.json</code>: each Noticed line a pass found in a brief or a request. A home marks each one with <code>jbus noticed take</code> or <code>drop</code>. Nothing here writes.</p>';
  return h + (all.length ? '<ul class="clean rows">' + all.map(noticedRow).join("") + '</ul>' : '<p class="src">No Noticed line is kept yet.</p>') +
    (older ? '<p class="src">' + plural(older, "older marked line is", "older marked lines are") + ' not shown: <code>jbus noticed --all</code> prints every one.</p>' : "");
}
panel({
  title: "Noticed",
  drawer: dNoticed,
  adds: {
    you: function () {
      var n = noticedNew().length;
      return n ? { n: n, label: "noticed, not counted", open: "noticed", count: "count:noticed" } : "";
    }
  }
});
