"""The band at the top of `#/`: in one look, is anything wrong, what waits on the user, and are
we moving.

The band is one list of items, each of one tier, in the order of `TIERS`: `wrong`, what is wrong
across the projects that is the user's (`state.users`, as `/stack.json`'s `wrong` merges it),
with jbus stopped or its passes failing first; `yours`, what only the user can move (the panel
`you`'s `needs`), where the rows of one project that wait for the user's approval are one item;
and `moving`, one item that says how much is open, what merged today and how many threads are
out. Inside a tier the oldest comes first, and an item with no time last. The band reads what
`/stack.json` already says and counts nothing of its own, so it never disagrees with the triage
tab.

What is wrong and owned by an agent is on its row, never in the band (`state.fixing`). Where
nothing that is wrong is the user's and nothing waits on the user, the band is `calm`: its one
item is the line that says the work moves.

Above the items is the verdict: one word of `verdict.WORDS` and its exact cause, which
`verdict.judge` gives over the pipeline's board of every project, with the groups of still rows
it counts, the count of what needs the user, and since when nothing was done.

The page keeps when the user last looked, for every tab: each render while the tab shows keeps
its time, and a tab nobody sees keeps none. A visit starts when the tab shows, and its "since you
looked" line says what changed between the look before it and its start, so the line stays the
same while the user reads it and is gone on the next visit."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

from jbus.view import verdict as verdicts
from jbus.view.state import Read, iso, users

FIRST = False
TIERS = ("wrong", "yours", "moving")
ITEM = {
    key: None
    for key in ("tier", "kind", "subj", "cause", "since", "where", "open", "verb", "count")
}
TOP = {key: None for key in ("tier", "kind", "subj", "cause", "since")}
GROUP = {key: None for key in ("kind", "text", "count", "head", "since")}
VERDICT = {
    "word": None,
    "cause": None,
    "groups": [GROUP],
    "needs": None,
    "quiet_since": None,
    "last_merge": None,
    "per_hour": None,
    "window": None,
    "merges": [None],
    "top": TOP,
}
SHAPE = {"glance": {"calm": None, "verdict": VERDICT, "items": [ITEM]}}
WINDOW = verdicts.WINDOW
"""The hours over which the verdict counts merges an hour: the last three, across midnight too."""
RANK = ("jbus", "main", "ci", "stall", "thread", "idle", "bus", "source", "unasked")
"""The kinds of `wrong` by how much each holds the work back, most first: the verdict names the
first, and of two of one kind the older."""
VERB = {
    "jbus": "Open pulse",
    "main": "Open pulse",
    "ci": "Open checks",
    "bus": "Open bus",
    "source": "Open pulse",
    "unasked": "Open pulse",
    "thread": "Open thread",
    "stall": "Open task",
    "idle": "Open task",
}
"""The verb of an item of each kind of `wrong`: each opens the drawer that has it."""
APPROVE = "approve"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _listed(names: list[str]) -> str:
    """Up to three names in full, and past that the first two and how many more."""
    if len(names) > 3:
        return f"{', '.join(names[:2])} and {len(names) - 2} more"
    return ", ".join(names)


def _path(project: str, home: str) -> str:
    return f"{project} › {home}" if home else project


def _pulse(projects: list[str]) -> str:
    return f"#/{quote(projects[0], safe='')}/pulse" if projects else "#/"


def _item(*values: Any) -> dict[str, Any]:
    """An item of the band from its values, in the order of `ITEM`, and what it counts as: one
    thing, unless it is a batch."""
    return dict(zip(ITEM, (*values, 1), strict=True))


def _jbus(jbus: dict[str, Any], projects: list[str]) -> list[dict]:
    """jbus itself, where it is wrong: stopped, or its passes raising, as the panel `pulse`
    says."""
    if jbus["stopped"]:
        cause = f"stopped: {jbus['why'] or 'no pass'}"
        since = jbus["last_end"]
    elif jbus["failed"]:
        cause, since = f"{_plural(jbus['failed'], 'pass', 'passes')} failed", jbus["failed_since"]
    else:
        return []
    where, open_ = "this machine", _pulse(projects)
    return [_item("wrong", "jbus", "jbus", cause, since, where, open_, VERB["jbus"])]


def _wrong(wrong: list[dict[str, Any]], projects: list[str]) -> list[dict[str, Any]]:
    found = []
    for one in wrong:
        places = [_path(place["project"], place["home"]) for place in one["where"]]
        first = one["where"][0]["open"] if one["where"] else _pulse(projects)
        where = _listed(places) or "this machine"
        verb = VERB.get(one["kind"], "Open it")
        found.append(
            _item("wrong", one["kind"], one["subj"], one["cause"], one["since"], where, first, verb)
        )
    return found


def _oldest(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The items oldest first and one with no time last, two of one time in the order given."""
    return sorted(items, key=lambda one: (one["since"] is None, one["since"] or ""))


def _yours(needs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What waits on the user, oldest first, with the rows of one project that wait for the
    user's approval as one item, at the place of the oldest of them."""
    found, batch = [], {}
    for one in needs:
        if one["kind"] == APPROVE:
            if one["project"] in batch:
                batch[one["project"]].append(one)
                continue
            batch[one["project"]] = [one]
        subj = one["subj"] or one["what"]
        cause = one["why"] or (one["what"] if one["what"] != subj else one["verb"])
        where = _path(one["project"], one["home"])
        found.append(
            _item("yours", one["kind"], subj, cause, one["since"], where, one["open"], one["verb"])
        )
    for item in found:
        if item["kind"] != APPROVE:
            continue
        project = item["where"].split(" › ")[0]
        rows = batch.get(project, [])
        if len(rows) < 2:
            continue
        item["subj"] = _plural(len(rows), "approval", "approvals")
        item["cause"] = _listed([one["subj"] or one["what"] for one in rows])
        item["where"] = project
        item["open"] = f"#/{quote(project, safe='')}/you/{APPROVE}"
        item["verb"] = f"Approve {len(rows)}"
        item["count"] = len(rows)
    return found


def _moving(answer: dict[str, Any]) -> dict[str, Any]:
    projects = answer["projects"]
    open_ = sum(one["open"] for one in projects)
    merged = sum(one["merged"] for one in projects)
    out = sum(one["health"]["threads"] or 0 for one in projects)
    cause = (
        f"{open_} open in {_plural(len(projects), 'project', 'projects')}, "
        f"{merged} merged today, {_plural(out, 'thread', 'threads')} out"
    )
    if answer["proceeds"]:
        n = len(answer["proceeds"])
        cause += f", {_plural(n, 'gate takes its', 'gates take their')} default if you say nothing"
    names = [one["name"] for one in projects]
    since = answer["machine"]["jbus"]["last_end"]
    return _item("moving", "moving", "moving", cause, since, "", _pulse(names), "")


def _top(wrong: list[dict[str, Any]], yours: list[dict[str, Any]]) -> dict[str, Any]:
    """What holds the work back most: of what is wrong, the first kind of `RANK` and of that
    kind the oldest; with nothing wrong, the oldest of what waits on the user; else nothing."""
    ranked = sorted(wrong, key=lambda one: (RANK + (one["kind"],)).index(one["kind"]))
    first = (ranked or yours or [dict.fromkeys(TOP, "") | {"since": None}])[0]
    return {key: first[key] for key in TOP}


def _start(read: Read) -> str:
    """Where the merges the band reads start: the start of the user's day, or the start of the
    window where that is earlier, so a merge before midnight still counts in the window."""
    return min(read.day, iso(read.now - timedelta(hours=WINDOW)))


def _board(reads: list[Read]) -> dict[str, Any]:
    """The rows of the pipeline's board of each project, and the rows it cannot place."""
    boards = [read.panel("pipeline") for read in reads]
    return {key: [one for board in boards for one in board[key]] for key in ("rows", "unplaced")}


def _verdict(
    reads: list[Read],
    needs: int,
    wrong: list[dict[str, Any]],
    merges: list[str],
    last: str | None,
    now: datetime,
    top: dict[str, Any],
) -> dict[str, Any]:
    """The verdict's word and its cause (`verdict.judge`), over the boards of `reads`, with the
    groups of still rows it counts, what needs the user and since when the work is quiet. Beside
    them are the last merge, the merges an hour over the last `WINDOW` hours, and the top
    cause."""
    merges = sorted(merges, key=datetime.fromisoformat)
    start = now - timedelta(hours=WINDOW)
    recent = [at for at in merges if datetime.fromisoformat(at) >= start]
    judged = verdicts.judge(_board(reads), needs, wrong, merges, last, now)
    return {
        "word": judged.word,
        "cause": judged.cause,
        "groups": [vars(one) for one in judged.groups],
        "needs": judged.needs,
        "quiet_since": judged.quiet_since,
        "last_merge": merges[-1] if merges else None,
        "per_hour": round(len(recent) / WINDOW, 1),
        "window": WINDOW,
        "merges": merges,
        "top": top,
    }


def _last(acts: list[dict[str, Any] | None]) -> str | None:
    return max((one["at"] for one in acts if one), key=datetime.fromisoformat, default=None)


def band(
    answer: dict[str, Any], now: datetime, merges: list[str], reads: list[Read]
) -> dict[str, Any]:
    """The band of `answer`, which holds what `/stack.json` holds, at `now`. `merges` are the
    times of the merges across the projects since `_start`, and `reads` the projects."""
    names = [one["name"] for one in answer["projects"]]
    wrong = _jbus(answer["machine"]["jbus"], names) + _wrong(answer["wrong"], names)
    wrong, yours = _oldest(wrong), _yours(answer["needs"])
    items = [*wrong, *yours, _moving(answer)]
    last = _last([one["last"] for one in answer["projects"]])
    needs = len(answer["needs"])
    verdict = _verdict(reads, needs, wrong, merges, last, now, _top(wrong, yours))
    return {"glance": {"calm": not wrong and not yours, "verdict": verdict, "items": items}}


def stack(base: Read, reads: list[Read], answer: dict[str, Any]) -> dict[str, Any]:
    """What the band adds to `/stack.json`: `base` is the machine's read, `reads` each
    project's, and `answer` the rest of `/stack.json`. The merges are the ones the panel
    `merged` reads (`Read.merged_since`), from the start of the user's day or of the window,
    whichever is earlier."""
    merges = [one["at"] for read in reads for one in read.merged_since(_start(read))]
    return band(answer, base.now, merges, reads)


def build(read: Read) -> dict[str, Any]:
    """The band of one project, from the project's own pieces: its list of what is wrong and
    what waits on the user. The machine's part, jbus and the counts, is `/stack.json`'s, so the
    verdict of one project cannot see that jbus stopped."""
    needs = read.panel("you")["needs"] if read.name else []
    names = [read.name] if read.name else []
    wrong, yours = _oldest(_wrong(users(read), names)), _yours(needs)
    merges = [one["at"] for one in read.merged_since(_start(read))] if read.name else []
    reads = [read] if read.name else []
    last = _last(read.acts[-1:]) if read.name else None
    verdict = _verdict(reads, len(needs), wrong, merges, last, read.now, _top(wrong, yours))
    return {"glance": {"calm": not wrong and not yours, "verdict": verdict, "items": wrong + yours}}
