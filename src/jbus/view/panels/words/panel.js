/* Your words: the questions you answered, each word sent down by `jbus word`, and each
   approval of a row with what it rests on. `words:<kind>` opens it at a list, and
   `words:<key>` at one entry. */
var WORDKIND = { answer: "questions you answered", word: "words sent down", approval: "approvals of a row" };
function wordsOf(kind) { return S.words.filter(function (w) { return w.kind === kind; }); }
function wordEntry(key) { return S.words.filter(function (w) { return w.key === key; })[0] || null; }
function whenSaid(at) { var t = ms(at); return t == null ? "a time not kept" : day(t); }
function picked(w) { return "your pick on a Lavish page, " + whenSaid(w.said_at) + ", " + (w.said_in || "").split("/").pop(); }
function wordRow(w, hit) {
  var h = '<li' + (w.key === hit ? ' class="hit"' : "") + '>';
  if (w.kind === "answer" && w.home) {
    return h + '<span class="n" data-gloss="count:question">' + esc(w.number) + '</span> <b>' + esc(w.question) + '</b> ' + taskBtn(w.slug) +
      '<br><span class="tag">Default</span> ' + esc(w["default"] || "nothing is said") +
      '<br><span class="tag">Closed by its home</span> &quot;' + esc(w.words) + '&quot;' +
      '<br><span class="src">Its home wrote this in its gates.md. It is not your answer as jbus took it, and has no time.</span></li>';
  }
  if (w.kind === "answer") {
    return h + '<span class="n" data-gloss="count:question">' + esc(w.number) + '</span> <b>' + esc(w.question) + '</b> ' + taskBtn(w.slug) +
      '<br><span class="tag">Default</span> ' + esc(w["default"] || "nothing is said") +
      '<br><span class="tag">Your answer</span> &quot;' + esc(w.words) + '&quot; ' + (w.keeps ? '<span class="chip ok">the default stands</span>' : '<span class="chip user">not the default</span>') +
      '<br><span class="src">' + esc(whenSaid(w.at)) + (w.by ? ", by " + esc(w.by) : "") + (w.where ? ", in " + esc(w.where) : "") + '</span></li>';
  }
  if (w.kind === "word") {
    return h + '&quot;' + esc(w.words) + '&quot;' +
      '<br><span class="src">Said ' + esc(whenSaid(w.at)) + (w.said_in ? " in " + esc(w.said_in) : "") + (w.checked ? "" : " (time typed)") + '. Kept ' + esc(whenSaid(w.kept_at)) + '. ' +
      (w.sent_at ? "Sent on " + esc(whenSaid(w.sent_at)) + "." : "Not sent on yet" + (w.waits ? ": " + esc(w.waits) : "") + ".") + '</span></li>';
  }
  var rests = w.rests && wordEntry(w.rests);
  return h + taskBtn(w.slug) + ' ' + (w.basis ? '<span class="chip plain">' + esc(w.basis === "rule" ? "by rule " + w.ref : "by " + w.basis) + '</span>' : gap("no record")) +
    (w.basis ? '<br><span class="tag">Rests on</span> &quot;' + esc(w.words) + '&quot;' + (rests ? " " + openBtn("words:" + w.rests, "see it") : "") +
      '<br><span class="src">' + (w.basis === "rule" ? "A follow-up of " + esc(w.follows) + "; he did not speak of this row" : w.basis === "page" ? esc(picked(w).replace(/^y/, "Y")) : "Said " + esc(whenSaid(w.said_at)) + (w.said_in ? " in " + esc(w.said_in) : "") + (w.checked ? "" : " (time typed)")) + '. Run ' + esc(whenSaid(w.ran_at)) + ' by ' + esc(w.who) + '.</span>'
      : '<br>' + esc(w.line) + (w.words ? '<br><span class="src">The row holds &quot;' + esc(w.words) + '&quot;.</span>' : "")) + '</li>';
}
function dWords(arg) {
  var hit = arg || "", kind = WORDKIND[hit] ? hit : (wordEntry(hit) || {}).kind;
  var h = head("Your words", plural(S.words.length, "thing", "things") + " you said, newest first");
  h += '<p class="src" style="margin-top:15px">From <code>questions.json</code>, <code>words.json</code> and <code>queue.json</code>, as jbus wrote them. Nothing here waits on you, and nothing here writes.</p>';
  ["answer", "word", "approval"].forEach(function (k) {
    var items = wordsOf(k);
    h += '<h3' + (k === hit ? ' class="hit"' : "") + '>' + items.length + " " + WORDKIND[k] + '</h3>' +
      (items.length ? '<ul class="clean rows">' + items.map(function (w) { return wordRow(w, kind === k ? hit : ""); }).join("") + '</ul>' : '<p class="src">None.</p>');
  });
  return h;
}
panel({
  title: "Your words",
  drawer: dWords,
  adds: {
    task: function (t) {
      var w = wordEntry("approval:" + t.slug);
      if (!w) return "";
      var said = w.basis ? (w.basis === "rule" ? "by rule " + w.ref + ", a follow-up of " + w.follows : w.basis === "page" ? "on " + picked(w) : "on your word, said " + whenSaid(w.said_at)) + ", run " + whenSaid(w.ran_at) + " by " + w.who : w.line;
      return '<span class="tag">Approval</span> ' + openBtn("words:approval:" + t.slug, said);
    }
  }
});
