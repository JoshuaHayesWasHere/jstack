"""This module finds what waits on the user. For each approved row that cannot move, this module
follows the row's `depends` links up to a root.

A root is one thing only the user can do, and it has a key:

- `#<n>`: hand-merge, with `jmerge --accept`, a green and reviewed pull request that `jmerge` holds.
  The line names the one safety fact that the review proved at the head;
- `held:<slug>`: pick up a red pull request whose row `twice` held, that `jmerge` says has failed
  its check, and that no thread is at work on: no crew is told of a held row, so only the user
  moves it;
- `re-approve:<slug>`: approve again a brief that changed after their go;
- `approve:<slug>`: approve a row that an approved row depends on;
- `config:<project>`: sign in to T3 Code.

`walk` starts at every approved row that was not launched and follows its `depends` links
(`Pass.reasons`, which `dispatch` records). A stacked link (`jbus.stack`) launched before its
base merged, and its own merge still waits on its base's: `walk` starts at it too, and follows it
to its base. It starts too at a row `twice` held whose pull request is red and that no thread
works on (`held:<slug>`). It stops at a root or at progress: a thread, a pull
request on which `jmerge` waits, a slot, or a gate that the Chef already has. `tell` sends one
`waiting-on-user` event for each root, and sends that event again each hour while the root is still
open. `tell` also rewrites `stall.json`, which records when jbus first saw each root and when jbus
last sent the root. `tell` returns the roots that are still open, and `waiting` lists them with
everything else that waits on the user.

`hung` handles a turn that hangs: a thread that is out and has written nothing for too long
(`live`). `hung` sends one `stall` event for that thread and that run, and writes one line of
`hung.jsonl`. A later pass adds a line that says what became of the turn: it wrote again by itself,
someone interrupted it, or it ended. jbus interrupts nothing and sends the thread nothing.

`twice` ends a row's loop of failed checks, and `redhead` reads why a red is not the row's own. It
keeps, in `fails.json`, each head at which the row's pull request failed a required check
(`rebase.ran_and_failed`, a check the home's `required-checks` names, or jmerge's default where it
names none). A row that is held already is not counted. A pull request's check runs on GitHub's
merge of its head into main, and a failed job's log names that main (`tested`). A head whose check
ran on a main whose own check failed, a tip `main.json` called `broken` (`mainmoved.main_check`), is
kept apart and counted for nothing: main failed there, not the row, whatever commit the head's
branch was based on (#1177, 2026-11-06). A head whose failed tests each failed on two other branches
in `jbus ci`'s window (`reverts.flaky`, `jbus ci`'s flake rule) is kept apart too and counted for
nothing: the red is shared, not the row's (#1219 and #1220, 2026-11-07). A head at which each failed
job failed at a step whose log names no failed test and no make target and shows a download or
network failure (`infra`, `FETCH`), such as a package's download, is kept apart too and counted for
nothing: that step ran nothing of the row's (2026-11-09). A lint step, which also runs no test and
no make target, shows no fetch failure and counts. Each sign is searched in the own part of the log
of the step that failed the job, the last one to fail (`failed_step`), not the whole log. A head
that is only a merge of main into the head seen before it (`merge_of_main`), as `git merge main` and
GitHub's update-branch make one, is kept apart too, under `moved`, and counted for nothing, where it
fails something that head did not (`failures`: a failed test's id, or a lint rule and its path):
main moved under it, as when two diffs that each pass a size cap cross it together, and a held crew
would get no fix message to mend it (#1720, 2026-11-11). Its crew is told to fix it as at any first
failure. A counted head keeps the failed tests its failed jobs' logs name (`named`). At the second
counted head, a push or a merge of main that failed nothing new, whose logs name failed tests, the
red is one the crew can mend by name: `twice` holds nothing and pages nobody, and keeps the head as
`told` in `fails.json`, from which `jbus.rebase.github` words the crew's one message of that head's
failed check, naming the tests and both heads (#1691, 2026-11-11: both its failed heads failed on
one test of the change's own, and the row waited 22 minutes for an approve that carried no
decision). At the third counted head (`LIMIT`), or at the second where its logs name no failed test,
`twice` holds the row (`jbus queue hold`), keeping the go the hold takes, and pages the Chef once, a
gate `check failed twice` that names the row, the pull request, each counted head and the failed
jobs at each. The page's key goes into `fails.json` (`paging`) before the hold, and `held_at` after
the page, so a pass that dies between the hold and the page leaves the page owed: the next pass
pages under the same key, which the log takes once (`_page`). The outbox then sends the crew of a
held row no rebase and no fix message (`outbox.FIXES`), so none goes out at a later head. The row's
`why` says `check failed twice` while it is held. In the pass that sees every required check passed
at the head, `twice` lifts its own hold and puts back the go it took (`lifted`, `queue.lift`), where
the row's brief is still the one that go was for; a row held again since, by anyone, or whose brief
changed since, stays held until an approve. Either way the count starts again from none. A counted
head, of a held row or not, whose every required check then passes at that same head, as on a rerun,
leaves the count: its red was not the row's to keep (#1708, 2026-11-11).

`hung` also keeps `stalls.jsonl`, how long each running row's thread was quiet or hung (`spells`):
the stall minutes the telemetry store reads (`jbus.telemetry.views.weekly_stall`).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import jsettings
from jbriefs import stacked as stacks
from jbus import (
    Refused,
    alert,
    cancelled,
    crewthread,
    queue,
    read_json,
    rebase,
    redhead,
    verbs,
    waiting,
    watch,
    write_json,
)
from jbus.dispatch import launched
from jbus.mainmoved import main_check
from jbus.merge import parse
from jbus.passes import Changed, Depends, Pass
from jbus.record import PASSES as PASS_LOG
from jbus.t3 import Client
from jbus.wake import notify
from jbus.watch import FAILS, JUDGING, TOLD, TWICE, World, at_work, task_brief
from jmerge import judgement, ready
from jmerge.lines import READY
from jsettings import store

if TYPE_CHECKING:
    from jbus.poll import Half

EVENTS = {"waiting-on-user": "quiet", "stall": "quiet"}
EVENT = "waiting-on-user"
AGAIN = 60 * 60

STALL = "stall"
PASSES = 10
REVIEWING = 30
HUNG = "hung.jsonl"
SPELLS = "stalls.jsonl"
STALLED = ("quiet", "hung")
GAP = timedelta(minutes=20)
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
    lines = [line for line in map(parse, pulls) if line and line.reason]
    holds = {line.number: (line.name, line.reason) for line in lines if line.word == "hold"}
    merges: dict[int, str] = {}
    failing = {
        line.number: line.reason
        for line in lines
        if (line.code or ready.code_of(line.reason)) == ready.CHECK_FAILED.code
    }

    def red(slug: str, pull: dict[str, Any]) -> str:
        """The root of a red pull request `twice` held its row for, that no thread works on, or
        nothing: no crew is told of it while the row is held, so only the user moves it."""
        number, row = pull["number"], table.get(slug, {})
        held = row.get("held") and watch.failed_twice(run, slug)
        if number not in failing or at_work(world.threads.get(slug, [])) or not held:
            return ""
        return (
            f"pick up #{number} {pull.get('url', '')}: {failing[number]}, {slug} is held by "
            f"{TWICE} and no thread is at work on it"
        )

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
                stuck = red(slug, pull)
                if stuck:
                    return {f"held:{slug}": stuck}
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
            sha = judgement.brief_sha(queue.brief(run.state, slug) or "")[:12]
            return {f"approve:{slug}": f"approve {slug}: {waiting.approve(name, slug, sha, user)}"}
        return {}

    found: Roots = {}
    for row in sorted(rows, key=queue.order):
        pull = world.open.get(row["slug"])
        if row["slug"] in run.reasons or on_base(row["slug"]) or pull and red(row["slug"], pull):
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
    return judgement.approved_text(row, queue.brief(run.state, slug) or "")


def tell(
    run: Pass,
    client: Client | None,
    world: World | None,
    rows: list[queue.Row] | None,
    pulls: list[str],
) -> list[waiting.Item]:
    """Send each root that is due, say which roots cleared, and rewrite `stall.json`. Return the
    roots that are still open, each `{"key", "line", "since", "unblocks"}`.

    `tell` also raises each due root on the desk. `tell` prints the root while the project's home
    thread's wakes fail. A pass judges no row when it could not ask T3 Code or GitHub, could
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
    quiet = alert.streak(run.config.state_dir, alert.home(name)) is not None
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
    if status is None:
        return ENDED
    if status in BECAME:
        return BECAME[status]
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
    spells(run, out)
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


def _keep(run: Pass, line: dict[str, Any], file: str = HUNG) -> bool:
    """Add one line to `hung.jsonl`, or to `file`. When `_keep` cannot write the line, it says so,
    and the pass goes on."""
    try:
        store.append_jsonl(run.state / file, [line], mode=0o600)
    except OSError as error:
        run.say(f"wait {run.project.name}: {file} could not be written ({error})")
        return False
    return True


LIMIT = 3
"""The counted failed head at which `twice` holds the row, where an earlier one does not."""
COUNTS = {2: "two", 3: "three"}


def _failure(red: rebase.Red, names: list[str], tests: list[str]) -> dict[str, Any]:
    """Return what `fails.json` keeps of a failed head: the failed checks, their jobs and the
    failed tests their logs name."""
    jobs = [f"{repo} job {job}" for repo, job in red.jobs]
    return {"checks": names, "jobs": jobs, "tests": tests}


def holds(heads: dict[str, dict[str, Any]]) -> bool:
    """Say whether the row's counted failed heads hold it: at the `LIMIT`-th, or at the second
    where its logs name no failed test, which leaves its crew nothing to mend by name."""
    counted = list(heads.values())
    return len(counted) >= LIMIT or (len(counted) == 2 and not counted[-1].get("tests"))


def lifted(
    run: Pass, slug: str, row: queue.Row, pull: dict[str, Any], required: tuple[str, ...]
) -> bool:
    """Lift the row's hold where every required check passed at the pull request's head and the
    hold is `twice`'s, which kept the go it took: the go comes back with no approve
    (`queue.lift`). Say whether it did. `queue.lift` refuses a row held by anyone since, whose
    hold kept no go, and one whose brief changed since its go: each stays held for an approve."""
    if not row.get("held"):
        return False
    if ready.waiting(pull.get("statusCheckRollup") or [], required):
        return False
    head = str(pull.get("headRefOid") or "")[:12]
    try:
        said = queue.lift(run.state, slug)
    except Refused as error:
        run.say(f"wait {slug}: every required check passed at {head}, and it stays held ({error})")
        return False
    run.say(f"lifted {slug}: every required check passed at {head}; {said}")
    return True


PAGING = "paging"
"""The key of `twice`'s page in `fails.json`, written before the hold, so that a pass that dies
between the hold and the page leaves the page owed and not lost (`_page`)."""


def _said(head: str, one: dict[str, Any]) -> str:
    jobs = ", ".join(one.get("jobs") or ()) or "no job GitHub gave"
    return f"{head[:12]}: {', '.join(one.get('checks') or ())} failed ({jobs})"


def twice(run: Pass, world: World, rows: list[queue.Row]) -> None:
    """Count, for each row's open pull request, the heads at which a required check failed, and
    hold the row and page the Chef once where they hold it (`holds`, `TWICE`): at the third, or at
    the second where its logs name no failed test. A second head whose logs name failed tests is
    kept as `told`, the head whose message tells the crew of them. A head whose check ran on a red
    main is not counted, nor one whose failed tests are each a flake of two other branches, nor
    one that failed only at an infra step (`infra`), nor a merge of main that brought a new
    failure (`merge_of_main`). A held row is counted no further; its own hold is lifted once
    every required check passes at its head (`lifted`), and once its hold is lifted, by that or
    an approve, its count starts again."""
    path = run.state / FAILS
    was: dict[str, Any] = read_json(path, {})
    table = {row["slug"]: row for row in rows}
    required = cancelled.required(run)
    kept: dict[str, Any] = {}
    for slug, pull in world.open.items():
        row, head = table.get(slug), str(pull.get("headRefOid") or "")
        if row is None or not head or not crewthread.tended(run, slug):
            continue
        if lifted(run, slug, row, pull, required):
            kept[slug] = {"heads": {}, "red": [], "shared": [], "infra": [], "moved": []}
            kept[slug]["last"] = {"head": head, "failed": []}
            continue
        one = dict(was.get(slug) or {})
        if one.get("held_at") and not row.get("held"):
            one = {}
        heads, on_red = dict(one.get("heads") or {}), list(one.get("red") or ())
        flakes, infras = list(one.get("shared") or ()), list(one.get("infra") or ())
        moved, last = list(one.get("moved") or ()), dict(one.get("last") or {})
        kept[slug] = {**one, "heads": heads, "red": on_red, "shared": flakes, "infra": infras}
        kept[slug]["moved"] = moved
        kept[slug].pop(JUDGING, None)
        if one.get(PAGING) and not one.get("held_at"):
            _page(run, slug, row, pull, kept[slug])
            continue
        if head in heads and not ready.waiting(pull.get("statusCheckRollup") or [], required):
            del heads[head]
            kept[slug]["last"] = {"head": head, "failed": []}
            run.say(f"uncounted {slug}: every required check passed at {head[:12]} on a rerun")
            continue
        if row.get("held") or any(head in seen for seen in (heads, on_red, flakes, infras)):
            continue
        if head in moved:
            continue
        found = rebase.ran_and_failed(run, world, pull)
        names = [name for name in found.names if name in required]
        if not names:
            if not ready.waiting(pull.get("statusCheckRollup") or [], required):
                kept[slug]["last"] = {"head": head, "failed": []}
            continue
        main = redhead.tested(run, head, found)
        check = main_check(run, main) if main else ""
        if main is None or check == "pending":
            run.say(f"wait {slug}: not yet known which main {head[:12]} was checked on, or if red")
            if len(heads) == 1:
                kept[slug][JUDGING] = head
            continue
        failed = redhead.failures(run, found)
        kept[slug]["last"] = {"head": head, "failed": sorted(failed)}
        if check == "failed":
            on_red.append(head)
            run.say(
                f"failed {slug}: #{pull['number']} at {head[:12]} ran on main's red "
                f"{main[:12]}, not counted"
            )
            continue
        if tests := redhead.shared(run, pull, found):
            flakes.append(head)
            run.say(
                f"failed {slug}: #{pull['number']} at {head[:12]} failed only tests that also "
                f"failed on two other branches ({', '.join(tests)}), not counted"
            )
            continue
        if steps := redhead.infra(run, world, found):
            infras.append(head)
            run.say(
                f"failed {slug}: #{pull['number']} at {head[:12]} failed only at "
                f"{', '.join(dict.fromkeys(steps))}, a step that failed to fetch and ran no test, "
                "not counted"
            )
            continue
        before = str(last.get("head") or "")
        new = sorted(failed - set(last.get("failed") or ()))
        if main and new and redhead.merge_of_main(run, head, before, main):
            moved.append(head)
            run.say(
                f"failed {slug}: #{pull['number']} at {head[:12]}, a merge of main into "
                f"{before[:12]}, failed {', '.join(new)}, which {before[:12]} did not: main moved "
                "under it, not counted"
            )
            continue
        tests = redhead.named(run, found)
        heads[head] = {"at": run.now.isoformat(), **_failure(found, names, tests)}
        if not holds(heads):
            if len(heads) > 1:
                kept[slug][TOLD] = head
                run.say(
                    f"failed {slug}: #{pull['number']} at {head[:12]}, its second failed head, "
                    f"failed on {', '.join(heads[head]['tests'])}: crew told, a third holds"
                )
            continue
        kept[slug][PAGING] = f"{TWICE} {' '.join(failed[:12] for failed in heads)}"
        write_json(path, {**was, **kept})
        _page(run, slug, row, pull, kept[slug])
    if kept != was:
        write_json(path, kept)


def _page(run: Pass, slug: str, row: queue.Row, pull: dict[str, Any], one: dict[str, Any]) -> None:
    """Hold the row and page the Chef under the key `one[PAGING]`, which `fails.json` kept
    before the hold, and mark the page done in `held_at`. A pass that died after the hold finds
    the key and no `held_at`, and pages here again: `Box.send` takes a repeat of the key as the
    page it logged, so the Chef is paged once, and never not at all."""
    heads = one["heads"]
    if row.get("held"):
        said = f"held {slug}"
    else:
        try:
            said = queue.hold(run.state, slug, keep=True)
        except Refused as error:
            run.say(f"wait {slug}: {TWICE}, and it could not be held ({error})")
            return
    number, url = pull["number"], pull.get("url", "")
    count = COUNTS.get(len(heads), len(heads))
    at = "; ".join(_said(failed, heads[failed]) for failed in heads)
    text = (
        f"#{number} {url} of {slug} failed a required check at {count} heads: {at}. jbus {said}, "
        "and sends its crew no rebase and no fix until every required check passes at a head, "
        "which gives the row back its go, or the row is approved again."
    )
    run.gate(slug, TWICE, text, key=one[PAGING])
    one["held_at"] = run.now.isoformat()


def _twice(half: Half) -> None:
    world = half.seen.world
    if half.rows is not None and world is not None:
        twice(half.run, world, half.rows)


def _open_spells(run: Pass) -> dict[str, dict[str, Any]]:
    """Return each spell of `stalls.jsonl` that no later line ends, by its thread."""
    try:
        lines = (run.state / SPELLS).read_text(errors="replace").splitlines()
    except OSError:
        return {}
    still: dict[str, dict[str, Any]] = {}
    for line in lines:
        try:
            one = json.loads(line)
        except ValueError:
            continue
        if not isinstance(one, dict) or not isinstance(one.get("since"), str):
            continue
        if "minutes" in one:
            still.pop(str(one.get("thread")), None)
        else:
            still[str(one.get("thread"))] = one
    return still


def _last_pass(run: Pass) -> datetime | None:
    """The start of the last pass that ended, from the last line of `passes.jsonl` (`jbus.record`),
    or None where there is none. The log gets a line at the end of every pass, whatever T3 Code and
    GitHub answered, so its last line is the pass before this one. Only the file's tail is read,
    one that doubles until it holds the whole last line, since a line names each step's seconds and
    so grows with the projects."""
    try:
        with (run.config.state_dir / PASS_LOG).open("rb") as log:
            size, tail = log.seek(0, 2), 4096
            while True:
                log.seek(max(0, size - tail))
                lines = log.read().decode(errors="replace").splitlines()
                if tail >= size or len(lines) > 1:
                    break
                tail *= 2
    except OSError:
        return None
    try:
        said = json.loads(lines[-1]) if lines else None
    except ValueError:
        return None
    return _moment(said.get("at")) if isinstance(said, dict) else None


def _moment(said: object) -> datetime | None:
    """The moment a stored time names, or None where it names no moment with its zone."""
    try:
        found = datetime.fromisoformat(str(said))
    except ValueError:
        return None
    return found if found.tzinfo else None


def spells(run: Pass, out: list[dict[str, Any]]) -> None:
    """Keep `stalls.jsonl`, one spell for each stretch a running row's thread is `quiet` or `hung`.

    The first pass that runs `spells` begins the file with `{"at", "began": true}`, when the record
    began: a row merged from that day on with no spell had none, and one merged before it is a gap
    (`jbus.telemetry.views.stalls_since`).

    A row's thread is one whose title names a slug and that is not a home's. The pass that first
    sees the thread quiet or hung adds `{"at", "thread", "role", "slug", "since"}`, where `since`
    is when the thread last wrote (`threads.out`'s `wrote`), so the spell holds the whole silence.
    The passes after it add nothing while the thread stays quiet or hung since that write. The
    pass that sees the spell end adds the same line with `until`, `minutes` and `became`: the
    liveness it turned to, or `gone` where T3 Code no longer lists the thread. A thread that wrote
    again ends the spell at its write, and one that did not (it waits on the user's answer, its
    turn ended, or it is gone) at this pass. A thread that waits on a request is `waiting`, never
    quiet, so no spell counts time the user owes an answer. A spell is counted once, on the line
    that ends it, however many passes saw it. The open spells are read back from the file, so a
    pass that died is picked up by the next one, as `hung.jsonl`'s calls are.

    A spell counts only the silence the passes saw. A stretch of more than `GAP` since the last
    pass (`_last_pass`) is a gap: the machine was suspended, or jbus did not run. A shorter
    stretch, such as a slow pass or one that found the lock busy, counts whole.
    The minutes of a gap that fall in a spell are its `unseen` minutes, and `minutes` leaves them
    out. A pass that comes after a gap writes an open spell's line again with its `unseen` minutes,
    so the line read back carries them; a spell that this pass opens or ends counts its share of the
    gap at once.
    """
    at = jsettings.stamp(run.now, z=True)
    if not (run.state / SPELLS).exists():
        _keep(run, {"at": at, "began": True}, SPELLS)
    last = _last_pass(run)
    gap = last if last is not None and run.now - last > GAP else None

    def unseen(spell: dict[str, Any], since: datetime | None, end: datetime | None) -> float:
        kept = spell.get("unseen")
        before = kept if isinstance(kept, int | float) else 0.0
        if gap is None or since is None or end is None:
            return before
        return round(before + max(0.0, (end - max(since, gap)).total_seconds()) / 60, 1)

    by_id = {one["id"]: one for one in out}
    stalled = {
        one["id"]: one
        for one in out
        if one["live"] in STALLED and one["slug"] and one["role"] != "home" and one["wrote"]
    }
    for thread, spell in _open_spells(run).items():
        one, since = by_id.get(thread), _moment(spell["since"])
        wrote = _moment(one["wrote"]) if one else None
        moved = since is not None and wrote is not None and since < wrote <= run.now
        if thread in stalled and not moved:
            del stalled[thread]
            if gap is not None:
                _keep(run, spell | {"unseen": unseen(spell, since, run.now)}, SPELLS)
            continue
        end = wrote if moved else run.now
        left = unseen(spell, since, end)
        minutes = round((end - since).total_seconds() / 60 - left, 1) if since and end else None
        until = one["wrote"] if moved and one else at
        became = one["live"] if one else "gone"
        ended = {"at": at, "until": until, "minutes": minutes, "became": became}
        _keep(run, spell | ({"unseen": left} if left else {}) | ended, SPELLS)
    for thread, one in stalled.items():
        line = {"at": at, "thread": thread, "role": one["role"], "slug": one["slug"]}
        left = unseen({}, _moment(one["wrote"]), run.now)
        _keep(run, {**line, "since": one["wrote"], **({"unseen": left} if left else {})}, SPELLS)


def _tell(half: Half) -> None:
    """Tell what waits on the user, and store the roots for `waiting.keep`."""
    half.roots = tell(half.run, half.client, half.seen.world, half.table, half.users)


STEPS = (
    verbs.Step("tellers", 90, "stall.twice", _twice, ("world",)),
    verbs.Step("close", 10, "stall.tell", _tell),
)
