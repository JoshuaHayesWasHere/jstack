"""`jbus line-wait`: how long pull requests waited in jmerge's line on a day, read from the home's
`merge.log`.

jmerge merges main into one pull request at a time, the head of the line, and every other green
pull request whose check ran over an older main waits behind it with `[in-line]`. A pull request's
in-line episode starts at its `[in-line]` line and ends at its next line of any other kind, at
its merge or close as GitHub gives it in the CI ledger's `ci-prs.jsonl` (a pull request merged by
hand gets no line of jmerge's), or at the end of the window while it is still in line, whichever
comes first. `merge.log` writes a pull request's line only when its reason changes, so an episode
is one start and one end, to the minute.
`merge-waits.jsonl` cannot give this: a row starts its `ready` again at each new head, so a merged
row shows no in-line time.

The head is the pull request the latest `[in-line]` line names. A pull request whose check ran
over today's main is not in the line and merges as before (`features/jmerge/docs/jmerge.md`), so
it can merge past the head; main then moved under the head's check, and jmerge asks GitHub to
merge main into the head again (`[base-moved-asked]`), which costs another CI round. That ask is a
restart, named with the pull requests that merged past it.

The verb prints, for the window: the in-line PR-minutes, the merges, the PR-minutes per merge, the
restarts, and the minutes of each pull request. The window is the day, cut to `--since` and
`--until`, and for today to now. `merge.log`'s times are the machine's local time, as jmerge
writes them.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

import jbus
from jbus import verbs
from jbus.ci import ledger
from jmerge import lines, ready

_STAMP = len("2026-11-04 08:24 ")
_HEAD = re.compile(re.escape(ready.IN_LINE.split("{number}")[0]) + r"(\d+)")


@dataclass(frozen=True)
class Restart:
    """The head's check started again at `at`, after the `jumpers` merged past it."""

    head: int
    at: datetime
    jumpers: tuple[int, ...]


@dataclass(frozen=True)
class LineWait:
    """What the line cost in a window: the in-line minutes of each pull request, the pull
    requests merged, and the restarts of the head."""

    since: datetime
    until: datetime
    minutes: dict[int, int]
    merges: tuple[int, ...]
    restarts: tuple[Restart, ...]


def _timed(text: str) -> Iterator[tuple[datetime, lines.Line]]:
    """Each line of `merge.log` about a pull request, with its time."""
    for raw in text.splitlines():
        try:
            at = datetime.strptime(raw[: _STAMP - 1], "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        if said := lines.one(raw[_STAMP:]):
            yield at, said


def ends(pulls: Path) -> dict[int, datetime]:
    """When each pull request of the ledger at `pulls` merged or closed, whichever came first, in
    the machine's local time, as `merge.log` writes it."""
    found: dict[int, datetime] = {}
    for one in ledger.read(pulls):
        stamps = [one.get("merged"), one.get("closed")]
        times = [
            datetime.fromisoformat(at).astimezone().replace(tzinfo=None) for at in stamps if at
        ]
        if times and isinstance(one.get("number"), int):
            found[one["number"]] = min(times)
    return found


def measure(text: str, since: datetime, until: datetime, ended: dict[int, datetime]) -> LineWait:
    """Read `merge.log`'s text for the window from `since` to `until`, where `ended` gives when
    each pull request merged or closed on GitHub."""
    minutes: dict[int, int] = {}
    merges: list[int] = []
    restarts: list[Restart] = []
    started: dict[int, datetime] = {}
    jumped: dict[int, list[int]] = {}
    head: int | None = None

    def count(number: int, start: datetime, end: datetime) -> None:
        last = min(end, until, ended.get(number, end))
        spent = (last - max(start, since)) // timedelta(minutes=1)
        if spent > 0:
            minutes[number] = minutes.get(number, 0) + spent

    for at, said in _timed(text):
        if at > until:
            break
        number, code = said.number, said.code or ready.code_of(said.reason)
        if said.word != "merged" and code == ready.IN_LINE.code:
            started.setdefault(number, at)
            if found := _HEAD.match(said.reason):
                head = int(found[1])
            continue
        if number in started:
            count(number, started.pop(number), at)
        if said.word == "merged":
            if at >= since:
                merges.append(number)
            if number == head:
                head = None
            elif head is not None:
                jumped.setdefault(head, []).append(number)
            jumped.pop(number, None)
        elif code == ready.BASE_MOVED_ASKED.code and number in jumped:
            jumpers = tuple(jumped.pop(number))
            if at >= since:
                restarts.append(Restart(number, at, jumpers))
    for number, start in started.items():
        count(number, start, until)
    return LineWait(since, until, minutes, tuple(merges), tuple(restarts))


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _numbers(numbers: tuple[int, ...]) -> str:
    named = [f"#{one}" for one in numbers]
    return named[0] if len(named) == 1 else ", ".join(named[:-1]) + " and " + named[-1]


def _clock(moment: datetime, day: date) -> str:
    return "24:00" if moment.date() > day else f"{moment:%H:%M}"


def report(wait: LineWait, project: str, log: object) -> list[str]:
    """The lines `jbus line-wait` prints."""
    day = wait.since.date()
    total = sum(wait.minutes.values())
    per = f"{total / len(wait.merges):.1f}" if wait.merges else "none, no merge"
    said = [
        f"jmerge's line in {project} on {day}, {_clock(wait.since, day)} to "
        f"{_clock(wait.until, day)}, from {log}:",
        f"in-line PR-minutes: {total}, over {_plural(len(wait.minutes), 'pull request')}",
        f"merges: {len(wait.merges)}",
        f"PR-minutes per merge: {per}",
        f"head restarts by a pull request jumping the line: {len(wait.restarts)}",
    ]
    said += [
        f"- #{one.head} at {one.at:%H:%M}, after {_numbers(one.jumpers)} merged past it"
        for one in wait.restarts
    ]
    ranked = sorted(wait.minutes.items(), key=lambda pair: (-pair[1], pair[0]))
    if ranked:
        said.append("by pull request: " + ", ".join(f"#{n} {m}" for n, m in ranked))
    return said


def _hour(text: str) -> time:
    try:
        return time.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a time of day, as 13:05") from None


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--day", type=date.fromisoformat, help="the day, as 2026-11-04 (default: today)"
    )
    parser.add_argument("--since", type=_hour, help="start the window at this time of the day")
    parser.add_argument("--until", type=_hour, help="end the window at this time of the day")


def _run(args: argparse.Namespace, config: jbus.Config) -> int:
    project = verbs.project(config, args.project)
    log = config.home(project) / "merge.log"
    if not log.is_file():
        raise jbus.Refused(f"refused: no merge.log at {log}")
    now = datetime.now()
    day = args.day or now.date()
    since = datetime.combine(day, args.since or time())
    midnight = datetime.combine(day, time()) + timedelta(days=1)
    until = min(datetime.combine(day, args.until) if args.until else midnight, now)
    gone = ends(config.state(project) / ledger.PULLS)
    wait = measure(log.read_text(errors="replace"), since, until, gone)
    print("\n".join(report(wait, project.name, log)))
    return 0


VERBS = (
    verbs.Verb(
        "line-wait",
        "how long pull requests waited in jmerge's line on a day: in-line PR-minutes per merge",
        _arguments,
        _run,
    ),
)
