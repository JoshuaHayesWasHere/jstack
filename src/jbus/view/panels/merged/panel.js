function dMerged() {
  var mt = S.merged.slice().reverse();
  return head("Done", mt.length + " merged today") +
    '<p class="src" style="margin-top:15px">main at <code>' + esc(S.main.sha.slice(0, 7) || "unknown") + '</code>' + (ms(S.main.at) == null ? "" : ", moved " + day(ms(S.main.at))) + '. ' + (S.queue.by_status.merged || 0) + ' rows merged in all.</p>' + note("frozen") +
    '<h3>Newest first</h3><ul class="clean steps">' + mt.map(function (m) {
      var a = ms(m.approved), at = ms(m.at);
      return '<li><span class="t">' + hm(at) + '</span><span>' + taskBtn(m.slug) + ' <span class="src">' + esc(m.pr) + '</span></span><span class="d">' + (a == null ? "" : dur(at - a)) + '</span></li>';
    }).join("") + '</ul><p class="src" style="margin-top:7.5px">The time on the right is from approval to merge.</p>';
}
panel({ drawer: dMerged });
