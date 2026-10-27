var LABEL = { accept: "Accept the default", option: "Send this option", words: "Send my words" };
function way(w) { return OPEN_GATE.words.trim() ? "words" : OPEN_GATE.opt === taken(w) ? "accept" : "option"; }
function gateFoot(w) {
  var k = way(w), words = OPEN_GATE.words.trim(), named = OPEN_GATE.opt >= 0 && OPEN_GATE.opt !== taken(w) ? w.options[OPEN_GATE.opt].name : "";
  var say = k === "accept" ? '<div class="will none"><b>Nothing is sent.</b> The default stands and question ' + esc(w.number) + ' closes.</div>'
    : '<div class="will"><b>' + (w.thread ? "Goes at once to " + esc(whose(w)) : "Recorded now, and sent once a brief names the thread of " + esc(w.slug)) + ':</b><br>&quot;' + esc([named, words].filter(Boolean).join(". ")) + '&quot;' + (w.undo ? ', with how to undo the default: ' + esc(w.undo) : "") + '</div>';
  return say + bad(OPEN_GATE.error) + '<button type="button" class="confirm ' + k + '" id="gsend"' + (OPEN_GATE.busy ? " disabled" : "") + '>' + LABEL[k] + '</button>';
}
function dGate(n) {
  var w = gateOf(n); if (!w) return null;
  OPEN_GATE = { n: w.number, w: w, opt: taken(w), words: OPEN_GATE && OPEN_GATE.n === w.number ? OPEN_GATE.words : "", error: "", busy: false };
  var t = TASK[w.slug] || ENDED[w.slug], h = head("Gate", "Question " + w.number);
  h += '<p style="margin-top:15px"><b>' + esc(w.question) + '</b></p>' +
    '<dl class="kv"><dt>Asked by</dt><dd>' + esc(w.role || "a thread") + ' ' + taskBtn(w.slug) + (t && t.pr ? ' <code>' + esc(t.pr) + '</code>' : "") + ' ' + ageChip(w.since, "user") + '</dd>' +
    (w.context ? '<dt>Context</dt><dd>' + esc(w.context) + '</dd>' : "") +
    '<dt>Default taken</dt><dd>' + esc(w["default"] || "nothing is said") + '</dd><dt>Built on</dt><dd>' + esc(w.built_on || "nothing is said") + '</dd><dt>To undo</dt><dd>' + esc(w.undo || "nothing is said") + '</dd></dl>';
  h += w.options.length ? '<h3>' + w.options.length + ' options the thread proposed</h3><div class="opts">' + w.options.map(function (o, i) {
    return '<button type="button" class="opt" data-opt="' + i + '" aria-pressed="' + (OPEN_GATE.opt === i) + '"><b>' + esc(o.name) + '</b>' + (o["default"] ? ' <i class="om tk">taken as default</i>' : "") + (o.recommended ? ' <i class="om rc">the thread recommends</i>' : "") + '<small>' + esc(o.follows) + '</small></button>';
  }).join("") + '</div>' : '<h3>Options</h3><p class="src">None are on record for this gate. Accept the default, or answer in your own words.</p>';
  h += '<textarea id="gwords" aria-label="Your own words" placeholder="Or answer in your own words">' + esc(OPEN_GATE.words) + '</textarea><div id="gfoot">' + gateFoot(w) + '</div>';
  if (t && t.pr) h += ghBox(w.slug);
  return h;
}
function sendGate() {
  var w = OPEN_GATE && OPEN_GATE.w; if (!w || OPEN_GATE.busy) return;
  var body = { numbers: [Number(w.number)] }, words = OPEN_GATE.words.trim(), mine = OPEN_GATE;
  if (OPEN_GATE.opt >= 0) body.option = w.options[OPEN_GATE.opt].name;
  if (words) body.words = words;
  function draw() { if (OPEN_GATE === mine && $("gfoot")) $("gfoot").innerHTML = gateFoot(w); }
  OPEN_GATE.busy = true; OPEN_GATE.error = ""; draw();
  send(body, function (why) { mine.busy = false; mine.error = why; draw(); });
}
document.addEventListener("click", function (e) {
  var o = e.target.closest("[data-opt]");
  if (o && OPEN_GATE) {
    OPEN_GATE.opt = +o.getAttribute("data-opt");
    $("dw").querySelectorAll("[data-opt]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === o)); });
    $("gfoot").innerHTML = gateFoot(OPEN_GATE.w);
    return;
  }
  if (e.target.closest("#gsend")) sendGate();
});
document.addEventListener("input", function (e) {
  if (e.target.id !== "gwords" || !OPEN_GATE) return;
  OPEN_GATE.words = e.target.value;
  $("gfoot").innerHTML = gateFoot(OPEN_GATE.w);
});
panel({ reads: "mixed", drawer: dGate });
