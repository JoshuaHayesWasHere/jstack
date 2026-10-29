"""A home clears its own blockers, and only what Josh has to decide reaches the home thread.

Each test drives the real commands in a verify-jstack sandbox, as a home types them: `jbus gate`,
`jbus clear`, `jbus queue add` and `jbus poll`. The stand-in for T3 Code keeps every wake it is
sent in `t3/wake.jsonl`, and that file is what a test reads to say what reached Josh.
"""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from jbus.health import PREFIX
from test_verify_jstack import SCRIPTS, inside, launch, says

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
    each test starts on a project jbus has seen once and has posted nothing for. That pass pages
    each reading of the host past its limit, a full disk say: the page is the host's and not the
    project's, so the test starts once it is out, with no five-minute gap after it to wait on."""
    root = sandbox.parent
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
    assert posted(sandbox) == []
    wakes = root / "state" / "demo" / "home-thread" / "wake.json"
    if wakes.exists():
        wakes.write_text(json.dumps(json.loads(wakes.read_text()) | {"posted": 0}))
    return sandbox


def run(sandbox, command, stdin=None):
    if stdin is None:
        return inside(sandbox, command)
    return subprocess.run(
        ["sh", "-c", f'. "{sandbox}" && {command}'], input=stdin, capture_output=True, text=True
    )


def posted(sandbox):
    """Every event a wake took to the home thread, in order, but the pages of `jbus health`: those
    read the host's own state, its disk, which no test sets."""
    wake = sandbox.parent / "t3" / "wake.jsonl"
    lines = wake.read_text().splitlines() if wake.exists() else []
    events = [event for line in lines for event in json.loads(line)["events"]["events"]]
    return [one for one in events if not one["line"].startswith(f"alert: {PREFIX}")]


def listed(sandbox):
    """The lines of each message of the one list (`jbus.wakes`) that reached a home thread, which
    carries each decision of the list."""
    calls = sandbox.parent / "t3" / "calls.jsonl"
    lines = calls.read_text().splitlines() if calls.exists() else []
    sent = [json.loads(line)["arguments"] for line in lines if '"t3_thread_send"' in line]
    told = [one["message"] for one in sent if one["clientRequestId"].startswith("wakes|demo|")]
    return [[line.removeprefix("- ") for line in one.split("\n\n")[1].splitlines()] for one in told]


def waiting_to_post(sandbox):
    outbox = sandbox.parent / "state" / "demo" / "home-thread" / "outbox.json"
    return json.loads(outbox.read_text()) if outbox.exists() else []


def brief(slug, *head):
    lines = [
        f"# {slug}: a demo task",
        f"Task: {slug}, a demo task",
        "Done when:",
        "- the demo works",
        "Proves it: the demo's test",
        "Size: S",
        "Where: `src/`",
        "Design: none, a demo",
        "Review: none",
        "Playbook: none",
        "Pull request: none",
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


def brief_sha(sandbox, slug):
    """The first 12 hex of the sha256 of the slug's brief in jbus's state, as `--sha` takes it."""
    kept = sandbox.parent / "state" / "demo" / "briefs" / f"{slug}.md"
    return hashlib.sha256(kept.read_bytes()).hexdigest()[:12]


def approve(sandbox, slug):
    """Approve a row on the user's word, as `jbus word` keeps it from the user's message."""
    ref = says(sandbox, f"go {slug}", message=f"m-go-{slug}")
    said = run(sandbox, f"jbus word --to demo --message {ref}").stdout.split()
    sha = brief_sha(sandbox, slug)
    return run(sandbox, f"jbus queue approve {slug} --sha {sha} --word {said[-1]}")


def test_a_gate_the_user_need_not_decide_is_closed_by_the_pass_with_no_event(demo):
    assert run(demo, "jbus gate alpha", GATE).stdout == "queued: question 1\n"

    cleared = run(demo, "jbus clear")
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
    assert waiting_to_post(demo) == []
    assert "question 1" not in run(demo, "jbus clear").stdout


def test_a_red_check_gets_a_fix_row_with_no_event(demo):
    assert run(demo, "jbus queue add beta --priority 1", brief("beta")).returncode == 0
    assert approve(demo, "beta").returncode == 0
    assert "launched beta" in run(demo, "jbus poll").stdout
    run(demo, '"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py FAILURE')
    run(demo, "jbus poll")

    cleared = run(demo, "jbus clear")
    added = run(demo, "jbus queue add beta-fix --priority 1", fix("beta-fix", "check:beta"))
    standing = demo.parent / "home" / ".local" / "state" / "home" / "demo" / "standing.md"
    standing.write_text("1. A home approves the fix of its own row's red check.\n")
    sha = brief_sha(demo, "beta-fix")
    ruled = run(demo, f"jbus queue approve beta-fix --sha {sha} --rule 1 --follows beta")
    run(demo, "jbus poll")

    assert cleared.stdout.startswith("fix check:beta: its check failed, brief a fix")
    assert "try 1 of 2" in cleared.stdout
    assert added.returncode == 0, added.stdout + added.stderr
    assert ruled.returncode == 0, ruled.stdout + ruled.stderr
    assert "beta-fix" in run(demo, "jbus queue show").stdout
    assert posted(demo) == []
    assert waiting_to_post(demo) == []


def test_a_gate_josh_has_to_decide_reaches_the_home_thread_once_from_the_one_list(demo):
    assert run(demo, "jbus gate alpha", HOLDS).stdout == "queued: question 1\n"

    run(demo, "jbus poll")
    cleared = run(demo, "jbus clear")
    run(demo, "jbus gate alpha", HOLDS)
    run(demo, "jbus poll")

    assert posted(demo) == []
    ((line,),) = listed(demo)
    assert line.startswith("question 1: remove the three stale branches, it holds (deletes data)")
    assert "decision question 1" in cleared.stdout


def test_a_fix_with_no_when_green_line_is_refused(demo):
    added = run(demo, "jbus queue add gamma-fix --priority 1", fix("gamma-fix", "check:gamma", ""))

    assert added.returncode == 1
    assert "has no When green: line" in added.stdout + added.stderr
    assert "gamma-fix" not in run(demo, "jbus queue show").stdout
    assert not (
        demo.parent / "home" / ".local" / "state" / "home" / "demo" / "blockers.json"
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
    (event,) = [one for one in posted(demo) if "check:delta" in one["line"]]
    assert event["event"] == "decision"
    assert event["say"].startswith("demo: decision delta-fix-3: check:delta had 2 fixes")
    assert 'Reply: "demo check:delta: I take it"' in event["say"]


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
    stuck = run(demo, "jbus clear").stdout
    end_thread(demo, "lam", "completed")
    tasks = demo.parent / "home" / ".local" / "state" / "home" / "demo" / "tasks"
    result = "\n## Result\nStatus: done\nBranch: lam   Pull request: none\nLeft: the docs page\n"
    (tasks / "lam.md").write_text((tasks / "lam.md").read_text() + result)
    run(demo, "jbus poll")
    left = run(demo, "jbus clear").stdout

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
    waits = run(demo, "jbus clear").stdout
    for slug in ("mu-fix-1", "mu-fix-2"):
        assert remove(demo, slug).returncode == 0
    freed = run(demo, "jbus clear").stdout
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
    (event,) = [one for one in posted(demo) if "row:mu had" in one["line"]]
    assert 'Reply: "demo row:mu: I take it"' in event["say"]


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
    blockers = demo.parent / "home" / ".local" / "state" / "home" / "demo" / "blockers.json"
    assert [one["slug"] for one in json.loads(blockers.read_text())["check:nu"]] == ["nu-fix-4"]


def test_a_scope_change_raised_by_hand_is_one_decision_with_its_reply(demo):
    question = "--question 'add a second sign-in to the plan?' --reply 'scope: yes, add it'"

    first = run(demo, f"jbus decide alpha {question}")
    again = run(demo, f"jbus decide alpha {question}")
    run(demo, "jbus poll")

    assert first.stdout == "raised: alpha: add a second sign-in to the plan?\n"
    assert again.stdout == "raised already: alpha: add a second sign-in to the plan?\n"
    (event,) = posted(demo)
    assert event["say"] == (
        'demo: decision alpha: add a second sign-in to the plan?. Reply: "demo scope: yes, add it"'
    )


def test_a_scoped_home_raises_its_own_gates_and_not_the_root_s(demo):
    state = demo.parent / "home" / ".local" / "state" / "home" / "demo"
    (state / "s").mkdir()
    (state / "s" / "plan.md").write_text("# plan\n")
    (state / "s" / "home-id").write_text("mcp:scoped-home\n")
    (state / "tasks" / "alpha.md").write_text("# alpha: a demo task\nHome: s\n")
    run(demo, "jbus gate alpha", HOLDS)

    root = run(demo, "jbus clear").stdout
    scoped = run(demo, "jbus clear --scope s").stdout

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
    """Queue a fix of the key, approve it on the standing rule, launch it and fail its check."""
    added = run(sandbox, f"jbus queue add {slug} --priority 1", fix(slug, key))
    assert added.returncode == 0, added.stdout + added.stderr
    sha = brief_sha(sandbox, slug)
    ruled = run(sandbox, f"jbus queue approve {slug} --sha {sha} --rule 1 --follows rho")
    assert ruled.returncode == 0, ruled.stdout + ruled.stderr
    assert f"launched {slug}" in run(sandbox, "jbus poll").stdout
    red_pull(sandbox, slug, path)
    end_thread(sandbox, slug, "idle")


def test_a_fix_whose_own_check_failed_is_not_at_work_and_the_next_try_then_the_cap_follow(demo):
    launched(demo, "rho")
    red_pull(demo, "rho", "src/rho/a.py")
    end_thread(demo, "rho", "idle")
    standing = demo.parent / "home" / ".local" / "state" / "home" / "demo" / "standing.md"
    standing.write_text("1. A home approves the fix of its own row's red check.\n")

    red_fix(demo, "rho-fix", "check:rho", "src/rho/b.py")
    second = run(demo, "jbus clear").stdout
    red_fix(demo, "rho-fix-2", "check:rho", "src/rho/c.py")
    capped = run(demo, "jbus clear").stdout
    run(demo, "jbus poll")

    assert second.startswith("fix check:rho: its check failed, brief a fix"), second
    assert "try 2 of 2" in second
    assert capped.startswith("decision check:rho: check:rho had 2 fixes"), capped
    (event,) = [one for one in posted(demo) if "check:rho had" in one["line"]]
    assert event["event"] == "decision"
    assert 'Reply: "demo check:rho: I take it"' in event["say"]
