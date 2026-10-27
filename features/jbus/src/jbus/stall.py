"""This module finds what waits on the user. For each approved row that cannot move, this module
follows the row's `depends` links up to a root.

A root is one thing only the user can do, and it has a key:

- `#<n>`: hand-merge, with `jmerge --accept`, a green and reviewed pull request that `jmerge` holds.
  The line names the one safety fact that the review proved at the head;
- `re-approve:<slug>`: approve again a brief that changed after their go;
- `approve:<slug>`: approve a row that an approved row depends on;
- `config:<project>`: sign in to T3 Code.

`walk` starts at every approved row that was not launched and follows its `depends` links
(`Pass.reasons`, which `dispatch` records). A stacked link (`jbus.stack`) launched before its
base merged, and its own merge still waits on its base's: `walk` starts at it too, and follows it
to its base. It stops at a root or at progress: a thread, a pull
request on which `jmerge` waits, a slot, or a gate that the Chef already has. `tell` sends one
`waiting-on-user` event for each root, and sends that event again each hour while the root is still
open. `tell` also rewrites `stall.json`, which records when jbus first saw each root and when jbus
last sent the root. `tell` returns the roots that are still open, and `waiting` lists them with
everything else that waits on the user.

`guarded` handles what waits on a crew. What waits on a crew is a pull request that changes a
guarded path. `jmerge` keeps such a pull request on a `wait` line, and that line wakes nobody. The
line may say that the head has no proven safety fact, while the head is a fix pushed after the last
review. Then `guarded` asks the crew for the one scoped review that proves the fix, once per head.
When the line still says the same of the same head after `PASSES` passes, `guarded` logs one
`stall` event, which is quiet and in the digest. `guarded.json` counts the passes.

`hung` handles a turn that hangs: a thread that is out and has written nothing for too long
(`live`). `hung` sends one `stall` event for that thread and that run, and writes one line of
`hung.jsonl`. A later pass adds a line that says what became of the turn: it wrote again by itself,
someone interrupted it, or it ended. jbus interrupts nothing and sends the thread nothing.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

import jsettings
from jbriefs import below, findings
from jbriefs import parse as briefs
from jbus import mirror, queue, read_json, rebase, verbs, waiting, write_json
from jbus.dispatch import launched
from jbus.merge import parse
from jbus.passes import Changed, Depends, Pass
from jbus.t3 import Client
from jbus.wake import notify
from jbus.watch import World, task_brief
from jmerge import stacked as stacks
from jmerge.lines import READY

if TYPE_CHECKING:
    from jbus.cli import Half

EVENTS = {"waiting-on-user": "quiet", "stall": "quiet"}
EVENT = "waiting-on-user"
AGAIN = 60 * 60

_GUARDED = re.compile(r"guarded \(touches \S+\), .+")
_UNPROVEN = re.compile(r"\bno proven safety fact at ([0-9a-f]{12})\b")
STALL = "stall"
PASSES = 10
REVIEWING = 30
HUNG = "hung.jsonl"
WROTE, INTERRUPTED, ENDED = "wrote again", "interrupted", "ended"
BECAME = {"interrupted": INTERRUPTED, "cancelled": INTERRUPTED} | dict.fromkeys(
    ("completed", "failed", "rolled_back"), ENDED
)

Roots = dict[str, tuple[str, list[str]]]


def hand_merge(run: Pass, number: int, url: str, why: str) -> str:
    """Return the step the user takes for a held pull request: the command that merges it by hand,
    with the safety fact that its review proved.

    `hand_merge` asks `jmerge` what an accept would do, with `--check`, which merges nothing. Where
    `jmerge` would refuse, there is no command to give, and the returned line says what the pull
    request lacks.
    """
    held = f"hand-merge #{number} {url}: {why}"
    ran = run.run("jmerge", "--accept", str(number), "--check")
    lines = [line.strip() for line in ran.stdout.splitlines()]
    ready = next((m for m in map(READY.match, lines) if m and int(m[1]) == number), None)
    if ready:
        user = run.user
        accept = f'jmerge --accept {number} --by {user.user} --at "{user.form()}"'
        return f"{held}; {ready[2]}; {accept}"
    said = (line for line in map(parse, lines) if line and line.word != "merged")
    short = next((line.reason for line in said if line.reason and line.number == number), "")
    return f"{held}; not yet, {short or f'jmerge --accept {number} --check did not answer'}"


def walk(run: Pass, world: World, rows: list[queue.Row], pulls: list[str]) -> Roots:
    """Return the roots that end the chains of approved rows that wait, each root with the rows that
    it unblocks."""
    name = run.project.name
    user = run.user
    table = {row["slug"]: row for row in rows}
    said = (line for line in map(parse, pulls) if line and line.word == "hold" and line.reason)
    holds = {line.number: (line.name, line.reason) for line in said}
    merges: dict[int, str] = {}

    def on_base(slug: str) -> str:
        """The row a stacked link still sits on, or nothing: its merge waits on that row's."""
        found = stacks.of(task_brief(run, slug)) if table.get(slug, {}).get("depends") else None
        return found.slug if found and not found.at else ""

    def roots(slug: str, seen: set[str]) -> dict[str, str]:
        if slug in seen:
            return {}
        seen.add(slug)
        on = on_base(slug)
        pull = world.open.get(slug)
        if pull:
            number = pull["number"]
            if number not in holds:
                return roots(on, seen) if on else {}
            if number not in merges:
                merges[number] = hand_merge(run, number, *holds[number])
            return {f"#{number}": merges[number]}
        if on and (slug in world.threads or launched(run, slug)):
            return roots(on, seen)
        if slug in world.merged or slug in world.threads or launched(run, slug):
            return {}
        reason, row = run.reasons.get(slug), table.get(slug)
        if isinstance(reason, Changed) and row:
            command = waiting.approve(name, slug, reason.sha, user)
            lines = "; ".join(reason.lines)
            said = f"brief now {reason.sha}, approved {reason.was}; changed: {lines}"
            action = f"re-approve {slug} ({said}): {command}"
            return {f"re-approve:{slug}": action}
        if isinstance(reason, Depends):
            found: dict[str, str] = {}
            for other in reason.slugs:
                found |= roots(other, seen)
            return found
        if reason is None and row and not row.get("approved"):
            sha = queue.brief_sha(queue.brief(run.state, slug) or "")[:12]
            return {f"approve:{slug}": f"approve {slug}: {waiting.approve(name, slug, sha, user)}"}
        return {}

    found: Roots = {}
    for row in sorted(rows, key=queue.order):
        if row["slug"] in run.reasons or on_base(row["slug"]):
            for key, action in roots(row["slug"], set()).items():
                found.setdefault(key, (action, []))[1].append(row["slug"])
    return found


def config(run: Pass, client: Client | None, rows: list[queue.Row] | None) -> Roots:
    """Return the project's own root: no sign-in to T3 Code."""
    if client is not None:
        return {}
    unblocks = [row["slug"] for row in rows or [] if row.get("status") == "queued"]
    return {f"config:{run.project.name}": ("run jbus t3 login", unblocks)}


def done(run: Pass, world: World | None, rows: list[queue.Row] | None, key: str) -> bool:
    """Say whether the user has done the thing that a root asks for, so that the root is closed.
    `done` uses only facts that need no row judged."""
    kind, _, slug = key.partition(":")
    if key.startswith("#"):
        return world is not None and key not in {f"#{p['number']}" for p in world.open.values()}
    if rows is None or kind not in ("approve", "re-approve"):
        return False
    row = next((row for row in rows if row["slug"] == slug), None)
    if row is None or kind == "approve":
        return row is None or bool(row.get("approved"))
    return queue.approved_text(row, queue.brief(run.state, slug) or "")


def tell(
    run: Pass,
    client: Client | None,
    world: World | None,
    rows: list[queue.Row] | None,
    pulls: list[str],
) -> list[waiting.Item]:
    """Send each root that is due, say which roots cleared, and rewrite `stall.json`. Return the
    roots that are still open, each `{"key", "line", "since", "unblocks"}`.

    `tell` also raises each due root on the desk. `tell` prints the root when the project's first
    route's last send failed. A pass judges no row when it could not ask T3 Code or GitHub, could
    not read the queue, or ran with dispatch off. Such a pass keeps the roots that it had as they
    were, and neither sends nor clears them, except a root that is plainly `done`. `tell` also keeps
    the root of a held pull request as it was when the pull request is still open and `jmerge` said
    nothing of it in this pass. In that case either `jmerge` did not run, or the home merges.
    """
    name = run.project.name
    user = run.user
    on = run.config.dispatch and not run.config.stop_path.exists()
    judged = on and client is not None and world is not None and rows is not None
    silent = {f"#{pull['number']}" for pull in (world.open.values() if world else [])} - {
        f"#{line.number}" for line in map(parse, pulls) if line
    }
    found = walk(run, world, rows, pulls) if judged else {}
    found |= config(run, client, rows)
    was: dict[str, Any] = read_json(run.state / "stall.json", {})
    before = {one["key"]: one for one in waiting.read(run.state) or [] if "unblocks" in one}
    quiet = run.box.marks().get("failed", 0) > 0
    kept: dict[str, Any] = {}
    shown = []
    for key, (action, unblocks) in found.items():
        entry = was.get(key) or {"since": run.now.isoformat()}
        since = user.clock(datetime.fromisoformat(entry["since"]))
        line = (
            f"{EVENT} {name}: {action} · unblocks {', '.join(unblocks) or 'none'} · since {since}"
        )
        sent = entry.get("sent")
        if not sent or (run.now - datetime.fromisoformat(sent)).total_seconds() >= AGAIN:
            run.box.send(key, EVENT, line)
            entry = {**entry, "sent": run.now.isoformat()}
            notify(line)
            if quiet:
                run.say(line)
        kept[key] = entry
        shown.append({"key": key, "line": action, "since": entry["since"], "unblocks": unblocks})
    for key, entry in was.items():
        if key in kept:
            continue
        cleared = key.startswith("config:") or (judged and key not in silent)
        if cleared or done(run, world, rows, key):
            run.say(f"cleared {key}")
        else:
            kept[key] = entry
            shown += [before[key]] if key in before else []
    if kept != was:
        write_json(run.state / "stall.json", kept)
    return shown


def reviewed(brief: str) -> str:
    """Return the head that the last review saw when it ran, as the crew skill's "A second pass"
    reads it."""
    heads = [one.head for one in findings.triage(brief).sections if one.ran]
    return heads[-1] if heads else ""


def launched_for(brief: str, head: str) -> bool:
    """Say whether the crew already launched the scoped review of this head. The sign is a
    `Scoped reviewer:` line that ends `of <head>`, as the crew skill's "A second pass" reads it. A
    line that names another head is no launch for this head. Neither is a line that names no head,
    as lines written for a rebase did before jbus's ask named the head. Neither is the line that a
    session writes when it had no launch tool, `Scoped reviewer: none, ...`."""
    return any(map(below.launched, below.reviewers(brief, "Scoped reviewer", head)))


def prove(run: Pass, client: Client, world: World, number: int, slug: str, short: str) -> None:
    """Ask the crew of a done brief for the scoped review of a fix that no review has proved.

    `prove` asks nothing when the review is of the commit that `jmerge` names. That review's proof
    is unproven or failed, and a second review of the same commit would not change it. Such a wait
    is a stall. `prove` also asks nothing when the crew wrote a `Scoped reviewer:` line for the
    head, including a line that says the crew had no launch tool. That crew has told its home and
    has nothing more to do.

    The commit that `jmerge` names is the head. For a rebase that changed the patch, the named
    commit is the commit before the head instead: `jmerge` compared the head with that commit and
    found no proof there, so the fix was rebased after no review proved it. Either way, `prove` asks
    for a review of the head.
    """
    head = world.open[slug].get("headRefOid", "")
    named = _UNPROVEN.search(short)
    if not named or f"proof|{slug}|{head[:12]}" in run.box.sent():
        return
    brief = task_brief(run, slug)
    changed = [(before, to) for moved, before, to in below.rebases(brief) if moved]
    rebased = [before for before, to in changed[-1:] if to == head]
    at = (rebased or [head])[0]
    saw = reviewed(brief)
    done = below.line(mirror.last_result(brief), "Status:") == "done"
    if not at.startswith(named[1]) or not done or not saw or saw == at:
        return
    if below.reviewers(brief, "Scoped reviewer", head):
        return
    default = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    old, new = (run.run("git", "merge-base", default.stdout.strip(), to) for to in (saw, head))
    if default.returncode or old.returncode or new.returncode:
        run.say(f"wait {slug}: no range from the default branch to {saw[:12]} and {head[:12]}")
        return
    ask = rebase.unproven(f"{old.stdout.strip()}..{saw}", f"{new.stdout.strip()}..{head}")
    rebase.deliver(run, client, world, number, short, ask)


def guarded(run: Pass, client: Client, world: World, pulls: list[str]) -> None:
    """Ask for the proof that a guarded pull request lacks, and say when a guarded wait lasts too
    long.

    `guarded` counts each pass in which `jmerge` says the same of the same head. At the `PASSES`th
    pass it sends one `stall` event, which names the pull request, the head and the crew's thread.
    `guarded` starts the count again, once, when the crew launches a scoped reviewer for the head.
    The event then comes at the `REVIEWING`th pass and says so, since a review takes longer than
    `PASSES` passes.
    """
    by_number = {pull["number"]: slug for slug, pull in world.open.items()}
    was: dict[str, Any] = read_json(run.state / "guarded.json", {})
    kept: dict[str, Any] = {}
    for said in map(parse, pulls):
        if not said or said.word != "wait" or not _GUARDED.fullmatch(said.reason):
            continue
        number, url, short = said.number, said.name, said.reason
        slug = by_number.get(number, "")
        head = world.open[slug].get("headRefOid", "") if slug else ""
        if not head:
            continue
        prove(run, client, world, number, slug, short)
        brief = task_brief(run, slug)
        reviewing = launched_for(brief, head)
        seen = was.get(slug, {})
        same = (seen.get("head"), seen.get("short")) == (head, short)
        same = same and seen.get("reviewing", False) == reviewing
        passes = seen.get("passes", 0) + 1 if same else 1
        kept[slug] = {"head": head, "short": short, "passes": passes, "reviewing": reviewing}
        if passes >= (REVIEWING if reviewing else PASSES):
            more = ", with a scoped reviewer launched" if reviewing else ""
            line = (
                f"{STALL} {slug}: #{number} {url} has waited {passes} passes at {head[:12]}"
                f"{more}, {short}; its crew's thread is {briefs.thread_of(brief) or 'not known'}"
            )
            run.find(slug, STALL, line, key=f"{head[:12]} {reviewing} {short}")
    if kept != was:
        write_json(run.state / "guarded.json", kept)


def _calls(run: Pass) -> dict[tuple[str, str], dict[str, Any]]:
    """Return each `hung` call in `hung.jsonl` whose end no later line records, by its thread and
    its run."""
    try:
        lines = (run.state / HUNG).read_text(errors="replace").splitlines()
    except OSError:
        return {}
    still: dict[tuple[str, str], dict[str, Any]] = {}
    for line in lines:
        try:
            one = json.loads(line)
        except ValueError:
            continue
        if not isinstance(one, dict) or not isinstance(one.get("at"), str):
            continue
        key = (str(one.get("thread")), str(one.get("run")))
        if "became" in one:
            still.pop(key, None)
        else:
            still[key] = one
    return still


def watched(run: Pass) -> frozenset[str]:
    """Return the threads for which a `hung` call is still open. A pass reads each of them to say
    what became of the call."""
    return frozenset(thread for thread, _ in _calls(run))


def _became(now: dict[str, Any] | None, at_run: str, call: dict[str, Any]) -> str:
    """Return what became of a `hung` call, or nothing while the call is still open or the pass
    cannot tell.

    `now` is the call's thread as this pass has it, or None when T3 Code no longer lists the thread
    as out. The run's own status shows whether someone interrupted the run or the run ended. A run
    that is neither active nor among the runs read has ended. A run that is still under way wrote
    again if its thread wrote an item after the call. A message queued to the thread does not count
    as a write (`threads.out`).
    """
    if now is None:
        return ENDED
    if now["runs"] is None or now["run"] == at_run and at_run not in now["runs"]:
        return ""
    status = now["runs"].get(at_run)
    if status is None or status in BECAME:
        return BECAME.get(status, ENDED)
    try:
        wrote = datetime.fromisoformat(now["wrote"]) > datetime.fromisoformat(call["at"])
    except (TypeError, ValueError):
        return ""
    return WROTE if wrote else ""


def hung(run: Pass, out: list[dict[str, Any]] | None) -> None:
    """Report each thread that turned `hung`, once for that thread and that run, and keep the record
    on which a count of false alarms is based.

    `out` is what `threads.out` gave. The event is loud. Its line gives the thread's title, how long
    the thread has written nothing, and how many runs wait behind it. Each call is one line of
    `hung.jsonl`, with the thread, its role, the run, the time, the minutes silent and the runs
    queued behind. The first pass that can tell what became of a call adds one more line,
    `{"at", "thread", "run", "became"}`.

    `hung` writes a call's line before it sends the event, so every alarm has its record. If a pass
    dies between the write and the send, the next pass writes the line again and then sends the
    event. When `hung` cannot write a line, it says so and sends nothing, and the next pass tries
    again. `hung` does not report a thread for which a read gave no active run, since there is no
    run to report.
    """
    if out is None:
        return
    at = jsettings.stamp(run.now, z=True)
    by_id = {one["id"]: one for one in out}
    for (thread, at_run), call in _calls(run).items():
        became = _became(by_id.get(thread), at_run, call)
        if became:
            _keep(run, {"at": at, "thread": thread, "run": at_run, "became": became})
    sent = run.box.sent()
    for one in out:
        key = f"hung {one['id']} {one['run']}"
        if one["live"] != "hung" or not one["run"] or f"{STALL}|{one['slug']}|{key}" in sent:
            continue
        queued = one["queued"]
        behind = f"{queued or 'no'} {'run waits' if queued < 2 else 'runs wait'} behind it"
        line = (
            f'{STALL} {one["slug"] or run.project.name}: thread "{one["title"]}" has written '
            f"nothing for {one['silent']} min, {behind}"
        )
        call = {name: one[name] for name in ("title", "role", "slug", "run", "silent", "queued")}
        if _keep(run, {"at": at, "thread": one["id"], **call}):
            run.find(one["slug"], STALL, line, key=key)


def _keep(run: Pass, line: dict[str, Any]) -> bool:
    """Add one line to `hung.jsonl`. When `_keep` cannot write the line, it says so, and the pass
    goes on."""
    try:
        handle = os.open(run.state / HUNG, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(handle, (json.dumps(line) + "\n").encode())
        finally:
            os.close(handle)
    except OSError as error:
        run.say(f"wait {run.project.name}: {HUNG} could not be written ({error})")
        return False
    return True


def _tell(half: Half) -> None:
    """Tell what waits on the user, and store the roots for `waiting.keep`."""
    half.roots = tell(half.run, half.client, half.seen.world, half.table, half.users)


STEPS = (
    verbs.Step(
        "tellers",
        110,
        "stall.guarded",
        lambda half: guarded(half.run, half.client, half.seen.world, half.said),
        ("client", "world"),
    ),
    verbs.Step("close", 10, "stall.tell", _tell),
)
