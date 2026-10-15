/* What waits on you: the drawer of the lists, where the gates jbus holds are ticked and
   closed with their defaults. The wait band of the first screen opens it. */
function ticked() { return gates().map(function (w) { return w.number; }).filter(function (n) { return TICK[n]; }); }
function batchFoot() {
  var ns = ticked(), one = ns.length === 1;
  return (ns.length ? '<div class="will none">Closes ' + (one ? "question " : "questions ") + esc(names(ns)) + ' with ' + (one ? "its default" : "their defaults") + '. Nothing is sent to any thread.</div>'
    : '<p class="src" style="margin:10px 0 0">Tick the gates to close with their defaults. Another option, or your own words, is a gate opened by itself.</p>') +
    bad(BATCH.error) + '<button type="button" class="confirm accept" id="bsend"' + (ns.length && !BATCH.busy ? "" : " disabled") + '>Accept the default for ' + ns.length + '</button>';
}
function gateRow(w) {
  var can = w.answerable;
  return (can ? '<label class="tick"><input type="checkbox" data-tick="' + esc(w.number) + '"' + (TICK[w.number] ? " checked" : "") + ' aria-label="Tick question ' + esc(w.number) + ' to close it with its default"></label>' : "") +
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
function dYou(hit) {
  var n = S.waiting.length, h = head("Waits on you", plural(n, "thing waits", "things wait") + " on you"), can = gates();
  h += '<p class="src" style="margin-top:15px">From <code>waiting-on-user.json</code>, the one list a pass writes. A gate that jbus holds is answered here. Nothing else on the page writes, and nothing here approves.</p>' + note("mixed");
  KINDS.forEach(function (k) {
    var items = waits(k);
    if (!items.length && (k === "hold" || k === "config")) return;
    h += '<h3' + (k === hit ? ' class="hit"' : "") + '>' + items.length + " " + KIND[k][1] + '</h3>' +
      (k === "gate" && can.length ? '<p style="margin:0 0 5px"><button type="button" class="btn" id="tickall">Tick all ' + can.length + ' that can be answered here</button></p>' : "") +
      (items.length ? '<ul class="clean rows">' + items.map(function (w) {
      if (k === "gate") return '<li' + (k === hit ? ' class="hit"' : "") + '>' + gateRow(w) + '</li>';
      var body = (w.slug ? taskBtn(w.slug) + " " : "") + (k === "hold" ? link(w.url, "#" + w.number) + " " : "");
      return '<li' + (k === hit ? ' class="hit"' : "") + '>' + body + ' ' + ageChip(w.since, "user") +
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
  var every = gates().every(function (w) { return TICK[w.number]; });
  gates().forEach(function (w) { TICK[w.number] = !every; });
  $("dw").querySelectorAll("[data-tick]").forEach(function (x) { x.checked = !every; });
  $("bfoot").innerHTML = batchFoot();
});
document.addEventListener("change", function (e) {
  var x = e.target.closest && e.target.closest("[data-tick]"); if (!x) return;
  TICK[x.getAttribute("data-tick")] = x.checked;
  $("bfoot").innerHTML = batchFoot();
});
panel({ drawer: dYou });
