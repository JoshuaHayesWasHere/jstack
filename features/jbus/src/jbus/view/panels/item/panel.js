var ITEM_WHERE = { chat: "Sous Chef's chat", view: "the view", cli: "the command line", pass: "a pass of jbus" };
var APPROVING = null;
var LOST_GO = "The view server did not answer, so it is not known whether the go was written. Read the item again before you approve it.";
function takes(id) { return (S.takes || {})[id] || { source: "", approve: false }; }
function goOf(it) {
  if (!APPROVING || APPROVING.id !== it.id) APPROVING = { id: it.id, busy: false, said: null };
  return APPROVING;
}
function itemLine(l) {
  return '<li><span class="t">' + hm(ms(l.at)) + '</span><span><span class="chip plain">' + esc(l.verb) + '</span> by ' + esc(l.by) + ' in ' + esc(l.where) + '<span class="r">' + esc(l.line) + '</span></span><span class="d"><code>' + esc(l.id) + '</code></span></li>';
}
function dItem(id) {
  var it = ITEMS[id]; if (!it) return null;
  var more = takes(id), source = more.source || (it.lines[0] && it.lines[0].verb === "proposed" ? it.lines[0].where : ""), go = goOf(it);
  if (!go.busy) go.seen = it.last_event;
  var h = head("Work item", id + (it.title ? " " + it.title : ""));
  h += '<div class="now w-' + (it.state === "waiting_on_you" || it.state === "proposed" ? "user" : "crew") + '"><span class="tag">Now: ' + esc(ITEM_WORD[it.state] || it.state) + '</span><span class="big">' + esc(it.title || it.slug || id) + '</span></div>';
  h += '<dl class="kv" style="margin-top:12.5px"><dt>What</dt><dd>' + esc(it.title || "no title kept") + '</dd><dt>Source</dt><dd>' + esc(ITEM_WHERE[source] || source || "not kept") + '</dd><dt>Owner</dt><dd>' + esc(it.owner) + '</dd><dt>State</dt><dd>' + esc(ITEM_WORD[it.state] || it.state) + '</dd>' +
    (it.slug ? '<dt>Task</dt><dd>' + taskBtn(it.slug) + '</dd>' : "") + '<dt>Risk</dt><dd>' + esc(it.risk) + '</dd></dl>';
  if (it.risk === "review") h += '<div class="will none"><b>A review item: a merge, a secret or the config.</b> Sous Chef\'s chat shows it with no button. Answer it here, in ' + openBtn("you", "Needs you") + ', as today.</div>';
  h += '<h3>Its last lines</h3>' + (it.lines.length ? '<ul class="clean steps">' + it.lines.map(itemLine).join("") + '</ul>' : '<p class="src">None kept.</p>');
  if (more.approve) h += '<h3>Approve</h3><p class="src" style="margin:0 0 6px">Gives ' + esc(id) + ' your go by its id' + (it.slug ? '. Its row ' + esc(it.slug) + ' still takes its own go' : "") + '.</p><button type="button" class="btn fill" id="iapprove"' + (go.busy ? " disabled" : "") + '>Approve ' + esc(id) + '</button>';
  if (go.said) h += '<div class="will' + (go.said.bad ? " bad" : "") + '" role="status"><b>' + esc(go.said.say) + '</b></div>';
  return h;
}
function approveItem() {
  var go = APPROVING, it = go && ITEMS[go.id]; if (!it || go.busy) return;
  go.busy = true; go.said = null;
  var b = $("iapprove"); if (b) b.disabled = true;
  ask("/approve" + QUERY, { item: go.id, seen_event: go.seen }).then(function (r) {
    go.said = r && r.say ? { say: r.say, bad: r.http !== 200 } : { say: r && r.error ? "The server refused the go: " + r.error + "." : LOST_GO, bad: true };
    return poll(true);
  }, function () { go.said = { say: LOST_GO, bad: true }; }).then(function () {
    go.busy = false;
    if (APPROVING === go && top() === "item:" + go.id && drawer.open) { var h = dItem(go.id); if (h) { $("dw").innerHTML = h; titled(); } }
  });
}
document.addEventListener("click", function (e) {
  if (APPROVING && e.target.closest("#iapprove")) approveItem();
});
panel({ reads: "mixed", drawer: dItem });
