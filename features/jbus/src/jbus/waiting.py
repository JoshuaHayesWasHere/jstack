"""The one list of what waits on the user: `waiting-on-user.json` in a project's state
directory.

Each pass rewrites it. An item is one thing only the user can do, `{"kind", "key", "line",
"since"}` with what its kind adds, and the kinds are `KINDS`:

- `gate`: an open question jbus holds (`questions`), with `source` `jbus` and a line that
  says `question <n>`, the number `jbus answer` takes, or an open gate of the home's
  `gates.md` or of a scoped home's, with its `number`, `question`, `default`, the `home` it
  is in (nothing for the repo's own) and the `slug` that asked. A gate of a `gates.md` that
  jbus holds as a question, open or closed, is the question and is not read from the file;
- `row`: a row of the queue at `gate` that has no open pull request, with its `slug`: the
  line is the condition jbus recorded for it. A condition about a pull request is recorded
  once, for its crew or its message, and the row is at `gate` for that one pass;
- `left`: a row whose thread ended with a Result that leaves something, with its `slug`:
  the line is the row's `why`. It is one item until the Result leaves nothing or the row
  is gone. A row that merged with something left is listed while its thread is not at
  work, and from the pass after the one that told its thread of the merge. A row whose
  `Left:` line its home was told of (`leftover`) waits on that home and is not listed.
  It is listed, with the reason after its `why`, where it has no home to tell, or its home
  has not closed it in time;
- `approve`: a row with no approval, or one whose brief changed after it, with its `slug`:
  the line is the command that approves it;
- `hold`: a pull request `jmerge` holds, with its `number` and `url`;
- `config`: a webhook that is not set, or no sign-in to T3 Code.

An item of a slug that was removed from the queue (`queue.removed`) is on no list: `read`
leaves it out of what a pass left, and `keep` out of what it finds, so its going is no
change of the list and sends no event.

`key` names an item from pass to pass, and `since` is when a pass first listed it. A root
`stall` found is laid over the item of the same key: its line says more, and it has
`unblocks`. A row to approve is listed once, as `approve`, also when it sits at `gate` for
its changed brief. A pass that could not ask about a kind keeps the items of that kind it
had.

A pass that leaves other keys than it found sends one `waiting` event: how many wait, the
new ones by name (`short`), and each line with `+` for a new one and `-` for one that is
gone. It is for the chat only when the list gained what `asks` something new of the user:
a hold, an approval or a config item, which this event is the one telling of, or a gate
of a home's `gates.md`. A config item is a condition of jbus's own, and still asks: with no
sign-in to T3 Code jbus has stopped, and only the user can sign in. Any other change is
`quiet`: a pass that only took items off, a question jbus holds, which its own `gate` event
said when it was asked, and a row jbus put at `gate`, which is jbus's own condition. The
first pass that writes the list sends none. No webhook URL, key or token is in the file or
the event: `redact` takes each out of what a pass found, before it is compared with the
file.

What blocks is a part of this list, and the one function that decides it is `blocking`: an
item is open and nothing can move without the user. It is the design's Blocking test
(`features/jbus/docs/jbus.md`, "What blocks"), by these fields:

- (a) a `gate` whose `default` is empty, which only a home's `gates.md` can have since `jbus
  gate` refuses a question with none, or whose question or context names one of `PAUSE`.
  jstack keeps no always-pause list of its own: `PAUSE` is it, read off the words;
- (b) an `approve` item, a row whose `brief_sha` is empty since nobody approved it or whose
  brief changed after the go, and a row of the queue that waits with no brief in
  `briefs/<slug>.md`;
- (c) a `hold`, a pull request `jmerge` holds;
- (d) a stall: a `left` item, a leftover that is the user's since its home did not close it
  in `CLOSE_MINUTES` or has none; a `config` item; a streak of `alert` that alerted, of this
  project or of the pass, but for the second target's own; and a gate that has a default
  whose slug wrote no event for `CLOSE_MINUTES` and has no thread at work.

A gate with a default whose thread still writes, a `row` jbus put at `gate`, and a leftover
its home has are not blocking.

`cadence` keeps `blocking.json`, `{"open", "reminded", "period"}`, and queues the second
target's bodies (`wake.Box.post`): the items that opened in a pass, one `reminder` for each
item still open `REMIND_MINUTES` after it opened, and a `refresh` of every open item, oldest
first, on the pass that begins a new `REFRESH_MINUTES`, also when none is open. An item is
named by its key, the list's own, so a question by its number. A pass that cannot judge a
stall, or is blind, closes nothing it had.

The file had another name once (`jbus.old_names`). `read` takes a file of that name where there is
none of this one, each line by the name its event has now, and `keep` removes it once it has
written this one.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
from collections.abc import Collection
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsettings
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
from jbus.wake import CONDITION, Pass, Slot, renamed
from jbus.watch import LIVE, World

if TYPE_CHECKING:
    from jbus.cli import Half

EVENTS = {"waiting": "user"}
EVENT = "waiting"


@dataclass(frozen=True)
class Kind:
    """A kind of what waits on the user, and how the page shows it: `label` heads its list in
    the drawer of what waits on the user, `verb` is the button of an item of it, and `shown`
    is its place in that drawer, where a pass lists the kinds in the order of `KINDS`."""

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
    Kind("config", "Setup jbus lacks", "Set up", 6),
)
ASKS = ("hold", "approve", "config")

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
    """The name of each kind, in the order of `KINDS`."""
    return [one.name for one in KINDS]


def verb(name: str) -> str:
    """The button of an item of the kind `name`."""
    return next(one.verb for one in KINDS if one.name == name)


def shown() -> list[dict[str, Any]]:
    """The kinds as the page has them, in the order it shows them."""
    return [asdict(one) for one in sorted(KINDS, key=lambda one: one.shown)]


def kind(key: str) -> str:
    """The kind a key names: `#<n>` is a hold, and any other says it before its colon."""
    if key.startswith("#"):
        return "hold"
    named = key.partition(":")[0].removeprefix("re-")
    return named if named in kinds() else "config"


def short(one: Item) -> str:
    """An item in a few words: its kind, and its number for a gate or a hold, its slug for a
    row, or what its key names."""
    by = "number" if one["kind"] in ("gate", "hold") else "slug"
    what = one.get(by) or one["key"].rpartition(":")[2].lstrip("#")
    home = f"{one['home']}#" if one.get("home") else ""
    return f"{'question' if questions.listed(one) else one['kind']} {home}{what}"


def read(state: Path) -> list[Item] | None:
    """The list as the last pass left it, or None where no pass has written one.

    A list from before items had a kind names each by `root`: it is read as its key.
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
    """The command that records the user's go for the brief whose sha256 starts with `sha`,
    with the three things the go can rest on."""
    return f"jbus --project {name} queue approve {slug} --sha {sha} with {queue.BASIS}"


def gates(
    home: Path, held: list[questions.Question] | None = None, gone: Collection[str] = ()
) -> list[Item]:
    """The open gates of the home's `gates.md` and of each scoped home's, then the open
    questions of `held`. A gate of a file that is one of `held` is counted once, as the
    question: open, or not at all once it is closed. One that a slug in `gone` asked is
    left out."""
    held = held or []
    keys = {one.key for one in held}
    found = []
    for file, number, asked, body, key in mirror.home_gates(home):
        if not mirror.field(body, "Status").startswith("open") or key in keys:
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
                "default": mirror.field(body, "Default"),
                "home": where,
                "slug": mirror.asker(body),
            }
        )
    found += [questions.item(one) for one in held if one.answer is None]
    return [one for one in found if one["slug"] not in gone]


def unapproved(run: Pass, rows: list[queue.Row]) -> list[Item]:
    """The rows that were not launched because nobody approved them."""
    found = []
    for row in sorted(rows, key=queue.order):
        slug = row["slug"]
        if row.get("status", "queued") == "queued" and not row.get("approved"):
            sha = queue.brief_sha(queue.brief(run.state, slug) or "")[:12]
            line = f"approve {slug}: {approve(run.project.name, slug, sha, run.user)}"
            found.append({"kind": "approve", "key": f"approve:{slug}", "line": line, "slug": slug})
    return found


def asks(one: Item) -> bool:
    """Whether an item the list gained asks something new of the user."""
    if one["kind"] == "gate":
        return not questions.listed(one)
    return one["kind"] in ASKS


def gated(run: Pass, world: World, rows: list[queue.Row]) -> list[Item]:
    """The rows at `gate` that this pass recorded a condition for, and that have no open pull
    request. One a lost reply of T3 Code keeps there for a pass asks nothing of the user."""
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
    """The rows whose Result leaves something that no thread is at work on
    (`leftover.ended`), but for one its home has: the line of any other that has a record
    says why it is the user's."""
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
    """The open pull requests `jmerge` holds: by what it printed in this pass, or, where the
    home merges, by the last line it logged for each. A pull request that is still open and
    that `jmerge` said nothing of keeps the hold it had: `jmerge` did not run.

    A pass that could not ask T3 Code or GitHub has no `world`, and takes `jmerge` at its
    word: a pull request it holds in this pass is open, and one it said nothing of keeps
    the hold it had. So a hold is told also where nothing but `jmerge` answers. `keep`
    asks this only where `jmerge` ran in the pass: the last lines a home logged are never
    taken out, and with no `world` nothing says which of them are of a pull request that
    is still open."""
    lines = [line.strip() for line in pulls]
    if merge.home_thread(run):
        last = read_json(run.home / "merge.log.last", {})
        lines = [line for line in (last.values() if isinstance(last, dict) else [])]
    lines = [line for line in lines if isinstance(line, str)]
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
    """Rewrite the list, and send one event when its keys are not the ones it had: for the
    chat when it gained what `asks` something new of the user, and `quiet` for any other
    change.

    `roots` is what `stall.tell` gives. `derived` says the rows' statuses are this pass's,
    and `read_all` that `dispatch` read every row of the queue in it.

    A condition `dispatch` records for a row is recorded only in a pass in which it reads
    that row with a slot free. So a row the list has at `gate` stays there through a pass that sent
    none for it, while it is not launched and `dispatch` did not say what else it waits
    for: it did not read the row, or the pass was full, and it held the row's gate back
    (`Pass.held`) or recorded `Slot` for it.
    """
    was = read(run.state)
    before = {one["key"]: one for one in was or []}

    def had(of: str) -> list[Item]:
        """What the list held of a kind this pass cannot judge. A root is `stall`'s to give."""
        kept = (one for one in before.values() if one["kind"] == of)
        return [{name: value for name, value in one.items() if name != "unblocks"} for one in kept]

    try:
        found = gates(run.home, questions.read(run.state), run.removed)
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
    stale = world is None and merge.home_thread(run)
    found += had("hold") if stale else holds(run, world, pulls, had("hold"))
    secret = run.config.secrets()
    items = {one["key"]: one for one in redact(found, secret)}
    for root in redact(roots, secret):
        key = root["key"]
        named = {"slug": key.partition(":")[2]} if kind(key) == "approve" else {}
        items[key] = {"kind": kind(key), **named, **items.get(key, {}), **root}
    for key in [key for key in items if kind(key) == "approve"]:
        items.pop(f"row:{key.partition(':')[2]}", None)
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
        loud = None if any(map(asks, new)) else "quiet"
        run.box.send("", EVENT, line, "\n".join(marked), loud=loud)
    write_json(path(run.state), listed, mode=0o600)
    for file in _named_before(run.state):
        with contextlib.suppress(OSError):
            file.unlink()
    return listed


def paused(text: str) -> str:
    """The always-pause name a text falls under, or nothing."""
    return next((name for name, rule in PAUSE.items() if re.search(rule, text, re.I)), "")


def _last_events(run: Pass) -> dict[str, datetime]:
    """When each slug last had an event in the log."""
    last: dict[str, datetime] = {}
    for one in run.box.log():
        slug = one.get("slug")
        if slug:
            at = datetime.fromisoformat(one["at"])
            last[slug] = max(last.get(slug, at), at)
    return last


def _at_work(world: World, slug: str) -> bool:
    """Whether any thread of the slug is at work: a crewmate beside its reviewer counts."""
    return any(
        thread.get("status") in LIVE and not thread.get("settled")
        for thread in world.threads.get(slug, [])
    )


def _why(
    run: Pass, one: Item, world: World | None, last: dict[str, datetime]
) -> tuple[str, str] | None:
    """The case of the Blocking test an item of the list is, and why, or None where it is
    not blocking. `("?", "")` is a stall this pass cannot judge: it has no `world`."""
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
    """The streaks that alerted and still stand, of this project or of the pass. The second
    target's own is left out: it would be posted to the webhook that fails."""
    name = run.project.name
    mine = {alert.PASS, alert.webhook(name), alert.top_level(name), alert.jmerge(name)}
    found = []
    for key, one in sorted(alert.streaks(run.config.state_dir).items()):
        if key in mine and one.get("alerted"):
            line = f"alert: {key} failed {one.get('count')} times in a row"
            item = {"key": f"alarm:{key}", "kind": "alarm", "line": line, "since": one["since"]}
            found.append(_blocks(run, item, "d", "a jbus alarm"))
    return found


def _briefless(run: Pass, rows: list[queue.Row] | None, listed: list[Item]) -> list[Item]:
    """The rows that wait to launch with no brief stored for them."""
    keys = {one["key"] for one in listed}
    found = []
    for row in sorted(rows or [], key=queue.order):
        slug = row["slug"]
        if row.get("status", "queued") not in ("queued", "gate") or f"approve:{slug}" in keys:
            continue
        if slug in run.removed or queue.brief(run.state, slug) is not None:
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
    """What blocks, oldest first: each item of the list that passes the Blocking test, each
    row with no brief, and each alarm. `had` is what blocked in the last pass: a stall this
    pass cannot judge, and a row with no brief where it has no rows, stays as it was."""
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
    """One body for the second target. One of kind `events` has `events`, empty, so every
    body of that kind has the same keys."""
    made = {"kind": kind, "project": run.project.name, "at": run.now.isoformat()}
    if kind == "events":
        made["events"] = []
    made |= {"say": _say(run.project.name, kind, items), "items": items}
    return redact(made, run.config.secrets())


def _opened(one: Item, had: dict[str, Item], last: str | None, now: datetime) -> str:
    """When an item began to block: as the last pass had it, or for one new to the list
    since that pass its own `since`, or this pass. A gate that turns into a stall begins to
    block now, not when it was asked."""
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
    """Judge what blocks, queue the second target's bodies, and rewrite `blocking.json`. The
    answer is what blocks, oldest first by when each began to block (`opened`). `listed` is
    None for a blind pass: it judges nothing, keeps what it had open, and still sends what
    falls due. The first pass that writes the file sends no opening body: what blocks then
    did not open in it. With no second target it judges nothing and writes nothing, so the
    first pass that has one starts from what blocks then. The marks are written before the
    bodies are queued: a pass that dies between the two sends a body once too few, never
    twice."""
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
    """Rewrite the list, and keep it for `cadence`."""
    run, world, rows = half.run, half.seen.world, half.table
    half.listed = keep(
        run, world, rows, half.users, half.roots, derived=half.derived, read_all=half.read
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
