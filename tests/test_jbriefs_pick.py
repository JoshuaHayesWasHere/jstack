"""`jbriefs pick` names the role, the playbook and the skills for a brief, a request or a
question, from the tree; the poteto-help skill's block runs it and prints the same lines; and
its tips are the ones `hooks/skill-tips.sh` gives for the same words."""

import json
import os
import re
import subprocess
import textwrap

import pytest

from jbriefs import pick
from testing.paths import REPO

SKILL = REPO / "skills" / "poteto-help" / "SKILL.md"
HOOK = REPO / "harness" / "jstack" / "claude-code" / "hooks" / "skill-tips.sh"

BRIEF = """\
# tidy-gauge: the gauge prints its slots in order
Task: "the gauge's slots come out in any order" (the user)
Done when:
- `jgauge test-slot` prints its slots in order, and a test pins it
Where: src/jgauge/
Pull request: open one when done
Review: review
Playbook: feature
Read: see /pr-review and /no-such-skill, and skills/grilling for the questions
"""
REQUEST = """\
# why-slow: why the pass takes a minute
Question: why does one jbus pass take a minute, and where does the time go
Playbook: investigation
"""
QUESTION = "I want someone to grill me on this plan before I start\n"


def jbriefs(*args, stdin=None):
    done = subprocess.run(
        ["uv", "run", "--quiet", "--no-sync", "--project", str(REPO), "jbriefs", "pick", *args],
        input=stdin,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.splitlines()


@pytest.fixture
def home(tmp_path):
    """A home folder with one brief, one scout's request and one question kept as a note."""
    made = tmp_path / "state" / "demo"
    for where, name, text in (
        ("tasks", "tidy-gauge.md", BRIEF),
        ("scouts", "why-slow.md", REQUEST),
        ("notes", "question.md", QUESTION),
    ):
        (made / where).mkdir(parents=True)
        (made / where / name).write_text(text)
    return made


def test_a_brief_is_a_crewmates_with_its_playbook_line(home):
    said = jbriefs(str(home / "tasks" / "tidy-gauge.md"))
    assert said[:2] == [
        "role crew: /crew tidy-gauge (skills/crew/SKILL.md)",
        "playbook feature: playbooks/feature.md (its Playbook: line)",
    ]


def test_a_request_is_a_scouts_with_its_playbook_line(home):
    said = jbriefs(str(home / "scouts" / "why-slow.md"))
    assert said[:2] == [
        "role scout: /scout why-slow (skills/scout/SKILL.md)",
        "playbook investigation: playbooks/investigation.md (its Playbook: line)",
    ]


def test_a_question_is_the_homes_and_its_tip_is_named(home):
    from_file = jbriefs(str(home / "notes" / "question.md"))
    from_stdin = jbriefs("-", stdin=QUESTION)
    assert from_file == from_stdin
    assert from_stdin == [
        "role home: /home (skills/home/SKILL.md)",
        "playbook none: (no row the home runs fits)",
        'tip grilling: /grilling (skills/grilling/SKILL.md), its tip "grill me"',
    ]


def test_each_name_the_brief_gives_is_printed_and_an_unknown_one_is_not_dropped(home):
    said = jbriefs(str(home / "tasks" / "tidy-gauge.md"))
    assert said[2:] == [
        "named pr-review: /pr-review (skills/pr-review/SKILL.md)",
        "unknown no-such-skill: (no skills/no-such-skill/SKILL.md)",
        "named grilling: /grilling (skills/grilling/SKILL.md)",
    ]


def test_names_under_the_result_are_not_the_briefs(tmp_path):
    brief = tmp_path / "tasks" / "done.md"
    brief.parent.mkdir()
    brief.write_text(BRIEF + "\n## Result\nPlaybook: feature; see /handoff and /not-the-briefs\n")
    said = jbriefs(str(brief))
    assert not [line for line in said if "handoff" in line or "not-the-briefs" in line]


def test_a_playbook_line_that_names_no_file_is_printed_as_unknown(tmp_path):
    brief = tmp_path / "tasks" / "odd.md"
    brief.parent.mkdir()
    brief.write_text(BRIEF.replace("Playbook: feature", "Playbook: fix"))
    assert jbriefs(str(brief))[1] == "unknown fix: (its Playbook: line names no file in playbooks/)"


def test_a_brief_with_no_playbook_line_takes_the_row_of_its_role_that_fits(tmp_path):
    (tmp_path / "tasks").mkdir()
    cases = {
        "Where: src/jgauge/": "feature",
        "Where: skills/grilling/SKILL.md, skills/grilling/references/": "authoring-a-skill",
        "Where: playbooks/feature.md, tests/test_playbooks.py": "authoring-a-playbook",
        "Where: src/x/\nCandidates: two\nJudge: the user\nPull request: ask first": "eval",
    }
    for where, expected in cases.items():
        brief = tmp_path / "tasks" / "a.md"
        brief.write_text(
            BRIEF.replace("Playbook: feature\n", "").replace("Where: src/jgauge/", where)
        )
        assert jbriefs(str(brief))[1].startswith(f"playbook {expected}: playbooks/{expected}.md")


def test_every_skill_and_playbook_printed_is_a_file(home):
    lines = [
        *jbriefs(str(home / "tasks" / "tidy-gauge.md")),
        *jbriefs(str(home / "scouts" / "why-slow.md")),
        *jbriefs("-", stdin="review the pr and fix this bug, then catch me up, see /handoff\n"),
    ]
    named = [line for line in lines if not line.startswith(("unknown ", "playbook none:"))]
    files = [re.search(r"\b(?:features|skills|playbooks)/[\w/.-]+\.md", line) for line in named]
    assert None not in files and len(named) >= 8
    assert [f[0] for f in files if not (REPO / f[0]).is_file()] == []


def skill_block():
    (found,) = re.findall(r"^```sh\n(.*?)^```$", SKILL.read_text(), re.M | re.S)
    return textwrap.dedent(found)


def run_block(user, cwd, typed):
    body = skill_block().replace("<what the user typed after the skill's name>", typed)
    env = {"HOME": str(user), "PATH": os.environ["PATH"], "GIT_CONFIG_GLOBAL": os.devnull}
    done = subprocess.run(["sh", "-c", body], cwd=cwd, env=env, capture_output=True, text=True)
    assert done.returncode == 0 and done.stderr == "", done.stderr
    return done.stdout.splitlines()


@pytest.fixture
def user(tmp_path, home):
    """A user's home directory with the skill linked as `install.sh` links it, and the home
    folder of the repo `demo` under its state."""
    made = tmp_path / "user"
    (made / ".claude" / "skills").mkdir(parents=True)
    (made / ".claude" / "skills" / "poteto-help").symlink_to(SKILL.parent)
    (made / ".local" / "state" / "home").mkdir(parents=True)
    (made / ".local" / "state" / "home" / "demo").symlink_to(home)
    return made


@pytest.fixture
def demo(tmp_path):
    made = tmp_path / "demo"
    made.mkdir()
    subprocess.run(
        ["git", "init", "-q", made], check=True, env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull}
    )
    return made


def test_the_skills_block_prints_the_same_lines_as_jbriefs_pick(user, home, demo):
    for typed, path in (
        (str(home / "tasks" / "tidy-gauge.md"), str(home / "tasks" / "tidy-gauge.md")),
        ("tidy-gauge", str(home / "tasks" / "tidy-gauge.md")),
        ("why-slow", str(home / "scouts" / "why-slow.md")),
        ("tasks/tidy-gauge.md", str(home / "tasks" / "tidy-gauge.md")),
    ):
        said = run_block(user, demo, typed)
        assert said[0] == f"root: {REPO}"
        assert said[1:-1] == jbriefs(path)
        assert said[-1] == "setup: README.md, Quickstart" or said[-1].startswith("setup: sh ")
    asked = run_block(user, demo, QUESTION.strip())
    assert asked[1:-1] == jbriefs("-", stdin=QUESTION)


def test_the_skills_block_says_so_when_it_is_not_linked(tmp_path, demo):
    (tmp_path / "bare").mkdir()
    assert run_block(tmp_path / "bare", demo, "anything") == [
        "no root: ~/.claude/skills/poteto-help is not a link into the repo this skill lives in"
    ]


def hook_tip(tmp_path, prompt):
    """The skill the installed `hooks/skill-tips.sh` tips for a prompt, in a fresh session, or
    None."""
    outside = tmp_path / "outside"
    outside.mkdir(exist_ok=True)
    event = {"session_id": f"s{abs(hash(prompt))}", "cwd": str(outside), "prompt": prompt}
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ["PATH"],
        "GIT_CEILING_DIRECTORIES": str(tmp_path),
    }
    done = subprocess.run(
        ["sh", str(HOOK)], input=json.dumps(event), capture_output=True, text=True, env=env
    )
    assert done.returncode == 0
    if not done.stdout:
        return None
    return re.search(r"tip: /([a-z0-9-]+) ", done.stdout).group(1)


@pytest.mark.parametrize(
    "prompt",
    [
        "grill me on this plan",
        "how does the jbus pass work",
        "why did we pick sqlite for the queue",
        "can you review the pr and then catch me up",
        "this reads like chatgpt, it sounds like ai",
        "please wrap up and hand off",
        "/grilling grill me",
        "nothing here asks for a skill at all",
    ],
)
def test_the_first_tip_is_the_one_the_tips_hook_gives(tmp_path, prompt):
    tips = pick.tipped(prompt, pick.skills())
    assert hook_tip(tmp_path, prompt) == (tips[0][0] if tips else None)
