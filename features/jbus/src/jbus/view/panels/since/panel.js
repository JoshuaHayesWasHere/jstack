(function () {
  var css = document.createElement("style");
  css.textContent = ".sn { border-left: 5px solid var(--ink-3); padding: 2px 0 2px 10px; margin: 0 0 10px; }" +
    ".sn p { margin: 0; font-size: 15px; color: var(--ink-2); overflow-wrap: anywhere; } .sn b { color: var(--ink); }" +
    ".sn .sn-c { font-size: 17px; } .sn a { color: var(--ink-2); } .sn a code { font-weight: 700; }";
  document.head.appendChild(css);
})();
/* The one thing kept: the last time the page was in view, as a number in this browser's own
   storage. `SINCE_WAS` is the visit before this one, read at load and again each time the page
   comes back into view after it was hidden. */
var SINCE_KEY = "jbus.since.looked", SINCE_MAX = 3, SINCE_WAS = sinceKept(), SINCE_HIDDEN = document.visibilityState === "hidden";
var SINCE_SAY = [["merged", "merged", "merged", "Merged"], ["stuck", "newly stuck", "newly stuck", "Stuck"], ["default", "default taken", "defaults taken", "Default taken for"]];
function sinceKept() { try { var v = Number(localStorage.getItem(SINCE_KEY)); return v > 0 ? v : null; } catch (e) { return null; } }
function sinceLook() { if (document.visibilityState !== "hidden" && NOW) { try { localStorage.setItem(SINCE_KEY, String(NOW)); } catch (e) {} } }
document.addEventListener("visibilitychange", function () {
  var hidden = document.visibilityState === "hidden";
  if (SINCE_HIDDEN && !hidden) SINCE_WAS = sinceKept();
  SINCE_HIDDEN = hidden;
});
function sinceNames(list) {
  var shown = list.slice(0, SINCE_MAX).map(function (e) { return '<a href="' + esc(linkOf(e.open)) + '"><code>' + esc(e.subj) + '</code></a>'; });
  return shown.join(", ") + (list.length > SINCE_MAX ? " and " + (list.length - SINCE_MAX) + " more" : "");
}
function sinceCard() {
  var s = STACK && STACK.since, was = SINCE_WAS;
  if (!s) return "";
  sinceLook();
  if (was == null || NOW - was < 60e3) return "";
  var from = ms(s.from), after = from != null && was < from ? from : was, by = {};
  s.events.forEach(function (e) { var at = ms(e.at); if (at != null && at > after) (by[e.kind] = by[e.kind] || []).push(e); });
  var counts = [], names = [];
  SINCE_SAY.forEach(function (k) {
    var list = by[k[0]] || [];
    if (!list.length) return;
    counts.push(plural(list.length, k[1], k[2]));
    names.push(k[3] + " " + sinceNames(list) + ".");
  });
  var head = after === was ? "Since you looked " + short(NOW - was) + " ago:" : "Over the last " + short(NOW - from) + ", since you looked " + short(NOW - was) + " ago:";
  return '<section class="sn" data-role="since" aria-label="Since you looked"><p class="sn-c"><b>' + head + '</b> <span data-role="since-counts">' + (counts.length ? counts.join(", ") : "nothing merged, nothing newly stuck") + '</span>.</p>' +
    (names.length ? '<p data-role="since-names">' + names.join(" ") + '</p>' : "") + '</section>';
}
panel({
  gloss: { since: ["Since you looked", "The line at the top of the overview of every project: what merged, what got stuck and still is, and which questions jbus closed with their default, since this browser last showed the page. The time of that last look is the one thing the page keeps, in the browser, and it holds nothing else."] },
  card: sinceCard
});
