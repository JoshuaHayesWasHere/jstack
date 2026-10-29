"""The one entry point: `jbus poll`, `jbus queue show|add|approve|hold|remove|apply`, `jbus
plan [close <entry>]`, `jbus gate <slug>`, `jbus answer <number>`, `jbus done <slug>`, `jbus
status`, `jbus events`, `jbus digest`, `jbus alarm`, `jbus view`, `jbus word`, `jbus project
add`, and `jbus t3 login|launch-test`.

`jbus poll` is one pass over every project in the config, under one lock: it runs `jmerge`
where the home is off, reads what the threads wrote down, asks T3 Code and GitHub what is
out, sends a line for each finding, ties each crew to its thread (the link, the relay and
the settle), tells a crew whose pull request `jmerge` calls stale or conflicting to rebase,
and one whose pull request is short of something it can fix what to do (`expedite`),
launches the rows of the queue that were approved, rewrites the table's derived columns
(with why each row waits, and a line for each change of status), says what waits on the user
(`stall`), again each hour, and rewrites the one list of it (`waiting`).
A row that ended with something left is sent to its home to close, once (`leftover`): it
waits on that home, and on the user only where it has no home or the home did not close it.
The launches come after every project was asked what is out: `max_running` caps the crews
out across all of them, and the free slots go to the projects in turn (`rotation`).
A gate a thread pipes to `jbus gate` is a question with a number (`questions`): it waits on
the user until `jbus answer` closes it, and a pass carries an answer that is not the default
to the thread that asked.
Everything it finds is an event with a loudness (`wake.LOUDNESS`), and the project's
home thread is woken only for what the user must act on: a new question, a hold or an
approval that is theirs, an alert, a stall. Everything else is quiet: it is in the log, which
`jbus events` prints and the view shows. A failure that repeats is told once, and once
when it ends (`alert`).
`jbus word` is the user's word down to a home: it keeps what the user said for one project or for
all, and sends it to the thread in each home's `home-id` as a queued message, at once and
then on each pass until it went (`word`). It is no event, so it wakes nothing.
Once a day it asks `jmerge` what a sweep would remove, and again on each pass until
`jmerge` has run. Each pass ends by rewriting the status file, which `jbus status` prints:
what a home thread that is down cannot say.
`jbus view` is no pass: it is a server that shows what the passes left, and it reads no
config (`jbus.view`).
`jbus project add` is no pass either: it adds one project's table to the config, and the
next pass loads it (`jbus.project`).
A scratch home of the config is no project of the pass, and no repo step is run for it
(`jbus.load`): its words go to its thread in a chore of the pass (`word.scratch`).
Beside the status file is the record of the pass
(`record`), written when the pass starts and again when it ends.
No model reads anything.
"""

from __future__ import annotations

import jbus
from jbus import verbs

LISTED = verbs.listed(jbus.__path__)


def main(argv: list[str] | None = None) -> int:
    typed, _ = verbs.parser(LISTED, __doc__).parse_known_args(argv)
    verb = verbs.verb(LISTED[typed.command])
    parser = verbs.parser(LISTED, __doc__, [verb])
    args, extra = parser.parse_known_args(argv)
    extra = verbs.words_left(args, extra)
    from jbus import queue

    for given in extra:
        column = given.lstrip("-").split("=")[0].replace("-", "_")
        if column in queue.DERIVED:
            print(f"refused: {column} is derived from T3 Code and GitHub, and no command writes it")
            return 2
    if extra:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    try:
        return verb.run(args, jbus.load() if verb.config else None)
    except Exception as error:
        from jbus import t3

        if not isinstance(error, jbus.Refused | t3.T3Error):
            raise
        print(error)
        return 1
