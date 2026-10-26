/* Find: a box over every row of the queue. Each word typed must be in the row's slug or the
   title of its brief, and each match gives its stage, its pull request and when it merged.
   `find:<words>` opens the drawer with those words in the box. */
var FOUND = [], FIND_MAX = 50;
function findRows(words) {
  var want = words.toLowerCase().split(/\s+/).filter(Boolean);
  if (!want.length) return [];
  return FOUND.filter(function (r) {
    var hay = (r.slug + " " + r.title).toLowerCase();
    return want.every(function (w) { return hay.indexOf(w) >= 0; });
  });
}
function findSaid(words, hits) {
  if (!words.trim()) return "Type part of a slug or a title. " + plural(FOUND.length, "row", "rows") + " to look in.";
  if (!hits.length) return "No row has " + words.trim() + " in its slug or its title.";
  return plural(hits.length, "match", "matches") + (hits.length > FIND_MAX ? ", the first " + FIND_MAX + " shown: type more to narrow it" : "") + ".";
}
function findList(hits) {
  return '<ul class="clean rows">' + hits.slice(0, FIND_MAX).map(function (r) {
    var at = ms(r.merged);
    return '<li>' + taskBtn(r.slug) + (r.title ? '<br><span class="src">' + esc(r.title) + '</span>' : "") + '<br>' +
      '<span class="chip ' + (at == null ? "plain" : "ok") + '">' + esc(r.stage || "unknown") + '</span> ' +
      (r.pr ? '<span class="src">' + esc(r.pr) + '</span> ' : '<span class="src">no pull request</span> ') +
      (at == null ? "" : '<span class="src">merged ' + day(at) + '</span>') + '</li>';
  }).join("") + '</ul>';
}
function dFind(arg, data) {
  FOUND = data.found;
  setTimeout(function () { var q = $("find-q"); if (q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); } });
  return head("Find", "Find a task") +
    '<input type="search" id="find-q" aria-label="Part of a slug or a title" placeholder="Part of a slug or a title" autocomplete="off" spellcheck="false" value="' + esc(arg) + '" style="font:inherit;color:inherit;display:block;width:100%;margin-top:15px;border:1.5px solid var(--line);border-radius:8px;background:var(--canvas);padding:7px 9px;min-height:44px">' +
    findShown(arg, true);
}
function findShown(words, html) {
  var hits = findRows(words), said = findSaid(words, hits), list = findList(hits);
  if (html) return '<p class="src" id="find-n" role="status" style="margin-top:10px">' + esc(said) + '</p><div id="find-l">' + list + '</div>';
  $("find-n").textContent = said; put($("find-l"), list);
}
document.addEventListener("input", function (e) {
  if (e.target.id !== "find-q") return;
  findShown(e.target.value, false);
});
panel({
  title: "Find a task",
  drawer: dFind
});
