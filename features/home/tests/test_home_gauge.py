"""The tests cover `jgauge context` and `hooks/home-gauge.sh`. They check the count that the hook
tells a home, and when the hook tells the home that count. They check the tool calls that the hook
refuses once a home is past its ceiling, and the record that the hook leaves. Every hook test runs
the hook on a made-up transcript."""

import json
import os
import re
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from jgauge import cli
from testing.paths import REPO

CHECKOUT = REPO.resolve() / "features" / "home"
HOOK = CHECKOUT / "hooks" / "home-gauge.sh"
HANDOFF = CHECKOUT / "skills" / "handoff" / "SKILL.md"
T3 = ("T3_CODE_MCP_AUTHORIZATION", "T3_MCP_BEARER_TOKEN")
SESSION = "22222222-2222-4222-8222-222222222222"
OVER = (
    "context: {count} tokens, over this home's limit of {limit}."
    f" Finish the step in hand, then read {HANDOFF} and do its steps. Start nothing new."
)
REFUSED = (
    "context: {count} tokens, over this home's ceiling of {ceiling}."
    f" Only the handoff runs now: read {HANDOFF} and do its steps."
)
T3_CODE = "mcp__t3-code__"


def call(key, fresh, read, written, *, stop="tool_use"):
    usage = {
        "input_tokens": fresh,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": written,
        "output_tokens": 7,
    }
    message = {"id": key, "model": "claude-x", "stop_reason": stop, "usage": usage}
    return {"type": "assistant", "message": message}


def transcript(tmp_path, *entries):
    path = tmp_path / f"{SESSION}.jsonl"
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
    return path


def git(cwd, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", *identity, *args], cwd=cwd, check=True, capture_output=True)


def test_context_prints_the_input_side_of_the_last_call_and_not_the_peak(tmp_path, capsys):
    path = transcript(tmp_path, call("m1", 5, 900, 95), call("m2", 2, 300, 40))
    assert cli.main(["context", str(path)]) == 0
    assert capsys.readouterr().out == "342\n"


def test_context_counts_a_call_with_no_finished_line(tmp_path, capsys):
    path = transcript(tmp_path, call("m1", 1, 10, 0), call("m2", 3, 20, 4, stop=None))
    assert cli.main(["context", str(path)]) == 0
    assert capsys.readouterr().out == "27\n"


def test_context_prints_0_for_a_transcript_with_no_call(tmp_path, capsys):
    said = {"type": "user", "message": {"role": "user", "content": "hello"}}
    for entries in ([said], []):
        assert cli.main(["context", str(transcript(tmp_path, *entries))]) == 0
        assert capsys.readouterr().out == "0\n"


def test_context_says_so_when_there_is_no_transcript(tmp_path):
    with pytest.raises(SystemExit, match="jgauge: transcript missing"):
        cli.main(["context", str(tmp_path / "none.jsonl")])


class Scene:
    """A user's home directory, a repo's main checkout, and a session's transcript."""

    def __init__(self, tmp_path):
        self.user = tmp_path / "user"
        self.user.mkdir()
        self.home_dir = self.user / ".local" / "state" / "home" / "demo"
        self.main = tmp_path / "code" / "demo"
        self.main.mkdir(parents=True)
        git(self.main, "init", "-q")
        self.transcript = transcript(tmp_path, call("m1", 4, 250000, 50000))
        self.count = 300004

    def gauge(self, root=None, *, cwd=None, t3=T3[0], event="PostToolUse", path=None, **more):
        """Run the hook as the harness does after a tool call in a thread opened in `root`. At
        the time of the call, the thread's shell is in `cwd`. `t3` is the variable T3 Code sets
        for the thread, or None outside T3 Code."""
        root = root or self.main
        env = {key: value for key, value in os.environ.items() if key not in T3}
        env.update(HOME=str(self.user), CLAUDE_PROJECT_DIR=str(root))
        if path:
            env["PATH"] = path
        if t3:
            env[t3] = "x"
        stdin = {
            "session_id": SESSION,
            "transcript_path": str(self.transcript),
            "cwd": str(cwd or root),
            "hook_event_name": event,
            **more,
        }
        done = subprocess.run(
            ["sh", str(HOOK)],
            input=json.dumps(stdin).encode(),
            capture_output=True,
            env=env,
            check=True,
        )
        return done.stdout.decode()

    def before(self, tool, **given):
        """Run the hook as the harness does before the call of `tool` with the input `given`."""
        return self.gauge(event="PreToolUse", tool_name=tool, tool_input=given)

    def state(self, name):
        return str(self.home_dir / name)

    def fill(self, count):
        self.transcript.write_text(json.dumps(call("m1", 0, count, 0)) + "\n")

    def limit(self, text):
        self.home_dir.mkdir(parents=True, exist_ok=True)
        (self.home_dir / "limit").write_text(text)

    def record(self):
        return (self.home_dir / "gauge").read_text()


@pytest.fixture
def scene(tmp_path):
    return Scene(tmp_path)


def told(said, event="PostToolUse"):
    """The one line the hook's output gives the model."""
    output = json.loads(said)
    assert output == {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": output["hookSpecificOutput"]["additionalContext"],
        }
    }
    return output["hookSpecificOutput"]["additionalContext"]


def test_a_home_at_the_limit_of_300000_is_told_its_count_in_one_line(scene):
    assert told(scene.gauge()) == OVER.format(count=300004, limit=300000)
    scene.transcript.write_text(json.dumps(call("m1", 0, 250000, 50000)) + "\n")
    assert told(scene.gauge()) == OVER.format(count=300000, limit=300000)


def test_a_home_under_the_limit_is_told_nothing(scene):
    scene.transcript.write_text(json.dumps(call("m1", 0, 250000, 49999)) + "\n")
    assert scene.gauge() == ""


def test_the_limit_is_the_one_line_of_the_homes_limit_file(scene):
    scene.limit("300005\n")
    assert scene.gauge() == ""
    scene.limit("1000\n")
    assert told(scene.gauge()) == OVER.format(count=300004, limit=1000)


@pytest.mark.parametrize("text", ["", "\n", "a lot\n", "-5\n", "1000 2000\n"])
def test_a_limit_file_that_is_no_count_leaves_the_limit_at_300000(scene, text):
    scene.limit(text)
    assert told(scene.gauge()) == OVER.format(count=300004, limit=300000)
    assert scene.record().split()[:2] == ["300004", "300000"]


def test_it_speaks_on_the_event_it_was_run_for(scene):
    said = told(scene.gauge(event="UserPromptSubmit"), event="UserPromptSubmit")
    assert said == OVER.format(count=300004, limit=300000)


def test_each_run_writes_the_count_the_limit_the_session_and_the_time(scene):
    scene.limit("400000\n")
    before = int(time.time())
    assert scene.gauge() == ""
    count, limit, session, epoch = scene.record().split()
    assert (count, limit, session) == ("300004", "400000", SESSION)
    assert before <= int(epoch) <= int(time.time())
    assert scene.record().count("\n") == 1
    scene.transcript.write_text(json.dumps(call("m2", 1, 2, 3)) + "\n")
    assert scene.gauge() == ""
    assert scene.record().split()[:3] == ["6", "400000", SESSION]
    assert sorted(path.name for path in scene.home_dir.iterdir()) == ["gauge", "limit"]


def test_a_thread_outside_t3_code_is_no_home(scene):
    assert scene.gauge(t3=None) == ""
    assert not scene.home_dir.exists()
    assert told(scene.gauge(t3=T3[1])) == OVER.format(count=300004, limit=300000)


def test_a_thread_in_a_worktree_is_no_home(scene, tmp_path):
    git(scene.main, "commit", "-q", "--allow-empty", "-m", "first")
    tree = tmp_path / "tree"
    git(scene.main, "worktree", "add", "-q", str(tree))
    assert scene.gauge(tree) == ""
    assert scene.gauge(tmp_path) == ""
    assert not scene.home_dir.exists()


def test_a_home_whose_shell_moved_is_still_the_home_of_the_repo_it_started_in(scene, tmp_path):
    git(scene.main, "commit", "-q", "--allow-empty", "-m", "first")
    tree, other = tmp_path / "tree", tmp_path / "code" / "other"
    git(scene.main, "worktree", "add", "-q", str(tree))
    other.mkdir()
    git(other, "init", "-q")
    for cwd in (tree, other, tmp_path):
        assert told(scene.gauge(cwd=cwd)) == OVER.format(count=300004, limit=300000)
    assert sorted(path.name for path in scene.home_dir.parent.iterdir()) == ["demo"]


def test_a_subagents_tool_call_is_told_nothing_and_leaves_no_record(scene):
    assert scene.gauge(agent_id="a84972d636ef06fb8", agent_type="Explore") == ""
    assert not scene.home_dir.exists()


def test_a_thread_in_the_scratch_folder_is_no_home(scene):
    scratch = scene.user / ".t3" / "scratch" / "one"
    scratch.mkdir(parents=True)
    git(scratch, "init", "-q")
    assert scene.gauge(scratch) == ""
    assert not (scene.user / ".local").exists()


def test_an_experts_thread_is_no_home(scene):
    (scene.main / "CHARTER.md").write_text("# an expert\n")
    scene.fill(900000)
    assert scene.gauge() == ""
    assert scene.before("Agent") == ""
    launch = {"title": "expert: demo", "message": "/expert demo"}
    assert scene.before(T3_CODE + "t3_thread_launch", **launch) == ""
    assert not scene.home_dir.exists()


def test_a_repo_with_an_off_file_has_no_home(scene):
    scene.limit("1000\n")
    (scene.home_dir / "off").write_text("")
    assert scene.gauge() == ""
    assert not (scene.home_dir / "gauge").exists()


def test_a_session_with_no_transcript_is_told_nothing_and_leaves_no_record(scene):
    scene.transcript.unlink()
    assert scene.gauge() == ""
    assert not scene.home_dir.exists()


def refused(said):
    """The reason the hook's output gives the model for a tool call it denies."""
    output = json.loads(said)
    assert output == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": output["hookSpecificOutput"]["permissionDecisionReason"],
        }
    }
    return output["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_home_at_the_ceiling_of_350000_is_refused_a_tool_call_with_one_line(scene):
    scene.fill(350000)
    said = refused(scene.before("Read", file_path=str(scene.main / "README.md")))
    assert said == REFUSED.format(count=350000, ceiling=350000)
    assert scene.record().split()[:3] == ["350000", "300000", SESSION]


def test_each_line_names_a_skill_file_that_is_there(scene):
    scene.fill(350000)
    lines = [told(scene.gauge()), refused(scene.before("Agent"))]
    named = [Path(path) for line in lines for path in re.findall(r"read (\S+) and", line)]
    assert [path.name for path in named if path.is_file()] == ["SKILL.md", "SKILL.md"]


def test_a_home_under_the_ceiling_is_refused_nothing(scene):
    scene.fill(349999)
    for tool in ("Read", "Agent", "Bash"):
        assert scene.before(tool) == ""
    assert told(scene.gauge()) == OVER.format(count=349999, limit=300000)


def test_the_ceiling_is_the_second_line_of_the_homes_limit_file(scene):
    scene.limit("1000\n300005\n")
    assert scene.before("Agent") == ""
    assert told(scene.gauge()) == OVER.format(count=300004, limit=1000)
    scene.limit("1000\n300004\n")
    assert refused(scene.before("Agent")) == REFUSED.format(count=300004, ceiling=300004)


@pytest.mark.parametrize("text", ["1000\n", "1000\n\n", "1000\na lot\n", "1000\n-5\n"])
def test_a_second_line_that_is_no_count_leaves_the_ceiling_at_350000(scene, text):
    scene.limit(text)
    scene.fill(349999)
    assert scene.before("Agent") == ""
    scene.fill(350000)
    assert refused(scene.before("Agent")) == REFUSED.format(count=350000, ceiling=350000)


def test_a_ceiling_under_the_limit_is_the_limit(scene):
    for text in ("400000\n", "400000\n200000\n"):
        scene.limit(text)
        scene.fill(399999)
        assert scene.before("Agent") == ""
        scene.fill(400000)
        assert refused(scene.before("Agent")) == REFUSED.format(count=400000, ceiling=400000)


HANDOFF = [
    ("Skill", {"skill": "handoff"}),
    ("Read", {"file_path": "handoff.md"}),
    ("Write", {"file_path": "handoff.md", "content": "x"}),
    ("Edit", {"file_path": "review-speed/plan.md", "old_string": "a", "new_string": "b"}),
    ("Read", {"file_path": "attic/../demo/./plan.md"}),
    ("Read", {"checkout": "templates/handoff.md"}),
    ("Read", {"checkout": "templates/handoff-seed.md"}),
    ("Read", {"checkout": "templates/../skills/home/SKILL.md"}),
    ("Bash", {"command": "git status -sb"}),
    ("ToolSearch", {"query": "select:mcp__t3-code__t3_thread_launch", "max_results": 5}),
    (T3_CODE + "t3_thread_configuration", {}),
    (T3_CODE + "list_scheduled_tasks", {}),
    (T3_CODE + "update_scheduled_task", {"scheduledTaskId": "t1", "enabled": False}),
    (T3_CODE + "delete_scheduled_task", {"scheduledTaskId": "t1"}),
    (T3_CODE + "t3_thread_launch", {"title": "home: demo", "message": "/home carry on"}),
    (T3_CODE + "t3_thread_launch", {"title": "home: demo", "message": "/home"}),
    (T3_CODE + "t3_thread_launch", {"title": "home: party", "message": "You are the next thread"}),
    ("mcp__t3_code__t3_thread_launch", {"title": "home: demo", "message": "/home scope\nseed"}),
    (T3_CODE + "t3_thread_list", {"titleContains": "home: demo"}),
    (T3_CODE + "t3_thread_send", {"threadId": "t", "message": "the home of demo is another now"}),
    (T3_CODE + "t3_thread_update", {"action": "rename", "title": "home: demo (handed off)"}),
    (T3_CODE + "t3_thread_organize", {"action": "settle"}),
]


@pytest.mark.parametrize(
    ("tool", "given"), HANDOFF, ids=[f"{t}-{i}" for i, (t, _) in enumerate(HANDOFF)]
)
def test_past_the_ceiling_a_call_the_handoff_makes_still_runs(scene, tool, given):
    scene.fill(350000)
    if "file_path" in given:
        given = given | {"file_path": scene.state(given["file_path"])}
    if "checkout" in given:
        given = {"file_path": f"{CHECKOUT}/{given['checkout']}"}
    assert scene.before(tool, **given) == ""
    assert refused(scene.before("Agent")) == REFUSED.format(count=350000, ceiling=350000)


def test_past_the_ceiling_a_call_the_handoff_does_not_make_is_denied(scene):
    scene.fill(350000)
    line = REFUSED.format(count=350000, ceiling=350000)
    crew = {"title": "fix-it", "message": "/crew fix-it"}
    for tool, given in [
        (T3_CODE + "t3_thread_launch", crew),
        (T3_CODE + "t3_thread_launch", {"title": "fix-it", "message": "/homework"}),
        (T3_CODE + "t3_thread_launch", {}),
        ("t3_thread_launch", {"title": "home: demo", "message": "/home"}),
        ("mcp__other__t3_thread_send", {"threadId": "t", "message": "x"}),
        (T3_CODE + "t3_thread_read", {"threadId": "t"}),
        (T3_CODE + "schedule_task", {"title": "audit"}),
        ("Agent", {"description": "look", "prompt": "look around"}),
        ("Read", {"file_path": str(scene.main / "README.md")}),
        ("Read", {"file_path": scene.state("../../../../../code/demo/README.md")}),
        ("Write", {"file_path": str(scene.home_dir.parent) + "-old/plan.md", "content": "x"}),
        ("Read", {"file_path": f"{CHECKOUT}/hooks/home-gauge.sh"}),
        ("Read", {"file_path": f"{CHECKOUT}/templates/../README.md"}),
        ("Read", {"file_path": "templates/handoff.md"}),
        ("Write", {"file_path": f"{CHECKOUT}/templates/handoff.md", "content": "x"}),
        ("Edit", {"file_path": f"{CHECKOUT}/skills/home/SKILL.md"}),
        ("Edit", {}),
        ("Skill", {"skill": "home"}),
        ("Skill", {}),
    ]:
        assert refused(scene.before(tool, **given)) == line, (tool, given)
    assert refused(scene.gauge(event="PreToolUse")) == line


def test_a_session_that_is_no_home_is_refused_nothing(scene, tmp_path):
    scene.fill(900000)
    git(scene.main, "commit", "-q", "--allow-empty", "-m", "first")
    tree = tmp_path / "tree"
    git(scene.main, "worktree", "add", "-q", str(tree))
    for more in ({"root": tree}, {"t3": None}, {"agent_id": "a84972d636ef06fb8"}):
        assert scene.gauge(event="PreToolUse", tool_name="Agent", tool_input={}, **more) == ""
    assert not scene.home_dir.exists()
    assert refused(scene.before("Agent")) == REFUSED.format(count=900000, ceiling=350000)


@pytest.mark.parametrize("how", ["gone", "a directory", "not text"])
def test_a_hook_that_cannot_read_the_transcript_denies_nothing(scene, how):
    scene.limit("0\n0\n")
    scene.transcript.unlink()
    if how == "a directory":
        scene.transcript.mkdir()
    elif how == "not text":
        scene.transcript.write_bytes(b"\xff\x00 nothing here\n" * 3)
    assert scene.before("Agent") == ""
    assert scene.gauge(event="PreToolUse", tool_name="Agent", transcript_path=7) == ""


def timed(scene, tmp_path, given):
    """The seconds each `tail` and `jq` the hook runs takes, and its CPU seconds, in one call
    before the tool call with the input `given`: each runs through a shim that times the real
    one. A `jq` that reads a pipe waits for what comes in it, and its CPU time does not."""
    shims = tmp_path / "shims"
    shims.mkdir(exist_ok=True)
    log = tmp_path / "timed.log"
    log.write_text("")
    for tool in ("tail", "jq"):
        shim = shims / tool
        shim.write_text(
            f"#!{sys.executable}\n"
            "import resource, subprocess, sys, time\n"
            "began = time.perf_counter()\n"
            f"done = subprocess.run([{shutil.which(tool)!r}, *sys.argv[1:]])\n"
            "took = time.perf_counter() - began\n"
            "used = resource.getrusage(resource.RUSAGE_CHILDREN)\n"
            f"with open({str(log)!r}, 'a') as log:\n"
            f"    log.write(f'{tool} {{took:.3f}} {{used.ru_utime + used.ru_stime:.3f}}\\n')\n"
            "sys.exit(done.returncode)\n"
        )
        shim.chmod(0o755)
    path = f"{shims}{os.pathsep}{os.environ['PATH']}"
    scene.gauge(event="PreToolUse", path=path, tool_name="Read", tool_input=given)
    times = map(str.split, log.read_text().splitlines())
    return ", ".join(f"{tool} {took} s ({used} CPU s)" for tool, took, used in times)


def cpu():
    """The CPU seconds the children this process waited on have used: a runner whose cores are
    busy makes the hook wait longer, and does not make it use more."""
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return children.ru_utime + children.ru_stime


def reference(scene, folder):
    """The CPU seconds of a fixed run of the programs the hook starts, each started the times
    the hook starts it, on nothing it reads: the yardstick of this machine."""
    script = folder / "reference.sh"
    script.write_text(
        'cd "$1" || exit 1\n'
        "for n in 1 2 3 4 5; do git rev-parse --git-dir > /dev/null; done\n"
        "for n in 1 2; do jq -n 1 > /dev/null; done\n"
        'tail -c 1 "$0" > /dev/null\n'
        'mkdir -p "$2" && date +%s > "$2/new" && mv "$2/new" "$2/old"\n'
        'basename "$2" > /dev/null && dirname "$2" > /dev/null\n'
    )
    began = cpu()
    subprocess.run(["sh", str(script), str(scene.main), str(folder / "made")], check=True)
    return cpu() - began


def test_before_a_tool_call_on_a_transcript_of_2_mb_it_uses_under_2_2_references(scene, tmp_path):
    """Before each tool call the hook reads the transcript's tail, so on 2 MB it uses 1.5 to 1.9
    times the reference's CPU time (1.50 on a macOS runner under the whole suite), and reading
    it all, or its tail three times, takes it to 2.5 or more. Its wall time tells nothing on a
    busy runner: a call that took 16 ms on an idle Linux took 131 ms at best of five on a macOS
    runner under the whole suite."""
    said = {"type": "user", "message": {"role": "user", "content": "x" * 2000}}
    lines = [json.dumps(entry) + "\n" for entry in (said, call("m1", 4, 250000, 50000))]
    scene.transcript.write_text("".join(lines) * (2_000_000 // sum(map(len, lines)) + 1))
    assert scene.transcript.stat().st_size > 2_000_000
    given = {"file_path": str(scene.main / "README.md")}
    took, used, yardsticks = [], [], []
    for _ in range(5):
        began, start = cpu(), time.perf_counter()
        assert scene.before("Read", **given) == ""
        took.append(time.perf_counter() - start)
        used.append(cpu() - began)
        yardsticks.append(reference(scene, tmp_path))
    times = min(used) / min(yardsticks)
    assert times < 2.2, (
        f"the hook used {min(used):.4f} CPU s before a tool call, {times:.2f} times the"
        f" reference's {min(yardsticks):.4f} s, {times / 2.2:.2f} times the limit of 2.2;"
        f" the five used {', '.join(f'{one:.4f}' for one in used)} CPU s and took"
        f" {', '.join(f'{one:.3f}' for one in took)} s; in a sixth, {timed(scene, tmp_path, given)}"
    )
    assert scene.record().split()[0] == "300004"


def big(size):
    return {"type": "user", "message": {"role": "user", "content": "x" * size}}


@pytest.mark.parametrize(
    "entries",
    [
        [],
        [big(10)],
        [call("m1", 5, 900, 95), call("m2", 2, 300, 40)],
        [call("m1", 1, 10, 0), call("m2", 3, 20, 4, stop=None)],
        [call("m1", 5, 900, 95), big(300000)],
        [big(300000), call("m1", 5, 900, 95), big(1000)],
        [call("m1", 5, 900, 95), big(300000), call("m2", 1, 2, 3), big(1000)],
        [
            call("m1", 5, 900, 95),
            {
                "type": "assistant",
                "message": {"id": "s", "model": "<synthetic>", "usage": {"input_tokens": 9}},
            },
        ],
        [
            call("m1", 5, 900, 95),
            {
                "type": "assistant",
                "message": {"id": "", "model": "m", "usage": {"input_tokens": 9}},
            },
        ],
        [
            call("m1", 5, 900, 95),
            {"type": "assistant", "message": {"id": "m2", "model": "m", "usage": None}},
        ],
        [
            call("m1", 5, 900, 95),
            {
                "type": "assistant",
                "message": {
                    "id": "m2",
                    "model": "m",
                    "usage": {"input_tokens": -4, "cache_read_input_tokens": "9"},
                },
            },
        ],
    ],
)
def test_the_count_the_hook_records_is_the_one_jgauge_context_prints(scene, capsys, entries):
    """The counts agree even when `jgauge context` prints no count. It prints none for a transcript
    that has no line it can read."""
    scene.transcript.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
    with scene.transcript.open("a") as file:
        file.write('{"type": "assistant", "message": {"id": "m9", "usa')
    try:
        cli.main(["context", str(scene.transcript)])
    except SystemExit:
        pass
    count = capsys.readouterr().out.split()
    assert scene.gauge() == ""
    assert [path.read_text().split()[0] for path in scene.home_dir.glob("gauge")] == count
