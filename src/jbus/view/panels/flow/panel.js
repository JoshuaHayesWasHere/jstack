/* The queue as a flow: a drawer of the full width, and a row picked in it marks its way. */
function standsAt(slug) {
  var t = TASK[slug] || ENDED[slug];
  if (!t) return slug + " (not in the queue)";
  if (t.who !== "user") return slug + " (" + t.state.name + ")";
  return "your " + ({ asking: "gate on ", unapproved: "approval of " }[t.state.kind] || "word on ") + slug;
}
/* Every queued row and every row that is out, a column for each wave. `pick` is the row
   whose way is marked: what it waits on, back to the rows that are out, and what waits on it. */
function dFlow(pick) {
  var rows = S.tasks.filter(function (t) { return t.step === "queued"; }), out = S.tasks.filter(function (t) { return t.step !== "queued"; });
  var p = TASK[pick], up = {}, down = {}, look = p ? p.blockers.slice() : [];
  while (look.length) { var s = look.pop(); if (!up[s]) { up[s] = true; if (TASK[s]) look = look.concat(TASK[s].blockers); } }
  if (p) p.behind.forEach(function (b) { down[b] = true; });
  var drawn = Object.keys(up).filter(function (s) { return TASK[s]; }).length, rest = Object.keys(up).filter(function (s) { return !TASK[s]; });
  var last = rows.reduce(function (a, t) { return !a || t.wave > a.wave ? t : a; }, null), at = last ? last.slug : "", met = {};
  while (TASK[at] && TASK[at].waits_on && !met[at]) { met[at] = true; at = TASK[at].waits_on; }
  var cols = out.length ? [["Out", out]] : [];
  for (var w = 0; last && w <= last.wave; w++) cols.push([w === 0 ? "Ready" : w === 1 ? "Next" : "Wave " + w, rows.filter(function (t) { return t.wave === w; })]);
  function one(t) {
    var how = !p ? "" : t === p ? "pk" : up[t.slug] ? "up" : down[t.slug] ? "dn" : "dim";
    var says = how === "up" ? ", " + p.slug + " waits on it" : how === "dn" ? ", it waits on " + p.slug : "";
    return '<button type="button" class="fr w-' + esc(t.who) + (t.unconfirmed ? " unc" : "") + (how ? " " + how : "") + '" data-pick="' + esc(t.slug) + '" aria-pressed="' + (t === p) + '" aria-label="' + esc(t.slug + ": " + t.state.name + says + (t.unconfirmed ? ", " + t.unconfirmed.line : "")) + '"><i class="sh"></i><span class="lb">' + esc(t.slug) + '</span>' + (t.blocks ? '<span class="bn" title="' + behind(t.blocks) + '">' + t.blocks + '</span>' : "") + '</button>';
  }
  return head("The line", "The queue as a flow") +
    '<div class="now"><span class="tag">The longest chain</span><span class="big">' + (!last ? "No row is queued" : !last.wave ? "No queued row waits behind another" : (last.wave + 1) + " deep, behind " + esc(standsAt(at))) + '</span>' +
    (last && last.wave ? '<span class="src">It ends at</span> <button type="button" class="linkish" data-pick="' + esc(last.slug) + '">' + esc(last.slug) + '</button>' : "") + '</div>' + note("frozen") +
    (p ? '<p style="margin:12.5px 0 0">' + taskBtn(p.slug) + ' waits on ' + plural(drawn, "row", "rows") + ' here' + (rest.length ? ' and on ' + esc(rest.map(standsAt).join(", ")) : "") + ', and ' + plural(p.blocks, "row waits", "rows wait") + ' on it.</p><div class="key"><span><i class="sw user"></i>it waits on</span><span><i class="sw crew"></i>waits on it</span></div>'
      : '<p class="src" style="margin:12.5px 0 0">Pick a row to mark what it waits on and what waits on it.</p>') +
    '<div class="flow">' + cols.map(function (c) { return '<div class="fc"><h3>' + c[0] + ' <span class="n zero">' + c[1].length + '</span></h3>' + c[1].map(one).join("") + '</div>'; }).join("") + '</div>';
}
document.addEventListener("click", function (e) {
  var k = e.target.closest("[data-pick]");
  if (!k) return;
  var slug = k.getAttribute("data-pick");
  $("dw").innerHTML = dFlow(k.getAttribute("aria-pressed") === "true" ? "" : slug);
  var again = $("dw").querySelector('.fr[data-pick="' + CSS.escape(slug) + '"]'); if (again) again.focus();
});
panel({ drawer: dFlow, wide: true });
