var NEEDS_FOR = 10, FIRST = 3;
var ACCEPTING = {}, SAID = [], FORM = {}, TYPED = {}, UNFOLDED = false;
var LOST_APPROVAL = "The view server did not answer, so it is not known whether the approval was written. Read the list again before you approve.";
var LOST_LINE = "The view server did not answer, so it is not known whether your line was kept. Read the list again before you send it again.";
var ACT_VERB = { answer: "Answer", approve: "Approve", steer: "Steer" };
var ACT_SAYS = { answer: "Sending your answer", approve: "Approving it", steer: "Sending your line" };
document.head.insertAdjacentHTML("beforeend", '<style>' +
  '.nq .nf { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; flex: 1 1 100%; min-width: 0; }' +
  '.nq .nf input { flex: 1 1 220px; min-width: 0; min-height: 40px; font: inherit; font-size: 15px; padding: 4px 10px; border: 1.5px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--ink); }' +
  '.nq .nd { font-size: 15px; color: var(--ink-2); overflow-wrap: anywhere; }' +
  '.nq .nd b { color: var(--ink); font-weight: 600; }' +
  '#nfall { margin: 2px 0 4px; font-size: 15px; color: var(--ink-2); overflow-wrap: anywhere; }' +
  '#nfall b { color: var(--ink); font-weight: 600; }' +
  '.needs.bar #nfall { flex: 1 1 100%; order: 3; margin: 0 0 2px; }' +
  '#nq > .nr[hidden] { display: none; }' +
  '#nfold { margin: 4px 0 0; }' +
  '#nsaid .stl { margin: 8px 0 0; font-size: 15px; color: var(--ink-2); overflow-wrap: anywhere; }' +
  '@media (max-width: 600px) { #nq .na { flex: 1 1 100%; } #nq .na .btn { flex: 1 1 auto; min-height: 44px; } .nq .nf input { min-height: 44px; flex-basis: 100%; } }' +
  '</style>');
function needId(w) { return w.project + "/" + w.key; }
function needNumber(w) { return w.answerable ? name(w.open.split("/").pop()) : ""; }
function needLink(w) { var at = parse(w.open); return href(at.project, at.target); }
function inlineAccept(w) { return (w.answerable && w.verb === "Accept default") || (!!w.item && !!PROJECT); }
function acts(w) { return w.act === "answer" ? w.answerable : w.act === "approve" ? (!!w.item || !!w.sha) : w.act === "steer"; }
function typed(w) { return !!(w.act === "steer" || (w.act === "answer" && FORM[needId(w)])); }
function saysSlug(line, slug) { return (" " + line + " ").split(/[^\w.-]+/).indexOf(slug) >= 0; }
function oneList(src) {
  return src.needs.concat(src.proceeds).slice().sort(function (a, b) {
    var x = ms(a.since), y = ms(b.since);
    return x == null ? (y == null ? 0 : 1) : y == null ? -1 : x - y;
  });
}
function needMeta(w) {
  var v = ms(w.since), due = ms(w.due), bits = PROJECT ? [] : [esc(w.project)];
  if (w.slug && !saysSlug(w.what, w.slug)) bits.push('<a class="ilk" href="' + esc(href(w.project, "task:" + w.slug)) + '" aria-label="Task ' + esc(w.slug) + ': open it">' + esc(w.slug) + '</a>');
  if (w.item) bits.push('<a class="ilk" href="' + esc(needLink(w)) + '">' + esc(w.item) + '</a>');
  if (w.sha) bits.push("brief <code>" + esc(w.sha) + "</code>");
  bits.push(v == null ? "no time kept" : NOW - v < 60e3 ? "new" : "waiting " + short(NOW - v));
  if (due != null) bits.push(due <= NOW ? "goes ahead now" : "goes ahead in " + short(due - NOW) + ", at " + hm(due));
  if (w.risk !== "reversible") bits.push(esc(w.risk));
  if (w.unblocks.length) bits.push("unblocks " + esc(w.unblocks.slice(0, 2).join(", ")) + (w.unblocks.length > 2 ? " and " + (w.unblocks.length - 2) + " more" : ""));
  return bits.join(" &middot; ");
}
function falls(src) {
  var due = src.proceeds.map(function (w) { return ms(w.due); }).filter(function (v) { return v != null; }), first = due.length ? Math.min.apply(null, due) : null;
  if (first == null) return src.needs.length ? "Nothing falls due on its own: each waits for you." : "";
  return first <= NOW ? "A default is taken now, if you say nothing." : "Nothing falls due before <b>" + hm(first) + "</b>, if you say nothing.";
}
function everywhere(src) {
  var all = STACK ? STACK.needs.length : null;
  return !PROJECT || all == null || all === src.needs.length ? "" : '<b data-gloss="count:waits">' + all + "</b> " + (all === 1 ? "waits" : "wait") + " on you in every project";
}
function fallLine(src) {
  var box = $("nfall"), brief = !PROJECT || !UNFOLDED, due = src.proceeds.some(function (w) { return ms(w.due) != null; });
  if (!box) { $("needs-h").insertAdjacentHTML("afterend", '<p id="nfall"></p>'); box = $("nfall"); }
  var bits = brief ? [due ? falls(src) : ""].filter(Boolean) : [falls(src), everywhere(src)].filter(Boolean);
  box.hidden = !bits.length;
  put(box, bits.join(" &middot; "));
}
function needForm(w) {
  var id = needId(w), keep = w.act === "answer" && w.verb === "Accept default";
  var hint = w.act === "steer" ? "Your line for its home" : keep ? "Your answer, or leave it empty to keep the default" : "Your answer";
  return '<div class="nf"><input type="text" maxlength="600" data-type="' + esc(id) + '" value="' + esc(TYPED[id] || "") + '" placeholder="' + esc(hint) + '" aria-label="' + esc(hint + ": " + w.what) + '">' +
    '<button type="button" class="btn fill" data-accept="' + esc(id) + '">' + (w.act === "steer" ? "Send" : keep && !(TYPED[id] || "").trim() ? "Keep default" : "Send") + '</button>' +
    (w.act === "answer" ? '<button type="button" class="btn" data-shut="' + esc(id) + '">Cancel</button>' : "") + '</div>';
}
function needAct(w) {
  var id = needId(w), now = ACCEPTING[id];
  if (now) return '<span class="acc">' + (now.sent ? saysNow(now) + "&hellip;" : saysNow(now) + ' in <span class="cd"></span> s &middot; <button type="button" class="btn" data-undo="' + esc(id) + '">Undo</button>') + '</span>';
  if (!acts(w)) {
    if (PROJECT) return '<button type="button" class="btn" data-open="' + esc(parse(w.open).target) + '">' + esc(w.verb) + '</button>';
    return '<a class="btn" href="' + esc(needLink(w)) + '">' + esc(w.verb) + '</a>';
  }
  if (w.act === "steer" || FORM[id]) return "";
  if (w.act === "approve") return '<button type="button" class="btn fill" data-accept="' + esc(id) + '" aria-description="Approves ' + esc(w.item || w.slug) + ' in ' + NEEDS_FOR + ' seconds, and it can be undone until then">Approve</button>';
  var form = '<button type="button" class="btn" data-form="' + esc(id) + '" aria-description="Opens a box for your own answer to question ' + esc(needNumber(w)) + '">Answer&hellip;</button>';
  if (w.verb !== "Accept default") return form.replace('class="btn"', 'class="btn fill"');
  return '<button type="button" class="btn fill" data-accept="' + esc(id) + '" aria-description="Accepts the default of question ' + esc(needNumber(w)) + ' in ' + NEEDS_FOR + ' seconds, and it can be undone until then">Accept default</button>' + form;
}
function saysNow(now) { return now.w.act === "answer" && !now.words ? "Accepting the default" : ACT_SAYS[now.w.act]; }
function needRow(w, brief) {
  var act = needAct(w), title = '<a class="nw" href="' + esc(needLink(w)) + '"><b>' + esc(w.what) + '</b></a>';
  if (brief) return '<div class="nb">' + title + '<span class="nd"><b>Goes ahead:</b> ' + esc(w["default"]) + '</span></div>' +
    (act ? '<div class="na">' + act + '</div>' : "") + (typed(w) && !ACCEPTING[needId(w)] ? needForm(w) : "");
  return '<div class="nb">' + title + (w.why ? '<span class="ny">' + esc(w.why) + '</span>' : "") +
    '<span class="nd"><b>If you do nothing:</b> ' + esc(w["default"]) + '</span><span class="nm"' + (ms(w.since) == null ? "" : ' title="Since ' + esc(day(ms(w.since))) + '"') + '>' + needMeta(w) + '</span></div>' +
    (act ? '<div class="na">' + act + '</div>' : "") + (typed(w) && !ACCEPTING[needId(w)] ? needForm(w) : "");
}
function lastPass() {
  var j = jb(), t = j && (ms(j.status && j.status.last_pass) || ms(j.last_end)), said = passWord(t);
  return said ? " &middot; " + said : "";
}
function saidRows() {
  var src = PROJECT ? S : null, steered = src && src.steered ? src.steered : [];
  return SAID.map(function (s) {
    return '<p class="' + (s.bad ? "will bad" : "will none") + '"><b>' + esc(s.say) + '</b>' + (s.undo ? ' <button type="button" class="btn" data-unsay="1">Undo the approval</button>' : "") + '</p>';
  }).join("") + (steered.length ? '<p class="stl">Steered, with its home: ' + steered.map(function (w) { return '<a href="' + esc(needLink(w)) + '">' + esc(w.subj || w.what) + '</a> at ' + esc(hm(ms(w.steered))); }).join(", ") + '. Each comes back here if it changes after your line.</p>' : "");
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
function foldLine(all) {
  var box = $("nfold"), more = all.length - FIRST;
  if (!box) { $("nq").insertAdjacentHTML("afterend", '<p id="nfold"></p>'); box = $("nfold"); }
  box.hidden = more <= 0;
  put(box, more <= 0 ? "" : '<button type="button" class="btn" data-fold="1" aria-controls="nq" aria-expanded="' + UNFOLDED + '">' + (UNFOLDED ? "Show the first " + FIRST : "+" + more + " more need you") + '</button>');
}
function renderNeeds() {
  leaveAccepts();
  var src = PROJECT ? S : STACK, box = $("needs");
  box.hidden = !src || !!NOSUCH;
  if (box.hidden) return;
  var needs = src.needs, soon = src.proceeds, bar = !PROJECT;
  box.classList.toggle("bar", bar);
  $("needs-go").hidden = !bar || !needs.length && !soon.length;
  fallLine(src);
  if (bar) {
    var tail = (needs.length ? ["oldest " + ago(needs[0].since)] : []).concat(soon.length ? [soon.length + (needs.length ? " more" : "") + " on default"] : []);
    put($("needs-h"), (needs.length ? '<b class="nn" data-gloss="count:waits">' + needs.length + '</b> ' + (needs.length === 1 ? "waits" : "wait") + ' on you' : "Nothing waits on you" + lastPass()) + (tail.length ? ' <span class="nm">' + (needs.length ? "" : "&middot; ") + esc(tail.join(" \u00b7 ")) + '</span>' : ""));
    keyed($("nq"), "li", "nr", []);
    $("nq").hidden = true;
    if ($("nfold")) $("nfold").hidden = true;
    put($("nsaid"), saidRows());
    put($("nx"), "");
    return;
  }
  var all = oneList(src), focus = document.activeElement, at = focus && focus.getAttribute && focus.getAttribute("data-type"), caret = at ? focus.selectionStart : 0;
  put($("needs-h"), (needs.length ? '<b class="nn" data-gloss="count:waits">' + needs.length + '</b> Needs you' : "Nothing needs you" + lastPass()) + (soon.length ? ' <span class="nm">&middot; ' + soon.length + (soon.length === 1 ? " goes" : " go") + ' ahead on ' + (soon.length === 1 ? "its" : "their") + ' default</span>' : ""));
  var folded = !UNFOLDED && all.length > FIRST;
  keyed($("nq"), "li", "nr", all.map(function (w) { return { key: needId(w), html: needRow(w, !UNFOLDED) }; }));
  [].forEach.call($("nq").children, function (li, n) { li.hidden = folded && n >= FIRST && !ACCEPTING[li.getAttribute("data-key")]; });
  $("nq").hidden = !all.length;
  foldLine(all);
  put($("nsaid"), saidRows());
  put($("nx"), !PROJECT ? "" : added("you").map(function (a) {
    return '<button type="button" class="tok sans faint" data-open="' + esc(a.said.open || a.from) + '" aria-description="' + esc(a.said.n + " " + a.said.label) + ': open it"><b' + (a.said.count ? ' data-gloss="' + esc(a.said.count) + '"' : "") + '>' + esc(a.said.n) + '</b> <span class="lb">' + esc(a.said.label) + '</span></button>';
  }).join(" "));
  if (at) { var back = document.querySelector('#needs [data-type="' + CSS.escape(at) + '"]'); if (back && back !== document.activeElement) { back.focus(); back.setSelectionRange(caret, caret); } }
  ticks();
}
function findNeed(id) { var src = PROJECT ? S : STACK; return src.proceeds.concat(src.needs).filter(function (x) { return needId(x) === id; })[0]; }
function startAccept(id) {
  var w = findNeed(id);
  if (!w || ACCEPTING[id] || !acts(w)) return;
  var words = (TYPED[id] || "").trim();
  if (w.act === "steer" && !words) { SAID = [{ say: "Write the line for its home first.", bad: true }]; renderNeeds(); return; }
  if (w.act === "answer" && !words && w.verb !== "Accept default") { SAID = [{ say: "This question has no default to keep: write your answer first.", bad: true }]; renderNeeds(); return; }
  SAID = [];
  var now = ACCEPTING[id] = { left: NEEDS_FOR, sent: false, w: w, words: words };
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
  var now = ACCEPTING[id], w = now.w, here = "?project=" + encodeURIComponent(w.project);
  now.sent = true; renderNeeds();
  function over(say, bad, undo) { delete ACCEPTING[id]; delete FORM[id]; if (!bad) delete TYPED[id]; SAID = [{ say: say, bad: bad, undo: undo }]; renderNeeds(); }
  function told(r, lost) { return r && r.say ? r.say : r && r.error ? "The server refused it: " + r.error + "." : lost; }
  if (w.act === "approve" && w.item) {
    ask("/steer" + here, { item: w.item, action: "approve", words: "", seen_event: w.seen, confirm: false }).then(function (r) {
      over(told(r, LOST_APPROVAL), !r || r.http !== 200);
      poll(true);
    }, function () { over(LOST_APPROVAL, true); });
    return;
  }
  if (w.act === "approve") {
    ask("/panel/you/approve" + here, { slug: w.slug, sha: w.sha }).then(function (r) {
      var ok = r && r.http === 200;
      over(told(r, LOST_APPROVAL), !ok, ok ? { project: w.project, slug: w.slug, word: r.word } : null);
      poll(true);
    }, function () { over(LOST_APPROVAL, true); });
    return;
  }
  if (w.act === "steer") {
    ask("/panel/you/steer" + here, { subj: w.subj, words: now.words }).then(function (r) {
      over(told(r, LOST_LINE), !r || r.http !== 200);
      poll(true);
    }, function () { over(LOST_LINE, true); });
    return;
  }
  ask("/answer" + here, now.words ? { numbers: [Number(needNumber(w))], words: now.words } : { numbers: [Number(needNumber(w))] }).then(function (r) {
    if (!r || !r.closed) { over(r && r.error ? "The server refused the write: " + r.error + "." : UNKNOWN_END, true); return; }
    var one = r.closed[0] || r.refused[0];
    over(one ? one.say : UNKNOWN_END, !one || !r.closed.length || !(one.sent || one.keeps));
    poll(true);
  }, function () { over(UNKNOWN_END, true); });
}
function unsay() {
  var s = SAID[0], u = s && s.undo; if (!u) return;
  s.undo = null; renderNeeds();
  ask("/panel/you/hold?project=" + encodeURIComponent(u.project), { slug: u.slug, word: u.word }).then(function (r) {
    SAID = [{ say: r && r.say ? r.say : "The view server did not answer, so it is not known whether the go was taken back.", bad: !r || r.http !== 200 }];
    renderNeeds(); poll(true);
  }, function () { SAID = [{ say: "The view server did not answer, so it is not known whether the go was taken back.", bad: true }]; renderNeeds(); });
}
document.addEventListener("click", function (e) {
  var a = e.target.closest("[data-accept]"), u = e.target.closest("[data-undo]"), f = e.target.closest("[data-form]"), x = e.target.closest("[data-shut]");
  if (a) startAccept(a.getAttribute("data-accept"));
  else if (u) undoAccept(u.getAttribute("data-undo"));
  else if (f) { var id = f.getAttribute("data-form"); FORM[id] = true; renderNeeds(); var box = document.querySelector('#needs [data-type="' + CSS.escape(id) + '"]'); if (box) box.focus(); }
  else if (x) { delete FORM[x.getAttribute("data-shut")]; renderNeeds(); }
  else if (e.target.closest("[data-unsay]")) unsay();
  else if (e.target.closest("[data-fold]")) {
    UNFOLDED = !UNFOLDED; renderNeeds();
    var next = UNFOLDED ? document.querySelector("#nq > .nr:nth-child(" + (FIRST + 1) + ") .nw") : document.querySelector("#nfold [data-fold]"); if (next) next.focus();
  }
});
document.addEventListener("input", function (e) {
  var t = e.target.closest && e.target.closest("[data-type]"); if (!t) return;
  TYPED[t.getAttribute("data-type")] = t.value;
  var w = findNeed(t.getAttribute("data-type")); if (w && w.act === "answer") renderNeeds();
});
document.addEventListener("keydown", function (e) {
  var t = e.key === "Enter" && e.target.closest && e.target.closest("[data-type]"); if (!t) return;
  e.preventDefault(); startAccept(t.getAttribute("data-type"));
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
function approveLine(w) {
  var need = S.needs.filter(function (x) { return x.key === w.key; })[0];
  return (need && need.sha ? "brief <code>" + esc(need.sha) + "</code> &middot; " : "") + '<a href="' + esc(href(PROJECT)) + '">Approve it in Needs you</a>';
}
function dYou(arg) {
  var hit = arg.split(":")[0], named = arg.slice(hit.length + 1), n = S.needs.length, h = head("Waits on you", plural(n, "thing waits", "things wait") + " on you"), can = gates();
  h += '<p class="src" style="margin-top:15px">The count is Needs you, as the band and the triage tab count it. The lists are from <code>waiting-on-user.json</code>, the one list a pass writes, and also hold the gates that go ahead on their default. A gate that jbus holds is answered here. A work item is approved and steered in its own drawer.</p>';
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
        '<br>' + (k === "approve" ? approveLine(w) : esc(w.line)) +
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
