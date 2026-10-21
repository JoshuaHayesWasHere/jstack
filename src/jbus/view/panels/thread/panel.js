var REQ = { researching: "user", reported: "ok", blocked: "user", "not done": "user", "no Report": "gap" };
var REQSAY = { researching: "Its request has no Report yet", reported: "Its Report is written and says done", blocked: "Its Report says it could not go on", "not done": "Its Report is written and says it is not done", "no Report": "Its thread ended with no Report written: it stopped short" };
function onIt(slug) { return (S.threads || []).filter(function (t) { return t.slug === slug && (t.role === "crew" || t.role === "reviewer"); }); }
function about(t) { return threadLine(t, '<code>' + esc(t.title) + '</code>'); }
function works(t) {
  var slug = t.slug, task = TASK[slug] || ENDED[slug], m = DONE[slug], q = t.request;
  if (t.role === "scout") {
    if (!q || q.state === "missing") return '<p>' + gap("not there") + ' No request <code>scouts/' + esc(slug) + '.md</code> in the home of ' + esc(PROJECT) + '.</p>';
    return '<p><span class="chip ' + REQ[asked(t)] + '">' + esc(asked(t)) + '</span> ' + esc(REQSAY[asked(t)]) + '.</p><dl class="kv"><dt>request</dt><dd><code>scouts/' + esc(slug) + '.md</code></dd><dt>asks</dt><dd>' + esc(q.asks || "no title line") + '</dd>' +
      (q.status ? '<dt>Status</dt><dd>' + esc(q.status) + '</dd>' : "") + '</dl>';
  }
  if (t.role === "home") return '<p>The home of ' + esc(PROJECT) + ': it plans the work and hands out each task on the line, ' + plural(S.tasks.length, "open task", "open tasks") + ' now.</p>';
  if (t.role === "other") return '<p class="src">Its title names no role, so what it works on is not known.</p>';
  if (task) return '<p>' + taskBtn(slug) + ' is on <b>' + esc((STEP[task.step] || { name: task.step }).name) + '</b>: ' + esc(task.state.name) + ', waits for ' + esc(task.state.waits) + '.</p>';
  if (m) return '<p>' + taskBtn(slug) + ' merged ' + day(ms(m.at)) + '.</p>';
  return '<p><code>' + esc(slug) + '</code> is not in the queue now.</p>';
}
function dThread(arg) {
  var i = arg.indexOf(":"), role = i < 0 ? arg : arg.slice(0, i), slug = i < 0 ? "" : arg.slice(i + 1), r = ROLE[role];
  if (!r) return null;
  if (slug === "-") slug = "";
  var title = slug || r.called;
  if (!S.threads) return head("Thread", title, true) + '<div class="now e-op"><span class="tag">Not known</span><span class="big">The last pass left no list of the threads: a blind spot, not none.</span></div>';
  var mine = S.threads.filter(function (t) { return t.role === role && t.slug === slug; });
  if (!mine.length) return null;
  var front = mine.filter(function (t) { return t.out; })[0] || mine[mine.length - 1];
  var h = head("Thread", title, true);
  h += '<div class="now w-' + r.holder + '"><span class="tag"><span class="w-' + r.holder + '"><i class="sh"></i></span> ' + esc(r.called)+ '</span><span class="big">' + (front.out ? esc(front.live) : "ended") + ': ' + esc(LIVESAY[front.live]) + '</span><p style="margin:4px 0 0">' + esc(r.says) + '</p></div>';
  h += '<h3>What it works on</h3>' + works(front);
  h += '<h3>' + (mine.length > 1 ? mine.length + " threads" : "The thread") + ', as the last pass saw ' + (mine.length > 1 ? "them" : "it") + '</h3><ul class="clean rows">' + mine.map(about).join("") + '</ul>';
  return h + '<p style="margin-top:12.5px">' + openBtn("threads", "Every thread of " + PROJECT) + '</p>';
}
panel({
  drawer: dThread,
  adds: {
    task: function (t) {
      if (!S.threads) return "Its threads are not known: the last pass left no list.";
      var list = onIt(t.slug);
      return list.length ? "Its threads: " + list.map(function (one) { return threadChip(one, ""); }).join(" ") : "No thread on it was listed by the last pass.";
    }
  }
});
