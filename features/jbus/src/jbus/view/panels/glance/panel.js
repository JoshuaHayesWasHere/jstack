var GLANCE_MAX = 4;
var GLANCE_TIER = { wrong: "Wrong", yours: "Waits on you" };
(function () {
  var css = document.createElement("style");
  css.textContent =
    ".gl { margin-top: 10px; border: 1.5px solid var(--hair); border-radius: 10px; background: var(--surface); padding: 6px 14px 8px; }" +
    ".gl-h { font-size: 18px; font-weight: 400; line-height: 1.35; margin: 0 0 2px; display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 12px; }" +
    ".gl-v { flex: 1 1 320px; min-width: 0; } .gl-v b { font-weight: 800; }" +
    ".gl-c { flex: none; display: inline-flex; gap: 10px; font-weight: 700; white-space: nowrap; overflow-wrap: normal; } .gl-c b { font-size: 22px; line-height: 1.1; }" +
    ".gl-cw { color: var(--missed); } .gl-cy { color: var(--due); }" +
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
    ".gl.calm { border-left: 5px solid var(--brand); }" +
    ".gl-calm { margin: 2px 0; font-size: 17px; }" +
    "@media (max-width: 640px) { .gl { padding: 6px 10px 8px; } .gl-r .btn { min-height: 44px; } .gl-s { font-size: 16px; } }";
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
var GLANCE_KEY = "jbus.glance.looked", GLANCE_LOOKED = (function () { try { return Number(localStorage.getItem(GLANCE_KEY)) || null; } catch (e) { return null; } })();
var GLANCE_MOTION = { moving: "Moving.", still: "Not moving.", rest: "At rest." };
function glanceVerdict(v) {
  var said = '<b>' + GLANCE_MOTION[v.motion] + '</b> ' +
    (ms(v.last_merge) == null ? "No merge today." : "Last merge " + glanceWhen(v.last_merge) + ", " + v.per_hour + " merges an hour over the last " + v.window + " h.");
  if (v.top.tier) said += ' ' + (v.top.tier === "wrong" ? "Held by" : "Waits on you:") + ' <code>' + esc(v.top.subj) + '</code> ' + esc(v.top.cause) + (ms(v.top.since) == null ? "" : ', for ' + short(NOW - ms(v.top.since))) + '.';
  return said;
}
function glanceSince(g) {
  var was = GLANCE_LOOKED;
  try { localStorage.setItem(GLANCE_KEY, String(NOW)); } catch (e) {}
  if (was == null || NOW - was < 60e3) return null;
  function after(t) { var v = ms(t); return v != null && v > was; }
  var merged = g.verdict.merges.filter(after).length, wrong = 0, yours = 0, bits = [];
  g.items.forEach(function (it) { if (after(it.since)) { if (it.tier === "wrong") wrong += 1; else if (it.tier === "yours") yours += 1; } });
  if (merged) bits.push(merged + " merged");
  if (wrong) bits.push(wrong + " newly wrong");
  if (yours) bits.push(yours + " new for you");
  return { ago: short(NOW - was), merged: merged, said: bits.length ? bits.join(", ") : "nothing changed" };
}
function glanceCard() {
  var g = STACK && STACK.glance;
  if (!g) return "";
  var moving = g.items.filter(function (it) { return it.tier === "moving"; })[0], since = glanceSince(g);
  if (g.calm) return '<section class="gl calm" data-role="glance" aria-label="At a glance"><p class="gl-calm" data-role="calm"><b>All clear:</b> nothing wrong, nothing waits on you. ' + glanceVerdict(g.verdict) + ' ' + (moving ? glanceMoving(moving) : "") +
    (since && since.merged ? ' &middot; ' + plural(since.merged, "merge", "merges") + ' since you looked' : "") + '</p></section>';
  var wrong = g.items.filter(function (it) { return it.tier === "wrong"; }), yours = g.items.filter(function (it) { return it.tier === "yours"; });
  var counts = [], owed = yours.reduce(function (n, it) { return n + (it.count || 1); }, 0);
  if (wrong.length) counts.push('<span class="gl-cw"><b>' + wrong.length + '</b> wrong</span>');
  if (owed) counts.push('<span class="gl-cy"><b>' + owed + '</b> ' + (owed === 1 ? "waits" : "wait") + ' on you</span>');
  return '<section class="gl" data-role="glance" aria-labelledby="gl-h"><h2 class="gl-h" id="gl-h"><span class="gl-v">' + glanceVerdict(g.verdict) + '</span> <span class="gl-c">' + counts.join(" ") + '</span></h2>' +
    (since ? '<p class="gl-since">Since you looked ' + esc(since.ago) + ' ago: ' + esc(since.said) + '.</p>' : "") +
    glanceTier("wrong", wrong) + glanceTier("yours", yours) +
    (moving ? '<p class="gl-m">' + glanceMoving(moving) + '</p>' : "") + '</section>';
}
panel({
  gloss: { glance: ["At a glance", "The band at the top of the overview of every project. Its first line is the verdict: whether the work moves, with the last merge and the merges an hour over the last 3 hours, and the one thing that holds it back most, with how long. Then what is wrong, then what waits on you, then the open work. With nothing wrong and nothing waiting on you, it is one line."] },
  card: glanceCard
});
