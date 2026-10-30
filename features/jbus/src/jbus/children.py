"""jbus's watch of the homes: what a home has out, and the stall of a home that has gone quiet
with work out.

A child home is a scope of the repo's home: a directory of the state with a `home-id` or a
`Was home:` line. The root home, the state directory itself, is watched as a child is, under the
key `/` in `children.json`, which no scope's name can be. What a home has out (`out`) is read
from jbus's own records, never from the home: each queue row of a brief of its that is not over,
each entry of its plan whose go holds with no live row (`plan.owed`), each crew or reviewer
thread of such a brief that the last pass found unsettled, each question jbus holds for it, and
each open gate of its `gates.md`. A row that is queued and not launched is out, and it has no
crew yet.

`jbus out --scope <scope>` prints one line for each, and nothing when nothing is out. The
handoff skill lists it in the note of a scope it archives, whose work is the root home's from
then on (`RetireHandsOver` in `features/home/spec/HomeTree.tla`). It prints `unknown:` and ends 1 when jbus's last pass is too
old for its list of threads to be trusted.

`watch`, a step of each pass, flags a home that has been quiet for its patience with work out, or
a routine that missed its beat (`StallFlagged`). A routine is a scope whose directory has a
`rhythm` file, its beat in minutes, and it is watched whatever it has out. Any other home is
watched while it has a crew, a pull request, an owed entry, a question or a gate out, and the root
only while it has one of the first three: a question or a gate waits on the user. A home is
quiet from the last thing it did that jbus can see: a write of one of its crew or reviewer
threads, a change in what it has out, or, before jbus nudged it in this spell, a write of its
home thread. A message queued to the home thread is no write (`threads`). A turn jbus's own nudge
started is no progress, so once nudged the home thread's writes do not end the spell. At its
patience (`PATIENCE`, or the routine's beat) jbus nudges the home thread and the user hears of
it at once, the first strike (`FirstStrike`); a patience after that nudge it nudges it again; a
patience after the second it asks the user, and nudges no more (`NudgesBounded`,
`AsksAfterTwo`). Each step waits a patience after the last, so a home first checked long after it
went quiet still gets that time to act on a nudge. `children.json` keeps each spell: when it
began, how far it went, when it took its last step, and what the home had out.
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import jsettings
from jbriefs import below
from jbriefs import home as homes
from jbus import (
    Config,
    Refused,
    alert,
    mirror,
    outbox,
    plan,
    questions,
    queue,
    read_json,
    record,
    verbs,
    write_json,
)
from jbus.passes import Pass
from jbus.t3 import Client, T3Error, T3Refused

EVENTS = {"home-stall": "quiet"}
STALL = "home-stall"
FILE = "children.json"
PATIENCE = 60
"""The minutes a child with work out may be quiet before the root flags it."""
STALE = 10
"""The minutes after which the last pass's list of threads is too old to say what is out."""
QUEUED = ("row queued", "row gate")
USERS = ("out question ", "out gate ")
"""What waits on the user and not on the home: the root is not watched for it, since it cannot
be retired."""
STEPS_OF = ("calm", "nudged1", "nudged2", "asked")
ROOT = "/"
"""The root home's key in `children.json`: a scope is a directory, so none is named `/`."""
NUDGE = (
    "jbus: {home} has had {what} out and has done nothing jbus can see for {minutes} "
    "minutes. Carry on with your plan: read `{plan}` and your briefs' last "
    "Results, and pick up each thread that stopped, as the home skill's \"Picking up a thread "
    'that stopped" says. This is nudge {n} of 2; after the second, the user is asked.'
)


def out(root: Path, scope: Path, state: Path, threads: list[dict[str, Any]]) -> list[str]:
    """Return a line for each thing the home at `scope`, a scope or the root itself, has out, in
    a fixed order: its rows that are not over, its entries whose go holds with no live row, its
    crew and reviewer threads in `threads` (the last pass's), its questions, and its open
    gates."""
    rows = queue.load(state)
    texts = {row["slug"]: queue.brief(state, row["slug"]) or "" for row in rows}
    for kind in ("tasks", "scouts"):
        for file in sorted((root / kind).glob("*.md")):
            texts.setdefault(file.stem, file.read_text(errors="replace"))
    mine = {slug for slug, text in texts.items() if homes.home_of(root, text) == scope}
    found = [
        f"out {row['slug']}: row {row.get('status') or 'queued'}"
        for row in rows
        if row["slug"] in mine and not queue.over(row)
    ]
    found += [
        f"out entry {made.entry}: go holds, no live row"
        for made in plan.owed(state, root, rows)
        if made.scope == ("" if scope == root else scope.name)
    ]
    found += [
        f"out {one['slug']}: {one['role']} thread {one['id']} is not settled"
        for one in threads
        if one.get("role") in ("crew", "reviewer") and one.get("slug") in mine
    ]
    own = "home" if scope == root else f"home-{scope.name}"
    found += [
        f"out question {one.number}: {one.question}"
        for one in questions.load(state)
        if one.answer is None and (one.slug == own or one.slug in mine)
    ]
    found += [
        f"out gate {number}: {asked}"
        for number, asked, _, body in mirror.gates(_read(scope / "gates.md"))
        if below.line(body, "Status:").startswith("open")
    ]
    return found


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _stale(config: Config, name: str, now: datetime) -> str:
    """Say why the last pass's list of the project's threads cannot be trusted, or nothing: the
    pass is too old, or it could not ask T3 Code or GitHub about this project, so the list is
    the one an earlier pass left."""
    kept = record.read(config)
    silent = kept.get("silent")
    if isinstance(silent, dict) and silent.get(name):
        return f"jbus's last pass could not ask {silent[name]} about {name}"
    started = kept.get("started")
    try:
        at = datetime.fromisoformat(str(started))
    except ValueError:
        return "jbus has recorded no pass"
    minutes = int((now - at).total_seconds() // 60)
    return f"jbus's last pass is {minutes} minutes old" if minutes > STALE else ""


def _out(args: argparse.Namespace, config: Config) -> int:
    """`jbus out --scope <scope>`: say what the scoped home still has out, and nothing when
    nothing is."""
    project = verbs.here(config, args.project)
    root = config.home(project)
    scope = root / args.scope
    if not (scope / "plan.md").exists():
        raise Refused(f"refused: {scope} has no plan.md, so {args.scope} is no scoped home")
    old = _stale(config, project.name, queue.clock())
    if old:
        print(f"unknown: {old}, so its list of threads cannot say what {args.scope} has out")
        return 1
    state = config.state_dir / project.state
    said = out(root, scope, state, record.seen(config, project.name))
    if said:
        print("\n".join(said))
    return 0


def _outs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", required=True, help="the scoped home whose work is asked of")


VERBS = (verbs.Verb("out", "say what a scoped home still has out, for its retire", _outs, _out),)


def _rhythm(scope: Path) -> int:
    """The routine's beat in minutes, or 0 for a child that is no routine."""
    text = _read(scope / "rhythm").strip()
    return int(text) if text.isdigit() and int(text) > 0 else 0


def _at(stamp: str) -> datetime | None:
    try:
        return jsettings.when(stamp)
    except (TypeError, ValueError):
        return None


def _send(run: Pass, client: Client, thread: str, message: str, key: str) -> bool:
    """Queue one message to the child's home thread, once for the key. Return whether it is
    done: sent, or refused for good."""
    if key in run.box.sent():
        return True
    name = key.split("|")[1]
    try:
        went = outbox.send(
            run,
            client,
            thread=thread,
            row=name,
            key=key,
            text=message,
            template=STALL,
            needs="act",
        )
    except T3Refused as error:
        run.say(f"wait {name}: T3 Code refused {thread} its nudge ({error})")
    except T3Error as error:
        run.say(f"wait {name}: {thread} could not be nudged ({error})")
        return False
    else:
        if not went:
            return False
    run.box.mark(key)
    return True


def watch(run: Pass, client: Client, threads: list[dict[str, Any]] | None) -> None:
    """Count each home's quiet, the root's and each child's, and nudge, tell or ask for each one
    that is due. See the module. A queue or a question file that does not parse says nothing of
    what is out: the pass gates it, and the watch waits for it."""
    if threads is None:
        return
    try:
        queue.load(run.state)
        questions.read(run.state)
    except (queue.Unparsable, questions.Unparsable):
        return
    was: dict[str, Any] = read_json(run.state / FILE, {})
    kept: dict[str, Any] = {}
    for scope in [run.home, *(one for one, _, _ in homes.scopes(run.home))]:
        thread = homes.thread_of(scope)
        lines = out(run.home, scope, run.state, threads)
        if scope == run.home:
            lines = [line for line in lines if not line.startswith(USERS)]
        launched = [line for line in lines if line.split(": ", 1)[1] not in QUEUED]
        beat = _rhythm(scope)
        if not thread or not (launched or beat):
            continue
        name = ROOT if scope == run.home else scope.name
        seen = hashlib.sha256("\n".join(line.split(": ")[0] for line in launched).encode())
        sig = seen.hexdigest()[:12]
        prev = was.get(name, {})
        step = prev.get("step", "calm") if prev.get("sig") == sig else "calm"
        slugs = {line.split()[1].rstrip(":") for line in lines}
        writes = [
            _at(str(one.get("wrote") or one.get("updatedAt")))
            for one in threads
            if (one.get("role") in ("crew", "reviewer") and one.get("slug") in slugs)
            or (one.get("id") == thread and step == "calm")
        ]
        latest = max((at for at in writes if at), default=None)
        since = _at(prev.get("since", "")) if prev.get("sig") == sig else None
        if since is None:
            since = latest or run.now
            step = "calm"
        elif latest and latest > since:
            since, step = latest, "calm"
        patience = beat or PATIENCE
        quiet = int((run.now - since).total_seconds() // 60)
        rank = STEPS_OF.index(step)
        spell = {"since": since.isoformat(), "step": step, "sig": sig}
        last = _at(prev.get("at", "")) if rank else None
        start = last or since + timedelta(minutes=patience * rank)
        if last:
            spell["at"] = last.isoformat()
        if step != "asked" and run.now - start >= timedelta(minutes=patience):
            what = f"{len(launched)} things" if launched else "its beat"
            if _act(run, client, name, thread, spell, quiet, what):
                spell["step"] = STEPS_OF[rank + 1]
                spell["at"] = run.now.isoformat()
        kept[name] = spell
    for name, spell in was.items():
        if spell.get("step", "calm") != "calm" and kept.get(name, {}).get("step", "calm") == "calm":
            alert.retire(run.config.state_dir, _stall(run, name))
    if kept != was:
        write_json(run.state / FILE, kept)


def _stall(run: Pass, name: str) -> str:
    """The key of the alert a home's stall raises, which ends when its spell does."""
    return f"{STALL} {run.project.name} {name}"


def _act(
    run: Pass, client: Client, name: str, thread: str, spell: dict[str, Any], quiet: int, what: str
) -> bool:
    """Take the next step of a child's spell: a nudge, with the first strike told to the user,
    a second nudge, or the question to the user. Return whether it is done. While the home's
    instance is capped no step is taken: the home could not act on it, so the step waits for the
    reset. The outbox holds a nudge, and the question waits here."""
    step, since = spell["step"], spell["since"]
    home = "the root home" if name == ROOT else f"the home {name}"
    if step in ("calm", "nudged1"):
        n = 1 if step == "calm" else 2
        plan = "jbus plan" if name == ROOT else f"jbus plan --scope {name}"
        text = NUDGE.format(home=home, what=what, minutes=quiet, plan=plan, n=n)
        if not _send(run, client, thread, text, f"{STALL}|{name}|{since} {n}"):
            return False
        run.say(f"{STALL} {name}: nudged its home, thread {thread}, {n} of 2")
        if n == 2:
            return True
        line = f"{STALL} {name}: {home} has had {what} out and been quiet {quiet} min"
        line = f"{line}; jbus nudged it, thread {thread}"
        if run.find(name, STALL, line, key=f"{since} strike"):
            alert.raise_(run.config, _stall(run, name), line, owner=run.project.name, now=run.now)
        return True
    if outbox.capped(run, client, thread):
        return False
    line = f"{STALL} {name}: {home} is still quiet after two nudges, {quiet} min"
    line = f"{line}: get it going, or retire it; thread {thread}"
    if run.find(name, STALL, line, key=f"{since} ask"):
        alert.raise_(run.config, _stall(run, name), line, owner=run.project.name, now=run.now)
    return True


STEPS = (
    verbs.Step(
        "after-expedite",
        17,
        "children.watch",
        lambda half: watch(half.run, half.client, half.out),
        ("client",),
    ),
)
