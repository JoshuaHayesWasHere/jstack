"""The two lessons skills, `correct` and `reflect`: the tests lift their shell blocks out and
run them."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from testing.paths import REPO

FEATURE = Path(__file__).parents[1]
SKILLS = {name: FEATURE / "skills" / name / "SKILL.md" for name in ("correct", "reflect")}
FIXTURE = Path(__file__).parent / "fixtures" / "projects"
EM_DASH = "\N{EM DASH}"
TEXTS = sorted(
    path for name in SKILLS for path in (FEATURE / "skills" / name).rglob("*") if path.is_file()
)
HOME_SESSION = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_SESSION = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def sh_blocks(text):
    return re.findall(r"^```sh\n(.*?)^```$", text, re.M | re.S)


def block(skill, marker):
    (found,) = [body for body in sh_blocks(SKILLS[skill].read_text()) if marker in body]
    return found


def em_dashes(text):
    lines = [n for n, line in enumerate(text.splitlines(), 1) if EM_DASH in line]
    return [f"has an em dash on line {lines}"] if lines else []


@pytest.mark.parametrize("path", TEXTS, ids=lambda path: str(path.relative_to(REPO)))
def test_no_em_dash(path):
    assert em_dashes(path.read_text()) == []


def test_reflect_has_its_four_prompts():
    named = set(re.findall(r"`(references/[a-z-]+\.md)`", SKILLS["reflect"].read_text()))
    there = {
        f"references/{path.name}" for path in (SKILLS["reflect"].parent / "references").iterdir()
    }
    assert named == there


def test_an_em_dash_in_a_skill_is_a_problem():
    assert em_dashes(f"# a\n\nOne thing {EM_DASH} and another.\n") == ["has an em dash on line [3]"]


class Machine:
    """A user's home directory with the fixture as its `~/.claude/projects`."""

    def __init__(self, tmp_path):
        self.user = tmp_path / "user"
        self.projects = self.user / ".claude" / "projects"
        shutil.copytree(FIXTURE, self.projects)
        self.cwd = tmp_path / "somewhere"
        self.cwd.mkdir()
        self.aged(HOME_SESSION, 2000)
        self.aged(OTHER_SESSION, 1000)

    def file(self, session, directory="-work-demo"):
        return self.projects / directory / f"{session}.jsonl"

    def aged(self, session, seconds):
        os.utime(self.file(session), (seconds, seconds))

    def run(self, script, *, cwd=None, **env):
        cwd = cwd or self.cwd
        base = {"PATH": os.environ["PATH"], "HOME": str(self.user), "PWD": str(cwd)}
        done = subprocess.run(
            ["sh", "-c", script], capture_output=True, text=True, env={**base, **env}, cwd=cwd
        )
        assert done.returncode == 0, done.stderr
        return done.stdout.splitlines()


@pytest.fixture
def machine(tmp_path):
    return Machine(tmp_path)


FIND = block("reflect", "CLAUDE_CODE_SESSION_ID")


def test_the_thread_that_runs_it_gets_its_own_transcript(machine):
    machine.aged(OTHER_SESSION, 3000)
    assert machine.run(FIND, CLAUDE_CODE_SESSION_ID=HOME_SESSION) == [
        str(machine.file(HOME_SESSION))
    ]


@pytest.mark.parametrize("session", [HOME_SESSION, OTHER_SESSION])
def test_a_session_id_put_before_the_block_finds_that_thread(machine, session):
    printed = machine.run(f"S={session}\n{FIND}", CLAUDE_CODE_SESSION_ID="not-this-one")
    assert printed == [str(machine.file(session))]


@pytest.mark.parametrize(
    ("newer", "older"), [(HOME_SESSION, OTHER_SESSION), (OTHER_SESSION, HOME_SESSION)]
)
def test_a_directory_put_before_the_block_finds_its_newest_thread(machine, newer, older):
    machine.aged(newer, 5000)
    machine.aged(older, 4000)
    printed = machine.run(f"W=/work/demo\n{FIND}", CLAUDE_CODE_SESSION_ID="not-this-one")
    assert printed == [str(machine.file(newer))]


def test_with_no_session_id_it_is_the_newest_thread_of_the_directory_it_runs_in(machine):
    named = re.sub(r"[^A-Za-z0-9]", "-", str(machine.cwd))
    (machine.projects / "-work-demo").rename(machine.projects / named)
    assert machine.run(FIND) == [str(machine.file(HOME_SESSION, named))]


def test_a_subagent_s_transcript_is_never_the_one_found(machine):
    machine.file(HOME_SESSION).unlink()
    machine.file(OTHER_SESSION).unlink()
    assert machine.run(f"W=/work/demo\n{FIND}") == [
        f"no transcript: nothing under {machine.projects} for /work/demo"
    ]


def test_a_session_that_is_not_there_is_said_and_no_other_is_given(machine):
    assert machine.run(f"S=cccccccc\n{FIND}") == [
        f"no transcript: nothing under {machine.projects} for cccccccc"
    ]


DIGEST = block("reflect", "input_line_number")


def test_the_digest_is_what_was_said_and_done_with_the_long_parts_cut(machine, tmp_path):
    (found,) = machine.run(FIND, CLAUDE_CODE_SESSION_ID=HOME_SESSION)
    script = DIGEST.replace("<the file step 1 printed>", found)
    assert script != DIGEST
    (printed,) = machine.run(script, TMPDIR=str(tmp_path))
    out = tmp_path / f"reflect-{HOME_SESSION}.txt"
    digest = out.read_text()
    assert printed == f"{out} {len(digest.encode())} bytes"

    lines = digest.splitlines()
    assert [line for line in lines if line.startswith("line ")] == [
        "line 2, user:",
        "line 4, assistant:",
        "line 5, user:",
        "line 7, user:",
        "line 8, assistant:",
    ]
    assert lines[1] == "Fix the login test, and never use tabs."
    assert lines[4] == "Reading the test first."
    assert lines[5].startswith('[Bash] {"command":"make check"')
    assert "private reasoning" not in digest
    assert "not a turn" not in digest
    result = next(line for line in lines if line.startswith("[result] "))
    assert len(result) == len("[result] ") + 300
    assert "the end of a long result" not in digest
    text = next(line for line in lines if line.startswith("Replaced the tabs."))
    assert len(text) == 4000
    assert "the end of a long text" not in digest


EVIDENCE = block("correct", "git log")


def test_correct_lists_the_commits_and_brief_lines_that_are_corrections(tmp_path):
    user = tmp_path / "user"
    tasks = user / ".local" / "state" / "home" / "demo" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "one.md").write_text(
        "# one\nTask: a task\n## Result\nSteers: use spaces, not tabs\nNoticed: none\n"
        "## Review\nFindings:\n- warning src/a.py:3 a tab\n- not a finding\n"
    )
    (tasks / "two.md").write_text("## Result\nSteers: none\nNoticed: the lint is off\n")
    repo = tmp_path / "code" / "demo"
    repo.mkdir(parents=True)
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(user),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        **{
            f"GIT_{who}_{what}": "t@example.com"
            for who in ("AUTHOR", "COMMITTER")
            for what in ("NAME", "EMAIL")
        },
    }

    def git(*args):
        subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)

    git("init", "-q")
    for subject in (
        "feat: a thing",
        "fix(a): tabs again",
        'Revert "feat: a thing"',
        "docs: prefix",
    ):
        git("commit", "-q", "--allow-empty", "-m", subject)
    done = subprocess.run(
        ["sh", "-c", EVIDENCE], cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    printed = [re.sub(r"^[0-9a-f]{7,} ", "", line) for line in done.stdout.splitlines()]
    assert printed == [
        "## commits that fix or revert",
        'Revert "feat: a thing"',
        "fix(a): tabs again",
        "## steers, things noticed and review findings in the briefs",
        "one.md:Steers: use spaces, not tabs",
        "one.md:- warning src/a.py:3 a tab",
        "two.md:Noticed: the lint is off",
    ]


@pytest.mark.parametrize(
    "lines",
    [
        None,
        [],
        ['{"type": "attachment"}'],
        ['{"type": "user", "message": {"content": "said"}}', "not json"],
    ],
    ids=["no file", "empty", "no turn", "cut off"],
)
def test_a_digest_that_was_not_made_is_said(machine, tmp_path, lines):
    transcript = tmp_path / "cccccccc.jsonl"
    if lines is not None:
        transcript.write_text("".join(line + "\n" for line in lines))
    script = DIGEST.replace("<the file step 1 printed>", str(transcript))
    assert machine.run(script, TMPDIR=str(tmp_path)) == [
        f"no digest: jq failed on {transcript}, or it holds no turn"
    ]


def test_a_turn_with_no_content_is_left_out_of_the_digest(machine, tmp_path):
    transcript = tmp_path / "cccccccc.jsonl"
    transcript.write_text(
        '{"type": "user", "message": {"content": "said"}}\n'
        '{"type": "assistant", "message": {"content": null}}\n'
    )
    script = DIGEST.replace("<the file step 1 printed>", str(transcript))
    out = tmp_path / "reflect-cccccccc.txt"
    assert machine.run(script, TMPDIR=str(tmp_path)) == [f"{out} 20 bytes"]
    assert out.read_text() == "line 1, user:\nsaid\n\n"


AGENT_TYPES = dict(
    re.fullmatch(r"(\S+) \(Tools: (.*)\)", line).groups()
    for line in (REPO / "testing/tests/fixtures/claude/agent-types.txt").read_text().splitlines()
)
WRITE_TOOLS = ["Edit", "NotebookEdit", "Write"]


def write_tools(tools):
    """The write tools an agent type has, read from the Agent tool's list of its tools."""
    named = set(tools.removeprefix("All tools except ").split(", "))
    if tools == "*":
        return WRITE_TOOLS
    if tools.startswith("All tools except "):
        return [tool for tool in WRITE_TOOLS if tool not in named]
    return [tool for tool in WRITE_TOOLS if tool in named]


def launch_problems(call):
    """What lets a subagent change a file when `call` starts it. `call` is an Agent call."""
    kind = call.get("subagent_type", "general-purpose")
    if kind not in AGENT_TYPES:
        return [f"{kind} is no agent type in testing/tests/fixtures/claude/agent-types.txt"]
    found = [f"{kind} has the {tool} tool" for tool in write_tools(AGENT_TYPES[kind])]
    if call.get("isolation"):
        found.append("a worktree of its own hides what it writes from the worktree check")
    return found


def reviewer_launch():
    """The one JSON block of the reflect skill: the Agent call that starts a reviewer."""
    (body,) = re.findall(r"^```json\n(.*?)^```$", SKILLS["reflect"].read_text(), re.M | re.S)
    return json.loads(body)


def test_a_reviewer_is_started_with_no_tool_that_writes():
    assert launch_problems(reviewer_launch()) == []


def test_a_reviewer_runs_on_the_session_s_model_in_the_foreground():
    call = reviewer_launch()
    assert {key: call.get(key) for key in ("model", "effort", "run_in_background")} == {
        "model": None,
        "effort": None,
        "run_in_background": False,
    }


EVERY_WRITE_TOOL = [
    "general-purpose has the Edit tool",
    "general-purpose has the NotebookEdit tool",
    "general-purpose has the Write tool",
]


@pytest.mark.parametrize(
    ("call", "problems"),
    [
        ({"subagent_type": "Explore"}, []),
        ({"subagent_type": "Plan"}, []),
        ({"subagent_type": "general-purpose"}, EVERY_WRITE_TOOL),
        pytest.param({}, EVERY_WRITE_TOOL, id="no type named is a general-purpose agent"),
        ({"subagent_type": "statusline-setup"}, ["statusline-setup has the Edit tool"]),
        (
            {"subagent_type": "reviewer"},
            ["reviewer is no agent type in testing/tests/fixtures/claude/agent-types.txt"],
        ),
        (
            {"subagent_type": "Explore", "isolation": "worktree"},
            ["a worktree of its own hides what it writes from the worktree check"],
        ),
    ],
    ids=["Explore", "Plan", "general-purpose", "no type", "statusline-setup", "unknown", "apart"],
)
def test_an_agent_call_that_can_write_is_a_problem(call, problems):
    assert launch_problems(call) == problems


@pytest.mark.parametrize(
    ("tools", "has"),
    [
        ("*", ["Edit", "NotebookEdit", "Write"]),
        ("All tools except Agent, Edit, Write, NotebookEdit", []),
        ("All tools except Agent, Edit", ["NotebookEdit", "Write"]),
        ("Read, Grep", []),
        ("Read, Write", ["Write"]),
    ],
)
def test_the_write_tools_of_an_agent_type_are_read_from_its_tools(tools, has):
    assert write_tools(tools) == has


WORKTREE = block("reflect", "reflect-before")


class Worktree:
    """A git repository with one commit, in which the test runs the reflect skill's worktree
    check."""

    def __init__(self, tmp_path):
        self.path = tmp_path / "repo"
        self.path.mkdir()
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            **{
                f"GIT_{who}_{what}": "t@example.com"
                for who in ("AUTHOR", "COMMITTER")
                for what in ("NAME", "EMAIL")
            },
        }
        self.git("init", "-q")
        (self.path / "kept.txt").write_text("kept\n")
        (self.path / "open.txt").write_text("as committed\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "first")
        (self.path / "open.txt").write_text("the thread's own edit\n")
        (self.path / "new.txt").write_text("the thread's own file\n")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.path, env=self.env, check=True, capture_output=True)

    def check(self, when, cwd=None):
        script = WORKTREE.replace("<before or after>", when)
        assert script != WORKTREE
        done = subprocess.run(
            ["sh", "-c", script], cwd=cwd or self.path, env=self.env, capture_output=True, text=True
        )
        assert done.returncode == 0, done.stderr
        return done.stdout.splitlines()


@pytest.fixture
def worktree(tmp_path):
    return Worktree(tmp_path)


def test_reviewers_that_only_read_leave_the_worktree_unchanged(worktree):
    assert worktree.check("before") == ["worktree recorded"]
    assert worktree.check("after") == ["worktree unchanged"]
    assert worktree.check("after") == ["worktree unchanged"]


def written(worktree):
    (worktree.path / "notes.md").write_text("a lesson\n")


def edited(worktree):
    (worktree.path / "kept.txt").write_text("kept, and more\n")


def edited_a_file_already_dirty(worktree):
    (worktree.path / "open.txt").write_text("the thread's own edit, and a reviewer's\n")


def rewritten(worktree):
    (worktree.path / "new.txt").write_text("a reviewer's file now\n")


def deleted(worktree):
    (worktree.path / "kept.txt").unlink()


def committed(worktree):
    worktree.git("commit", "-q", "--allow-empty", "-m", "a reviewer's commit")


@pytest.mark.parametrize(
    ("change", "status"),
    [
        (written, [" M open.txt", "?? new.txt", "?? notes.md"]),
        (edited, [" M kept.txt", " M open.txt", "?? new.txt"]),
        (edited_a_file_already_dirty, [" M open.txt", "?? new.txt"]),
        (rewritten, [" M open.txt", "?? new.txt"]),
        (deleted, [" D kept.txt", " M open.txt", "?? new.txt"]),
        (committed, [" M open.txt", "?? new.txt"]),
    ],
    ids=lambda value: value.__name__ if callable(value) else None,
)
def test_a_reviewer_that_changed_the_worktree_fails_the_run(worktree, change, status):
    worktree.check("before")
    change(worktree)
    assert worktree.check("after") == ["worktree changed: the run fails", *status]


def test_a_change_outside_the_directory_the_check_runs_in_fails_the_run(worktree):
    (worktree.path / "sub").mkdir()
    (worktree.path / "other").mkdir()
    (worktree.path / "other" / "notes.txt").write_text("the thread's own notes\n")
    worktree.check("before", cwd=worktree.path / "sub")
    assert worktree.check("after", cwd=worktree.path / "sub") == ["worktree unchanged"]
    (worktree.path / "other" / "notes.txt").write_text("a reviewer's notes now\n")
    assert worktree.check("after", cwd=worktree.path / "sub") == [
        "worktree changed: the run fails",
        " M open.txt",
        "?? new.txt",
        "?? other/",
    ]


def test_the_worktree_is_recorded_again_at_the_next_run(worktree):
    worktree.check("before")
    written(worktree)
    assert worktree.check("before") == ["worktree recorded"]
    assert worktree.check("after") == ["worktree unchanged"]


def test_a_check_with_nothing_recorded_before_is_said(worktree):
    assert worktree.check("after") == [
        "no worktree check: nothing was recorded before the reviewers"
    ]


def test_outside_a_git_repository_there_is_no_worktree_check(worktree, tmp_path):
    for when in ("before", "after"):
        assert worktree.check(when, cwd=tmp_path) == [
            f"no worktree check: {tmp_path} is not in a git repository"
        ]


def test_a_check_that_is_not_told_when_says_so(worktree):
    assert worktree.check("later") == ["no worktree check: when is 'later', not before or after"]
