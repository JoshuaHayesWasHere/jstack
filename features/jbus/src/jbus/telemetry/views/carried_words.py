"""Each word the user had a home carry (fault F4, `acts.jsonl`'s `word`), and the thread it went to
and when (`word-sends.json`), with no word of its text."""

SQL = (
    "SELECT a.project, a.id AS word, a.at AS kept_at, a.said_at, a.said_in, a.source, "
    "a.party, a.route, a.subject, a.outcome, a.words_len, s.thread, s.sent_at, "
    "coalesce(s.waiting, 0) AS waiting, a.day FROM acts a LEFT JOIN word_sends s "
    "ON s.project = a.project AND s.word = a.id WHERE a.verb = 'word'"
)
