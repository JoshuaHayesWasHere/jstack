function dSteps(hit) {
  var h = head("The line", "The steps, top to bottom");
  h += '<p class="src" style="margin-top:15px">Top to bottom is the path of a task. The shape of a token says who holds it. ' + S.queue.total + ' rows in <code>queue.json</code>: ' + Object.keys(S.queue.by_status).map(function (k) { return S.queue.by_status[k] + " " + esc(k); }).join(", ") + '.</p>' + note("frozen");
  h += '<div class="key">' + ["user", "crew", "home", "rev", "ci", "bus", "dep"].concat(lanes()[0] === UNKNOWN ? ["unknown"] : []).map(function (w) { return '<span class="w-' + w + '"><i class="sh"></i>' + WHO[w] + '</span>'; }).join("") + '<span><i class="mk long"></i>over 30 min on the step</span><span><i class="mk rep"></i>on this step again</span>' + ["moving", "quiet", "hung"].map(function (w) { return '<span><i class="mk lv-' + w + '"></i>its thread is ' + w + '</span>'; }).join("") + '</div>';
  h += '<ul class="clean rows" style="margin-top:10px">' + lanes().map(function (s) {
    var here = s.key === "merged" ? [] : S.tasks.filter(function (t) { return t.step === s.key; }), n = s.key === "merged" ? S.merged.length : here.length, extra = "";
    if (s.key === "queued") extra = '<br><span class="src">Diamond: not approved and nothing in the way, so it waits on you. Ring: another task comes first. Bar: approved and free, jbus launches it when there is room.</span><br>' + openBtn("flow", "The queue as a flow");
    if (s.key === "merged") extra = '<br>' + openBtn("merged", "All " + n + " merged today");
    return '<li' + (s.key === hit ? ' class="hit"' : "") + '>' + (s.group ? '<span class="tag">' + esc(s.group) + '</span><br>' : "") + '<span class="n' + (n ? "" : " zero") + '" data-gloss="count:lane">' + n + '</span> <b>' + esc(s.name) + '</b>' + hint("step:" + s.key, s.name) + ' ' + (s.who ? '<span class="chip ' + esc(s.who) + '">' + (s.who === "ok" ? "done" : "held by " + WHO[s.who]) + '</span>' : '<span class="chip plain">the holder depends on the row</span>') +
      '<br><span class="src">' + esc(s.note) + '</span>' + extra + (!here.length ? "" : s.key !== hit ? '<div class="wrap">' + here.map(function (t) { return taskBtn(t.slug); }).join("") + '</div>' :
        '<ul class="clean rows" style="margin-top:7.5px">' + here.map(function (t) {
          return '<li>' + taskBtn(t.slug) + (t.pr ? ' <code>' + esc(t.pr) + '</code>' : "") + ' ' + ageChip(t.since, t.who) + (t.visits > 1 ? ' <span class="chip plain">' + ord(t.visits) + ' time on this step</span>' : "") + '<br>' + esc(t.state.say) + '</li>';
        }).join("") + '</ul>') + '</li>';
  }).join("") + '</ul>';
  return h;
}
panel({ drawer: dSteps });
