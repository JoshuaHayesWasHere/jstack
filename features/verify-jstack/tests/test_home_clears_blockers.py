"""A home clears its own blockers, and only what Josh has to decide reaches the home thread.

Each test drives the real commands in a verify-jstack sandbox, as a home types them: `jbus gate`,
`jbus tidy blockers`, `jbus queue add` and `jbus poll`. The stand-in for T3 Code keeps every wake it
is sent in `t3/wake.jsonl`, and that file is what a test reads to say what reached Josh.
"""

import contextlib
import json
import os
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

import pytest

from jbus.health import PREFIX
from test_verify_jstack import BUILT, SCRIPTS, inside, launch, says

GATE = """## Gate <n>: tea or coffee?
Status: open
Asked by: alpha, thread mcp:a-thread
Default: made tea
Built on it: the cups
Undo: pour it out
Option: tea (default, recommended): the cups stay
Option: coffee: they go
"""
HOLDS = """## Gate <n>: remove the three stale branches?
Status: open
Asked by: alpha, thread mcp:a-thread
Default: the three branches stay until the user says
Built on it: nothing yet
Undo: nothing to undo
Holds: deletes data
Fail-safe: the dry-run lists the 3 branches, bundle at ~/b.bundle
Option: remove them (default, recommended): the branches go
Option: keep them: nothing changes
"""
QUIET = 60
"""How long `quiet` waits for a pass's runs to end: a sandbox's jmerge asks only the stand-in gh,
so its run ends in seconds."""


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("sandbox")
    ran = launch(tmp)
    assert ran.returncode == 0, ran.stderr
    env_sh = Path(ran.stdout.strip().removeprefix("ready: . "))
    yield env_sh
    subprocess.run([SCRIPTS / "cleanup.sh", env_sh.parent], capture_output=True)


@pytest.fixture
def demo(sandbox):
    """The sandbox with the demo project's jbus state and home state emptied, and one pass run, so
    each test starts on a project jbus has seen once and has posted nothing for (`fresh`)."""
    fresh(sandbox)
    return sandbox


def fresh(sandbox):
    """Empty the demo project's jbus state and home state, and run one pass. That pass pages
    each reading of the host past its limit, a full disk say: the page is the host's and not the
    project's, so the test starts once it is out, with no five-minute gap after it to wait on.
    It empties the state folder once no pass writes into it, and hands over a sandbox none does
    (`quiet`)."""
    root = sandbox.parent
    quiet(root)
    for gone in (root / "state", root / "home" / ".local" / "state" / "home" / "demo"):
        subprocess.run(["rm", "-rf", gone], check=True)
    (root / "state").mkdir()
    (root / "home" / ".local" / "state" / "home" / "demo" / "tasks").mkdir(parents=True)
    (root / "t3" / "wake.jsonl").unlink(missing_ok=True)
    (root / "gh" / "open.json").write_text("[]\n")
    threads = root / "t3" / "threads.json"
    if threads.exists():
        kept = json.loads(threads.read_text())
        threads.write_text(json.dumps([one | {"settled": True} for one in kept]))
    assert run(sandbox, "jbus poll").returncode == 0
    quiet(root)
    assert posted(sandbox) == []


def quiet(root):
    """Wait until no process a pass left running writes into the sandbox's state folder
    (`writers`), and end any still going after `QUIET` seconds."""
    deadline = time.monotonic() + QUIET
    while (left := writers(root)) and time.monotonic() < deadline:
        time.sleep(0.05)
    for pid in left:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
    while writers(root):
        time.sleep(0.05)


def writers(root):
    """The processes a pass in the sandbox `root` started and left running, each writing into
    its state folder: the scorecard's build and jmerge's run (`jbus.telemetry.start`,
    `jbus.merge.start`), both named on their command line by a path in that folder."""
    ps = subprocess.run(["ps", "-A", "-ww", "-o", "pid=,stat=,command="], capture_output=True)
    rows = (line.split(None, 2) for line in ps.stdout.decode().splitlines())
    inside = f"{root / 'state'}/"
    return [
        int(pid) for pid, stat, command in rows if not stat.startswith("Z") and inside in command
    ]


def run(sandbox, command, stdin=None):
    if stdin is None:
        return inside(sandbox, command)
    return subprocess.run(
        ["sh", "-c", f'. "{sandbox}" && {command}'], input=stdin, capture_output=True, text=True
    )


def listed(sandbox):
    """The lines of each message of the one list (`jbus.wakes`) that reached a home thread, but
    the pages of `jbus health`: those read the host's own state, its disk, which no test sets."""
    wake = sandbox.parent / "t3" / "wake.jsonl"
    told = (
        [json.loads(line)["lines"] for line in wake.read_text().splitlines()]
        if wake.exists()
        else []
    )
    kept = [[one for one in lines if not one.startswith(f"alert: {PREFIX}")] for lines in told]
    return [lines for lines in kept if lines]


def posted(sandbox):
    """Every line the one list took to a home thread, in order."""
    return [line for lines in listed(sandbox) for line in lines]


def brief(slug, *head):
    lines = [
        f"# {slug}: a demo task",
        f"Task: {slug}, a demo task",
        "Why: the sandbox needs a row the queue takes",
        "Done when:",
        "- the demo works",
        "Proves it: the demo's test",
        "Size: S",
        "Where: `src/`",
        "Design: none, a demo",
        "Review: none",
        "Playbook: feature",
        "Skills: tdd",
        "Pull request: none",
        *([] if any(line.startswith("Home:") for line in head) else ["Home: uncategorized"]),
        *head,
        "",
    ]
    return "\n".join(lines)


def fix(slug, key, green="When green: `check` passes on the fix's pull request at its head"):
    return brief(slug, f"Fix of: {key}", *([green] if green else []))


def at_zoned():
    """Now in this machine's time zone, as `jbus queue remove --at` takes it: jbus holds a typed
    time to its own clock, which the sandbox does not fake."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")


def approve(sandbox, slug):
    """Approve a row on the user's word, as `jbus word` keeps it from the user's message."""
    ref = says(sandbox, f"go {slug}", message=f"m-go-{slug}")
    said = run(sandbox, f"jbus word --to demo --message {ref}").stdout.split()
    return run(sandbox, f"jbus queue approve {slug} --word {said[-1]}")


def test_a_gate_the_user_need_not_decide_is_closed_by_the_pass_with_no_event(demo):
    assert (
        run(demo, "jbus gate alpha", GATE).stdout == "asked: queued: question 1\nGate: question 1\n"
    )

    cleared = run(demo, "jbus tidy blockers")
    polled = run(demo, "jbus poll")

    assert cleared.returncode == 0, cleared.stderr
    assert "question 1" not in cleared.stdout
    assert polled.returncode == 0, polled.stderr
    (record,) = json.loads((demo.parent / "state" / "demo" / "questions.json").read_text())[
        "records"
    ]
    assert record["answer"]["closed_by"] == "silence"
    assert not (demo.parent / "home" / ".local" / "state" / "home" / "demo" / "gates.md").exists()
    assert posted(demo) == []
    assert "question 1" not in run(demo, "jbus tidy blockers").stdout


def test_a_red_check_gets_a_fix_row_with_no_event(demo):
    assert run(demo, "jbus queue add beta --priority 1", brief("beta")).returncode == 0
    assert approve(demo, "beta").returncode == 0
    assert "launched beta" in run(demo, "jbus poll").stdout
    run(demo, '"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py FAILURE')
    run(demo, "jbus poll")

    cleared = run(demo, "jbus tidy blockers")
    added = run(demo, "jbus queue add beta-fix --priority 1", fix("beta-fix", "check:beta"))
    ruled = run(demo, "jbus queue approve beta-fix --rule 1 --follows beta")
    run(demo, "jbus poll")

    assert cleared.stdout.startswith("fix check:beta: its check failed, brief a fix")
    assert "try 1 of 2" in cleared.stdout
    assert added.returncode == 0, added.stdout + added.stderr
    assert ruled.returncode == 0, ruled.stdout + ruled.stderr
    assert "beta-fix" in run(demo, "jbus queue show").stdout
    assert posted(demo) == []


def test_a_gate_josh_has_to_decide_reaches_the_home_thread_once_from_the_one_list(demo):
    assert (
        run(demo, "jbus gate alpha", HOLDS).stdout
        == "asked: queued: question 1\nGate: question 1\n"
    )

    run(demo, "jbus poll")
    cleared = run(demo, "jbus tidy blockers")
    run(demo, "jbus gate alpha", HOLDS)
    run(demo, "jbus poll")

    ((line,),) = listed(demo)
    assert line.startswith("question 1: remove the three stale branches, it holds (deletes data)")
    assert "decision question 1" in cleared.stdout


def test_a_fix_with_no_when_green_line_is_refused(demo):
    added = run(demo, "jbus queue add gamma-fix --priority 1", fix("gamma-fix", "check:gamma", ""))

    assert added.returncode == 1
    assert "has no When green: line" in added.stdout + added.stderr
    assert "gamma-fix" not in run(demo, "jbus queue show").stdout
    assert not (
        demo.parent
        / "home"
        / ".local"
        / "state"
        / "home"
        / "demo"
        / "uncategorized"
        / "blockers.json"
    ).exists()


def test_a_blocker_past_its_cap_stops_and_gives_one_decision_event(demo):
    for slug in ("delta-fix-1", "delta-fix-2"):
        added = run(demo, f"jbus queue add {slug} --priority 1", fix(slug, "check:delta"))
        assert added.returncode == 0, added.stdout + added.stderr
    again = run(demo, "jbus queue add delta-fix-1 --priority 2", fix("delta-fix-1", "check:delta"))

    third = run(demo, "jbus queue add delta-fix-3 --priority 1", fix("delta-fix-3", "check:delta"))
    run(demo, "jbus poll")
    fourth = run(demo, "jbus queue add delta-fix-4 --priority 1", fix("delta-fix-4", "check:delta"))
    run(demo, "jbus poll")

    assert again.returncode == 0, again.stdout + again.stderr
    assert third.returncode == 1
    assert "check:delta had 2 fixes" in third.stdout + third.stderr
    assert fourth.returncode == 1
    shown = run(demo, "jbus queue show").stdout
    assert "delta-fix-3" not in shown and "delta-fix-4" not in shown
    (line,) = [one for one in posted(demo) if "check:delta" in one]
    assert line.startswith("decision delta-fix-3: check:delta had 2 fixes")
    assert (
        "Reply: reply in your own words to take check:delta on yourself or say what to do instead"
        in line
    )


def test_the_cap_is_the_one_jsettings_names(demo):
    config = demo.parent / "home" / ".config" / "jstack" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("retry_cap = 1\n")
    try:
        first = run(demo, "jbus queue add eps-fix-1 --priority 1", fix("eps-fix-1", "check:eps"))
        second = run(demo, "jbus queue add eps-fix-2 --priority 1", fix("eps-fix-2", "check:eps"))
    finally:
        config.unlink()

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 1
    assert "check:eps had 1 fix" in second.stdout + second.stderr


def end_thread(sandbox, slug, status):
    """Set the T3 Code status of the slug's crew thread, as the outside world would."""
    threads = sandbox.parent / "t3" / "threads.json"
    kept = json.loads(threads.read_text())
    for one in kept:
        if one.get("title") == f"crew: {slug}":
            one["status"] = status
    threads.write_text(json.dumps(kept))


def launched(sandbox, slug):
    assert run(sandbox, f"jbus queue add {slug} --priority 1", brief(slug)).returncode == 0
    assert approve(sandbox, slug).returncode == 0
    assert f"launched {slug}" in run(sandbox, "jbus poll").stdout


def remove(sandbox, slug):
    at = f'--at "{at_zoned()}"'
    return run(sandbox, f"jbus queue remove {slug} --by user {at}")


def test_a_stuck_row_and_then_its_leftover_each_get_a_fix_line_with_no_event(demo):
    launched(demo, "lam")
    end_thread(demo, "lam", "idle")
    run(demo, "jbus poll")
    stuck = run(demo, "jbus tidy blockers").stdout
    end_thread(demo, "lam", "completed")
    tasks = demo.parent / "home" / ".local" / "state" / "home" / "demo" / "tasks"
    result = "\n## Result\nStatus: done\nBranch: lam   Pull request: none\nLeft: the docs page\n"
    (tasks / "lam.md").write_text((tasks / "lam.md").read_text() + result)
    run(demo, "jbus poll")
    left = run(demo, "jbus tidy blockers").stdout

    assert stuck.startswith(
        'fix row:lam: it was refused or is stuck, brief a fix whose head has "Fix'
    )
    assert left.startswith(
        'fix left:lam: it left work, brief a fix whose head has "Fix of: left:lam"'
    )
    assert posted(demo) == []


def test_a_fix_at_work_is_waited_on_one_removed_unrun_gives_its_try_back_and_a_cap_is_one_decision(
    demo,
):
    launched(demo, "mu")
    end_thread(demo, "mu", "idle")
    run(demo, "jbus poll")
    for slug in ("mu-fix-1", "mu-fix-2"):
        added = run(demo, f"jbus queue add {slug} --priority 1", fix(slug, "row:mu"))
        assert added.returncode == 0, added.stdout + added.stderr
    waits = run(demo, "jbus tidy blockers").stdout
    for slug in ("mu-fix-1", "mu-fix-2"):
        assert remove(demo, slug).returncode == 0
    freed = run(demo, "jbus tidy blockers").stdout
    for slug in ("mu-fix-3", "mu-fix-4"):
        added = run(demo, f"jbus queue add {slug} --priority 1", fix(slug, "row:mu"))
        assert added.returncode == 0, added.stdout + added.stderr
    fifth = run(demo, "jbus queue add mu-fix-5 --priority 1", fix("mu-fix-5", "row:mu"))
    run(demo, "jbus poll")

    assert waits.startswith("wait row:mu: mu-fix-1, mu-fix-2 is at work on it")
    assert freed.startswith("fix row:mu: it was refused or is stuck"), freed
    assert "try 1 of 2" in freed
    assert fifth.returncode == 1
    assert "row:mu had 2 fixes (mu-fix-3, mu-fix-4)" in fifth.stdout + fifth.stderr
    (line,) = [one for one in posted(demo) if "row:mu had" in one]
    assert (
        "Reply: reply in your own words to take row:mu on yourself or say what to do instead"
        in line
    )


def test_a_batch_of_fixes_past_the_cap_queues_none_and_counts_none(demo):
    batch = "".join(
        f"add {slug} --priority 1\n--- brief {slug}\n{fix(slug, 'check:nu')}--- end\n"
        for slug in ("nu-fix-1", "nu-fix-2", "nu-fix-3")
    )

    applied = run(demo, "jbus queue apply", batch)
    after = run(demo, "jbus queue add nu-fix-4 --priority 1", fix("nu-fix-4", "check:nu"))

    assert applied.returncode == 1
    assert "check:nu had 2 fixes" in applied.stdout + applied.stderr
    shown = run(demo, "jbus queue show").stdout
    assert not any(f"nu-fix-{n} " in shown for n in (1, 2, 3))
    assert after.returncode == 0, after.stdout + after.stderr
    blockers = (
        demo.parent
        / "home"
        / ".local"
        / "state"
        / "home"
        / "demo"
        / "uncategorized"
        / "blockers.json"
    )
    assert [one["slug"] for one in json.loads(blockers.read_text())["check:nu"]] == ["nu-fix-4"]


def test_a_scope_change_raised_by_hand_is_one_decision_with_its_reply(demo):
    question = (
        "--question 'add a second sign-in to the plan?' "
        "--reply 'reply in your own words to add the sign-in or say what to do instead'"
    )

    first = run(demo, f"jbus decide alpha {question}")
    again = run(demo, f"jbus decide alpha {question}")
    run(demo, "jbus poll")

    assert first.stdout == "raised: alpha: add a second sign-in to the plan?\n"
    assert again.stdout == "raised already: alpha: add a second sign-in to the plan?\n"
    assert posted(demo) == [
        "decision alpha: add a second sign-in to the plan?. Reply: "
        "reply in your own words to add the sign-in or say what to do instead"
    ]


def test_a_scoped_home_raises_its_own_gates_and_not_the_root_s(demo):
    state = demo.parent / "home" / ".local" / "state" / "home" / "demo"
    (state / "s").mkdir()
    (state / "s" / "plan.md").write_text("# plan\n")
    (state / "s" / "home-id").write_text("mcp:scoped-home\n")
    (state / "tasks" / "alpha.md").write_text("# alpha: a demo task\nHome: s\n")
    run(demo, "jbus gate alpha", HOLDS)

    root = run(demo, "jbus tidy blockers").stdout
    scoped = run(demo, "jbus tidy blockers --scope s").stdout

    assert "question 1" not in root
    assert scoped.startswith("decision question 1: it holds (deletes data)")


def red_pull(sandbox, slug, path):
    """Open a pull request for the slug whose check failed, beside the ones already open."""
    pulls = sandbox.parent / "gh" / "open.json"
    were = json.loads(pulls.read_text())
    run(sandbox, f'"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" {slug} {path} FAILURE')
    (pull,) = json.loads(pulls.read_text())
    number = 7 + len(were)
    pull |= {"number": number, "url": f"https://example.test/pull/{number}"}
    pull["headRefOid"] = f"{number:040x}"
    pulls.write_text(json.dumps([*were, pull]))
    run(sandbox, "jbus poll")


def red_fix(sandbox, slug, key, path):
    """Queue a fix of the key, approve it by the follow-up rule, launch it and fail its check."""
    added = run(sandbox, f"jbus queue add {slug} --priority 1", fix(slug, key))
    assert added.returncode == 0, added.stdout + added.stderr
    ruled = run(sandbox, f"jbus queue approve {slug} --rule 1 --follows rho")
    assert ruled.returncode == 0, ruled.stdout + ruled.stderr
    assert f"launched {slug}" in run(sandbox, "jbus poll").stdout
    red_pull(sandbox, slug, path)
    end_thread(sandbox, slug, "idle")


def test_a_fix_whose_own_check_failed_is_not_at_work_and_the_next_try_then_the_cap_follow(demo):
    launched(demo, "rho")
    red_pull(demo, "rho", "src/rho/a.py")
    end_thread(demo, "rho", "idle")

    red_fix(demo, "rho-fix", "check:rho", "src/rho/b.py")
    second = run(demo, "jbus tidy blockers").stdout
    red_fix(demo, "rho-fix-2", "check:rho", "src/rho/c.py")
    capped = run(demo, "jbus tidy blockers").stdout
    run(demo, "jbus poll")

    assert second.startswith("fix check:rho: its check failed, brief a fix"), second
    assert "try 2 of 2" in second
    assert capped.startswith("decision check:rho: check:rho had 2 fixes"), capped
    (line,) = [one for one in posted(demo) if "check:rho had" in one]
    assert (
        "Reply: reply in your own words to take check:rho on yourself or say what to do instead"
        in line
    )


def test_the_state_is_emptied_only_once_no_pass_writes_into_it(demo):
    """A pass leaves the scorecard's build and jmerge's run going after it ends, and either one
    that writes after the state folder is emptied makes it again: the next `fresh` then failed to
    make it, with FileExistsError. A `jmerge` that takes two seconds holds each pass's run in that
    window, and `fresh` waits it out and hands over a sandbox no pass writes into."""
    jmerge = demo.parent / "stub" / "jmerge"
    jmerge.write_text(f'#!/bin/sh\nsleep 2\nexec "{BUILT / "jmerge"}" "$@"\n')
    jmerge.chmod(0o755)
    try:
        assert run(demo, "jbus poll").returncode == 0
        fresh(demo)
        assert writers(demo.parent) == []
    finally:
        jmerge.unlink()
