"""A home clears its own blockers, and only what Josh has to decide reaches the webhook.

Each test drives the real commands in a verify-jstack sandbox, as a home types them: `jbus gate`,
`jbus clear`, `jbus queue add` and `jbus poll`. The stand-in webhook keeps every POST in
`t3/wake.jsonl`, and that file is what a test reads to say what reached Josh.
"""

import json
import subprocess
from pathlib import Path

import pytest

from test_verify_jstack import SCRIPTS, inside, launch

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
AT = "2026-10-12 00:30"


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
    each test starts on a project jbus has seen once and has posted nothing for."""
    root = sandbox.parent
    for gone in (root / "state", root / "home" / ".local" / "state" / "home" / "demo"):
        subprocess.run(["rm", "-rf", gone], check=True)
    (root / "state").mkdir()
    (root / "home" / ".local" / "state" / "home" / "demo" / "tasks").mkdir(parents=True)
    (root / "t3" / "wake.jsonl").unlink(missing_ok=True)
    (root / "gh" / "open.json").write_text("[]\n")
    assert run(sandbox, "jbus poll").returncode == 0
    return sandbox


def run(sandbox, command, stdin=None):
    if stdin is None:
        return inside(sandbox, command)
    return subprocess.run(
        ["sh", "-c", f'. "{sandbox}" && {command}'], input=stdin, capture_output=True, text=True
    )


def posted(sandbox):
    """Every event the webhook was posted, in order."""
    wake = sandbox.parent / "t3" / "wake.jsonl"
    lines = wake.read_text().splitlines() if wake.exists() else []
    return [event for line in lines for event in json.loads(line)["events"]["events"]]


def waiting_to_post(sandbox):
    outbox = sandbox.parent / "state" / "demo" / "outbox.json"
    return json.loads(outbox.read_text()) if outbox.exists() else []


def brief(slug, *head):
    lines = [
        f"# {slug}: a demo task",
        "Task: a demo task",
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


def approve(sandbox, slug):
    """Approve a row on the user's word, as `jbus word` keeps it."""
    at = f"--at \"{AT} $(date -d '{AT}' +%Z)\""
    said = run(sandbox, f"jbus word --to demo --by user {at} go {slug}").stdout.split()
    sha = f'$(sha256sum "$JBUS_STATE_DIR/demo/briefs/{slug}.md" | cut -c1-12)'
    return run(sandbox, f"jbus queue approve {slug} --sha {sha} --word {said[-1]}")


def test_a_stale_gate_is_cleared_by_the_home_with_no_event(demo):
    assert run(demo, "jbus gate alpha", GATE).stdout == "queued: question 1\n"

    cleared = run(demo, "jbus clear --after 0")
    polled = run(demo, "jbus poll")

    assert cleared.returncode == 0, cleared.stderr
    assert "cleared question 1: took its default, made tea" in cleared.stdout
    gates = (demo.parent / "home" / ".local" / "state" / "home" / "demo" / "gates.md").read_text()
    assert "## Gate q1: tea or coffee?\n" in gates
    assert "Status: answered, the default taken by the home" in gates
    (record,) = json.loads((demo.parent / "state" / "demo" / "questions.json").read_text())[
        "records"
    ]
    assert record["answer"]["closed_by"] == "gates.md"
    assert polled.returncode == 0, polled.stderr
    assert posted(demo) == []
    assert waiting_to_post(demo) == []
    assert "cleared question 1" not in run(demo, "jbus clear --after 0").stdout


def test_a_young_gate_is_left_open(demo):
    run(demo, "jbus gate alpha", GATE)

    cleared = run(demo, "jbus clear")

    assert "question 1" not in cleared.stdout
    assert not (demo.parent / "home" / ".local" / "state" / "home" / "demo" / "gates.md").exists()


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
    sha = '$(sha256sum "$JBUS_STATE_DIR/demo/briefs/beta-fix.md" | cut -c1-12)'
    ruled = run(demo, f"jbus queue approve beta-fix --sha {sha} --rule 1 --follows beta")
    run(demo, "jbus poll")

    assert cleared.stdout.startswith("fix check:beta: its check failed, brief a fix")
    assert "try 1 of 2" in cleared.stdout
    assert added.returncode == 0, added.stdout + added.stderr
    assert ruled.returncode == 0, ruled.stdout + ruled.stderr
    assert "beta-fix" in run(demo, "jbus queue show").stdout
    assert posted(demo) == []
    assert waiting_to_post(demo) == []


def test_a_gate_josh_has_to_decide_gives_exactly_one_decision_event(demo):
    assert run(demo, "jbus gate alpha", HOLDS).stdout == "queued: question 1\n"

    run(demo, "jbus poll")
    cleared = run(demo, "jbus clear --after 0")
    run(demo, "jbus gate alpha", HOLDS)
    run(demo, "jbus poll")

    (event,) = posted(demo)
    assert event["event"] == "decision"
    assert event["slug"] == "alpha"
    assert event["say"].startswith(
        "demo: decision alpha: question 1: remove the three stale branches, it holds (deletes data)"
    )
    assert 'Reply: "demo question 1: default"' in event["say"]
    assert "decision question 1" in cleared.stdout
    assert "cleared question 1" not in cleared.stdout


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
