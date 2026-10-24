var NEEDS_FOR = 10;
var ACCEPTING = {}, SAID = [];
var LOST_APPROVAL = "The view server did not answer, so it is not known whether the approval was written. Read the list again before you approve.";
function needId(w) { return w.project + "/" + w.key; }
function needNumber(w) { return w.answerable ? name(w.open.split("/").pop()) : ""; }
function needLink(w) { var at = parse(w.open); return href(at.project, at.target); }
function inlineAccept(w) { return (w.answerable && w.verb === "Accept default") || (!!w.item && !!PROJECT); }
function saysSlug(line, slug) { return (" " + line + " ").split(/[^\w.-]+/).indexOf(slug) >= 0; }
function needMeta(w, soon) {
  var v = ms(w.since), due = ms(w.due), bits = PROJECT ? [] : [esc(w.project)];
  if (w.slug && !saysSlug(w.what, w.slug)) bits.push('<a class="ilk" href="' + esc(href(w.project, "task:" + w.slug)) + '" aria-label="Task ' + esc(w.slug) + ': open it">' + esc(w.slug) + '</a>');
  if (w.item) bits.push('<a class="ilk" href="' + esc(needLink(w)) + '">' + esc(w.item) + '</a>');
  bits.push(v == null ? "no time kept" : NOW - v < 60e3 ? "new" : "waiting " + short(NOW - v));
  if (soon && due != null) bits.push(due <= NOW ? "goes ahead now" : "goes ahead in " + short(due - NOW) + ", at " + hm(due));
  if (w.risk !== "reversible") bits.push(esc(w.risk));
  if (w.unblocks.length) bits.push("unblocks " + esc(w.unblocks.slice(0, 2).join(", ")) + (w.unblocks.length > 2 ? " and " + (w.unblocks.length - 2) + " more" : ""));
  return bits.join(" &middot; ");
}
function needAct(w) {
  var id = needId(w), now = ACCEPTING[id];
  if (now) return '<span class="acc">' + (now.sent ? (w.item ? "Approving it&hellip;" : "Closing it&hellip;") : (w.item ? "Approving " + esc(w.item) : "Accepting the default") + ' in <span class="cd"></span> s &middot; <button type="button" class="btn" data-undo="' + esc(id) + '">Undo</button>') + '</span>';
  if (inlineAccept(w)) return '<button type="button" class="btn fill" data-accept="' + esc(id) + '" aria-description="' + (w.item ? "Approves " + esc(w.item) : "Accepts the default of question " + esc(needNumber(w))) + ' in ' + NEEDS_FOR + ' seconds, and it can be undone until then">' + esc(w.verb) + '</button>';
  if (PROJECT) return '<button type="button" class="btn" data-open="' + esc(parse(w.open).target) + '">' + esc(w.verb) + '</button>';
  return '<a class="btn" href="' + esc(needLink(w)) + '">' + esc(w.verb) + '</a>';
}
function needRow(w, soon) {
  return '<div class="nb"><b class="nw">' + esc(w.what) + '</b>' + (w.why ? '<span class="ny">' + esc(w.why) + '</span>' : "") +
    (w["default"] ? '<span class="ny">If you do nothing: ' + esc(w["default"]) + '</span>' : "") + '<span class="nm"' + (ms(w.since) == null ? "" : ' title="Since ' + esc(day(ms(w.since))) + '"') + '>' + needMeta(w, soon) + '</span></div><div class="na">' + needAct(w) + '</div>';
}
function lastPass() {
  var j = jb(), t = j && (ms(j.status && j.status.last_pass) || ms(j.last_end)), said = passWord(t);
  return said ? " &middot; " + said : "";
}
function saidRows() {
  return SAID.map(function (s) { return '<p class="' + (s.bad ? "will bad" : "will none") + '"><b>' + esc(s.say) + '</b></p>'; }).join("");
}
function ticks() {
  [].forEach.call(document.querySelectorAll("#needs .cd"), function (el) {
    var id = el.closest("[data-key]").getAttribute("data-key"), now = ACCEPTING[id];
    if (now) say(el, String(now.left));
  });
}
function leaveAccepts() {
  Object.keys(ACCEPTING).forEach(function (id) {
    var now = ACCEPTING[id];
    if (now.sent || !PROJECT || PROJECT === now.w.project) return;
    clearInterval(now.timer); delete ACCEPTING[id];
  });
}
function renderNeeds() {
  leaveAccepts();
  var src = PROJECT ? S : STACK, box = $("needs");
  box.hidden = !src || !!NOSUCH;
  if (box.hidden) return;
  var needs = src.needs, soon = src.proceeds;
  put($("needs-h"), (needs.length ? '<b class="nn" data-gloss="count:waits">' + needs.length + '</b> Needs you' : "Nothing needs you" + lastPass()));
  keyed($("nq"), "li", "nr", needs.map(function (w) { return { key: needId(w), html: needRow(w, false) }; }));
  $("nq").hidden = !needs.length;
  keyed($("np"), "li", "nr", soon.map(function (w) { return { key: needId(w), html: needRow(w, true) }; }));
  $("np-w").hidden = !soon.length;
  var next = soon.map(function (w) { return ms(w.due); }).filter(function (v) { return v != null; });
  put($("np-h"), "Will proceed on default: " + soon.length + (next.length ? ", the first in " + short(Math.max(0, Math.min.apply(null, next) - NOW)) : ""));
  put($("nsaid"), saidRows());
  put($("nx"), !PROJECT ? "" : added("you").map(function (a) {
    return '<button type="button" class="tok sans faint" data-open="' + esc(a.said.open || a.from) + '" aria-description="' + esc(a.said.n + " " + a.said.label) + ': open it"><b' + (a.said.count ? ' data-gloss="' + esc(a.said.count) + '"' : "") + '>' + esc(a.said.n) + '</b> <span class="lb">' + esc(a.said.label) + '</span></button>';
  }).join(" "));
  ticks();
}
function startAccept(id) {
  var w = (PROJECT ? S : STACK).proceeds.concat((PROJECT ? S : STACK).needs).filter(function (x) { return needId(x) === id; })[0];
  if (!w || ACCEPTING[id] || !inlineAccept(w)) return;
  SAID = [];
  var now = ACCEPTING[id] = { left: NEEDS_FOR, sent: false, w: w };
  now.timer = setInterval(function () {
    now.left -= 1;
    leaveAccepts();
    if (!ACCEPTING[id]) return;
    if (now.left > 0) { ticks(); return; }
    clearInterval(now.timer);
    sendAccept(id);
  }, 1000);
  renderNeeds();
  var undo = document.querySelector('#needs [data-undo="' + CSS.escape(id) + '"]'); if (undo) undo.focus();
}
function undoAccept(id) {
  var now = ACCEPTING[id]; if (!now || now.sent) return;
  clearInterval(now.timer); delete ACCEPTING[id];
  renderNeeds();
  var back = document.querySelector('#needs [data-accept="' + CSS.escape(id) + '"]'); if (back) back.focus();
}
function sendAccept(id) {
  var now = ACCEPTING[id], w = now.w;
  now.sent = true; renderNeeds();
  function over(say, bad) { delete ACCEPTING[id]; SAID = [{ say: say, bad: bad }]; renderNeeds(); }
  if (w.item) {
    ask("/steer?project=" + encodeURIComponent(w.project), { item: w.item, action: "approve", words: "", seen_event: w.seen, confirm: false }).then(function (r) {
      over(r && r.say ? r.say : r && r.error ? "The server refused the approval: " + r.error + "." : LOST_APPROVAL, !r || r.http !== 200);
      poll(true);
    }, function () { over(LOST_APPROVAL, true); });
    return;
  }
  ask("/answer?project=" + encodeURIComponent(w.project), { numbers: [Number(needNumber(w))] }).then(function (r) {
    if (!r || !r.closed) { over(r && r.error ? "The server refused the write: " + r.error + "." : UNKNOWN_END, true); return; }
    var one = r.closed[0] || r.refused[0];
    over(one ? one.say : UNKNOWN_END, !one || !r.closed.length || !(one.sent || one.keeps));
    poll(true);
  }, function () { over(UNKNOWN_END, true); });
}
document.addEventListener("click", function (e) {
  var a = e.target.closest("[data-accept]"), u = e.target.closest("[data-undo]");
  if (a) startAccept(a.getAttribute("data-accept"));
  else if (u) undoAccept(u.getAttribute("data-undo"));
});
function ticked() { return gates().map(function (w) { return w.number; }).filter(function (n) { return TICKED_GATES[n]; }); }
function batchFoot() {
  var ns = ticked(), one = ns.length === 1;
  return (ns.length ? '<div class="will none">Closes ' + (one ? "question " : "questions ") + esc(names(ns)) + ' with ' + (one ? "its default" : "their defaults") + '. Nothing is sent to any thread.</div>'
    : '<p class="src" style="margin:10px 0 0">Tick the gates to close with their defaults. Another option, or your own words, is a gate opened by itself.</p>') +
    bad(BATCH.error) + '<button type="button" class="confirm accept" id="bsend"' + (ns.length && !BATCH.busy ? "" : " disabled") + '>Accept the default for ' + ns.length + '</button>';
}
function gateRow(w) {
  var can = w.answerable;
  return (can ? '<label class="tick"><input type="checkbox" data-tick="' + esc(w.number) + '"' + (TICKED_GATES[w.number] ? " checked" : "") + ' aria-label="Tick question ' + esc(w.number) + ' to close it with its default"></label>' : "") +
    '<span class="n" data-gloss="count:question">' + esc(w.number) + '</span> <b>' + esc(w.question) + '</b>' + (w.home ? ' <span class="chip plain">' + esc(w.home) + '</span>' : "") + ' ' + ageChip(w.since, "user") +
    (w.options.length ? '<br><span class="olist">' + w.options.map(function (o) { return '<span class="oc' + (o["default"] ? " tk" : "") + '">' + esc(o.name) + (o["default"] ? " (taken)" : "") + '</span>'; }).join("") + '</span>' : '<br>') +
    '<span class="tag">If you do not answer</span> ' + esc(w["default"] || "nothing is said") + '<br>' +
    (can ? openBtn("gate:" + w.number, "Open question " + w.number) : '<span class="src">It lives in a home\'s <code>gates.md</code>, and cannot be answered here.</span>');
}
function sendBatch() {
  var ns = ticked(); if (!ns.length || BATCH.busy) return;
  function draw() { if ($("bfoot")) $("bfoot").innerHTML = batchFoot(); }
  BATCH = { busy: true, error: "" }; draw();
  send({ numbers: ns.map(Number) }, function (why) { BATCH = { busy: false, error: why }; draw(); });
}
function dYou(arg) {
  var hit = arg.split(":")[0], named = arg.slice(hit.length + 1), n = S.waiting.length, h = head("Waits on you", plural(n, "thing waits", "things wait") + " on you"), can = gates();
  h += '<p class="src" style="margin-top:15px">From <code>waiting-on-user.json</code>, the one list a pass writes. A gate that jbus holds is answered here. A work item is approved and steered in its own drawer.</p>';
  S.kinds.forEach(function (kind) {
    var k = kind.name, items = waits(k);
    if (!items.length && (k === "hold" || k === "config")) return;
    h += '<h3' + (k === hit ? ' class="hit"' : "") + '>' + items.length + " " + kind.label + '</h3>' +
      (k === "gate" && can.length ? '<p style="margin:0 0 5px"><button type="button" class="btn" id="tickall">Tick all ' + can.length + ' that can be answered here</button></p>' : "") +
      (items.length ? '<ul class="clean rows">' + items.map(function (w) {
      var here = k === hit && (!named || named === w.slug || named === w.number);
      if (k === "gate") return '<li' + (here ? ' class="hit"' : "") + '>' + gateRow(w) + '</li>';
      var body = (w.slug ? taskBtn(w.slug) + " " : "") + (k === "hold" ? link(w.url, "#" + w.number) + " " : "");
      return '<li' + (here ? ' class="hit"' : "") + '>' + body + ' ' + ageChip(w.since, "user") +
        '<br>' + (k === "approve" ? '<code>' + esc(w.line) + '</code>' : esc(w.line)) +
        (w.unblocks && w.unblocks.length ? '<br><span class="tag">Unblocks</span> ' + w.unblocks.map(taskBtn).join(" ") : "") + '</li>';
    }).join("") + '</ul>' : '<p class="src">None.</p>') +
      (k === "gate" && can.length ? '<div id="bfoot">' + batchFoot() + '</div>' : "") +
      (k === "gate" ? '<p class="src" style="margin:10px 0 0">' + openBtn("words:answer", "The questions you answered, in Your words") + '</p>' : "");
  });
  var shut = S.gates.filter(function (g) { return !g.open; });
  if (shut.length) h += '<h3>' + plural(shut.length, "gate", "gates") + ' not open</h3><ul class="clean rows">' + shut.map(function (g) { return '<li><span class="n zero" data-gloss="count:question">' + esc(g.number) + '</span> ' + esc(g.question) + '<br><span class="src">' + esc(g.status) + '</span></li>'; }).join("") + '</ul>';
  return h;
}
document.addEventListener("click", function (e) {
  if (e.target.closest("#bsend")) { sendBatch(); return; }
  if (!e.target.closest("#tickall")) return;
  var every = gates().every(function (w) { return TICKED_GATES[w.number]; });
  gates().forEach(function (w) { TICKED_GATES[w.number] = !every; });
  $("dw").querySelectorAll("[data-tick]").forEach(function (x) { x.checked = !every; });
  $("bfoot").innerHTML = batchFoot();
});
document.addEventListener("change", function (e) {
  var x = e.target.closest && e.target.closest("[data-tick]"); if (!x) return;
  TICKED_GATES[x.getAttribute("data-tick")] = x.checked;
  $("bfoot").innerHTML = batchFoot();
});
panel({ reads: "mixed", drawer: dYou, draw: renderNeeds });
