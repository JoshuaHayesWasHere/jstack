var MS_PARTS = [["over", "merged", "var(--brand)"], ["pr", "at a pull request", "color-mix(in srgb, var(--brand) 45%, var(--surface))"], ["work", "in work", "var(--ink-3)"], ["queued", "queued", "var(--hair)"]];
var MS_MARK = {
  merged: ["merged", "background:var(--brand);border-color:var(--brand)", "var(--on-brand)"],
  working: ["working", "background:var(--surface);border-color:var(--ink-2)", "var(--ink)"],
  waiting: ["waiting on review or check", "background:var(--surface);border-color:var(--ink-3);border-style:dashed", "var(--ink)"],
  queued: ["queued", "background:var(--sunk);border-color:var(--hair);border-style:dashed", "var(--ink-2)"],
  "needs you": ["needs you", "background:var(--due-tint);border-color:var(--due)", "var(--due)"],
  stuck: ["stuck", "background:var(--missed-tint);border-color:var(--missed)", "var(--missed)"],
  blocked: ["blocked by another row", "background:var(--surface);border-color:var(--missed);border-style:dashed", "var(--missed)"]
};
var MS_ORDER = ["merged", "working", "waiting", "queued", "needs you", "stuck", "blocked"];
function msSum(list) { return list.reduce(function (n, c) { return n + c.count; }, 0); }
function msSplit(m) {
  var queued = msSum(m.rest.filter(function (c) { return c.word.indexOf("queued") === 0; }));
  return { over: m.over, pr: m.pulls.length, work: msSum(m.rest) - queued, queued: queued };
}
function msBar(m, said) {
  var parts = msSplit(m);
  var segs = MS_PARTS.filter(function (p) { return parts[p[0]]; }).map(function (p) {
    return '<i style="flex:' + parts[p[0]] + ' 0 0;background:' + p[2] + '" title="' + parts[p[0]] + " " + p[1] + '"></i>';
  }).join("");
  return '<div class="msb" role="img" aria-label="' + esc(said) + '" style="display:flex;gap:2px;height:6px;border-radius:3px;overflow:hidden;background:var(--sunk);margin:6px 0 8px">' + segs + '</div>';
}
function msNode(mark, label, sub, title) {
  var m = MS_MARK[mark] || MS_MARK.stuck;
  return '<span class="msn" data-mark="' + esc(mark) + '" title="' + esc(title || m[0]) + '" style="display:inline-flex;flex-direction:column;min-width:0;max-width:100%;padding:3px 9px;border:1.5px solid;border-radius:8px;line-height:1.25;' + m[1] + '">' +
    '<span style="font-family:var(--mono);font-size:14px;color:' + m[2] + ';overflow-wrap:anywhere">' + label + '</span>' + (sub ? '<span style="font-size:13px;color:' + (mark === "merged" ? m[2] : "var(--ink-2)") + ';overflow-wrap:anywhere">' + sub + '</span>' : "") + '</span>';
}
var MS_ARROW = '<span aria-hidden="true" style="color:var(--ink-3);padding:0 2px;align-self:center">&rarr;</span>';
function msStep(s) {
  var sub = s.mark === "blocked" ? "behind " + esc(s.by) : esc([s.step, s.pr].filter(Boolean).join(" ") || s.mark);
  return '<li style="display:contents">' + msNode(s.mark, known(s.slug) ? '<button type="button" class="linkish" data-open="task:' + esc(s.slug) + '" style="font:inherit;color:inherit;min-height:0;padding:0;border:0;background:none;box-shadow:none;text-align:left">' + esc(s.slug) + '</button>' : esc(s.slug), sub, (MS_MARK[s.mark] || MS_MARK.stuck)[0] + (s.say ? ": " + s.say : "")) + '</li>';
}
function msChain(m, end, done) {
  var out = [], i = 0, steps = m.steps;
  while (i < steps.length && steps[i].mark === "merged") i++;
  if (i) out.push('<li style="display:contents">' + msNode("merged", (i > 1 ? i + " merged" : esc(steps[0].slug)), steps.slice(0, i).map(function (s) { return esc(s.pr || ""); }).filter(Boolean).join(" ") || "merged", steps.slice(0, i).map(function (s) { return s.slug; }).join(", ")) + '</li>');
  steps.slice(i).forEach(function (s) { out.push(msStep(s)); });
  out.push('<li style="display:contents">' + msNode(done ? "merged" : "queued", esc(end), done ? "reached" : "not yet") + '</li>');
  return '<ol class="clean msc" aria-label="Steps toward ' + esc(end) + '" style="display:flex;flex-wrap:wrap;gap:6px 4px;align-items:stretch;margin:0">' + out.map(function (li, n) { return n ? li.replace('<li style="display:contents">', '<li style="display:contents">' + MS_ARROW) : li; }).join("") + '</ol>';
}
function msWhy(m, held) {
  var lines = [];
  if (m.holder) {
    var h = m.holder, first = m.steps.filter(function (s) { return s.slug === h.by; })[0], said = h.mark === "blocked" ? "waits on " + h.by + (first ? ", which is " + first.mark : "") : h.say || h.mark;
    lines.push('<span class="chip ' + (h.mark === "needs you" ? "user" : "bad") + '">' + esc(h.mark === "blocked" ? "blocked" : h.mark) + '</span> held at <code>' + esc(h.slug) + '</code>: ' + esc(said));
  }
  if (m.waits_on.length) lines.push('Waits on ' + m.waits_on.map(function (w) { return '<b>' + esc(w.milestone || "a row in no milestone") + '</b> (<code>' + esc(w.slug) + '</code>, ' + esc(w.mark) + ')'; }).join(", "));
  if (held.length) lines.push(held.map(function (k) { return '<b>' + esc(k) + '</b>'; }).join(", ") + (held.length === 1 ? " waits" : " wait") + ' on this');
  return lines.length ? '<div class="src" style="margin-top:6px;display:grid;gap:3px;overflow-wrap:anywhere">' + lines.map(function (l) { return '<span>' + l + '</span>'; }).join("") + '</div>' : "";
}
function msFrac(over, total) { return '<b style="font-variant-numeric:tabular-nums;white-space:nowrap">' + over + ' of ' + total + '</b>'; }
var MS_ITEM = "padding:12px 0;border-top:1px solid var(--hair)";
function msEntry(e, held) {
  var top = '<div style="display:flex;gap:8px;align-items:baseline;justify-content:space-between;min-width:0"><span style="min-width:0;overflow-wrap:anywhere"><code>' + esc(e.slug) + '</code> <span>' + esc(e.line) + '</span></span>' +
    (e.total ? msFrac(e.over, e.total) : '<span class="chip plain" style="' + (e.status.length <= 24 ? "flex:none;white-space:nowrap" : "max-width:50%") + '">' + esc(e.status) + '</span>') + '</div>';
  if (!e.total) return '<li class="mse" data-entry="' + esc(e.slug) + '" style="' + MS_ITEM + '">' + top + '</li>';
  return '<li class="mse" data-entry="' + esc(e.slug) + '" style="' + MS_ITEM + '">' + top + msBar(e, e.status) + msChain(e, "done", e.over === e.total) +
    '<div class="src" style="margin-top:6px;overflow-wrap:anywhere">' + esc(e.status) + '</div>' + msWhy(e, held[e.key] || []) + '</li>';
}
function msHome(h, held) {
  var name = h.name || "root", counted = h.entries.filter(function (e) { return e.total; });
  var over = counted.reduce(function (n, e) { return n + e.over; }, 0), total = counted.reduce(function (n, e) { return n + e.total; }, 0);
  var tail = h.plan !== "read" ? (h.plan === "missing" ? "no plan" : gap("plan not read")) : plural(h.entries.length, "entry", "entries") + (total ? ", " + over + " of " + total + " rows merged" : "");
  var moving = counted.filter(function (e) { return e.over < e.total; }), staged = h.entries.filter(function (e) { return !e.total; }), done = counted.filter(function (e) { return e.over === e.total; });
  moving.sort(function (a, b) { return (b.holder ? 1 : 0) - (a.holder ? 1 : 0); });
  var one = function (e) { return msEntry(e, held); }, shown = moving.concat(staged);
  return '<section class="msh" data-home="' + esc(h.name) + '"><h3>' + esc(name) + ' <span class="cnt" style="text-transform:none;letter-spacing:0">' + tail + '</span></h3>' +
    (shown.length ? '<ul class="clean">' + shown.map(one).join("") + '</ul>' : "") +
    (done.length ? '<details class="msd"><summary class="src" style="min-height:44px;display:flex;align-items:center;cursor:pointer">' + plural(done.length, "entry has", "entries have") + ' every row finished: <code style="margin-left:6px">jbus plan close</code></summary><ul class="clean">' + done.map(one).join("") + '</ul></details>' : "") + '</section>';
}
function msTrain(t, held) {
  var said = t.over + " of " + t.total + " merged into " + t.branch + ", " + plural(t.to_go, "row", "rows") + " to go before it lands";
  return '<li class="mst" data-train="' + esc(t.branch) + '" style="' + MS_ITEM + '"><div style="display:flex;gap:8px;align-items:baseline;justify-content:space-between;min-width:0"><span style="min-width:0;overflow-wrap:anywhere"><code>' + esc(t.branch) + '</code> lands on the default branch</span>' + msFrac(t.over, t.total) + '</div>' +
    msBar(t, said) + msChain(t, t.branch + " lands", false) + '<div class="src" style="margin-top:6px">' + esc(t.to_go ? plural(t.to_go, "row", "rows") + " to go before it lands" : "every row is in: it lands when its own pull request merges") + '</div>' + msWhy(t, held[t.key] || []) + '</li>';
}
function msKey() {
  return '<p class="src" style="display:flex;flex-wrap:wrap;gap:6px 12px;margin:12.5px 0 0;align-items:center">' + MS_ORDER.map(function (k) { var m = MS_MARK[k]; return '<span style="display:inline-flex;align-items:center;gap:5px"><i style="display:inline-block;width:14px;height:10px;border:1.5px solid;border-radius:3px;' + m[1] + '"></i>' + esc(m[0]) + '</span>'; }).join("") + '</p>';
}
function msHeld(chains) {
  var held = {};
  chains.forEach(function (c) { c.waits_on.forEach(function (w) { if (w.milestone && (held[w.milestone] || []).indexOf(c.key) < 0) (held[w.milestone] = held[w.milestone] || []).push(c.key); }); });
  return held;
}
function dMilestones(arg, data) {
  var m = data.milestones, entries = [], rowsOver = 0, rows = 0;
  m.homes.forEach(function (h) { h.entries.forEach(function (e) { entries.push(e); rowsOver += e.over; rows += e.total; }); });
  var chains = entries.concat(m.trains), held = msHeld(chains);
  var stuck = chains.filter(function (c) { return c.holder && c.over < c.total; }), done = entries.filter(function (e) { return e.total && e.over === e.total; }).length;
  var h = head("Progress", "Milestones");
  h += '<div class="now"><span class="tag">Now</span><span class="big">' + (stuck.length ? plural(stuck.length, "milestone is", "milestones are") + ' held, ' : "Nothing is held, ") + rowsOver + ' of ' + rows + ' rows merged</span>' +
    '<span class="src">' + plural(entries.length, "plan entry", "plan entries") + ' in ' + plural(m.homes.length, "home", "homes") + ', ' + plural(done, "has", "have") + ' every row finished.' +
    (stuck.length ? ' Held: ' + stuck.slice(0, 4).map(function (c) { return '<b>' + esc(c.key) + '</b> at <code>' + esc(c.holder.slug) + '</code>'; }).join(", ") + (stuck.length > 4 ? " and " + (stuck.length - 4) + " more" : "") + '.' : "") + '</span></div>' + msKey();
  h += m.homes.map(function (x) { return msHome(x, held); }).join("");
  var trains = m.trains.filter(function (t) { return t.total; }), empty = m.trains.filter(function (t) { return !t.total; });
  if (m.trains.length) h += '<section class="mstr"><h3>Trains <span class="cnt" style="text-transform:none;letter-spacing:0">' + plural(m.trains.length, "integration branch", "integration branches") + '</span></h3>' +
    (trains.length ? '<ul class="clean">' + trains.map(function (t) { return msTrain(t, held); }).join("") + '</ul>' : "") +
    (empty.length ? '<p class="src">No brief opens its pull request against ' + esc(empty.map(function (t) { return t.branch; }).join(", ")) + '.</p>' : "") + '</section>';
  return h + '<p class="src" style="margin-top:15px">Each chain is a milestone\'s rows in the order their dependencies give, toward its outcome. A mark is the state the last pass judged for the row. The count and its line are <code>jbus plan</code>\'s own. A train is a branch of the home\'s <code>integration</code> file, and its rows are the briefs whose <code>Pull request:</code> line opens against it. A row merged into a train is not on the default branch until the train\'s own pull request merges.</p>';
}
panel({ title: "Milestones", drawer: dMilestones, wide: true, reads: "server", gloss: { milestones: ["Milestones", "Each plan entry of each home and each train as a chain of its rows toward its outcome, each row marked merged, working, waiting, queued, needs you, stuck or blocked, with the step that holds it and what it waits on."] } });
