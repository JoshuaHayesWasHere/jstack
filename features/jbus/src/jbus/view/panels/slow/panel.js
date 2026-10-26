var SLOW_NAME = { runner: "Runner", review: "Review", rebase: "Rebase", you: "You" };
var SLOW_SAYS = { runner: "in check", review: "in review", rebase: "to rebase", you: "wait on you" };
/* Whether the reader opened the band (true) or folded it (false), or null where they have not: a redraw keeps what they chose. */
var SLOW_OPEN = null;
document.addEventListener("click", function (e) { var s = e.target.closest && e.target.closest('[data-role="slow"] > summary'); if (s) SLOW_OPEN = !s.parentNode.open; });
(function () {
  var css = document.createElement("style");
  css.textContent =
    ".sl { margin-top: 10px; border: 1.5px solid var(--hair); border-radius: 10px; background: var(--surface); padding: 6px 14px 8px; }" +
    ".sl.op { border-left: 5px solid var(--due); }" +
    ".sl-h { font-size: 17px; font-weight: 400; line-height: 1.35; margin: 0; padding: 2px 0; cursor: pointer; } .sl-h b { font-weight: 800; } .sl[open] .sl-h { margin-bottom: 6px; }" +
    ".sl-s { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }" +
    ".sl-c { min-width: 0; border-top: 3px solid var(--hair); padding-top: 3px; }" +
    ".sl-c.busy { border-top-color: var(--due); }" +
    ".sl-c a, .sl-c span.sl-in { display: grid; color: var(--ink); text-decoration: none; min-height: 40px; }" +
    ".sl-n { font-size: 13px; letter-spacing: .06em; text-transform: uppercase; color: var(--ink-2); }" +
    ".sl-v { font-size: 17px; overflow-wrap: anywhere; } .sl-v b { font-size: 22px; line-height: 1.1; }" +
    ".sl-a { font-size: 15px; color: var(--ink-2); overflow-wrap: anywhere; }" +
    ".sl-m { margin: 8px 0 0; font-size: 15px; color: var(--ink-2); display: flex; flex-wrap: wrap; gap: 2px 16px; } .sl-m b { color: var(--ink); }" +
    "@media (max-width: 640px) { .sl { padding: 6px 10px 8px; } .sl-s { grid-template-columns: repeat(2, minmax(0, 1fr)); } .sl-c a, .sl-c span.sl-in, .sl-h { min-height: 44px; } .sl-h { font-size: 16px; padding: 9px 0; } }";
  document.head.appendChild(css);
})();
function slowRoom() { return PROJECT ? S && S.room : STACK && STACK.machine.room; }
function slowWait(s) { var v = s.oldest && ms(s.oldest.since); return v == null ? null : NOW - v; }
function slowTop(stages) {
  return stages.filter(function (s) { return s.rows; }).sort(function (a, b) { return (slowWait(b) || 0) - (slowWait(a) || 0); })[0] || null;
}
function slowRows(s) { return s.key === "you" ? plural(s.rows, "waits", "wait") + " on you" : plural(s.rows, "row", "rows") + " " + SLOW_SAYS[s.key]; }
function slowAge(s) { var w = slowWait(s); return w == null ? (s.rows ? "no time kept" : "none") : "oldest " + short(w); }
function slowRunning(s) { return s.running ? ", " + s.running + " running" : ""; }
function slowSlots(t) {
  if (!t.total) return "Test slots: <b>not known</b>";
  if (!t.read) return "Test slots: <b>not known</b> of " + t.total;
  return "Test slots: <b>" + t.used + " of " + t.total + "</b> held" + (t.waiting ? ", " + plural(t.waiting, "thread waits", "threads wait") + (ms(t.since) == null ? "" : " (oldest " + short(NOW - ms(t.since)) + ")") : "");
}
function slowLoad(r) {
  if (!r) return "Load: <b>not known</b>";
  return "Load: <b>" + (r.load[0] == null ? "not known" : r.load[0] + " of " + r.cores + " cores") + "</b>" + (r.answer === "wait" ? ", no room: " + esc(r.why) : r.answer === "go" ? ", room to launch" : "");
}
function slowSay(g) {
  var top = slowTop(g.stages), t = g.slots, full = t.read && t.total && t.used >= t.total;
  var bits = [];
  if (top) bits.push("<b>" + esc(slowRows(top)) + "</b>" + (slowWait(top) == null ? "" : ", the oldest for " + short(slowWait(top))));
  if (full) bits.push("<b>every test slot is held</b>");
  return bits.length ? "Slowed by " + bits.join(", and ") + "." : "Nothing waits at a stage, and a test slot is free.";
}
function slowCell(s) {
  var inner = '<span class="sl-n">' + SLOW_NAME[s.key] + '</span><span class="sl-v"><b>' + s.rows + '</b> ' + esc(SLOW_SAYS[s.key]) + esc(slowRunning(s)) + '</span><span class="sl-a">' + esc(slowAge(s)) + '</span>';
  var to = s.oldest && s.oldest.open;
  return '<li class="sl-c' + (s.rows ? " busy" : "") + '" data-stage="' + esc(s.key) + '">' + (to ? '<a href="' + esc(linkOf(to)) + '" title="The oldest: ' + esc(s.oldest.what) + (STACK && STACK.projects.length > 1 ? ' in ' + esc(s.oldest.project) : "") + '">' + inner + '</a>' : '<span class="sl-in">' + inner + '</span>') + '</li>';
}
function slowBody(g) {
  return '<ul class="sl-s">' + g.stages.map(slowCell).join("") + '</ul>' +
    '<p class="sl-m"><span>' + slowSlots(g.slots) + '</span><span>' + slowLoad(slowRoom()) + '</span></p>';
}
function slowBusy(g) { return g.stages.some(function (s) { return s.rows; }) || (g.slots.read && g.slots.total && g.slots.used >= g.slots.total); }
function slowBand(g) {
  var open = SLOW_OPEN == null ? !window.matchMedia("(max-width: 640px)").matches : SLOW_OPEN;
  return '<details class="sl' + (slowBusy(g) ? " op" : "") + '" data-role="slow"' + (open ? " open" : "") + '><summary class="sl-h">' + slowSay(g) + '</summary>' + slowBody(g) + '</details>';
}
function slowCard() { return STACK && STACK.slow ? slowBand(STACK.slow) : ""; }
function dSlow(arg, data) {
  var g = data.slow;
  return head("The line", "What slows us") + '<div class="now' + (slowBusy(g) ? " e-op" : "") + '"><span class="tag">Now</span><span class="big">' + slowSay(g) + '</span></div>' + slowBody(g) +
    '<p class="src" style="margin-top:10px">A row waits at a stage from when it came to it. Runner is the step Check: a row waits for a runner, then for its check to end, and running counts the checks that started. You is what Needs you lists. Test slots are the full lane of <code>jgauge test-slot</code>, where a thread runs its check command, read from the kernel&#39;s list of held locks. Load is the room&#39;s.</p>';
}
panel({
  title: "What slows us",
  drawer: dSlow,
  card: slowCard,
  adds: {
    task: function (t) { return t.step === "check" || t.step === "rebase" || t.who === "rev" ? openBtn("slow", "What slows the line") : ""; }
  },
  gloss: { slow: ["What slows us", "How many rows wait at each stage, runner, review, rebase and you, with how long the oldest has waited, how many of the machine's test slots are held, and the machine's load. Its first line names the stage whose oldest row has waited longest."] }
});
