function dBlind() {
  return head("Under the line", plural(S.blind.length, "thing", "things") + " the page cannot say") +
    (S.blind.length ? '<ul class="clean rows" style="margin-top:10px">' + S.blind.map(function (g) { return '<li>' + gap("not known") + ' ' + esc(g.line) + ' ' + openBtn(g.open, "where") + '</li>'; }).join("") + '</ul>' : '<p class="src" style="margin-top:15px">Nothing.</p>');
}
panel({
  gloss: { blind: ["Blind spots", "Things this page cannot say now, each with where to look. They are said so that a gap is never drawn as calm."] },
  card: function () {
    return { at: 60, sum: plural(S.blind.length, "blind spot", "blind spots"), e: S.blind.length ? "op" : "ok", tag: "blind spots", val: String(S.blind.length), viz: "",
      label: S.blind.length + " things the page cannot say" };
  },
  drawer: dBlind
});
