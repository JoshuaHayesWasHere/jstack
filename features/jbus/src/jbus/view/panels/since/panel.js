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
var SINCE_LANDED = 4;
function sinceLanded() {
  var s = STACK && STACK.since, was = SINCE_WAS;
  if (!s) return "";
  sinceLook();
  var from = ms(s.from), after = was == null || from != null && was < from ? from : was, by = {};
  s.events.forEach(function (e) { var at = ms(e.at); if (at != null && (after == null || at > after)) (by[e.kind] = by[e.kind] || []).push(e); });
  var merged = (by.merged || []).slice().sort(function (a, b) { return ms(b.at) - ms(a.at); }), shown = merged.slice(0, SINCE_LANDED);
  var head = was == null ? (from == null ? "jbus keeps no time for these" : "over the last " + short(NOW - from) + ", your first look") : after === was ? "you looked " + short(NOW - was) + " ago" : "over the last " + short(NOW - from) + ", you looked " + short(NOW - was) + " ago";
  var rest = SINCE_SAY.slice(1).map(function (k) { var list = by[k[0]] || []; return list.length ? k[3] + " " + sinceNames(list) + "." : ""; }).filter(Boolean);
  return '<section class="ovc" data-role="since" aria-labelledby="ovc-since"><h2 class="ovc-h" id="ovc-since"><span class="tag" data-gloss="card:since">Landed since you looked <b>' + merged.length + '</b></span></h2>' +
    (shown.length ? '<ul class="clean">' + shown.map(function (e) {
      return '<li class="ld"><span>' + hm(ms(e.at)) + '</span><a href="' + esc(linkOf(e.open)) + '"><code>' + esc(e.subj) + '</code>' + (STACK.projects.length > 1 ? " " + esc(e.project) : "") + '</a></li>';
    }).join("") + '</ul>' : '<p class="ovc-s">Nothing merged.</p>') +
    '<p class="ovc-f">' + (merged.length > shown.length ? "and " + (merged.length - shown.length) + " more &middot; " : "") + head + '</p>' +
    (rest.length ? '<p class="ovc-f">' + rest.join(" ") + '</p>' : "") + '</section>';
}
panel({
  gloss: { since: ["Since you looked", "The card under the matrix of the overview of every project: what merged, newest first, then what got stuck and still is, and which questions jbus closed with their default, since this browser last showed the page. On the first look, it is what jbus kept of the last hours. The time of that last look is the one thing the page keeps, in the browser, and it holds nothing else."] },
  parts: { landed: sinceLanded }
});
