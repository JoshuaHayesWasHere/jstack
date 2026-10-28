"""The days the page's tests are drawn over: `lineup` makes a day of as many rows of each kind as a
counts set gives, and `DAYS` names the two the overview is shot over, the T moment and the
overloaded day. It opens no browser, so a test that counts what the server says of a day needs
no browser to make one."""

from typing import NamedTuple

from jmerge import lines as jlines
from jmerge import ready
from view.scene import GATE, PULL, ago, briefed, et, item, logged, row

FIRST = ("tea", "jam", "oat", "rye", "fig", "plum", "kale", "leek", "mint", "sage")


SECOND = ("kettle", "saucer", "ladle", "whisk", "platter", "skillet", "colander", "teapot")


REASON = {
    "result": "no brief has a Result that names it",
    "review": "it has no review yet",
    "findings": "its findings are not handled: the Result has no Fixed line",
    "second": "its fix changed more than the findings named: the second pass is not written",
    "check": "check has not passed",
    "rebase": "it conflicts with its base",
}


TODAY = {
    "yours": 3,
    "blocked": 6,
    "free": 3,
    "running": 6,
    "gate": 1,
    "result": 1,
    "review": 2,
    "findings": 2,
    "second": 1,
    "check": 1,
    "rebase": 1,
}


class Lot(NamedTuple):
    """Rows of one kind of a counts set, in one home, `""` for the root, and for a pull request
    the word its checks gave. A kind alone as a key of the set is `Lot(kind)`."""

    kind: str
    home: str = ""
    checks: str = "passed"


STACKS = ("stacked", "held", "left")
"""The kinds of a pull request on the step check that merges after its parent row, as `jmerge`
logs it with its code. A `held` one is also a hold no thread works on, and a `left` one a
leftover, so each of those two waits on the user."""


T = {
    Lot("running"): 4,
    Lot("second"): 1,
    Lot("second", "jview"): 1,
    Lot("gate", "jview"): 1,
    Lot("hold", "macos"): 1,
    Lot("check", "", "failed"): 5,
    Lot("check", "jview", "failed"): 7,
    Lot("check", "flow", "failed"): 6,
    Lot("check", "jview", "pending"): 2,
    Lot("check", "", "passed"): 2,
    Lot("check", "jview", "passed"): 4,
    Lot("check", "flow", "unrun"): 2,
    Lot("stacked"): 6,
    Lot("held"): 1,
    Lot("left"): 1,
}
"""The busiest moment of jstack's queue, 2026-10-26 13:00Z (`reports/jv-glance/state/`): 44 open,
20 the root's, 15 jview's, 8 flow's and 1 macos's. In check, 18 failing, 2 running or queued,
6 passed and 2 with no run, and 8 stacked, of which one is held and one left, so they wait on
the user with the row at its gate and the hold."""


MANY = TODAY | {"yours": 4, "blocked": 12, "free": 8, "running": 6, "gate": 3, "review": 3}


MANY |= {"check": 3}
"""The overloaded day (`reports/jv-glance/today/fixture-many-waiting-*`): 45 open, 12 behind
`tea-kettle`, which is not approved, 8 ready for a launch slot, and 7 that wait on the user."""


MANY_HOMES = ("", "jview", "flow")


def dealt(counts, homes):
    """The counts set with each kind's rows dealt over the homes, the first home first."""
    made = {}
    for kind, many in counts.items():
        for at, home in enumerate(homes):
            share = many // len(homes) + (at < many % len(homes))
            if share:
                made[Lot(kind, home)] = share
    return made


def slugs():
    return (f"{first}-{second}" for second in SECOND for first in FIRST)


def lineup(scene, counts, merged=30, gates=6):
    """A day of the given size: as many rows of each kind as `counts` gives, each in its home
    with its brief, `merged` rows merged today, `gates` open gates, and the list a pass would
    have left of what waits on the user. A key of `counts` is a kind or a `Lot`. A row of a
    home other than the root's has a brief in the home's `tasks/` that names it, and the home
    its `home-id`. A pull request on the step check has the word its lot gives, and a stacked
    one (`STACKS`) merges after a row before it in check, or after the first row where none is."""
    names = slugs()
    rows, log, listed, moves, homes, checked = [], [], [], [], {}, []
    number = 100
    first = next(names)
    for key, many in counts.items():
        kind, home, checks = Lot(key) if isinstance(key, str) else key
        for at in range(many):
            slug = first if (kind, at) == ("yours", 0) and first not in homes else next(names)
            homes[slug] = home
            old = et(ago(minutes=20 + 7 * at))
            if kind == "yours":
                rows.append(row(slug, approved="", why="not approved", since=old))
                listed.append(
                    item(
                        "approve",
                        f"approve:{slug}",
                        f"approve {slug}: jbus queue approve",
                        slug=slug,
                        minutes=20 + 7 * at,
                    )
                )
            elif kind == "blocked":
                rows.append(row(slug, depends=[first], why=f"depends on {first}", since=old))
            elif kind == "free":
                rows.append(row(slug, why="no slot", since=old))
            elif kind == "running":
                rows.append(row(slug, "running", thread=f"mcp:{at}"))
                moves.append((slug, "launched", "running", 5 + 9 * at))
            elif kind == "gate":
                rows.append(row(slug, "gate", why="a gate the Chef has", since=old))
                line = f"gate {slug}: which way?"
                listed.append(item("row", f"row:{slug}", line, slug=slug, minutes=122))
            elif kind in STACKS:
                number += 1
                parent = checked[at % len(checked)] if checked else first
                reason = ready.STACKED_ON.format(branch=parent, slug=parent, default="main")
                why = f"wait: {reason}"
                pr = f"#{number}"
                rows.append(
                    row(slug, "pr", pr=pr, checks=checks, why=why, since=old, merge_after=[parent])
                )
                waits = jlines.waits("wait", number, PULL.format(number), reason)
                stamp = et(ago(minutes=10 + 25 * at)).removesuffix(" ET")
                log.append(f"{stamp} {jlines.logged(waits)}")
                if kind == "held":
                    line = f"held {slug}: 43 minutes by {reason}, and no thread is at work on it"
                    listed.append(item("held", f"held:{slug}", line, slug=slug, minutes=43))
                elif kind == "left":
                    line = f"left {slug}: pull request #{number} is not open and not merged"
                    listed.append(item("left", f"left:{slug}", line, slug=slug, minutes=30))
            else:
                number += 1
                word = "hold" if kind == "hold" else "wait"
                reason = REASON.get(kind, "needs user, touches skills/crew/SKILL.md")
                rows.append(
                    row(slug, "pr", pr=f"#{number}", checks=checks, why=f"{word}: {reason}")
                )
                if kind == "check":
                    checked.append(slug)
                if at % 2:
                    log.append(logged(90 + at, word, number, reason))
                    log.append(logged(80 + at, "wait", number, "a check has not finished"))
                log.append(logged(10 + 25 * at, word, number, reason))
                if kind == "hold":
                    listed.append(
                        item("hold", f"#{number}", f"hold {number}: {reason}", number=number)
                    )
    for at in range(merged):
        slug = next(names)
        rows.append(row(slug, "merged", pr=f"#{at + 1}"))
        moves.append((slug, "pr", "merged", 3 + 11 * at))
    scene.queue(rows)
    scene.moves(*moves)
    scene.merge_log(*log, logged(1, "wait", 1, "check has not passed"))
    (scene.home / "gates.md").write_text(
        "\n".join(
            GATE.format(n=n + 1, asked=f"is it {n + 1}?", status="open", default="it is not")
            for n in range(gates)
        )
    )
    scene.waiting(listed)
    briefed(scene, **{slug.replace("-", "_"): home for slug, home in homes.items() if home})
    return [one["slug"] for one in rows if one["status"] != "merged"]


def t_moment(scene):
    """The day of `T`, with 27 rows merged and 6 gates that go ahead on their default."""
    return lineup(scene, T, merged=27, gates=6)


def overloaded(scene):
    """The day of `MANY`, its rows dealt over the root, jview and flow, with 12 rows merged and
    8 gates that go ahead on their default."""
    return lineup(scene, dealt(MANY, MANY_HOMES), merged=12, gates=8)


DAYS = {"t": t_moment, "many": overloaded}
"""The two days every view of the overview is shot over (`test_view_page_days.py`)."""
