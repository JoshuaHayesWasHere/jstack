/* One gate that jbus holds: the drawer that answers it, with an option or your own words. */
var LABEL = { accept: "Accept the default", option: "Send this option", words: "Send my words" };
function way(w) { return GATE.words.trim() ? "words" : GATE.opt === taken(w) ? "accept" : "option"; }
function gateFoot(w) {
  var k = way(w), words = GATE.words.trim(), named = GATE.opt >= 0 && GATE.opt !== taken(w) ? w.options[GATE.opt].name : "";
  var say = k === "accept" ? '<div class="will none"><b>Nothing is sent.</b> The default stands and question ' + esc(w.number) + ' closes.</div>'
    : '<div class="will"><b>' + (w.thread ? "Goes at once to " + esc(whose(w)) : "Recorded now, and sent once a brief names the thread of " + esc(w.slug)) + ':</b><br>&quot;' + esc([named, words].filter(Boolean).join(". ")) + '&quot;' + (w.undo ? ', with how to undo the default: ' + esc(w.undo) : "") + '</div>';
  return say + bad(GATE.error) + '<button type="button" class="confirm ' + k + '" id="gsend"' + (GATE.busy ? " disabled" : "") + '>' + LABEL[k] + '</button>';
}
function dGate(n) {
  var w = gateOf(n); if (!w) return null;
  GATE = { n: w.number, w: w, opt: taken(w), words: GATE && GATE.n === w.number ? GATE.words : "", error: "", busy: false };
  var t = TASK[w.slug] || ENDED[w.slug], h = head("Gate", "Question " + w.number);
  h += '<p style="margin-top:15px"><b>' + esc(w.question) + '</b></p>' +
    '<dl class="kv"><dt>Asked by</dt><dd>' + esc(w.role || "a thread") + ' ' + taskBtn(w.slug) + (t && t.pr ? ' <code>' + esc(t.pr) + '</code>' : "") + ' ' + ageChip(w.since, "user") + '</dd>' +
    (w.context ? '<dt>Context</dt><dd>' + esc(w.context) + '</dd>' : "") +
    '<dt>Default taken</dt><dd>' + esc(w["default"] || "nothing is said") + '</dd><dt>Built on</dt><dd>' + esc(w.built_on || "nothing is said") + '</dd><dt>To undo</dt><dd>' + esc(w.undo || "nothing is said") + '</dd></dl>';
  h += w.options.length ? '<h3>' + w.options.length + ' options the thread proposed</h3><div class="opts">' + w.options.map(function (o, i) {
    return '<button type="button" class="opt" data-opt="' + i + '" aria-pressed="' + (GATE.opt === i) + '"><b>' + esc(o.name) + '</b>' + (o["default"] ? ' <i class="om tk">taken as default</i>' : "") + (o.recommended ? ' <i class="om rc">the thread recommends</i>' : "") + '<small>' + esc(o.follows) + '</small></button>';
  }).join("") + '</div>' : '<h3>Options</h3><p class="src">None are on record for this gate. Accept the default, or answer in your own words.</p>';
  h += '<textarea id="gwords" aria-label="Your own words" placeholder="Or steer in your own words">' + esc(GATE.words) + '</textarea><div id="gfoot">' + gateFoot(w) + '</div>';
  if (t && t.pr) h += ghBox(w.slug);
  return h;
}
function sendGate() {
  var w = GATE && GATE.w; if (!w || GATE.busy) return;
  var body = { numbers: [Number(w.number)] }, words = GATE.words.trim(), mine = GATE;
  if (GATE.opt >= 0) body.option = w.options[GATE.opt].name;
  if (words) body.words = words;
  function draw() { if (GATE === mine && $("gfoot")) $("gfoot").innerHTML = gateFoot(w); }
  GATE.busy = true; GATE.error = ""; draw();
  send(body, function (why) { mine.busy = false; mine.error = why; draw(); });
}
document.addEventListener("click", function (e) {
  var o = e.target.closest("[data-opt]");
  if (o && GATE) {
    GATE.opt = +o.getAttribute("data-opt");
    $("dw").querySelectorAll("[data-opt]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === o)); });
    $("gfoot").innerHTML = gateFoot(GATE.w);
    return;
  }
  if (e.target.closest("#gsend")) sendGate();
});
document.addEventListener("input", function (e) {
  if (e.target.id !== "gwords" || !GATE) return;
  GATE.words = e.target.value;
  $("gfoot").innerHTML = gateFoot(GATE.w);
});
panel({ drawer: dGate });
