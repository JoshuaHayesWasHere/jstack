"""The skills added after the first eleven: each is typed only, and its shell blocks are run."""

import json
import os
import re
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SKILLS = REPO / "skills"
EM_DASH = "\N{EM DASH}"
BEFORE = {
    "correct",
    "crew",
    "expert",
    "grilling",
    "handoff",
    "home",
    "nohome",
    "pr-review",
    "reflect",
    "scout",
    "technical-writing",
    "unslop",
}
ADDED = sorted(path.name for path in SKILLS.iterdir() if path.is_dir() and path.name not in BEFORE)
BUILT_IN = set(
    """
    add-dir agents bashes bug clear code-review compact config context copy cost diff doctor
    effort exit export fast feedback help hooks ide init insights login logout loop mcp
    memory model permissions plan plugin pr-comments quit release-notes rename resume review
    rewind run sandbox schedule security-review simplify skills stats status statusline
    tasks terminal-setup theme todos upgrade usage vim workflows
    """.split()
)
NOT_IN_A_SUBAGENT_CALL = {"model", "effort", "isolation"}
DAY = 24 * 60 * 60


def test_each_skill_listed_as_here_before_the_understanding_skills_is_still_a_skill():
    assert BEFORE <= {path.name for path in SKILLS.iterdir() if path.is_dir()}


def front(text):
    """A skill's frontmatter as its `key: value` lines, as written, or None if it has none."""
    found = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not found:
        return None
    pairs = (line.partition(":") for line in found.group(1).splitlines())
    return {key.strip(): value.strip() for key, _, value in pairs}


def em_dashes(path):
    lines = [n for n, line in enumerate(path.read_text().splitlines(), 1) if EM_DASH in line]
    return [f"{path.name} has an em dash on line {lines}"] if lines else []


def problems(directory):
    """What is wrong with the skill in `directory` beyond what `test_skill_frontmatter.py` checks:
    a built-in command's name, and em dashes."""
    skill = directory / "SKILL.md"
    if not skill.is_file():
        return ["has no SKILL.md"]
    fields = front(skill.read_text())
    if fields is None:
        return ["has no frontmatter"]
    found = []
    name = fields.get("name")
    if name in BUILT_IN:
        found.append(f"has the name of the built-in command /{name}")
    for path in sorted(directory.rglob("*.md")):
        found += em_dashes(path)
    return found


def blocks(text, language):
    """The body of every fenced block of `language` in a skill, indent taken off, in order."""
    found = re.findall(rf"^([ \t]*)```{language}\n(.*?)^\1```$", text, re.M | re.S)
    return [textwrap.dedent(body) for _, body in found]


def block(skill, marker):
    """The one `sh` block of the skill named `skill` that has `marker` in it."""
    (found,) = [b for b in blocks((SKILLS / skill / "SKILL.md").read_text(), "sh") if marker in b]
    return found


def named_files(skill):
    """Every file a skill's text names by a path from its own directory."""
    text = skill.read_text()
    paths = re.findall(r"`((?:references|\.\.)/[^`<>*\s]+\.md)`", text)
    paths += re.findall(r"\]\(((?:\.|references)[^)\s]*)\)", text)
    return sorted(set(paths))


def run(body, cwd, home, before="", session=None):
    """Run a block as its reader would, in `cwd`, with `home` as the home directory."""
    env = {"HOME": str(home), "PATH": os.environ["PATH"], "GIT_CONFIG_GLOBAL": os.devnull}
    if session:
        env["CLAUDE_CODE_SESSION_ID"] = session
    done = subprocess.run(
        ["sh", "-c", before + body], cwd=cwd, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
    return done.stdout.splitlines()


def git(cwd, *args):
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(cwd),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "a",
        "GIT_AUTHOR_EMAIL": "a@example.com",
        "GIT_COMMITTER_NAME": "a",
        "GIT_COMMITTER_EMAIL": "a@example.com",
    }
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def aged(path, days, text="{}\n"):
    """Write `path` and set its last change `days` days back. Returns the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    then = time.time() - days * DAY
    os.utime(path, (then, then))
    return path


@pytest.fixture
def home(tmp_path):
    made = tmp_path / "home"
    made.mkdir()
    return made


@pytest.fixture
def repo(tmp_path):
    """A repository called demo, on `main`, with one commit."""
    made = tmp_path / "demo"
    made.mkdir()
    git(made, "init", "-q", "-b", "main")
    (made / "a.txt").write_text("one\n")
    git(made, "add", "a.txt")
    git(made, "commit", "-q", "-m", "one")
    return made


@pytest.fixture
def outside(tmp_path):
    """A directory that is in no repository, whatever the temporary directory is in."""
    made = tmp_path / "outside"
    made.mkdir()
    (made / ".git").write_text("not a repository\n")
    return made


def transcripts(home, directory):
    return home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(directory))


def test_skills_were_added():
    assert ADDED != []


@pytest.mark.parametrize("name", ADDED)
def test_an_added_skill_has_no_problem(name):
    assert problems(SKILLS / name) == []


@pytest.mark.parametrize("name", ADDED)
def test_every_file_an_added_skill_names_is_there(name):
    skill = SKILLS / name / "SKILL.md"
    missing = [path for path in named_files(skill) if not (skill.parent / path).is_file()]
    assert missing == []


@pytest.mark.parametrize(
    ("name", "body"),
    [
        pytest.param(name, body, id=f"{name}:{number}")
        for name in ADDED
        for number, body in enumerate(blocks((SKILLS / name / "SKILL.md").read_text(), "sh"), 1)
    ],
)
def test_every_block_of_an_added_skill_runs_and_says_something(name, body, repo, home):
    assert run(body, repo, home) != []


@pytest.mark.parametrize(
    ("name", "body"),
    [
        pytest.param(name, body, id=f"{name}:{number}")
        for name in ADDED
        for number, body in enumerate(blocks((SKILLS / name / "SKILL.md").read_text(), "json"), 1)
    ],
)
def test_a_subagent_an_added_skill_starts_is_read_only_on_this_sessions_model(name, body):
    call = json.loads(body)
    assert call.get("subagent_type") == "Explore", "a JSON block here is an Agent call"
    assert NOT_IN_A_SUBAGENT_CALL & set(call) == set()


def test_recall_lists_the_transcripts_of_this_directory_in_the_window_newest_first(repo, home):
    here = transcripts(home, repo)
    new = aged(here / "new.jsonl", 0)
    older = aged(here / "older.jsonl", 3)
    aged(here / "stale.jsonl", 30)
    aged(here / "mine.jsonl", 0)
    aged(here / "new" / "subagents" / "agent.jsonl", 0)
    aged(transcripts(home, "/another/project") / "theirs.jsonl", 0)
    body = block("recall", ".claude/projects")
    assert run(body, repo, home, session="mine") == [str(new), str(older)]
    assert run(body, repo, home, before="DAYS=2\n", session="mine") == [str(new)]


def test_recall_reads_the_directory_it_is_given(repo, home, tmp_path):
    worktree = tmp_path / "trees" / "fix.login"
    theirs = aged(transcripts(home, worktree) / "theirs.jsonl", 1)
    body = block("recall", ".claude/projects")
    assert run(body, repo, home, before=f"W={worktree}\n") == [str(theirs)]


def test_recall_says_so_when_there_is_no_transcript(repo, home):
    aged(transcripts(home, repo) / "stale.jsonl", 30)
    said = run(block("recall", ".claude/projects"), repo, home)
    assert said == [
        f"no transcript: nothing under {transcripts(home, repo)} changed in the last 7 days"
    ]


def test_recall_lists_what_the_home_wrote_in_the_window(repo, home):
    record = home / ".local" / "state" / "home" / "demo"
    brief = aged(record / "tasks" / "fix-login.md", 0)
    handoff = aged(record / "handoff.md", 2)
    aged(record / "tasks" / "old.md", 30)
    aged(record / "reports" / "page.html", 0)
    aged(home / ".local" / "state" / "home" / "other" / "handoff.md", 0)
    assert run(block("recall", "home record"), repo, home) == [str(brief), str(handoff)]


def test_recall_says_so_when_there_is_no_home_record(repo, home, outside):
    body = block("recall", "home record")
    record = home / ".local" / "state" / "home" / "demo"
    assert run(body, repo, home) == [
        f"no home record: nothing under {record} changed in the last 7 days"
    ]
    assert run(body, outside, home) == ["no home record: this is not a git repository"]


GATES = """\
## Gate 1: May the cache be dropped on deploy?
Status: open
Asked by: fix-login, thread mcp:1
Default: it is kept

## Gate 2: Which name does the flag get?
Status: answered
Default: the old one

## Gate 3: Is the old endpoint still called?
Status: open
"""


def test_ketchup_prints_the_gates_that_are_open(repo, home):
    aged(home / ".local" / "state" / "home" / "demo" / "gates.md", 0, GATES)
    root = home / ".local" / "state" / "home" / "demo" / "gates.md"
    scoped = aged(root.parent / "speed" / "gates.md", 0, GATES.replace("Gate 1", "Gate 7"))
    aged(root.parent / "tasks" / "gates.md", 0, "## Gate 9: Closed?\nStatus: answered\n")
    assert run(block("ketchup", "gates.md"), repo, home) == [
        f"## Gate 1: May the cache be dropped on deploy?, in {root}",
        f"## Gate 3: Is the old endpoint still called?, in {root}",
        f"## Gate 7: May the cache be dropped on deploy?, in {scoped}",
        f"## Gate 3: Is the old endpoint still called?, in {scoped}",
    ]


def test_ketchup_says_so_when_no_gate_is_open(repo, home, outside):
    body = block("ketchup", "gates.md")
    gates = home / ".local" / "state" / "home" / "demo" / "gates.md"
    none = f"no gates: none is open in {gates} or in a scoped home's, {gates.parent}/*/gates.md"
    assert run(body, repo, home) == [none]
    aged(gates, 0, GATES.replace("Status: open", "Status: answered"))
    assert run(body, repo, home) == [none]
    assert run(body, outside, home) == ["no gates: this is not a git repository"]


def test_automate_me_finds_the_mode_skills_and_when_each_last_changed(repo, home):
    own = aged(home / ".claude" / "skills" / "jay-mode" / "SKILL.md", 3)
    shared = aged(repo / ".claude" / "skills" / "priya-mode" / "SKILL.md", 0)
    aged(home / ".claude" / "skills" / "unslop" / "SKILL.md", 0)
    when = [time.strftime("%F", time.localtime(path.stat().st_mtime)) for path in (own, shared)]
    assert run(block("automate-me", "-mode"), repo, home) == [
        f"{own}, last changed {when[0]}",
        f"{shared}, last changed {when[1]}",
    ]


def test_automate_me_says_so_when_there_is_no_mode_skill(repo, home):
    aged(home / ".claude" / "skills" / "unslop" / "SKILL.md", 0)
    assert run(block("automate-me", "-mode"), repo, home) == [
        "no mode skill: none under ~/.claude/skills or .claude/skills"
    ]


def test_blast_radius_prints_the_files_a_branch_and_its_working_tree_changed(repo, home):
    git(repo, "checkout", "-q", "-b", "fix-login")
    (repo / "b.txt").write_text("two\n")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-q", "-m", "two")
    (repo / "a.txt").write_text("one\nand uncommitted\n")
    (repo / "c.txt").write_text("three\n")
    said = run(block("blast-radius", "merge-base"), repo, home)
    assert [line.split("|")[0].strip() for line in said[:2]] == ["a.txt", "b.txt"]
    assert said[2].strip().startswith("2 files changed")
    assert said[3:] == [" new, not added: c.txt"]


def test_blast_radius_reads_a_change_that_is_only_new_files(repo, home):
    (repo / "c.txt").write_text("three\n")
    assert run(block("blast-radius", "merge-base"), repo, home) == [" new, not added: c.txt"]


def test_blast_radius_says_so_when_there_is_no_change_to_read(repo, home, outside):
    body = block("blast-radius", "merge-base")
    assert run(body, repo, home) == ["no change to read: nothing differs from main"]
    assert run(body, outside, home) == [
        "no change to read: this is not a git repository with a branch main"
    ]


GOOD = """\
---
name: a-skill
description: Explain it.
disable-model-invocation: true
---

# A
"""


def check(tmp_path, text, name="a-skill"):
    path = tmp_path / name / "SKILL.md"
    path.parent.mkdir()
    path.write_text(text)
    return problems(path.parent)


def test_a_skill_hidden_from_the_model_has_no_problem(tmp_path):
    assert check(tmp_path, GOOD) == []


def test_the_name_of_a_built_in_command_is_a_problem(tmp_path):
    assert check(tmp_path, GOOD.replace("a-skill", "review"), name="review") == [
        "has the name of the built-in command /review"
    ]


def test_no_frontmatter_and_no_skill_file_are_problems(tmp_path):
    assert check(tmp_path, "# A\n") == ["has no frontmatter"]
    (tmp_path / "empty").mkdir()
    assert problems(tmp_path / "empty") == ["has no SKILL.md"]


def test_an_em_dash_in_a_file_beside_the_skill_is_a_problem(tmp_path):
    check(tmp_path, GOOD)
    reference = tmp_path / "a-skill" / "references" / "prompt.md"
    reference.parent.mkdir()
    reference.write_text(f"One thing {EM_DASH} and another.\n")
    assert problems(tmp_path / "a-skill") == ["prompt.md has an em dash on line [1]"]


def test_a_block_inside_a_list_is_found_with_its_indent_taken_off():
    text = (
        "1. a\n\n   ```sh\n   if true; then\n       echo b\n   fi\n   ```\n\n```sh\necho c\n```\n"
    )
    assert blocks(text, "sh") == ["if true; then\n    echo b\nfi\n", "echo c\n"]
