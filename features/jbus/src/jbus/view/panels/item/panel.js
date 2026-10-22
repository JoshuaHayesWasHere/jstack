var STEERS = { message: "Message home", hold: "Hold", redirect: "Redirect" };
var ITEM_WHERE = { chat: "Sous Chef's chat", view: "the view", cli: "the command line", pass: "a pass of jbus" };
var STEERED = null;
var LOST_STEER = "The view server did not answer, so it is not known whether the steer was written. Read the item again before you steer.";
function steering(id) { return (S.steering || {})[id] || { source: "", steers: [] }; }
function steerOf(it) {
  if (!STEERED || STEERED.id !== it.id) STEERED = { id: it.id, action: "", words: "", phase: "edit", said: null };
  return STEERED;
}
function willSay(it, st) {
  var words = st.words.trim();
  if (!st.action) return '<div class="will none">Pick a steer. Nothing is sent until you tap Steer.</div>';
  if (st.action === "message") return '<div class="will"><b>Sends one message to the home thread of ' + esc(it.id) + ', in your name' + (words ? ':</b><br>&quot;' + esc(words) + '&quot;' : '.</b> Write it above.') + '</div>';
  if (st.action === "hold") return '<div class="will"><b>Takes back the go of ' + esc(it.id) + (it.slug ? ", its row " + esc(it.slug) : "") + '.</b> It is held until you approve it again. Nothing is sent to a thread.' + (words ? '<br>Why, kept on its log: &quot;' + esc(words) + '&quot;' : "") + '</div>';
  return '<div class="will"><b>Writes your words as the new brief of ' + esc(it.slug) + ', and ' + esc(it.id) + ' goes back to you for approval.</b> Nothing is sent to a thread' + (words ? ':<br>&quot;' + esc(words) + '&quot;' : ". Write the brief above.") + '</div>';
}
function steerFoot(it) {
  var st = steerOf(it), ready = st.action && (st.action === "hold" || st.words.trim()), busy = st.phase === "busy";
  var said = st.said ? '<div class="will' + (st.said.bad ? " bad" : "") + '" role="status"><b>' + esc(st.said.say) + '</b></div>' : "";
  if (st.phase === "confirm") return said + '<div class="will bad" role="alert"><b>Hold ' + esc(it.id) + '?</b> Its go is taken back now.</div><p style="margin:8px 0 0"><button type="button" class="btn" id="isure">Yes, hold ' + esc(it.id) + '</button> <button type="button" class="btn" id="inot">Not now</button></p>';
  return said + willSay(it, st) + '<p style="margin:8px 0 0"><button type="button" class="btn" id="isend"' + (ready && !busy ? "" : " disabled") + '>' + (busy ? "Sending&hellip;" : "Steer") + '</button></p>';
}
function itemLine(l) {
  var did = l.verb === "steered" && l.action ? l.action : l.verb;
  return '<li><span class="t">' + hm(ms(l.at)) + '</span><span><span class="chip plain">' + esc(did) + '</span> by ' + esc(l.by) + ' in ' + esc(l.where) + '<span class="r">' + esc(l.line) + '</span></span><span class="d"><code>' + esc(l.id) + '</code></span></li>';
}
function dItem(id) {
  var it = ITEMS[id]; if (!it) return null;
  var more = steering(id), source = more.source || (it.lines[0] && it.lines[0].verb === "proposed" ? it.lines[0].where : "");
  var steers = more.steers.filter(function (a) { return STEERS[a]; }), st = steerOf(it);
  if (st.phase !== "busy") st.seen = it.last_event;
  var h = head("Work item", id + (it.title ? " " + it.title : ""));
  h += '<div class="now w-' + (it.state === "waiting_on_you" || it.state === "proposed" ? "user" : "crew") + '"><span class="tag">Now: ' + esc(ITEM_WORD[it.state] || it.state) + '</span><span class="big">' + esc(it.title || it.slug || id) + '</span></div>';
  h += '<dl class="kv" style="margin-top:12.5px"><dt>What</dt><dd>' + esc(it.title || "no title kept") + '</dd><dt>Source</dt><dd>' + esc(ITEM_WHERE[source] || source || "not kept") + '</dd><dt>Owner</dt><dd>' + esc(it.owner) + '</dd><dt>State</dt><dd>' + esc(ITEM_WORD[it.state] || it.state) + '</dd>' +
    (it.slug ? '<dt>Task</dt><dd>' + taskBtn(it.slug) + '</dd>' : "") + '<dt>Risk</dt><dd>' + esc(it.risk) + '</dd></dl>';
  if (it.risk === "review") h += '<div class="will none"><b>A review item: a merge, a secret or the config.</b> Sous Chef\'s chat shows it with no button. Answer it here, in ' + openBtn("you", "Needs you") + ', as today.</div>';
  h += '<h3>Its last lines</h3>' + (it.lines.length ? '<ul class="clean steps">' + it.lines.map(itemLine).join("") + '</ul>' : '<p class="src">None kept.</p>');
  if (more.steers.indexOf("approve") >= 0) h += '<h3>Approve</h3><p class="src" style="margin:0 0 6px">Gives ' + esc(id) + ' your go by its id' + (it.slug ? '. Its row ' + esc(it.slug) + ' still takes its own go' : "") + '.</p><button type="button" class="btn fill" id="iapprove"' + (st.phase === "busy" ? " disabled" : "") + '>Approve ' + esc(id) + '</button>';
  h += '<h3>Steer</h3>';
  if (!steers.length) return h + (st.said ? '<div class="will' + (st.said.bad ? " bad" : "") + '" role="status"><b>' + esc(st.said.say) + '</b></div>' : "") + '<p class="src">' + (it.state === "done" || it.state === "dropped" ? "An item that is " + esc(it.state) + " takes no steer." : "It takes no steer now.") + '</p>';
  h += '<div class="opts">' + Object.keys(STEERS).map(function (a) {
    var can = steers.indexOf(a) >= 0;
    return '<button type="button" class="opt" data-steer="' + a + '" aria-pressed="' + (st.action === a) + '"' + (can ? "" : " disabled") + '><b>' + STEERS[a] + '</b>' + (can ? "" : '<small>' + (a === "redirect" && it.state !== "running" && it.state !== "waiting_on_you" ? "Not for an item with no row: it has no brief to redirect." : "Not for an item that is " + esc(ITEM_WORD[it.state] || it.state).toLowerCase() + ".") + '</small>') + '</button>';
  }).join("") + '</div>';
  var hint = { message: "Your message to its home", hold: "Why it is held, if you like", redirect: "The new brief" }[st.action];
  h += '<textarea id="iwords" aria-label="' + esc(hint || "Your words") + '" placeholder="' + esc(hint || "Pick a steer first") + '"' + (st.action ? "" : " disabled") + '>' + esc(st.words) + '</textarea><div id="ifoot">' + steerFoot(it) + '</div>';
  return h;
}
function steerDraw() { var it = STEERED && ITEMS[STEERED.id]; if (it && $("ifoot")) $("ifoot").innerHTML = steerFoot(it); }
function steerSend(action) {
  var st = STEERED, it = st && ITEMS[st.id]; if (!it || st.phase === "busy") return;
  var body = { item: st.id, action: action, words: action === "approve" ? "" : st.words.trim(), seen_event: st.seen, confirm: action === "hold" };
  st.phase = "busy"; st.said = null; steerDraw();
  ask("/steer" + QUERY, body).then(function (r) {
    st.phase = "edit";
    st.said = r && r.say ? { say: r.say, bad: r.http !== 200 } : { say: r && r.error ? "The server refused the steer: " + r.error + "." : LOST_STEER, bad: true };
    if (r && r.http === 200) { st.action = ""; st.words = ""; }
    return poll(true);
  }, function () { st.phase = "edit"; st.said = { say: LOST_STEER, bad: true }; }).then(function () {
    if (STEERED === st && top() === "item:" + st.id && drawer.open) { var h = dItem(st.id); if (h) { $("dw").innerHTML = h; titled(); } var f = $("ifoot"); if (f) f.scrollIntoView({ block: "nearest" }); }
  });
}
document.addEventListener("click", function (e) {
  var o = e.target.closest("[data-steer]");
  if (o && STEERED && !o.disabled) {
    STEERED.action = o.getAttribute("data-steer"); STEERED.phase = "edit";
    $("dw").querySelectorAll("[data-steer]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === o)); });
    var t = $("iwords"); t.disabled = false; t.placeholder = { message: "Your message to its home", hold: "Why it is held, if you like", redirect: "The new brief" }[STEERED.action]; t.setAttribute("aria-label", t.placeholder);
    steerDraw(); return;
  }
  if (!STEERED) return;
  if (e.target.closest("#isend")) { if (STEERED.action === "hold") { STEERED.phase = "confirm"; steerDraw(); var y = $("isure"); if (y) y.focus(); } else steerSend(STEERED.action); }
  else if (e.target.closest("#isure")) steerSend("hold");
  else if (e.target.closest("#inot")) { STEERED.phase = "edit"; steerDraw(); }
  else if (e.target.closest("#iapprove")) steerSend("approve");
});
document.addEventListener("input", function (e) {
  if (e.target.id !== "iwords" || !STEERED) return;
  STEERED.words = e.target.value;
  steerDraw();
});
panel({ reads: "mixed", drawer: dItem });
