/* What the page cannot say: its card of the count, and the drawer of each line. */
function dBlind() {
  return head("Under the line", plural(S.blind.length, "thing", "things") + " the page cannot say") +
    (S.blind.length ? '<ul class="clean rows" style="margin-top:10px">' + S.blind.map(function (g) { return '<li>' + gap("not known") + ' ' + esc(g.line) + ' ' + openBtn(g.open, "where") + '</li>'; }).join("") + '</ul>' : '<p class="src" style="margin-top:15px">Nothing.</p>');
}
panel({
  card: function () {
    return { at: 60, e: S.blind.length ? "op" : "ok", tag: "blind spots", val: String(S.blind.length), viz: "",
      label: S.blind.length + " things the page cannot say" };
  },
  drawer: dBlind
});
