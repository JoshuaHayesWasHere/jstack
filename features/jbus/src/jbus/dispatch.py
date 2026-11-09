"""Launch a crewmate thread for a row of the queue, and only for a row the user approved.

`t3_thread_launch` has no retry key, so jbus keeps one: `<project>/<slug>/<brief_sha 12>`, a file
under `launches/`. jbus writes the file with `state: intent` and fsyncs it before the call, and adds
the thread id after the reply. jbus never launches again under a key that has a thread id. An intent
with no thread id means the reply was lost. jbus settles such an intent by looking the thread up.
It calls again only for a launch whose connection dropped (ECONNRESET, `T3Dropped`) and whose
lookup finds no thread, and only once (`settle_lost`).

Once a launch has its thread, `write_thread` puts `Thread: <id>` in the head of
`tasks/<slug>.md`. It is the one line jbus ever writes in a brief after the launch. When a
pass stopped before it wrote the line, the next pass writes it (`write_missing`).

`max_running` is one cap for the whole machine. `dispatch` gets the slots that all the
projects together leave free, and hands them out in turns, one launch a turn (`Turns`). Two
more caps hold inside each project (`Caps`): `max_per_project` crews out in the project, and
`max_per_home` crews out for each of its homes, the root and each scope. A crew counts toward
the home its queued brief names (`jbriefs.home.home_of`). A row whose home is full waits, and
the rows of the project's other homes still take its turns. A scout or a reviewer is no crew
and counts toward no cap.

Before a launch, jbus runs `jgauge room` to check that the machine and the plan have room,
the same check a home makes. A row with no room waits, and so does every row after it in the
pass, in every project. Where /tmp is what is full, the pass first removes what finished crews
left there (`jbus.cleanup.sweep`) and asks again. A row that still waits for /tmp says so from
that first pass, `waiting: /tmp at <n>% of its quota`, as its `why` and on `jbus needs`.

jbus does not lint a brief here. `jbus queue add` runs the lints (`jbriefs.parse.faults`) when it
first queues a row. A lint added after a row's approval does not make jbus refuse that row, whatever
the brief's `Design:`, `Proves it:`, `Skills:`, `Size:` or `Playbook:` line says. `jbus queue show`
lists such rows. jbus refuses a launch only when the approval no longer covers the brief
(`jbriefs.meaning`).

Before a launch puts a thread on a mirror instance (`jroles.mirror`, a home of T3's settings that
is not the main one), `mirrored` asks `jroles mirror --check` about that instance. On drift,
`mirrored` runs the mirror once and asks again. When the instance is still not mirrored, the pool
skips it for the rest of the pass: the launch goes to the next instance with headroom, or waits.

While `main.json` says main is red, a row launches only when it fixes main (`fixes_main`) or
launches stacked on an open row it depends on. Every other approved row waits with the reason
`main is red: waits for green` (`Red`), and launches on the first pass that reads main as green:
a crew launched onto a red main finds its check failed on main's break. A red main holds no pull
request (`jmerge.mainjson`); this rule holds back launches only.

Each crew gets a scratch folder on disk, `~/.cache/jstack/scratch/<repo>/<slug>`
(`JSTACK_SCRATCH_DIR` in place of `~/.cache/jstack/scratch`), made before its launch (`scratch`).
`t3_thread_launch` takes no environment, so the session-start hook
(`features/home/hooks/home-start.sh`) points the thread's `TMPDIR` at the folder it finds for its
worktree's repo and branch, and every `mktemp`, clone and worktree the thread makes goes there and
not in /tmp, whose tmpfs quota full repo copies filled. `jbus.threads.settle` removes the folder,
and prunes the worktrees that were in it, once it settles the crew's thread
(`jbus.cleanup.clear_scratch`).

jbus never holds back a launch because another brief names the same file, since each crew
has its own worktree and branch. The crew of the pull request that merges second rebases that
pull request, and `jbus.rebase` tells that crew to.
"""

from __future__ import annotations

import itertools
import os
import re
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jroles
import jroles.mirror
from jbriefs.home import home_of, named
from jbus import cleanup, queue, read_json, watch, write_json
from jbus.launches import record_path, records
from jbus.passes import Changed, Depends, Pass, Red, Rerun, Slot
from jbus.t3 import Client, T3Dropped, T3Error, T3Refused
from jbus.watch import TITLE, End, World, against, crew_threads, ended
from jmerge import judgement, mainjson
from jmerge import stacked as stacks
from jroles import ledger, pool


def launched(run: Pass, slug: str, role: str = queue.CREW) -> str:
    """Return the thread id of the slug's launch of `role`, or nothing if it has none. A scout's
    row taken over by the crewmate's brief it delivered keeps the scout's record beside the
    crewmate's."""
    found = records(run, slug, role)
    return next((r["thread"] for _, r in reversed(found) if r.get("thread")), "")


def scratch(run: Pass, slug: str) -> Path:
    """Return the scratch folder of the slug's crew, which is its thread's `TMPDIR`."""
    root = os.environ.get("JSTACK_SCRATCH_DIR") or Path.home() / ".cache" / "jstack" / "scratch"
    return Path(root) / run.project.checkout.name / slug


def write_thread(
    run: Pass, slug: str, thread: str, *, replace: bool = True, kind: str = "tasks"
) -> None:
    """Put `Thread: <id>` in the head of `tasks/<slug>.md`, as the home skill's step 3 does, or
    of `scouts/<slug>.md` with `kind` `scouts`.

    The line replaces an earlier `Thread:` line, so a brief never has two. Where the brief has
    none, the line goes above the first `## `, so it is above any Result that a fast crewmate
    has already written. Without `replace`, the function leaves a brief that already has a
    `Thread:` line as it is, whatever thread that line names.
    """
    path, line = run.home / kind / f"{slug}.md", f"Thread: {thread}"
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

    The line is missing when a pass ended between writing the launch record and writing the line.
    The function does not change a `Thread:` line that a brief already has, whatever thread that
    line names. The function runs before anything reads the briefs for their thread, so the pass
    that repairs a line also sends to the thread that the line names.
    """
    directory = run.config.state_dir / "launches" / run.project.name
    for slug in sorted(path.name for path in directory.glob("*") if path.is_dir()):
        found = [record for _, record in reversed(records(run, slug)) if record.get("thread")]
        if found:
            kind = "scouts" if found[0].get("role") == queue.SCOUT else "tasks"
            write_thread(run, slug, found[0]["thread"], replace=False, kind=kind)


GREEN_MAIN = "Green main:"

_FIXES_MAIN = re.compile(r"\bfix(?:es|ing)?\s+(?:the\s+)?(?:red\s+)?main\b", re.IGNORECASE)


def fixes_main(slug: str, brief: str) -> bool:
    """Whether the row fixes a red main: jbus filed it for one (`mainjson.fix_of`), or the first
    line of its brief, its heading, says it fixes main, as `# x: fix main's red test` does."""
    heading = "".join(brief.splitlines()[:1])
    return mainjson.fix_of(slug) or bool(_FIXES_MAIN.search(heading))


def green_main(brief: str, green: str) -> str:
    """Return the brief with `Green main: <sha>` under its first line, in place of any such
    line its head had. The sha is the last commit of main whose check passed
    (`jmerge.mainjson`). When main is red, a crew rebases onto that commit. When no green
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


def launched_text(brief: str, green: str, on: stacks.Stacked | None) -> str:
    """Return the brief a launch sends: with the `Green main:` line (`green_main`), or for a row
    that launches stacked, with its `Stacked on:` line in that place and no `Green main:`. A
    stacked crew starts from its base's branch, never from main, so the line that tells a crew
    which main to rebase onto has no place in its brief."""
    if on is None:
        return green_main(brief, green)
    return stacked(green_main(brief, ""), on)


def stacked(brief: str, on: stacks.Stacked | None) -> str:
    """Return the brief with `on`'s `Stacked on:` line under its first line, in place of any such
    line its head had, or with no such line where `on` is None."""
    kept, head = [], True
    for line in brief.splitlines(keepends=True):
        head = head and not line.startswith("## ")
        if not (head and line.startswith(stacks.LINE)):
            kept.append(line)
    if on is None:
        return "".join(kept)
    first, _, rest = "".join(kept).partition("\n")
    return f"{first}\n{stacks.line(on)}\n{rest}"


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


def settle_lost(run: Pass, client: Client) -> None:
    """Look up each launch whose reply was lost, and adopt the one thread that matches.

    A launch that stays lost becomes a gate. jbus does not launch its slug again until the
    user removes its file under `launches/` by hand. A lost launch holds back no other row.
    The one exception is a launch whose connection dropped before any reply: with no thread of
    its title and branch, its record turns `retry`, and the pass's turn launches the slug once
    more under the same record. A retry that drops too is a gate like any other.
    If the lost launch's thread does exist, the pass counts that thread with every other
    thread that T3 Code lists.
    """
    directory = run.config.state_dir / "launches" / run.project.name
    for path in sorted(directory.glob("*/*.json")):
        record, slug = read_json(path, {}), path.parent.name
        if (
            record.get("thread")
            or record.get("role") == queue.SCOUT
            or record.get("state") == "retry"
        ):
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
        elif not matching and record.get("dropped"):
            write_json(
                path, {"key": record.get("key"), "state": "retry", "at": run.now.isoformat()}
            )
            run.say(f"relaunch {slug}: its launch dropped and made no thread: once more")
        else:
            run.gate(slug, f"launch reply lost, {len(matching)} matching threads", str(path))


def mirrored(run: Pass, slug: str, instance: str, checked: dict[str, bool]) -> bool:
    """Say whether a thread may go on `instance`. It may when the instance is not a mirror in
    T3's settings, or when `jroles mirror --check` finds it mirrored, at once or after one run
    of the mirror. The function keeps the answer in `checked` for the pass. When the function
    refuses an instance for a slug, it says once for that slug that the instance is not mirrored."""
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


def pool_of(run: Pass, role: str, instance: str) -> tuple[str, ...]:
    """Return the pool a thread of `role`, a role of the map, on `instance` moves in. It is the
    first line of the role map that names the instance. The function reads the thread's own role's
    lines first, then every other role's in the map's order. Where no line names the instance, the
    pool is the instance alone. A reviewer on the crew's provider moves in the crew's pool when its
    `review` lines name two other instances."""
    for name in sorted(jroles.ROLES, key=lambda one: one != role):
        try:
            chosen = pool.selections(name)
        except jroles.Refused as error:
            run.say(f"wait {run.project.name}: the role map gives {name} no pool ({error})")
            continue
        for one in chosen:
            if instance in one.instances:
                return one.instances
    return (instance,)


def say_unread(run: Pass, instance: str) -> None:
    """Say, once a day, that a launch or a move lands on an account nobody can read
    (`jroles.pool.unread`). It still goes there."""
    unread = pool.unread(instance, run.now)
    line = f"note {run.project.name}: {unread}"
    if unread and run.find("", "note", line, key=f"unread {instance} {run.day}"):
        run.say(line)


def cannot_run(run: Pass, client: Client) -> dict[str, str] | None:
    """Return why T3 Code cannot run each provider instance it lists, its constraints joined, and
    nothing for one it can, or None where T3 Code did not say. A signed-out instance has
    `Provider is not authenticated.` among its constraints."""
    try:
        said = client.call("orchestrator_capabilities", {})
    except T3Error as error:
        run.say(f"wait {run.project.name}: T3 Code did not say which instances sign in ({error})")
        return None
    return {
        str(one["providerInstanceId"]): " ".join(str(c) for c in one.get("constraints") or [])
        for one in said.get("providers") or []
        if isinstance(one, dict) and one.get("providerInstanceId")
    }


def cannot_sign_in(run: Pass, client: Client) -> dict[str, str]:
    """Return why each instance T3 Code lists cannot take a launch now (`cannot_run`), for
    `jroles.pool.routes` to skip. An instance T3 Code does not list, or a pass where it did not
    say, skips nothing: the launch call says why it cannot go there."""
    return {name: why for name, why in (cannot_run(run, client) or {}).items() if why}


def mirrored_choice(
    run: Pass,
    slug: str,
    instances: tuple[str, ...],
    checked: dict[str, bool],
    here: str | None = None,
    kept: ledger.Ledger | None = None,
    full: float = ledger.FULL,
    skip: Mapping[str, str] | None = None,
) -> pool.Choice:
    """Return the pool's choice for `instances`, skipping every instance that is not
    mirrored, and every instance that `skip` names, for the reason it gives. The choice reads
    the ledger `kept`, or the ledger on disk where the caller gives none. `here` is the
    instance a thread is on already: choosing it is no move, so the function does not check
    its mirror. `full` is the level at which an instance counts as
    full: a real cap for a move, and the user's headroom for a launch."""
    skip = dict(skip or {})
    kept = ledger.read(instances) if kept is None else kept
    while True:
        choice = pool.choose(instances, kept, run.now, skip, full)
        at = choice.instance
        if at is None or at == here or mirrored(run, slug, at, checked):
            if at is not None:
                say_unread(run, at)
            return choice
        skip[at] = f"{at} is not mirrored"


def room(
    run: Pass, instance: str | None, *, role: str = "crew", light: bool = False
) -> tuple[str, list[str]]:
    """Return why a launch has no room, or nothing when it has room, together with the
    notes that `jgauge room` gave. `jgauge room` reads the plan's limits for `instance`, the
    instance the launch goes to. When the launch names no instance and takes the default, it
    reads the limits of `role`'s pool. `light` skips the load and the CPU pressure, for a
    thread that adds almost no CPU, such as a scout's.

    A check that did not run, or that said neither `go` nor `wait: `, also counts as no room.
    """
    asked = ("--instance", instance) if instance else ("--role", role) if role != "crew" else ()
    ran = run.run("jgauge", "room", *asked, *(("--light",) if light else ()))
    said = ran.stdout.strip()
    if ran.returncode == 0 and said == "go":
        noted = (line.partition("note: ") for line in ran.stderr.splitlines())
        return "", [note for before, found, note in noted if found and not before]
    if ran.returncode == 0 and said.startswith("wait: ") and "\n" not in said:
        return said.removeprefix("wait: "), []
    return "jgauge room did not run", []


def no_room(run: Pass, slug: str, why: str, waited: dict[str, Any]) -> None:
    """Say that a row waits for room. Once it has waited `room_passes` passes in a row, gate
    it, once.

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
class Caps:
    """`Caps` holds one project's crews out in a pass, counted by home, and the two caps on them.

    A home is the directory `jbriefs.home.home_of` gives: `root` for the root home, or one of
    its scopes. A launch in the pass adds its crew (`add`).
    """

    project: str
    root: Path
    per_home: int
    per_project: int
    out: Counter[Path] = field(default_factory=Counter)

    def add(self, home: Path) -> None:
        self.out[home] += 1

    def name(self, home: Path) -> str:
        return "the root home" if home == self.root else f"the {home.name} home"

    def full(self, home: Path | None = None) -> str:
        """Say which cap holds a row of `home` back, or nothing when both leave it room: its
        home's first, which still holds when the project has a crew less. With no `home`, say
        only whether the project is full."""
        if home is not None and self.out[home] >= self.per_home:
            return f"max_per_home is {self.per_home} in {self.name(home)}"
        if self.out.total() >= self.per_project:
            return f"max_per_project is {self.per_project} in {self.project}"
        return ""


def caps(run: Pass, slugs: tuple[str, ...]) -> Caps:
    """Count the crews out, `slugs`, by the home each one's queued brief names. The queued brief
    is the one the row was approved with, and the copy a launch writes in `tasks/` names the same
    home (`homed`). A crew whose queued brief is gone counts toward the root home."""
    made = Caps(run.project.name, run.home, run.config.max_per_home, run.config.max_per_project)
    for slug in slugs:
        made.add(home_of(run.home, queue.brief(run.state, slug) or ""))
    return made


@dataclass
class Turns:
    """A `Turns` holds one project's rows in a pass, lowest priority first, and its turns at the
    free slots.

    `left` holds the rows not read yet. The pass reads each row once. On a later turn it does
    not judge a skipped row again, and it sends no gate twice.
    """

    run: Pass
    client: Client
    world: World
    left: list[queue.Row]
    caps: Caps
    reported: frozenset[str] = frozenset()
    capped: list[queue.Row] = field(default_factory=list)
    waited: dict[str, Any] = field(default_factory=dict)
    checked: dict[str, bool] = field(default_factory=dict)

    def _ready(self, full: bool) -> Iterator[tuple[queue.Row, str, stacks.Stacked | None]]:
        """Read rows off `left`, and yield each row, with its brief and the stack it launches
        on, that waits only for a free slot.

        The method skips every other row. jbus never launches a row again once the row's thread
        has ended with a Result, nor a fix row of a red main whose own commit went green on a
        rerun (`_rerun`). When a row waits because its brief changed, waits on a slug
        it depends on, or waits for a red main to be green, the method adds the reason to
        `Pass.reasons`. While main is red, only a row that fixes main (`fixes_main`) or launches
        stacked on an open row is yielded. A row waits on a slug until
        that slug has merged, or has ended `done` with no pull request, or until the one slug it
        still waits on has opened its pull request: it then launches stacked on that pull
        request's branch (`World.stack_on`). Once the pass is `full`,
        the method reads a row only for its reason, sends no gate for it, and adds the row to
        `Pass.held`.

        The pass read the table before it merged and asked T3 Code, and the home may have added
        and approved the brief again since. So a go that does not hold for the stored brief is
        judged once more with the row and the brief as they are now, read together
        (`queue.current`), and the row is gated only when that go does not hold either. Each pass
        judges the row again, so the gate goes the pass its go holds.
        """
        run, world = self.run, self.world
        merged = (set(world.merged) - set(world.open)) | self.reported
        red = bool(mainjson.read(run.state).red)
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
            if mainjson.fix_of(slug) and (rerun := _rerun(run, slug)):
                run.reasons[slug] = Rerun(rerun)
                continue
            if slug in world.settled:
                if not full:
                    thread = world.settled[slug]["threadId"]
                    run.gate(slug, "a settled thread already has this slug", thread)
                else:
                    run.held.add(slug)
                continue
            brief = queue.brief(run.state, slug)
            if brief is None or not judgement.approved_text(row, brief):
                row, brief = queue.current(run.state, slug)
                if row is None or not row.get("approved"):
                    continue
            if brief is None or not judgement.approved_text(row, brief):
                now = judgement.brief_sha(brief or "")[:12]
                lines = tuple(queue.changed(row, brief))
                if not full:
                    what = f"brief changed after approval: {'; '.join(lines)}"
                    run.gate(slug, what, key=f"brief changed, now {now}")
                run.reasons[slug] = Changed(now, row.get("brief_sha", "")[:12], lines)
                continue
            met = merged | {
                other for other in row.get("depends", []) if ended(run, world, other) == End("done")
            }
            unmerged = [other for other in row.get("depends", []) if other not in met]
            on = world.stack_on(run, unmerged, brief)
            if unmerged and on is None:
                run.reasons[slug] = Depends(tuple(unmerged))
                continue
            if red and on is None and not fixes_main(slug, brief):
                run.reasons[slug] = Red()
                continue
            yield row, brief, on

    def live(self) -> list[Path]:
        """Return the worktrees T3 Code makes for the project's rows still out, whose Claude
        scratch folders `cleanup.sweep` keeps."""
        names = {self.run.project.name, self.run.project.checkout.name}
        rows = queue.load(self.run.state)
        out = (row["slug"] for row in rows if row.get("status") in queue.LIVE)
        return [cleanup.WORKTREES / name / slug for slug in out for name in names]

    def take(self) -> str:
        """Take one turn: launch the first row that may launch, and return how the turn
        ended.

        `LAUNCHED` means the turn used a slot, also for a launch whose reply was lost.
        `NOTHING` means no row is left to launch, or the project has `max_per_project` crews
        out, and `NO_ROOM` means a row waits for room on the machine. A row whose home has
        `max_per_home` crews out is set aside in `capped` for the pass, before it asks git or
        `jgauge room` anything, and the turn goes on to the next row.
        """
        run, client = self.run, self.client
        if self.caps.full():
            return NOTHING
        for row, brief, on in self._ready(full=False):
            slug = row["slug"]
            home = home_of(run.home, brief)
            if self.caps.full(home):
                self.capped.append(row)
                continue
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
            default = base.stdout.strip().removeprefix("origin/")
            plain = judgement.body(brief)
            green = mainjson.read(run.state).green
            text = homed(launched_text(plain, green, on), brief)
            target = run.home / "tasks" / f"{slug}.md"
            wrote = not target.exists()
            on_disk = "" if wrote else judgement.body(target.read_text(errors="replace"))
            if not wrote and on_disk.strip() != plain.strip():
                run.gate(slug, f"tasks/{slug}.md differs from the approved brief", str(target))
                continue
            out = cannot_sign_in(run, client)
            try:
                (routed,) = pool.routes("crew", run.now, out) or (None,)
                full = pool.headroom("crew")
            except jroles.Refused as error:
                run.gate(slug, "the role map gives the crew no model", str(error))
                continue
            if routed:
                instances = routed.selection.instances
                skip = pool.signed_out(instances, out)
                found = mirrored_choice(run, slug, instances, self.checked, full=full, skip=skip)
                routed = pool.Route(routed.selection, found)
            choice = routed.choice if routed else pool.Choice(None, "")
            if routed and choice.instance is None:
                line = f"wait {slug}: no launch: {choice.why}"
                if (
                    choice.until is None
                    or choice.passed
                    or run.find(
                        slug,
                        "stall",
                        f"stall {slug}: {choice.why}",
                        key=f"capped {choice.until.isoformat()}",
                    )
                ):
                    run.say(line)
                run.reasons[slug] = Slot()
                return NO_ROOM
            why, notes = room(run, choice.instance)
            if why and cleanup.waiting(why) and cleanup.sweep(run, self.live()):
                why, notes = room(run, choice.instance)
            for note in notes:
                day = run.day
                name = run.project.name
                run.find("", "note", f"note {name}: {note}", key=f"room {day}")
            if why:
                no_room(run, slug, why, self.waited)
                run.reasons[slug] = Slot(cleanup.waiting(why))
                return NO_ROOM
            again = queue.fresh(run.state, slug) or {}
            same = all(again.get(column) == row.get(column) for column in ("approved", "brief_sha"))
            if not same or not judgement.approved_text(row, queue.brief(run.state, slug) or ""):
                run.say(f"wait {slug}: its row changed during the pass")
                continue
            if wrote:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            elif (kept := target.read_text(errors="replace")) != (
                put := homed(launched_text(kept, green, on), brief)
            ):
                target.write_text(put)
            sha = judgement.brief_sha(brief)
            path = record_path(run, slug, sha)
            key = f"{run.project.name}/{slug}/{sha[:12]}"
            retried = read_json(path, {}).get("state") == "retry"
            intent = {"key": key, "state": "intent", "at": run.now.isoformat()}
            write_json(path, {**intent, "retried": True} if retried else intent)
            scratch(run, slug).mkdir(parents=True, exist_ok=True)
            try:
                reply = client.call(
                    "t3_thread_launch",
                    arguments(
                        run,
                        slug,
                        text,
                        on.branch if on else against(brief) or default,
                        routed,
                    ),
                )
            except T3Refused as error:
                path.unlink()
                if wrote:
                    target.unlink()
                run.gate(slug, "T3 Code refused the launch", str(error))
                continue
            except T3Error as error:
                if isinstance(error, T3Dropped) and not retried:
                    write_json(path, {**intent, "dropped": True})
                run.say(f"launch {slug}: no reply ({error}): it is looked up on the next pass")
                run.gated.add(slug)
                self.caps.add(home)
                return LAUNCHED
            self.caps.add(home)
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
            where = f" on {choice.instance}, {choice.why}" if choice.why else ""
            where += f", stacked on {on.slug}'s branch {on.branch}" if on else ""
            run.say(f"launched {slug}: {reply['threadId']}{where}")
            return LAUNCHED
        return NOTHING

    def rest(self, *, cap: bool) -> None:
        """Once the pass makes no more launches, read each remaining row to find why it waits.

        For the rows ahead of the first row that waits for a slot, the pass still sends the
        gates those rows are owed, whether or not a slot is free. `cap` means the machine's
        slots ran out. Then the pass names each row that waits, with the first cap that holds
        it, the project's, its home's or the machine's, and the time it began to wait for a
        slot: its `since`, or now for a new wait. A row that waits only for room is not named.
        """
        waits = list(self.capped)
        waits += [row for row, _, _ in itertools.islice(self._ready(full=False), 1)]
        waits += [row for row, _, _ in self._ready(full=True)]
        waits.sort(key=queue.order)
        limit = self.run.config.max_running
        for row in waits:
            self.run.reasons[row["slug"]] = Slot()
            brief = queue.brief(self.run.state, row["slug"]) or ""
            why = self.caps.full(home_of(self.run.home, brief))
            if not why and cap:
                why = f"max_running is {limit} across all projects"
            if why:
                held = row.get("why") == SLOT and row.get("since")
                since = held or self.run.user.stamp(self.run.now)
                self.run.say(f"{why}: {row['slug']} waits, since {since}")


def turns(
    run: Pass, client: Client, world: World, rows: list[queue.Row], out: tuple[str, ...]
) -> Turns:
    """Return the project's turns, with its crewmates' rows and `out`, the slugs of its crews out
    (`watch.Look.out`). A scout's row is launched by `jbus.scouts`, and a row that depends on it
    may launch once its Report says it is done (`watch.reported`)."""
    settle_lost(run, client)
    crew = sorted((row for row in rows if queue.role(row) == queue.CREW), key=queue.order)
    made = Turns(run, client, world, crew, caps(run, out))
    made.reported = watch.reported(run, rows)
    return made


def dispatch(projects: list[Turns], slots: int | None) -> list[str]:
    """Hand out the free slots, one launch a turn, going round the projects in the order
    given.

    `slots` is how many launches the pass may make: `max_running` minus the crews at work in
    every project. With no `slots`, the pass does not know how many crews are at work, and
    launches nothing.
    A project whose turn launches nothing, its rows all launched, waiting or capped, has no
    more turns in the pass. No room ends the
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


def _rerun(run: Pass, slug: str) -> str:
    """Return the green commit of main, where it is the very commit the fix row `slug` was filed
    for, and nothing otherwise. Such a red was a check that failed and then passed on a rerun:
    there is no red left to fix. `watch._withdraw` takes out a row that a later green made
    needless, and leaves this one, so the launch is where it stops."""
    green = mainjson.read(run.state).green
    return green[:12] if green and green.startswith(slug.removeprefix(mainjson.FIX)) else ""


def homed(text: str, brief: str) -> str:
    """Return `text` with the `Home:` line of `brief`, the queued brief, last in its head, when
    `brief` names a home and the head of `text` names none. Every message about a launched row is
    routed by its copy in `tasks/`, so the copy names the home its row belongs to. `judgement.body`
    leaves the line out, so the brief's sha stays the same."""
    home = named(brief)
    if not home or named(text):
        return text
    lines = text.splitlines(keepends=True)
    place = next((n for n, line in enumerate(lines) if line.startswith("## ")), len(lines))
    if place and not lines[place - 1].endswith("\n"):
        lines[place - 1] += "\n"
    lines.insert(place, f"Home: {home}\n")
    return "".join(lines)
