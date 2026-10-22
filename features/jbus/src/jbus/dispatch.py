"""Launch a crewmate thread for a row of the queue, and only for a row the user approved.

`t3_thread_launch` has no retry key, so jbus keeps one: `<project>/<slug>/<brief_sha 12>`,
a file under `launches/`. jbus writes the file with `state: intent` and fsyncs it before the
call, and adds the thread id after the reply. jbus never launches a key that has a thread id
again. An intent with no thread id is a lost reply. jbus settles it by looking the thread up,
never by calling again.

Once a launch has its thread, `write_thread` puts `Thread: <id>` in the head of
`tasks/<slug>.md`. It is the one line jbus ever writes in a brief after the launch. When a
pass died before it wrote the line, the next pass writes it (`write_missing`).

`max_running` is one cap for the whole machine. `dispatch` gets the slots that all the
projects together leave free, and hands them out in turns, one launch a turn (`Turns`).

Before a launch, jbus runs `jgauge room` to check that the machine and the plan have room,
the same check a home makes. A row with no room waits, and so does every row after it in the
pass, in every project.

jbus does not lint a brief here. `jbus queue add` runs the lints (`jbriefs.parse.faults`)
when it first queues a row. A lint added after a row's approval does not refuse that row,
whatever its `Design:`, `Proves it:`, `Skills:`, `Size:` or `Playbook:` line says, and
`jbus queue show` lists such rows. jbus refuses a launch only when the approval no longer
covers the brief (`jbriefs.meaning`).

Before a launch puts a thread on a mirror instance (`jroles.mirror`, a home of providers.json
that is not the main one), `mirrored` asks `jroles mirror --check` about it. On drift it runs
the mirror once and asks again. When the instance is still not mirrored, the pool passes over
it for the rest of the pass: the launch goes to the next instance with headroom, or waits.

jbus never holds back a launch because another brief names the same file, since each crew
has its own worktree and branch. When a launched brief shares a path with a brief still out,
jbus sends one `overlap` event and does nothing else. The crew of the pull request that
merges second rebases it, and `jbus.rebase` tells that crew to.
"""

from __future__ import annotations

import itertools
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jroles
import jroles.mirror
from jbus import queue, read_json, write_json
from jbus.t3 import Client, T3Error, T3Refused
from jbus.wake import Changed, Depends, Pass, Slot
from jbus.watch import TITLE, End, World, crew_threads, ended
from jmerge import mainjson
from jroles import ledger, pool

EVENTS = {"overlap": "quiet"}
_PATH = re.compile(r"`([^`\s]+)`")
OVERLAP_PATHS = 5


def record_path(run: Pass, slug: str, brief_sha: str) -> Path:
    return run.config.state_dir / "launches" / run.project.name / slug / f"{brief_sha[:12]}.json"


def records(run: Pass, slug: str) -> list[tuple[Path, dict[str, Any]]]:
    directory = run.config.state_dir / "launches" / run.project.name / slug
    return [(path, read_json(path, {})) for path in sorted(directory.glob("*.json"))]


def launched(run: Pass, slug: str) -> str:
    """Return the thread id of the slug's launch, or nothing if it has none."""
    return next((r["thread"] for _, r in reversed(records(run, slug)) if r.get("thread")), "")


def thread_of(brief: str) -> str:
    """Return the thread id on a brief's `Thread:` line. Like the skills, it reads the first
    such line."""
    for line in brief.splitlines():
        if line.startswith("Thread:"):
            return (line.split()[1:2] or [""])[0]
    return ""


def write_thread(run: Pass, slug: str, thread: str, *, replace: bool = True) -> None:
    """Put `Thread: <id>` in the head of `tasks/<slug>.md`, as the home skill's step 3 does.

    The line replaces an earlier `Thread:` line, so a brief never has two. Where the brief has
    none, the line goes above the first `## `, so it is above any Result that a fast crewmate
    has already written. Without `replace`, it leaves alone a brief that already has a
    `Thread:` line, whatever thread that line names.
    """
    path, line = run.home / "tasks" / f"{slug}.md", f"Thread: {thread}"
    try:
        lines = path.read_text().splitlines()
    except (OSError, ValueError):
        return
    if line in lines:
        return
    was = next((at for at, one in enumerate(lines) if one.startswith("Thread:")), None)
    if was is not None and not replace:
        return
    if was is not None:
        lines[was] = line
    else:
        head = next((at for at, one in enumerate(lines) if one.startswith("## ")), len(lines))
        lines.insert(head, line)
    temporary = path.with_name(path.name + ".thread")
    temporary.write_text("\n".join(lines) + "\n")
    os.replace(temporary, path)


def write_missing(run: Pass) -> None:
    """Write the `Thread:` line into each brief whose launch has a thread but whose brief
    never got the line.

    The line is missing when a pass ended between writing the launch record and writing the
    line. The function does not change a `Thread:` line that a brief already has, whatever
    thread it names. It runs before anything reads the briefs for their thread, so the pass
    that repairs a line also sends to the thread that the line names.
    """
    directory = run.config.state_dir / "launches" / run.project.name
    for slug in sorted(path.name for path in directory.glob("*") if path.is_dir()):
        if launched(run, slug):
            write_thread(run, slug, launched(run, slug), replace=False)


GREEN_MAIN = "Green main:"


def green_main(brief: str, green: str) -> str:
    """Return the brief with `Green main: <sha>` under its first line, in place of any such
    line its head had. The sha is the last commit of main whose check passed
    (`jmerge.mainjson`). A crew rebases onto that commit where main is red. When no green
    main is known, the brief gets no such line."""
    kept, head = [], True
    for line in brief.splitlines(keepends=True):
        head = head and not line.startswith("## ")
        if not (head and line.startswith(GREEN_MAIN)):
            kept.append(line)
    plain = "".join(kept)
    if not green:
        return plain
    first, _, rest = plain.partition("\n")
    return f"{first}\n{GREEN_MAIN} {green}\n{rest}"


def arguments(
    run: Pass, slug: str, brief: str, base: str, routed: pool.Route | None
) -> dict[str, Any]:
    """Return the arguments for `t3_thread_launch`: the home skill's crew launch with the
    brief in it. The model selection is the one the role map's `crew` line gives for the
    instance that `routed` chose."""
    made: dict[str, Any] = {
        "projectId": run.project.project_id,
        "title": f"{TITLE}{slug}",
        "workspaceStrategy": {
            "type": "worktree",
            "baseRef": base,
            "branch": slug,
            "startFromOrigin": True,
        },
        "message": f"/crew {slug}\n\n{brief}",
    }
    if run.config.runtime_mode:
        made["runtimeMode"] = run.config.runtime_mode
    if routed is not None:
        made["modelSelection"] = routed.as_json()
    return made


def where(brief: str) -> set[str]:
    for line in brief.splitlines():
        if line.startswith("Where:"):
            return {p for p in _PATH.findall(line) if "/" in p or "." in p}
    return set()


def _under(path: str, directory: str) -> bool:
    return path.startswith(directory.rstrip("/") + "/")


def shared(run: Pass, slug: str, brief: str) -> dict[str, list[str]]:
    """Return the paths this brief shares with each brief that is out, by that brief's slug
    (`jmerge --claims`).

    Where one of two paths is under the other, it names the file, not its directory. When
    `jmerge --claims` did not run, it names no brief. jbus only reports an overlap, and
    holds back no launch for it.
    """
    mine = where(brief)
    ran = run.run("jmerge", "--claims")
    found: dict[str, list[str]] = {}
    for line in ran.stdout.splitlines() if ran.returncode == 0 else []:
        other, _, rest = line.partition(" ")
        if other == slug or rest.startswith("not launched ") or "Where:" not in rest:
            continue
        both = {
            max(path, theirs, key=len)
            for theirs in where(rest[rest.index("Where:") :])
            for path in mine
            if path == theirs or _under(path, theirs) or _under(theirs, path)
        }
        if both:
            found[other] = sorted(both)
    return found


def overlaps(run: Pass, slug: str, brief: str) -> None:
    """Tell the Chef which files the row just launched shares with each other brief, once
    for each pair.

    Each crew works in its own worktree, so a shared file blocks no launch. The pull request
    that merges second is the one that rebases (`rebase.tell`).
    """
    for holder, paths in shared(run, slug, brief).items():
        named = ", ".join(paths[:OVERLAP_PATHS])
        if len(paths) > OVERLAP_PATHS:
            named += f" and {len(paths) - OVERLAP_PATHS} more"
        line = f"overlap {slug}: shares {named} with {holder}; whichever merges second rebases"
        run.find(slug, "overlap", line, key=f"{slug} {holder}")


def settle_lost(run: Pass, client: Client) -> None:
    """Look up each launch whose reply was lost, and adopt the one thread that matches.

    A launch that stays lost becomes a gate. jbus does not launch its slug again until the
    user removes its file under `launches/` by hand. A lost launch holds back no other row.
    If its thread does exist, the pass counts it with every other thread that T3 Code lists.
    """
    directory = run.config.state_dir / "launches" / run.project.name
    for path in sorted(directory.glob("*/*.json")):
        record, slug = read_json(path, {}), path.parent.name
        if record.get("thread"):
            continue
        try:
            listed = crew_threads(client, run.project.project_id, f"{TITLE}{slug}")
            matching = []
            for thread in (t for t in listed if t["title"] == f"{TITLE}{slug}"):
                read = client.call("t3_thread_read", {"threadId": thread["threadId"], "limit": 1})
                if (read.get("thread") or {}).get("branch") == slug:
                    matching.append(thread["threadId"])
        except T3Error as error:
            run.say(f"wait {slug}: its lost launch reply could not be looked up ({error})")
            run.gated.add(slug)
            continue
        if len(matching) == 1:
            write_json(
                path, {**record, "state": "launched", "thread": matching[0], "adopted": True}
            )
            write_thread(run, slug, matching[0])
            run.say(f"adopted {slug}: {matching[0]}")
            overlaps(run, slug, queue.brief(run.state, slug) or "")
        else:
            run.gate(slug, f"launch reply lost, {len(matching)} matching threads", str(path))


def mirrored(run: Pass, slug: str, instance: str, checked: dict[str, bool]) -> bool:
    """Say whether a thread may go on `instance`. It may when the instance is no mirror of
    providers.json, or when `jroles mirror --check` finds it mirrored, at once or after one run
    of the mirror. The function keeps the answer in `checked` for the pass. For each slug
    that it refuses an instance for, it says once that the instance is not mirrored."""
    if instance not in checked:
        try:
            named = {one.instance for one in jroles.mirror.declared(Path.home())}
        except jroles.Refused:
            named = {instance}
        asked = ("jroles", "mirror", "--instance", instance)
        ok = instance not in named or run.run(*asked, "--check").returncode == 0
        if not ok:
            run.run(*asked)
            ok = run.run(*asked, "--check").returncode == 0
        checked[instance] = ok
    if not checked[instance]:
        run.say(f"wait {slug}: {instance} is not mirrored")
    return checked[instance]


def mirrored_choice(
    run: Pass,
    slug: str,
    instances: tuple[str, ...],
    checked: dict[str, bool],
    here: str | None = None,
    kept: ledger.Ledger | None = None,
    full: float = ledger.FULL,
) -> pool.Choice:
    """Return the pool's choice for `instances`, passing over every instance that is not
    mirrored. The choice reads the ledger `kept`, or the ledger on disk where the caller gives
    none. `here` is the instance a thread is on already: choosing it is no move, so the
    function does not check its mirror. `full` is the level at which an instance counts as
    full: a real cap for a move, and the user's headroom for a launch."""
    skip: dict[str, str] = {}
    kept = ledger.read(instances) if kept is None else kept
    while True:
        choice = pool.choose(instances, kept, run.now, skip, full)
        at = choice.instance
        if at is None or at == here or mirrored(run, slug, at, checked):
            return choice
        skip[at] = f"{at} is not mirrored"


def room(run: Pass, instance: str | None) -> tuple[str, list[str]]:
    """Return why a launch has no room, or nothing when it has room, together with the
    notes that `jgauge room` gave. `jgauge room` reads the plan's limits for `instance`, the
    instance the launch goes to, or for the built-in one where the launch inherits.

    A check that did not run, or that said neither `go` nor `wait: `, also counts as no room.
    """
    ran = run.run("jgauge", "room", *(("--instance", instance) if instance else ()))
    said = ran.stdout.strip()
    if ran.returncode == 0 and said == "go":
        noted = (line.partition("note: ") for line in ran.stderr.splitlines())
        return "", [note for before, found, note in noted if found and not before]
    if ran.returncode == 0 and said.startswith("wait: ") and "\n" not in said:
        return said.removeprefix("wait: "), []
    return "jgauge room did not run", []


def no_room(run: Pass, slug: str, why: str, waited: dict[str, Any]) -> None:
    """Say that a row waits for room, and gate it once, at `room_passes` passes in a row.

    `waited` is what the previous pass recorded: the row that waited then, and its count.
    """
    if waited.get("slug") != slug:
        waited = {"slug": slug, "passes": 0, "since": run.now.isoformat()}
    waited = {**waited, "passes": waited["passes"] + 1}
    write_json(run.state / "room.json", waited)
    run.say(f"wait {slug}: no room: {why}")
    if waited["passes"] >= run.config.room_passes:
        what = f"no room for {waited['passes']} passes: {why}"
        run.gate(slug, what, key=f"no room since {waited['since']}")


LAUNCHED, NOTHING, NO_ROOM = "launched", "nothing", "no room"
SLOT = "no slot"


@dataclass
class Turns:
    """A `Turns` holds one project's rows in a pass, lowest priority first, and its turns at the
    free slots.

    `left` holds the rows not read yet. The pass reads each row once. On a later turn it does
    not judge again a row it passed over, and it sends no gate twice.
    """

    run: Pass
    client: Client
    world: World
    left: list[queue.Row]
    waited: dict[str, Any] = field(default_factory=dict)
    checked: dict[str, bool] = field(default_factory=dict)

    def _ready(self, full: bool) -> Iterator[tuple[queue.Row, str]]:
        """Read rows off `left`, and yield each row, with its brief, that waits only for a
        free slot.

        It passes over every other row. jbus never launches a row again once its thread has
        ended with a Result. When a changed brief or a slug the row depends on holds a row
        back, it adds the reason to `Pass.reasons`. A slug holds the row back until that slug
        has merged, or ended `done` with no pull request. Once the pass is `full`, it reads a
        row only for its reason and sends no gate for it. It adds each row it holds back to
        `Pass.held`.
        """
        run, world = self.run, self.world
        merged = set(world.merged) - set(world.open)
        while self.left:
            row = self.left.pop(0)
            slug = row["slug"]
            known = (run.gated, world.threads, world.open, world.merged)
            if any(slug in place for place in known) or launched(run, slug):
                continue
            if ended(run, world, slug):
                continue
            if not row.get("approved"):
                continue
            if slug in world.settled:
                if not full:
                    thread = world.settled[slug]["threadId"]
                    run.gate(slug, "a settled thread already has this slug", thread)
                else:
                    run.held.add(slug)
                continue
            brief = queue.brief(run.state, slug)
            if brief is None or not queue.approved_text(row, brief):
                now = queue.brief_sha(brief or "")[:12]
                if not full:
                    run.gate(slug, "brief changed after approval", key=f"brief changed, now {now}")
                run.reasons[slug] = Changed(now)
                continue
            met = merged | {
                other for other in row.get("depends", []) if ended(run, world, other) == End("done")
            }
            unmerged = [other for other in row.get("depends", []) if other not in met]
            if unmerged:
                run.reasons[slug] = Depends(tuple(unmerged))
                continue
            yield row, brief

    def take(self) -> str:
        """Take one turn: launch the first row that may launch, and return how the turn
        ended.

        `LAUNCHED` means the turn used a slot, also for a launch whose reply was lost.
        `NOTHING` means no row is left to launch, and `NO_ROOM` means a row waits for room on
        the machine.
        """
        run, client = self.run, self.client
        for row, brief in self._ready(full=False):
            slug = row["slug"]
            refs = run.run(
                "git",
                "for-each-ref",
                "--format=%(refname)",
                f"refs/heads/{slug}",
                f"refs/remotes/origin/{slug}",
            )
            remote = run.run("git", "ls-remote", "--heads", "origin", f"refs/heads/{slug}")
            if refs.returncode or remote.returncode:
                run.gate(slug, f"the remote could not be asked for a branch {slug}")
                continue
            if refs.stdout.strip() or remote.stdout.strip():
                there = refs.stdout.strip() or f"refs/heads/{slug} on origin"
                run.gate(slug, f"branch {slug} is there with no launch record", there)
                continue
            base = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
            if base.returncode or not base.stdout.strip():
                run.gate(slug, "the default branch is not known in the main checkout")
                continue
            plain = queue.body(brief)
            green = mainjson.read(run.state).green
            text = green_main(plain, green)
            target = run.home / "tasks" / f"{slug}.md"
            wrote = not target.exists()
            on_disk = "" if wrote else queue.body(target.read_text(errors="replace"))
            if not wrote and on_disk.strip() != plain.strip():
                run.gate(slug, f"tasks/{slug}.md differs from the approved brief", str(target))
                continue
            try:
                (routed,) = pool.routes("crew", run.now) or (None,)
                full = pool.headroom("crew")
            except jroles.Refused as error:
                run.gate(slug, "the role map gives the crew no model", str(error))
                continue
            if routed:
                found = mirrored_choice(
                    run, slug, routed.selection.instances, self.checked, full=full
                )
                routed = pool.Route(routed.selection, found)
            choice = routed.choice if routed else pool.Choice(None, "")
            if routed and choice.instance is None:
                line = f"wait {slug}: no launch: {choice.why}"
                if choice.until is None or choice.passed:
                    run.say(line)
                elif run.find(
                    slug,
                    "stall",
                    f"stall {slug}: {choice.why}",
                    key=f"capped {choice.until.isoformat()}",
                ):
                    run.say(line)
                run.reasons[slug] = Slot()
                return NO_ROOM
            why, notes = room(run, choice.instance)
            for note in notes:
                day = run.day
                name = run.project.name
                run.find("", "note", f"note {name}: {note}", key=f"room {day}")
            if why:
                no_room(run, slug, why, self.waited)
                run.reasons[slug] = Slot()
                return NO_ROOM
            again = queue.fresh(run.state, slug) or {}
            same = all(again.get(column) == row.get(column) for column in ("approved", "brief_sha"))
            if not same or not queue.approved_text(row, queue.brief(run.state, slug) or ""):
                run.say(f"wait {slug}: its row changed during the pass")
                continue
            if wrote:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            elif (named := green_main(kept := target.read_text(errors="replace"), green)) != kept:
                target.write_text(named)
            sha = queue.brief_sha(brief)
            path = record_path(run, slug, sha)
            key = f"{run.project.name}/{slug}/{sha[:12]}"
            write_json(path, {"key": key, "state": "intent", "at": run.now.isoformat()})
            try:
                reply = client.call(
                    "t3_thread_launch",
                    arguments(run, slug, text, base.stdout.strip().removeprefix("origin/"), routed),
                )
            except T3Refused as error:
                path.unlink()
                if wrote:
                    target.unlink()
                run.gate(slug, "T3 Code refused the launch", str(error))
                continue
            except T3Error as error:
                run.say(f"launch {slug}: no reply ({error}): it is looked up on the next pass")
                run.gated.add(slug)
                return LAUNCHED
            if not reply.get("threadId"):
                run.say(
                    f"launch {slug}: the reply named no thread: it is looked up on the next pass"
                )
                run.gated.add(slug)
                return LAUNCHED
            write_json(
                path,
                {
                    "key": key,
                    "state": "launched",
                    "thread": reply["threadId"],
                    "at": run.now.isoformat(),
                },
            )
            write_thread(run, slug, reply["threadId"])
            on = f" on {choice.instance}, {choice.why}" if choice.why else ""
            run.say(f"launched {slug}: {reply['threadId']}{on}")
            overlaps(run, slug, brief)
            return LAUNCHED
        return NOTHING

    def rest(self, *, cap: bool) -> None:
        """Once the pass makes no more launches, read each row left to find why it waits.

        For the rows ahead of the first row that waits for a slot, the pass still sends the
        gates they are owed, whether or not a slot is free. `cap` means the slots ran out.
        Then the pass names each row that waits, with the time it began to wait for a slot:
        its `since`, or now for a new wait.
        """
        waits = [row for row, _ in itertools.islice(self._ready(full=False), 1)]
        waits += [row for row, _ in self._ready(full=True)]
        limit = self.run.config.max_running
        for row in waits:
            self.run.reasons[row["slug"]] = Slot()
            if cap:
                held = row.get("why") == SLOT and row.get("since")
                since = held or self.run.user.stamp(self.run.now)
                who = f"{row['slug']} waits, since {since}"
                self.run.say(f"max_running is {limit} across all projects: {who}")


def turns(run: Pass, client: Client, world: World, rows: list[queue.Row]) -> Turns:
    settle_lost(run, client)
    return Turns(run, client, world, sorted(rows, key=queue.order))


def dispatch(projects: list[Turns], slots: int | None) -> list[str]:
    """Hand out the free slots, one launch a turn, going round the projects in the order
    given.

    `slots` is how many launches the pass may make: `max_running` less the crews at work in
    every project. With no `slots`, the pass does not know how many crews are at work, and
    launches nothing.
    A project whose turn launches nothing has no more turns in the pass. No room ends the
    turns of every project, because they all share one machine. Return the name of the
    project of each launch, in order.
    """
    for one in projects:
        one.waited = read_json(one.run.state / "room.json", {})
        (one.run.state / "room.json").unlink(missing_ok=True)
    if not projects:
        return []
    config, say = projects[0].run.config, projects[0].run.say
    if not config.dispatch:
        say("dispatch is off in the config: nothing is launched")
        return []
    if config.stop_path.exists():
        say(f"{config.stop_path} is there: nothing is launched")
        return []
    made: list[str] = []
    waiting, took = list(projects), ""
    while waiting and took != NO_ROOM and slots is not None and len(made) < slots:
        one = waiting.pop(0)
        took = one.take()
        if took == LAUNCHED:
            made.append(one.run.project.name)
            waiting.append(one)
    for one in projects:
        one.rest(cap=took != NO_ROOM and slots is not None)
    return made
