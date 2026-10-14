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

The file had another name once (`jbus.old_names`). `read` takes a file of that name where there is
none of this one, each line by the name its event has now, and `keep` removes it once it has
written this one.
"""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Collection
from datetime import datetime
from pathlib import Path
from typing import Any

import jsettings
from jbus import (
    leftover,
    merge,
    mirror,
    old_names,
    questions,
    queue,
    read_json,
    redact,
    write_json,
)
from jbus.wake import CONDITION, Pass, Slot, renamed
from jbus.watch import World

EVENTS = {"waiting": "user"}
EVENT = "waiting"
KINDS = ("gate", "row", "left", "approve", "hold", "config")
ASKS = ("hold", "approve", "config")

Item = dict[str, Any]


NAME = "waiting-on-user.json"


def path(state: Path) -> Path:
    return state / NAME


def _named_before(state: Path) -> list[Path]:
    return [state / f"{was}.json" for was, now in old_names().items() if f"{now}.json" == NAME]


def kind(key: str) -> str:
    """The kind a key names: `#<n>` is a hold, and any other says it before its colon."""
    if key.startswith("#"):
        return "hold"
    named = key.partition(":")[0].removeprefix("re-")
    return named if named in KINDS else "config"


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
    listed = sorted(items.values(), key=lambda one: KINDS.index(one["kind"]))
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
