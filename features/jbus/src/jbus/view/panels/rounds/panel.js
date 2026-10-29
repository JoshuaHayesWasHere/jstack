function roundsOf(slug) { return (S.rounds || []).filter(function (r) { return r.slug === slug; })[0] || null; }
function roundsSay(r) { return plural(r.reviews.length, "review", "reviews") + ", " + plural(r.woke, "wake", "wakes"); }
function yesNo(b) { return b ? "needed" : "not needed"; }
function dRounds(slug) {
  var r = roundsOf(slug);
  if (!r) return null;
  var h = head("Rounds", slug, true);
  if (!r.read) return h + '<div class="now"><span class="tag">Now</span><span class="big">' + gap("not read") + ' ' + esc(r.why) + '.</span><span class="src">Nothing is counted while the brief cannot be read: that is not a task with no review.</span></div>' + '<p>' + taskBtn(slug) + '</p>';
  h += '<div class="now"><span class="tag">Now</span><span class="big">' + esc(roundsSay(r)) + '</span></div>';
  h += '<h3>Reviews, in the order of the brief</h3>' + (r.reviews.length ? '<ul class="clean steps">' + r.reviews.map(function (v, i) {
    var t = ms(v.at);
    return '<li><span class="t">' + ord(i + 1) + '</span><span><span class="chip ' + (v.verdict === "clean" ? "ok" : v.verdict === "findings" ? "rev" : "gap") + '">' + esc(v.verdict || "no verdict") + '</span> review of <code>' + esc((v.head || "no head").slice(0, 12)) + '</code><span class="r">' + plural(v.findings, "finding", "findings") + '</span></span><span class="d">' + (t == null ? gap("no time kept") : day(t)) + '</span></li>';
  }).join("") + '</ul>' : '<p class="src">No review is written in the brief.</p>');
  h += '<h3>After the review</h3><dl class="kv"><dt>second pass</dt><dd>' + yesNo(r.second) + '</dd><dt>scoped review</dt><dd>' + yesNo(r.scoped) + '</dd><dt>wakes</dt><dd>' + r.woke + '</dd></dl>';
  return h + '<p class="src" style="margin-top:10px">Read from the brief with the reader <code>jmerge</code> merges by. A review has a time only where the event log has a <code>review</code> event of its head. Wakes are the lines that start <code>Woke</code> or <code>Woken</code>.</p><p>' + taskBtn(slug) + '</p>';
}
panel({
  drawer: dRounds,
  adds: {
    task: function (t) {
      var r = roundsOf(t.slug);
      if (!r) return "";
      return openBtn("rounds:" + t.slug, r.read ? roundsSay(r) : "The brief cannot be read, so its rounds are not known");
    }
  }
});
