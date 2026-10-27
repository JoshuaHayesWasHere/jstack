function silence(word, updated, started, queued) {
  var u = ms(updated), s = ms(started);
  return "Its thread is " + word + ": it has written nothing " + (u == null ? "for a time that was not kept" : "since " + day(u) + ", " + dur(NOW - u) + " ago") + (s == null ? "" : ", its turn started " + day(s)) + (queued ? ", and " + plural(queued, "run waits", "runs wait") + " behind it" : "") + ".";
}
function fixingLine(f) {
  var at = ms(f.told);
  return "Fixing: " + f.owner + ", " + (at == null ? "not told yet" : "told " + day(at)) + ".";
}
function segments(t) {
  var segs = [];
  t.history.forEach(function (l, i) {
    if (l.word === "merged") return;
    var a = ms(l.at), b = i + 1 < t.history.length ? ms(t.history[i + 1].at) : Math.max(NOW, a);
    segs.push({ a: a, b: b, step: l.step, who: (STEP[l.step] || {}).who || "crew", text: l.reason, cur: i === t.history.length - 1 });
  });
  return segs;
}
function dTask(slug) {
  var t = TASK[slug] || ENDED[slug], m = DONE[slug];
  if (!t && !m) return null;
  if (!t) {
    var at = ms(m.at), ap = ms(m.approved);
    return head("Task", slug + (m.pr ? " " + m.pr : ""), true) + '<div class="now w-ok"><span class="tag">Now: Merged</span><span class="big">Merged at ' + hm(at) + (ap == null ? "" : ", " + dur(at - ap) + " after approval") + '</span></div>' + (m.pr ? ghBox(slug) : "");
  }
  var st = t.state, bl = t.blocked, h = head("Task", slug + (t.pr ? " " + t.pr : ""), true);
  h += '<div class="now w-' + (t.who === "dep" || t.who === "bus" ? "plain" : esc(t.who)) + '"><span class="tag">Now: ' + esc(st.name) + '</span><span class="big">' + esc(st.say) + '</span>' +
    '<span class="chip ' + esc(t.who) + '">waits for ' + esc(st.waits) + '</span> ' + ageChip(t.since) + ' ' +
    (t.visits > 1 ? '<span class="chip plain">' + ord(t.visits) + ' time here</span> ' : "") +
    (bl && bl.by ? '<p style="margin:10px 0 0"><i class="mk blk"></i> Blocked by ' + taskBtn(bl.by) + ' <span class="chip plain">' + esc(bl.state) + '</span></p>' : "") +
    (t.blocks ? '<p style="margin:10px 0 0"><span class="bn">' + t.blocks + '</span> ' + behind(t.blocks).replace(/^\d+ /, "") + ': ' + t.behind.map(taskBtn).join(", ") + '</p>' : "") +
    (t.seen.live === "quiet" || t.seen.live === "hung" ? '<p style="margin:10px 0 0"><i class="mk lv-' + t.seen.live + '"></i> ' + esc(silence(t.seen.live, t.seen.wrote, t.seen.run_started, t.seen.queued)) + '</p>' : "") +
    (t.fixing ? '<p style="margin:10px 0 0">' + esc(fixingLine(t.fixing)) + '</p>' : "") +
    (st.row ? '<p style="margin:10px 0 0">' + gap("the row disagrees") + ' ' + esc(st.row) + '.</p>' : "") +
    (t.unconfirmed ? '<p style="margin:10px 0 0">' + gap("not confirmed") + ' ' + esc(t.unconfirmed.line.replace(/^not confirmed /, "")) + '.</p>' : "") +
    (ITEM_OF[slug] ? '<p style="margin:10px 0 0">Work item ' + openBtn("item:" + ITEM_OF[slug].id, ITEM_OF[slug].id) + ' <span class="chip plain">' + esc(ITEM_WORD[ITEM_OF[slug].state]) + '</span></p>' : "") +
    added("task", t).map(function (a) { return '<p style="margin:10px 0 0">' + a.said + '</p>'; }).join("") +
    '</div>';
  if (t.pr) h += ghBox(slug);
  if (t.depends.length) h += '<h3>Depends on</h3><ul class="clean steps">' + t.depends.map(function (d) {
    return '<li class="one"><span>' + taskBtn(d.slug) + ' <span class="chip ' + (d.state === "merged" || d.state === "done" ? "ok" : "user") + '">' + esc(d.state) + '</span></span></li>';
  }).join("") + '</ul>';
  var segs = segments(t);
  if (segs.length) {
    var a0 = segs[0].a, b1 = segs[segs.length - 1].b, span = Math.max(1, b1 - a0), tot = {};
    segs.forEach(function (g) { tot[g.who] = (tot[g.who] || 0) + (g.b - g.a); });
    h += '<h3>Where the time went</h3><svg class="seg" viewBox="0 0 1000 30" preserveAspectRatio="none" role="img" aria-label="Time for each holder from ' + day(a0) + ' to ' + day(b1) + '">' +
      segs.map(function (g) { return '<rect class="' + esc(g.who) + '" x="' + ((g.a - a0) / span * 1000).toFixed(1) + '" y="0" width="' + ((g.b - g.a) / span * 1000).toFixed(1) + '" height="30"><title>' + hm(g.a) + ' ' + esc((STEP[g.step] || {}).name) + ': ' + dur(g.b - g.a) + '</title></rect>'; }).join("") + '</svg>' +
      '<div class="axis"><span>' + day(a0) + '</span><span>' + dur(span) + '</span><span>' + hm(b1) + '</span></div>' +
      '<div class="key">' + ["crew", "rev", "ci", "user", "unknown"].filter(function (w) { return tot[w]; }).map(function (w) { return '<span><i class="sw ' + w + '"></i>' + WHO[w] + ' <b style="color:var(--ink)">' + dur(tot[w]) + '</b></span>'; }).join("") + '</div>' +
      '<ul class="clean steps" style="margin-top:10px">' + segs.map(function (g) {
        return '<li class="' + (g.cur ? "cur" : "") + '"><span class="t">' + hm(g.a) + '</span><span><span class="chip ' + esc(g.who) + '">' + esc((STEP[g.step] || {}).name) + '</span>' + (g.cur ? ' <span class="chip plain">now</span>' : "") + '<span class="r">' + esc(g.text) + '</span></span><span class="d">' + dur(g.b - g.a) + '</span></li>';
      }).join("") + '</ul><p class="src" style="margin-top:7.5px">From <code>merge.log</code>: each length runs until jmerge printed another reason.</p>';
  }
  var seen = t.seen;
  h += '<h3>What the last pass saw</h3><dl class="kv"><dt>thread</dt><dd>' + (seen.thread_status ? esc(seen.thread_status) + (ms(seen.thread_updated) == null ? "" : ", updated " + day(ms(seen.thread_updated))) : "none") + (seen.live ? ' <span class="chip ' + LIVE[seen.live] + '">' + esc(seen.live) + '</span>' : "") + '</dd><dt>threads out</dt><dd>' + seen.threads + '</dd>' +
    (seen.check ? '<dt>check</dt><dd>' + esc(seen.check.name) + ' <b>' + esc(seen.check.state) + '</b>' + (ms(seen.check.started) == null ? "" : ", started " + hm(ms(seen.check.started), true)) + '</dd>' : "") + '</dl>';
  h += '<h3>Events sent about this task</h3>' + (t.events.length ? '<ul class="clean steps">' + t.events.slice().reverse().map(eventRow).join("") + '</ul>' : '<p class="src">None in the log.</p>');
  h += '<h3>The queue row, as jbus wrote it' + (st.row ? ", which disagrees" : "") + '</h3><dl class="kv">' +
    [["slug", t.slug], ["status", t.status], ["priority", t.priority], ["approved", t.approved], ["updated", ms(t.updated) == null ? "" : day(ms(t.updated))], ["checks", t.checks], ["pr", t.row_pr], ["depends", t.depends.map(function (d) { return d.slug; }).join(", ")], ["thread", t.thread]]
      .map(function (kv) { return '<dt>' + kv[0] + '</dt><dd>' + (kv[1] === "" ? '<span class="src">empty</span>' : '<code>' + esc(kv[1]) + '</code>') + (kv[0] === "approved" && t.by_rule ? ' <span class="chip plain">by rule ' + esc(t.by_rule.rule) + '</span>' : "") + '</dd>'; }).join("") + '</dl>';
  return h;
}
panel({ drawer: dTask });
