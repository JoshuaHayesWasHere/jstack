var GLANCE_MAX = 4;
var GLANCE_TIER = { wrong: "Wrong", yours: "Waits on you" };
(function () {
  var css = document.createElement("style");
  css.textContent =
    ".gl { margin-top: 10px; border: 1.5px solid var(--hair); border-radius: 10px; background: var(--surface); padding: 6px 14px 8px; }" +
    ".gl-h { font-size: 18px; font-weight: 400; line-height: 1.35; margin: 0 0 2px; display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 12px; }" +
    ".gl-word { display: block; font-size: 30px; font-weight: 800; letter-spacing: .04em; line-height: 1.15; color: var(--ink); }" +
    ".gl-word.wrong { color: var(--missed); } .gl-word.yours, .gl-word.stalled { color: var(--due); } .gl-word.moving { color: var(--ok); } .gl-word.rest { color: var(--ink-2); }" +
    ".gl-cause { display: block; overflow-wrap: anywhere; }" +
    ".gl-sub { margin: 2px 0 0; font-size: 15px; color: var(--ink-2); } .gl-sub b { color: var(--ink); }" +
    ".gl-v { flex: 1 1 320px; min-width: 0; } .gl-v b { font-weight: 800; }" +
    ".gl-c { flex: none; display: inline-flex; gap: 10px; font-weight: 700; white-space: nowrap; overflow-wrap: normal; } .gl-c b { font-size: 22px; line-height: 1.1; }" +
    ".gl-cw { color: var(--missed); }" +
    ".gl-since { margin: 0; font-size: 15px; color: var(--ink-2); }" +
    ".gl-t { border-left: 5px solid var(--due); padding-left: 10px; margin: 6px 0 0; }" +
    ".gl-t.wrong { border-left-color: var(--missed); }" +
    ".gl-t h3 { font-size: 13px; letter-spacing: .06em; text-transform: uppercase; color: var(--ink-2); margin: 0; }" +
    ".gl-t ol { list-style: none; margin: 0; padding: 0; }" +
    ".gl-r { display: flex; gap: 4px 14px; align-items: center; justify-content: space-between; padding: 4px 0; border-top: 1px solid var(--hair); }" +
    ".gl-r:first-child { border-top: 0; }" +
    ".gl-b { display: grid; min-width: 0; flex: 1 1 0; line-height: 1.3; }" +
    ".gl-s { font-size: 17px; overflow-wrap: anywhere; } .gl-s code { font-weight: 700; }" +
    ".gl-w { font-size: 15px; color: var(--ink-2); overflow-wrap: anywhere; }" +
    ".gl-r .btn { flex: none; display: inline-flex; align-items: center; min-height: 40px; text-decoration: none; color: var(--ink); }" +
    ".gl-more { margin: 2px 0 0; font-size: 15px; } .gl-more a { color: var(--ink-2); font-weight: 700; }" +
    ".gl-m { margin: 8px 0 0; font-size: 15px; color: var(--ink-2); }" +
    ".gl-m b, .gl-calm b { color: var(--ink); }" +
    ".gl.calm { border-left: 5px solid var(--brand); } .gl.moving { border-left: 5px solid var(--ok); } .gl.yours, .gl.stalled { border-left: 5px solid var(--due); } .gl.wrong { border-left: 5px solid var(--missed); }" +
    ".gl-calm { margin: 2px 0; font-size: 17px; }" +
    "@media (max-width: 640px) { .gl { padding: 6px 10px 8px; } .gl-r .btn { min-height: 44px; } .gl-s { font-size: 16px; } .gl-word { font-size: 24px; } }";
  document.head.appendChild(css);
})();
function glanceAge(t) { var v = ms(t); return v == null ? "no time kept" : ago(t); }
function glanceRow(it) {
  var v = ms(it.since);
  return '<li class="gl-r" data-tier="' + esc(it.tier) + '" data-kind="' + esc(it.kind) + '"><div class="gl-b"><span class="gl-s"><code>' + esc(it.subj) + '</code> ' + esc(it.cause) + '</span>' +
    '<span class="gl-w"' + (v == null ? "" : ' title="Since ' + esc(day(v)) + '"') + '>' + esc(it.where) + ' &middot; ' + esc(glanceAge(it.since)) + '</span></div>' +
    '<a class="btn" href="' + esc(linkOf(it.open)) + '">' + esc(it.verb) + '</a></li>';
}
function glanceTier(tier, items) {
  if (!items.length) return "";
  var shown = items.slice(0, GLANCE_MAX), rest = items.length - shown.length;
  return '<div class="gl-t ' + tier + '"><h3>' + GLANCE_TIER[tier] + '</h3><ol>' + shown.map(glanceRow).join("") + '</ol>' +
    (rest ? '<p class="gl-more"><a href="#/triage">' + rest + ' more in Triage &rsaquo;</a></p>' : "") + '</div>';
}
function glanceWhen(t) { var v = ms(t); return v == null ? "" : NOW - v < 60e3 ? "just now" : short(NOW - v) + " ago"; }
function glanceMoving(it) { return esc(it.cause) + ' &middot; ' + (ms(it.since) == null ? "no pass kept" : "last pass " + glanceWhen(it.since)); }
var GLANCE_KEY = "jbus.since.looked", GLANCE_VISIT = null;
try { localStorage.removeItem("jbus.glance.looked"); } catch (e) {}
function glanceStamp() { try { return Number(localStorage.getItem(GLANCE_KEY)) || null; } catch (e) { return null; } }
function glanceShown() { return document.visibilityState !== "hidden"; }
var GLANCE_WAS = glanceStamp();
document.addEventListener("visibilitychange", function () { if (!glanceShown()) GLANCE_VISIT = null; else if (!GLANCE_VISIT) GLANCE_WAS = glanceStamp(); });
var GLANCE_WORD = {
  "CANNOT SEE": ["wrong", "verdict-cannot-see"],
  "HELD BY YOU": ["yours", "verdict-held"],
  "STALLED": ["stalled", "verdict-stalled"],
  "MOVING": ["moving", "verdict-moving"],
  "AT REST": ["rest", "verdict-rest"]
};
function glanceTone(v) { return (GLANCE_WORD[v.word] || [""])[0]; }
function glanceWord(v) {
  var w = GLANCE_WORD[v.word] || ["", ""];
  return '<span class="gl-word ' + w[0] + '" data-role="verdict-word" data-word="' + esc(v.word) + '" data-gloss="card:' + w[1] + '">' + esc(v.word) + '</span>';
}
function glanceCause(v) { return '<span class="gl-cause" data-role="verdict-cause">' + esc(v.cause.charAt(0).toUpperCase() + v.cause.slice(1)) + '.</span>'; }
function glanceSub(v) {
  var bits = [];
  if (v.needs) bits.push('<span data-role="verdict-needs"><b>' + v.needs + '</b> ' + (v.needs === 1 ? "needs" : "need") + ' you</span>');
  bits.push(ms(v.last_merge) == null ? "No merge today" : "Last merge " + glanceWhen(v.last_merge) + ", " + v.per_hour + " merges an hour over the last " + v.window + " h");
  if (ms(v.quiet_since) != null) bits.push("Nothing done for " + short(NOW - ms(v.quiet_since)));
  var top = v.top.tier ? ' &middot; ' + (v.top.tier === "wrong" ? "Held by" : "Waits on you:") + ' <code>' + esc(v.top.subj) + '</code> ' + esc(v.top.cause) + (ms(v.top.since) == null ? "" : ', for ' + short(NOW - ms(v.top.since))) : "";
  var said = bits.join(" &middot; ") + (top && v.top.tier !== "wrong" ? '<span class="gl-top">' + top + '</span>' : top);
  return '<p class="gl-sub" data-role="verdict-sub" title="' + said.replace(/<[^>]*>/g, "") + '.">' + said + '.</p>';
}
function glanceSince(g) {
  var visit = GLANCE_VISIT || { was: GLANCE_WAS, at: NOW };
  if (glanceShown()) {
    GLANCE_VISIT = visit;
    try { localStorage.setItem(GLANCE_KEY, String(NOW)); } catch (e) {}
  }
  var was = visit.was, at = visit.at;
  if (was == null || at - was < 60e3) return null;
  function after(t) { var v = ms(t); return v != null && v > was && v <= at; }
  var merged = g.verdict.merges.filter(after).length, wrong = 0, yours = 0, bits = [];
  g.items.forEach(function (it) { if (after(it.since)) { if (it.tier === "wrong") wrong += 1; else if (it.tier === "yours") yours += 1; } });
  if (merged) bits.push(merged + " merged");
  if (wrong) bits.push(wrong + " newly wrong");
  if (yours) bits.push(yours + " new for you");
  return { ago: short(at - was), merged: merged, said: bits.length ? bits.join(", ") : "nothing changed" };
}
function glanceCard() {
  var g = STACK && STACK.glance;
  if (!g) return "";
  var moving = g.items.filter(function (it) { return it.tier === "moving"; })[0], since = glanceSince(g);
  if (g.calm) return '<section class="gl calm ' + glanceTone(g.verdict) + '" data-role="glance" aria-label="At a glance"><h2 class="gl-h">' + glanceWord(g.verdict) + glanceCause(g.verdict) + '</h2>' + glanceSub(g.verdict) +
    '<p class="gl-calm" data-role="calm"><b>All clear:</b> nothing wrong, nothing waits on you. ' + (moving ? glanceMoving(moving) : "") +
    (since && since.merged ? ' &middot; ' + plural(since.merged, "merge", "merges") + ' since you looked' : "") + '</p></section>';
  var wrong = g.items.filter(function (it) { return it.tier === "wrong"; });
  var counts = wrong.length ? '<span class="gl-cw"><b>' + wrong.length + '</b> wrong</span>' : "";
  return '<section class="gl ' + glanceTone(g.verdict) + '" data-role="glance" aria-labelledby="gl-h"><h2 class="gl-h" id="gl-h"><span class="gl-v">' + glanceWord(g.verdict) + glanceCause(g.verdict) + '</span> <span class="gl-c">' + counts + '</span></h2>' + glanceSub(g.verdict) +
    (since ? '<p class="gl-since">Since you looked ' + esc(since.ago) + ' ago: ' + esc(since.said) + '.</p>' : "") +
    glanceTier("wrong", wrong) + '</section>';
}
function glanceTile(key, tag, value, said, tone, link) {
  var inner = '<span class="tag" data-gloss="card:' + key + '">' + tag + '</span><span class="tile-n">' + value + '</span><span class="tile-s">' + said + '</span>';
  return link ? '<a class="tile' + (tone ? " " + tone : "") + '" data-role="' + key + '" href="' + esc(link) + '">' + inner + '</a>'
    : '<div class="tile' + (tone ? " " + tone : "") + '" data-role="' + key + '">' + inner + '</div>';
}
function glanceOpen() {
  if (!STACK) return "";
  var ps = STACK.projects, open = 0, homes = [];
  ps.forEach(function (p) {
    open += p.open;
    p.homes.forEach(function (h) { if (h.open) homes.push((ps.length > 1 ? p.name + " " : "") + (h.name || "root") + " <b>" + h.open + "</b>"); });
  });
  return glanceTile("open", "Open", open, homes.length ? homes.join(" &middot; ") : "nothing open", "");
}
function glanceAct() {
  if (!STACK) return "";
  var last = null, what = "", still = null;
  STACK.projects.forEach(function (p) { var v = ms(p.last && p.last.at); if (v != null && (last == null || v > last)) { last = v; what = p.last.what; } });
  ((STACK.slow || {}).stages || []).forEach(function (s) { var v = s.oldest && ms(s.oldest.since); if (v != null && (!still || v < still.at)) still = { at: v, stage: s, one: s.oldest }; });
  var quiet = STACK.glance && ms(STACK.glance.verdict.quiet_since) != null;
  var said = still ? 'longest still: <a href="' + esc(linkOf(still.one.open)) + '">' + esc(still.one.what) + '</a>, ' + short(NOW - still.at) + (still.stage.key === "you" ? ", waiting on you" : " at " + esc(still.stage.key)) : "no row stands still";
  return '<div class="tile' + (quiet ? " op" : "") + '" data-role="act"' + (what ? ' title="' + esc("The last act: " + what) + '"' : "") + '><span class="tag" data-gloss="card:act">Since last act</span><span class="tile-n">' + (last == null ? "none kept" : short(NOW - last)) + '</span><span class="tile-s">' + said + '</span></div>';
}
function glanceHours(times) {
  var day = new Date(NOW); day.setHours(0, 0, 0, 0);
  var start = day.getTime(), hours = Math.floor((NOW - start) / 36e5) + 1, by = [];
  for (var i = 0; i < hours; i++) by.push(0);
  times.forEach(function (t) { var v = ms(t); if (v != null && v >= start && v <= NOW) by[Math.floor((v - start) / 36e5)] += 1; });
  var top = Math.max.apply(null, by.concat([1]));
  return '<span class="hours" role="img" aria-label="' + esc("Merges in each hour since 00:00: " + by.join(", ")) + '">' + by.map(function (n, h) {
    return '<i' + (n ? "" : ' class="zero"') + ' title="' + p2(h) + ':00, ' + plural(n, "merge", "merges") + '" style="height:' + (n ? Math.max(3, Math.round(28 * n / top)) : 1) + 'px"></i>';
  }).join("") + '</span>';
}
function glanceMerged() {
  var g = STACK && STACK.glance;
  if (!g) return "";
  var v = g.verdict, today = 0, recent = v.merges.filter(function (t) { return NOW - ms(t) <= v.window * 36e5; }).length;
  STACK.projects.forEach(function (p) { today += p.merged; });
  var one = STACK.projects.length === 1 ? href(STACK.projects[0].name, "merged") : "";
  return glanceTile("merged", "Merged today", today, glanceHours(v.merges) + "per hour since 00:00 &middot; <b>" + recent + "</b> in " + v.window + " h", "", one);
}
panel({
  gloss: {
    glance: ["At a glance", "The band at the top of the overview of every project. It leads with the verdict: one word, large, and its exact cause, counted from the board's rows that do not move. Under it: how many things need you, the last merge and the merges an hour over the last 3 hours, and the one thing that holds the work back most. Then what is wrong. What waits on you is the rail's Needs you."],
    "verdict-cannot-see": ["CANNOT SEE", "The first word that holds wins, and this one comes first: jbus is stopped or its passes fail, a source the view reads cannot be read, or CI could not be read. The view cannot say how the work goes, so it says what it cannot see."],
    "verdict-held": ["HELD BY YOU", "The largest group of rows that do not move waits on you: rows in Needs you, or rows behind a head that is. The cause names those groups, then what else slows the work."],
    "verdict-stalled": ["STALLED", "Rows are open, nothing merged in the last 3 hours, and nothing was done in the last 30 minutes. The cause names the largest groups of rows that do not move."],
    "verdict-moving": ["MOVING", "Rows are open and the work goes on: a merge in the last 3 hours, or an act in the last 30 minutes. The cause names what slows it, the largest groups of rows that do not move."],
    "verdict-rest": ["AT REST", "Nothing is open: no row, no scout. Nothing is wrong and nothing waits."],
    open: ["Open", "How many rows are open in every project, and how many of them each home has. The matrix below puts each in its stage."],
    act: ["Since last act", "How long ago anything was last done in any project: a launch, a move, a merge, a line jmerge wrote. Under it, the row that has stood still longest, and where. Amber once nothing was done for 30 minutes, a merge included, even when something merged in the last 3 hours."],
    merged: ["Merged today", "How many rows merged today, as each project counts them, and a bar for each hour since midnight, an hour with none drawn as a hairline. Then how many merged in the last 3 hours."]
  },
  parts: { band: glanceCard, open: glanceOpen, act: glanceAct, merged: glanceMerged }
});
