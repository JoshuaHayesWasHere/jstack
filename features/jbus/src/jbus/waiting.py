"""This module keeps the one list of what waits on the user, `waiting-on-user.json` in a project's
state directory.

Each pass rewrites the list. An item is one thing only the user can do,
`{"kind", "key", "line", "since"}` plus the fields its kind adds. The kinds are `KINDS`:

- `gate`: an open question that jbus holds (`questions`), with `source` `jbus` and a line that says
  `question <n>`, which is the number that `jbus answer` takes. A `gate` is also an open gate in the
  home's `gates.md` or in a scoped home's, with its `number`, `question`, `default`, the `home` it
  is in (nothing for the repo's own) and the `slug` that asked. When jbus holds a gate from a
  `gates.md` as a question, open or closed, the item is that question, and this module skips the
  copy of the gate in the file;
- `row`: a row of the queue at `gate` that has no open pull request, with its `slug`. The line is
  the condition that jbus recorded for the row. jbus records a condition about a pull request once,
  for the pull request's crew or for the message to that crew, and the row is at `gate` for that one
  pass;
- `left`: a row whose thread ended with a Result that leaves something, with its `slug`. The line is
  the row's `why`. The row stays one item until the Result leaves nothing or the row is gone. A row
  that merged with something left is listed while its thread is not at work, starting with the pass
  after the one that told the thread of the merge. When jbus has told a row's home about the row's
  `Left:` line (`leftover`), the row waits on that home and is not listed. The row is listed, with
  the reason after its `why`, when the row has no home to tell, or its home has not closed the
  leftover in time;
- `approve`: a row with no approval, or a row whose brief changed after its approval, with its
  `slug`. The line is the command that approves it;
- `hold`: a pull request that `jmerge` holds, with its `number` and `url`;
- `held`: rows held by one reason with no thread at work on it, from the pass that woke their home
  (`clock.held`), with their `rows` and the `home` that owns them. It leaves the list once the hold
  clears or a thread takes it up;
- `config`: no sign-in to T3 Code.

No list holds an item of a slug that was removed from the queue (`queue.removed`). `read` leaves
such an item out of what the last pass left, and `keep` leaves it out of what the pass finds. So the
removal does not change the list and sends no event.

`key` names an item from pass to pass, and `since` is when a pass first listed it. When `stall`
found a root with the same key as an item, `keep` lays the root's fields over the item's, since the
root's line says more and the root has `unblocks`. A row to approve is listed once, as `approve`,
also when it is at `gate` for its changed brief. A pass that could not ask about a kind keeps the
items of that kind that it had.

When a pass writes a list with other keys than the list that it found, the pass logs one `waiting`
event. The event gives how many items wait, the new ones by name (`short`), and each line, marked
`+` for a new item and `-` for one that is gone. It is `quiet`: the list is for the record and the
digest, and what on it the user has to decide reaches the user as a `decision` (`jbus.blockers`).
The first pass that writes the list logs no event. Neither the file nor the event holds a webhook
URL, key or token, since `redact` removes each of them from the pass's findings before the pass
compares those findings with the file.

What blocks is a part of this list, and `blocking` is the one function that decides it. An item
blocks when it is open and nothing can move without the user. That is the design's Blocking test
(`features/jbus/docs/jbus.md`, "What blocks"), applied to these fields:

- (a) a `gate` whose `default` is empty, or whose question or context names one of `PAUSE`. Only a
  gate in a home's `gates.md` can have an empty default, since `jbus gate` refuses a question with
  none. jstack keeps no always-pause list of its own: `PAUSE` is that list, matched against the
  gate's words;
- (b) an `approve` item, which is a row whose `brief_sha` is empty because nobody approved it or
  because its brief changed after the go, and a row of the queue that waits with no brief in
  `briefs/<slug>.md`;
- (c) a `hold`, which is a pull request that `jmerge` holds;
- (d) a stall, which is any of these: a `left` item, a leftover that is the user's because the row's
  home did not close it in `CLOSE_MINUTES` or the row has no home; a `config` item; a streak of
  `alert` that alerted, of this project or of the pass, except the second target's own; and a gate
  that has a default, whose slug wrote no event for `CLOSE_MINUTES` and has no thread at work.

None of these blocks: a gate with a default whose thread still writes, a `row` that jbus put at
`gate`, and a leftover that is still with its home.

`cadence` keeps `blocking.json`, `{"open", "reminded", "period"}`, and queues the second target's
bodies (`wake.Box.post`). It queues a body for the items that opened in a pass, one `reminder` for
each item still open `REMIND_MINUTES` after it opened, and a `refresh` of every open item, oldest
first. The `refresh` goes on the pass that begins a new `REFRESH_MINUTES` period, also when no item
is open. A body names an item by its key, the same key that the list uses, so it names a question by
its number. A pass that cannot judge a stall, or that is blind, closes no item that it had open.

The file once had another name (`jbus.old_names`). Where there is no file of the current name,
`read` takes a file of the old name, and renames each line's event to the name that the event has
now. `keep` removes the old file once it has written the new one.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
from collections.abc import Callable, Collection
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsettings
from jbriefs import below
from jbus import (
    alert,
    leftover,
    merge,
    mirror,
    old_names,
    questions,
    queue,
    read_json,
    redact,
    verbs,
    write_json,
)
from jbus.passes import CONDITION, Pass, Slot
from jbus.wake import renamed
from jbus.watch import LIVE, World

if TYPE_CHECKING:
    from jbus.cli import Half

EVENTS = {"waiting": "quiet"}
EVENT = "waiting"


@dataclass(frozen=True)
class Kind:
    """A `Kind` is one kind of item that waits on the user, together with how the page shows that
    kind. `label` heads the kind's list in the drawer of what waits on the user, and `verb` is the
    button on an item of the kind. `shown` is the kind's place in that drawer, whereas a pass lists
    the kinds in the order of `KINDS`."""

    name: str
    label: str
    verb: str
    shown: int


KINDS = (
    Kind("gate", "Open gates", "Accept default", 5),
    Kind("row", "Tasks at a gate", "Fix brief", 1),
    Kind("left", "Left over by tasks that ended", "Close it", 2),
    Kind("approve", "Rows to approve", "Approve launch", 4),
    Kind("hold", "Pull requests jmerge holds for your word", "Review merge", 3),
    Kind("held", "Holds no thread works on", "Pick it up", 7),
    Kind("config", "Setup jbus lacks", "Set up", 6),
)

Item = dict[str, Any]


NAME = "waiting-on-user.json"
BLOCKS = "blocking.json"
PAUSE = {
    "force-push": r"\bforce[- ]?push",
    "deploy": r"\bdeploy",
    "deleting data": r"\b(delet|drop|eras|wip)\w*\b[^.]*\b(data|database|tables?|rows|records)\b",
    "an outside message": (
        r"\b(customers?|outside|external|public)\b[^.]*\b(message|e-?mail|post|reply)"
        r"|\b(message|e-?mail|post|reply)\w*\b[^.]*\b(customers?|outside|external|public)\b"
    ),
}
KEEP_REMINDED = timedelta(days=14)


def path(state: Path) -> Path:
    return state / NAME


def _named_before(state: Path) -> list[Path]:
    return [state / f"{was}.json" for was, now in old_names().items() if f"{now}.json" == NAME]


def kinds() -> list[str]:
    """Return the name of each kind, in the order of `KINDS`."""
    return [one.name for one in KINDS]


def verb(name: str) -> str:
    """Return the button of an item of the kind `name`."""
    return next(one.verb for one in KINDS if one.name == name)


def shown() -> list[dict[str, Any]]:
    """Return the kinds as the page has them, in the order the page shows them."""
    return [asdict(one) for one in sorted(KINDS, key=lambda one: one.shown)]


def kind(key: str) -> str:
    """Return the kind that a key names. A key `#<n>` names a hold, and any other key names its kind
    before its colon."""
    if key.startswith("#"):
        return "hold"
    named = key.partition(":")[0].removeprefix("re-")
    return named if named in kinds() else "config"


def short(one: Item) -> str:
    """Say an item in a few words: its kind, then its number for a gate or a hold, its slug for a
    row, or what its key names."""
    by = "number" if one["kind"] in ("gate", "hold") else "slug"
    what = one.get(by) or one["key"].rpartition(":")[2].lstrip("#")
    home = f"{one['home']}#" if one.get("home") else ""
    return f"{'question' if questions.listed(one) else one['kind']} {home}{what}"


def subject(one: Item) -> str:
    """Return the row or question an item is about: the slug of its row, else `question <n>`
    for a gate (`question <home>#<n>` for a scoped home's), else `#<n>` for a hold, else what
    its key names after its kind."""
    if one.get("slug"):
        return str(one["slug"])
    if one["kind"] in ("gate", "hold") and one.get("number"):
        if one["kind"] == "hold":
            return f"#{one['number']}"
        home = f"{one['home']}#" if one.get("home") else ""
        return f"question {home}{one['number']}"
    return str(one["key"]).rpartition(":")[2]


def read(state: Path) -> list[Item] | None:
    """Return the list as the last pass left it, or None where no pass has written one.

    A list written before items had a kind uses `root` as each item's name, and `read` takes that
    name as the item's key.
    """
    kept = None
    for file in (path(state), *_named_before(state)):
        kept = read_json(file, None)
        if isinstance(kept, list):
            break
    else:
        return None
    items = []
    gone = queue.removed_slugs(state)
    names = old_names()
    for one in kept:
        if isinstance(one, dict) and one.get("slug") in gone:
            continue
        if isinstance(one, dict) and (one.get("key") or one.get("root")):
            key = one.get("key") or one.pop("root")
            line = {"line": renamed(one["line"], names)} if isinstance(one.get("line"), str) else {}
            items.append({"kind": kind(key), **one, **line, "key": key})
    return items


def approve(name: str, slug: str, sha: str, user: jsettings.Settings) -> str:
    """Return the command that records the user's go for the brief whose sha256 starts with `sha`,
    with the three things that the go is based on."""
    return f"jbus --project {name} queue approve {slug} --sha {sha} with {queue.BASIS}"


def gates(
    home: Path,
    held: list[questions.Question] | None = None,
    gone: Collection[str] = (),
    why: Callable[[questions.Question], str] = lambda one: "",
) -> list[Item]:
    """Return the open gates in the home's `gates.md` and in each scoped home's, then the open
    questions of `held`. A gate that is also one of `held` counts once, as the question, while it is
    open, and not at all once it is closed. Leave out a gate that a slug in `gone` asked. `why` is
    `questions.waits` of the project, for the line of a go gate."""
    held = held or []
    keys = {one.key for one in held}
    found = []
    for file, number, asked, body, key in mirror.home_gates(home):
        if not below.line(body, "Status:").startswith("open") or key in keys:
            continue
        where = "" if file.parent == home else file.parent.name
        digest = hashlib.sha256(asked.encode()).hexdigest()[:8]
        found.append(
            {
                "kind": "gate",
                "key": f"gate:{where}#{number}:{digest}",
                "line": f"gate {number}: {asked}",
                "number": number,
                "question": asked,
                "default": below.line(body, "Default:"),
                "home": where,
                "slug": mirror.asker(body),
            }
        )
    found += [questions.item(one, why(one)) for one in held if one.answer is None]
    return [one for one in found if one["slug"] not in gone]


def unapproved(run: Pass, rows: list[queue.Row]) -> list[Item]:
    """Return the rows that were not launched because nobody approved them."""
    found = []
    for row in sorted(rows, key=queue.order):
        slug = row["slug"]
        if row.get("status", "queued") == "queued" and not row.get("approved"):
            sha = queue.brief_sha(queue.brief(run.state, slug) or "")[:12]
            line = f"approve {slug}: {approve(run.project.name, slug, sha, run.user)}"
            found.append({"kind": "approve", "key": f"approve:{slug}", "line": line, "slug": slug})
    return found


def gated(run: Pass, world: World, rows: list[queue.Row]) -> list[Item]:
    """Return the rows at `gate` that have no open pull request and for which this pass recorded a
    condition. When a reply from T3 Code is lost, a row stays at `gate` for one pass with no
    condition recorded, and that row asks nothing of the user."""
    return [
        {
            "kind": "row",
            "key": f"row:{row['slug']}",
            "line": f"{CONDITION} {row['slug']}: {run.asked[row['slug']]}",
            "slug": row["slug"],
        }
        for row in sorted(rows, key=queue.order)
        if row.get("status") == "gate" and row["slug"] in run.asked
        if row["slug"] not in world.open
    ]


def left(run: Pass, world: World, rows: list[queue.Row]) -> list[Item]:
    """Return the rows whose Result leaves something that no thread is at work on
    (`leftover.ended`). Leave out a row whose leftover record says that its home still has it. When
    a row's record gives a reason why the row is the user's, the item's line ends with that reason.
    """
    held = leftover.read(run.state)
    found = []
    for slug, why in leftover.ended(run, world, rows):
        reason = leftover.his(held[slug], run.now) if slug in held else ""
        if slug in held and not reason:
            continue
        line = f"left {slug}: {why}" + (f"; {reason}" if reason else "")
        found.append({"kind": "left", "key": f"left:{slug}", "line": line, "slug": slug})
    return found


def holds(run: Pass, world: World | None, pulls: list[str], was: list[Item]) -> list[Item]:
    """Return the open pull requests `jmerge` holds, by what it said in this pass (`merge.shown`),
    also where the home merges. A pull request that is still open and that `jmerge` said nothing
    about keeps its earlier hold, since in that case `jmerge` did not reach it.

    A pass that could not ask T3 Code or GitHub has no `world`, and trusts `jmerge`. Such a pass
    counts a pull request that `jmerge` holds in this pass as open. A pull request that `jmerge`
    said nothing about keeps its earlier hold. So the list gets a hold even when nothing but
    `jmerge` answers.
    """
    lines = [line.strip() for line in pulls if isinstance(line, str)]
    is_open = None if world is None else {pull["number"] for pull in world.open.values()}
    parsed = [(line, merge.parse(line)) for line in lines]
    said = {line.number for _, line in parsed if line}

    def there(number: Any) -> bool:
        return is_open is None or number in is_open

    found = []
    for text, line in parsed:
        if line and line.word == "hold" and line.reason and there(line.number):
            found.append(
                {
                    "kind": "hold",
                    "key": f"#{line.number}",
                    "line": text,
                    "number": line.number,
                    "url": line.name,
                }
            )
    found += [one for one in was if there(one.get("number")) and one.get("number") not in said]
    return sorted(found, key=lambda one: one["number"])


def held(state: Path) -> list[Item]:
    """Return the holds that woke their home and that no thread works on yet (`clock.held`)."""
    kept = read_json(state / "held.json", {})
    return [
        {
            "kind": "held",
            "key": f"held:{key}",
            "line": f"held {', '.join(one['rows'])}: {one['minutes']} minutes by {one['reason']}, "
            "and no thread is at work on it",
            "rows": one["rows"],
            "home": one["home"],
        }
        for key, one in sorted(kept.items())
        if isinstance(one, dict) and one.get("woke")
    ]


def _earlier(*stamps: str) -> str:
    return min(stamps, key=datetime.fromisoformat)


def keep(
    run: Pass,
    world: World | None,
    rows: list[queue.Row] | None,
    pulls: list[str],
    roots: list[Item],
    *,
    derived: bool,
    read_all: bool,
) -> list[Item]:
    """Rewrite the list, and log one quiet event when the new list's keys differ from the old
    list's.

    `roots` is the list that `stall.tell` returns. `derived` says the rows' statuses are this
    pass's, and `read_all` says that `dispatch` read every row of the queue in this pass.

    `dispatch` records a condition for a row only in a pass in which it reads that row with a slot
    free. Some passes record no condition for a row that is at `gate` on the list. If the row is not
    launched and `dispatch` gave no other reason for it to wait, the row stays at `gate` through
    such a pass. In that pass `dispatch` did not read the row, or the pass was full and `dispatch`
    held the row's gate back (`Pass.held`) or recorded `Slot` for it.
    """
    was = read(run.state)
    before = {one["key"]: one for one in was or []}

    def had(of: str) -> list[Item]:
        """Return the items that the list had of a kind this pass cannot judge, without the
        `unblocks` field of a root, since `stall` gives the roots."""
        kept = (one for one in before.values() if one["kind"] == of)
        return [{name: value for name, value in one.items() if name != "unblocks"} for one in kept]

    try:
        asked = questions.read(run.state)
        found = gates(run.home, asked, run.removed, questions.waits(run.state, run.user))
    except questions.Unparsable:
        found = had("gate")
    if rows is not None and world is not None and derived:
        waits = {row["slug"] for row in rows if row.get("status") in ("queued", "gate")}

        def unjudged(slug: str) -> bool:
            unread = slug not in run.reasons and not read_all
            full = slug in run.held or isinstance(run.reasons.get(slug), Slot)
            return slug in waits and slug not in run.asked and (unread or full)

        found += gated(run, world, rows) + [one for one in had("row") if unjudged(one["slug"])]
        found += left(run, world, rows)
    else:
        found += had("row") + had("left")
    found += unapproved(run, rows) if rows is not None else had("approve")
    found += holds(run, world, pulls, had("hold"))
    found += held(run.state)
    secret = run.config.secrets()
    items = {one["key"]: one for one in redact(found, secret)}
    for root in redact(roots, secret):
        key = root["key"]
        named = {"slug": key.partition(":")[2]} if kind(key) == "approve" else {}
        items[key] = {"kind": kind(key), **named, **items.get(key, {}), **root}
    for key in [key for key in items if kind(key) == "approve"]:
        items.pop(f"row:{key.partition(':')[2]}", None)
        if not _approvable(run, key.partition(":")[2]):
            del items[key]
    now = run.now.isoformat()
    for key, one in items.items():
        stamps = [one.get("since", now), before.get(key, {}).get("since", now)]
        one["since"] = _earlier(*stamps)
    listed = sorted(items.values(), key=lambda one: kinds().index(one["kind"]))
    if was is not None and set(before) != set(items):
        new = [one for one in listed if one["key"] not in before]
        gone = [one for key, one in before.items() if key not in items]
        names = f" ({', '.join(map(short, new))})" if new else ""
        line = (
            f"{EVENT} {run.project.name}: {len(listed)} wait on {run.user.user}, "
            f"{len(new)} new{names}, {len(gone)} gone"
        )
        marked = [f"{'+' if one in new else ' '} {one['line']}" for one in listed]
        marked += [f"- {one['line']}" for one in gone]
        run.box.send("", EVENT, line, "\n".join(marked))
    write_json(path(run.state), listed, mode=0o600)
    for file in _named_before(run.state):
        with contextlib.suppress(OSError):
            file.unlink()
    return listed


def _approvable(run: Pass, slug: str) -> bool:
    """Say whether a row has a brief for the user to approve. The rows a pass read can be older
    than a removal that ran while the pass did, so this reads `removed.json` and the stored brief
    again. A row that is there with no brief is `_briefless`'s to report."""
    return slug not in run.removed and bool((queue.brief(run.state, slug) or "").strip())


def paused(text: str) -> str:
    """Return the always-pause name that matches a text, or nothing."""
    return next((name for name, rule in PAUSE.items() if re.search(rule, text, re.I)), "")


def _last_events(run: Pass) -> dict[str, datetime]:
    """Return when each slug last had an event in the log."""
    last: dict[str, datetime] = {}
    for one in run.box.log():
        slug = one.get("slug")
        if slug:
            at = datetime.fromisoformat(one["at"])
            last[slug] = max(last.get(slug, at), at)
    return last


def _at_work(world: World, slug: str) -> bool:
    """Say whether any thread of the slug is at work. The crewmate's thread and its reviewer's
    thread both count."""
    return any(
        thread.get("status") in LIVE and not thread.get("settled")
        for thread in world.threads.get(slug, [])
    )


def _why(
    run: Pass, one: Item, world: World | None, last: dict[str, datetime]
) -> tuple[str, str] | None:
    """Return the case of the Blocking test that an item of the list meets, and why, or None where
    the item does not block. `("?", "")` is a stall this pass cannot judge, since the pass has no
    `world`."""
    kind = one["kind"]
    if kind == "hold":
        return "c", "a pull request jmerge holds"
    if kind == "approve":
        return "b", "a row with no approval of its brief"
    if kind in ("left", "config"):
        return "d", "a leftover no home closed" if kind == "left" else "jbus cannot go on"
    if kind != "gate":
        return None
    if not str(one.get("default") or "").strip():
        return "a", "a gate with no default"
    named = paused(f"{one.get('question', '')} {one.get('context', '')}")
    if named:
        return "a", f"always-pause: {named}"
    slug = one.get("slug") or ""
    if not slug or slug == "home":
        return None
    if world is None:
        return "?", ""
    if _at_work(world, slug):
        return None
    since = last.get(slug) or datetime.fromisoformat(one["since"])
    if (run.now - since).total_seconds() < leftover.CLOSE_MINUTES * 60:
        return None
    return "d", f"no event for {leftover.CLOSE_MINUTES} min and no thread at work"


def _blocks(run: Pass, item: Item, case: str, why: str) -> Item:
    kept = ("key", "kind", "line", "since", "slug", "number", "url", "question", "default")
    return {"project": run.project.name, "case": case, "why": why} | {
        name: item[name] for name in kept if item.get(name) not in (None, "")
    }


def _alarms(run: Pass) -> list[Item]:
    """Return the streaks that alerted and are still open, of this project or of the pass. Leave out
    the second target's own streak, since jbus would post it to the same webhook that fails."""
    name = run.project.name
    mine = {alert.PASS, alert.home(name), alert.webhook(name), alert.top_level(name)}
    mine.add(alert.jmerge(name))
    found = []
    for key, one in sorted(alert.streaks(run.config.state_dir).items()):
        if key in mine and one.get("alerted"):
            line = f"alert: {key} failed {one.get('count')} times in a row"
            item = {"key": f"alarm:{key}", "kind": "alarm", "line": line, "since": one["since"]}
            found.append(_blocks(run, item, "d", "a jbus alarm"))
    return found


def _briefless(run: Pass, rows: list[queue.Row] | None, listed: list[Item]) -> list[Item]:
    """Return the rows that wait to launch with no brief stored for them."""
    keys = {one["key"] for one in listed}
    found = []
    for row in sorted(rows or [], key=queue.order):
        slug = row["slug"]
        if row.get("status", "queued") not in ("queued", "gate") or f"approve:{slug}" in keys:
            continue
        if slug in run.removed or (queue.brief(run.state, slug) or "").strip():
            continue
        line = f"brief {slug}: the queue has no brief for it, add it again"
        item = {"key": f"brief:{slug}", "kind": "brief", "line": line, "slug": slug}
        item["since"] = run.now.isoformat()
        found.append(_blocks(run, item, "b", "a row with no brief"))
    return found


def blocking(
    run: Pass,
    listed: list[Item],
    rows: list[queue.Row] | None,
    world: World | None,
    had: dict[str, Item] | None = None,
) -> list[Item]:
    """Return what blocks, oldest first: each item of the list that passes the Blocking test, each
    row with no brief, and each alarm. `had` is what blocked in the last pass. A stall this pass
    cannot judge stays as it was. So does a row with no brief when the pass has no rows."""
    had = had or {}
    last = _last_events(run)
    context = {questions.item(asked)["key"]: asked.context for asked in questions.load(run.state)}
    found = []
    for one in listed:
        said = _why(run, one | {"context": context.get(one["key"], "")}, world, last)
        if said is None:
            continue
        case, why = said
        if case == "?":
            found += [had[one["key"]]] if one["key"] in had else []
        else:
            found.append(_blocks(run, one, case, why))
    if rows is None:
        found += [one for one in had.values() if one["kind"] == "brief"]
    else:
        found += _briefless(run, rows, listed)
    found += _alarms(run)
    return sorted(found, key=lambda one: (datetime.fromisoformat(one["since"]), one["key"]))


def _say(name: str, kind: str, items: list[Item]) -> list[str]:
    if not items and kind == "refresh":
        return [f"{name}: nothing blocks"]
    return [f"{name}: {kind} {one['line']}" for one in items]


def _body(run: Pass, kind: str, items: list[Item]) -> dict[str, Any]:
    """Build one body for the second target. A body of kind `events` has an empty `events` field, so
    every body of that kind has the same keys."""
    made = {"kind": kind, "project": run.project.name, "at": run.now.isoformat()}
    if kind == "events":
        made["events"] = []
    made |= {"say": _say(run.project.name, kind, items), "items": items}
    return redact(made, run.config.secrets())


def _opened(one: Item, had: dict[str, Item], last: str | None, now: datetime) -> str:
    """Return when an item began to block. That is the time that the last pass recorded, or, for an
    item new to the list since that pass, its own `since`, or else this pass. A gate that turns into
    a stall begins to block now, not when the crew asked it."""
    if one["key"] in had:
        return had[one["key"]].get("opened") or had[one["key"]]["since"]
    if last is None or datetime.fromisoformat(one["since"]) > datetime.fromisoformat(last):
        return one["since"]
    return now.isoformat()


def _age(one: Item, now: datetime) -> float:
    return (now - datetime.fromisoformat(one["opened"])).total_seconds()


def cadence(
    run: Pass,
    listed: list[Item] | None,
    rows: list[queue.Row] | None,
    world: World | None,
) -> list[Item]:
    """Judge what blocks, queue the second target's bodies, and rewrite `blocking.json`. Return what
    blocks, oldest first by when each item began to block (`opened`).

    `listed` is None for a blind pass. Such a pass judges nothing and keeps open what it had open,
    but it still sends what falls due. The first pass that writes the file sends no opening body,
    since what blocks then did not open in that pass. With no second target, `cadence` judges
    nothing and writes nothing, so the first pass that has a second target starts from what blocks
    then. `cadence` writes the marks before it queues the bodies. If a pass dies between the two,
    jbus sends that body once too few, never twice.
    """
    path = run.state / BLOCKS
    if run.box.blocking is None:
        return []
    kept = read_json(path, None)
    first = not isinstance(kept, dict)
    kept = kept if isinstance(kept, dict) else {}
    had: dict[str, Item] = kept.get("open", {})
    now = run.now
    found = list(had.values()) if listed is None else blocking(run, listed, rows, world, had)
    found = [one | {"opened": _opened(one, had, kept.get("at"), now)} for one in found]
    found.sort(key=lambda one: (datetime.fromisoformat(one["opened"]), one["key"]))
    opened = [one for one in found if one["key"] not in had]
    reminded: dict[str, str] = kept.get("reminded", {})
    still = {one["key"] for one in found}
    reminded = {
        key: at
        for key, at in reminded.items()
        if key in still or now - datetime.fromisoformat(at) < KEEP_REMINDED
    }
    due = [
        one
        for one in found
        if one["key"] not in reminded and _age(one, now) >= leftover.REMIND_MINUTES * 60
    ]
    reminded |= {one["key"]: now.isoformat() for one in due}
    period = int(now.timestamp() // (leftover.REFRESH_MINUTES * 60))
    refresh = not first and period > kept.get("period", period)
    open_now = {one["key"]: one for one in redact(found, run.config.secrets())}
    marks = {"at": now.isoformat(), "open": open_now, "reminded": reminded, "period": period}
    write_json(path, marks, mode=0o600)
    if opened and not first:
        run.box.post(_body(run, "events", opened))
    if due:
        run.box.post(_body(run, "reminder", due))
    if refresh:
        run.box.post(_body(run, "refresh", found))
    return found


def _keep(half: Half) -> None:
    """Rewrite the list, and store it for `cadence`. The holds come from `Half.shown`, which where
    the home merges is what `jmerge --check` said in this pass (`merge.shown`)."""
    run, world, rows, pulls = half.run, half.seen.world, half.table, half.shown.crews(half.crews)
    half.listed = keep(
        run, world, rows, pulls, half.roots, derived=half.derived, read_all=half.read
    )


STEPS = (
    verbs.Step("close", 20, "waiting.keep", _keep, ("sight",)),
    verbs.Step(
        "close",
        30,
        "waiting.cadence",
        lambda half: cadence(half.run, half.listed, half.table, half.seen.world),
    ),
)
