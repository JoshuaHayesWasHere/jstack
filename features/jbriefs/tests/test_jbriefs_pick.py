"""`jbriefs pick` reads the tree and names the role, the playbook and the skills for a brief, a
request or a question. The block of the poteto-help skill runs it and prints the same lines."""

import os
import re
import subprocess
import textwrap

import pytest

from jbriefs import parse, pick
from testing.layouts import assembled
from testing.paths import REPO, playbooks

SKILL = REPO / "features" / "skill-library" / "skills" / "poteto-help" / "SKILL.md"
HANDING = REPO / "features" / "home" / "skills" / "home" / "handing-a-task-to-a-crewmate.md"

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
        "role crew: /crew tidy-gauge (features/crew/SKILL.md)",
        "playbook feature: features/crew/playbooks/feature.md (its Playbook: line)",
    ]


def test_a_request_is_a_scouts_with_its_playbook_line(home):
    said = jbriefs(str(home / "scouts" / "why-slow.md"))
    assert said[:2] == [
        "role scout: /scout why-slow (features/scout/SKILL.md)",
        "playbook investigation: features/scout/playbooks/investigation.md (its Playbook: line)",
    ]


def test_a_question_is_the_homes_and_its_tip_is_named(home):
    from_file = jbriefs(str(home / "notes" / "question.md"))
    from_stdin = jbriefs("-", stdin=QUESTION)
    assert from_file == from_stdin
    assert from_stdin == [
        "role home: /home (features/home/skills/home/SKILL.md)",
        "playbook none: (no row the home runs fits)",
        'tip grilling: /grilling (features/grilling/SKILL.md), its tip "grill me"',
    ]


def test_each_name_the_brief_gives_is_printed_and_an_unknown_one_is_not_dropped(home):
    said = jbriefs(str(home / "tasks" / "tidy-gauge.md"))
    assert said[2:] == [
        "named pr-review: /pr-review (features/pr-review/SKILL.md)",
        "unknown no-such-skill: (no skills/no-such-skill/SKILL.md)",
        "named grilling: /grilling (features/grilling/SKILL.md)",
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
        "Where: features/grilling/SKILL.md, features/grilling/references/": "authoring-a-skill",
        "Where: playbooks/feature.md, tests/test_playbooks.py": "authoring-a-playbook",
        "Where: src/x/\nCandidates: two\nJudge: the user\nPull request: ask first": "eval",
    }
    for where, expected in cases.items():
        brief = tmp_path / "tasks" / "a.md"
        brief.write_text(
            BRIEF.replace("Playbook: feature\n", "").replace("Where: src/jgauge/", where)
        )
        path = playbooks()[expected].relative_to(REPO).as_posix()
        assert jbriefs(str(brief))[1].startswith(f"playbook {expected}: {path}")


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
    (made / ".claude" / "skills" / "poteto-help").symlink_to(assembled() / "skills" / "poteto-help")
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
        assert said[0] == f"root: {os.path.realpath(assembled())}"
        assert said[1:-1] == jbriefs(path)
        assert said[-1] == "setup: README.md, Quickstart" or said[-1].startswith("setup: sh ")
    asked = run_block(user, demo, QUESTION.strip())
    assert asked[1:-1] == jbriefs("-", stdin=QUESTION)


def test_the_skills_block_says_so_when_it_is_not_linked(tmp_path, demo):
    (tmp_path / "bare").mkdir()
    assert run_block(tmp_path / "bare", demo, "anything") == [
        "no root: ~/.claude/skills/poteto-help is not a link into the repo this skill lives in"
    ]


@pytest.mark.parametrize(
    ("prompt", "first"),
    [
        ("grill me on this plan", "grilling"),
        ("how does the jbus pass work", "how"),
        ("why did we pick sqlite for the queue", "why"),
        ("this reads like chatgpt, it sounds like ai", "unslop"),
        ("can you review the pr and then catch me up", "ketchup"),
        ("please wrap up and hand off", "handoff"),
        ("/grilling grill me", None),
        ("nothing here asks for a skill at all", None),
    ],
)
def test_the_first_tip_is_the_skill_whose_tip_phrase_the_words_say(prompt, first):
    tips = pick.tipped(prompt, pick.skills())
    assert (tips[0][0] if tips else None) == first


RULE = {
    skill.name: skill
    for skill in [
        pick.Skill("blast-radius", ("blast radius", "what could this break")),
        pick.Skill("how", ("how does * work",)),
        pick.Skill("ketchup", ("catch me up", "catch me up on this chat")),
    ]
}


def first_tip(text, found=RULE):
    tips = pick.tipped(text, found)
    return tips[0][0] if tips else None


def test_a_tip_matches_by_whole_words_and_not_by_case():
    assert first_tip("BLAST-RADIUS,\nplease") == "blast-radius"
    assert first_tip("Blast  Radius?") == "blast-radius"
    for near in [
        "blast radiuses",
        "sandblast radius",
        "blast the radius",
        "what could this breaker",
    ]:
        assert first_tip(near) is None


def test_a_star_in_a_tip_phrase_stands_for_one_to_four_words():
    assert first_tip("how does the start hook work") == "how"
    assert first_tip("how does work") is None
    assert first_tip("how does one two three four five work") is None


def test_the_longest_phrase_that_matches_comes_first():
    assert first_tip("catch me up on this chat, what could this break") == "ketchup"
    assert first_tip("catch me up, and what could this break") == "blast-radius"


def test_a_skill_the_text_names_gets_no_tip():
    assert first_tip("run /blast-radius: what could this break") is None
    assert first_tip("is $blast-radius the one for what could this break") is None
    assert first_tip("after /blast-radius, catch me up") == "ketchup"
    assert first_tip("then /blast-radius-2 says what could this break") == "blast-radius"


TIPPED = sorted((s.name, s.phrases) for s in pick.skills().values() if s.phrases)


def test_the_repo_has_skills_with_a_tip_line():
    assert len(TIPPED) > 10


@pytest.mark.parametrize(("name", "phrases"), TIPPED, ids=[name for name, _ in TIPPED])
def test_each_tip_phrase_of_the_repos_skills_tips_that_skill(name, phrases):
    found = pick.skills()
    for phrase in phrases:
        text = f"So, {phrase.replace('*', 'the thing').upper()}?"
        assert name in [tipped for tipped, _ in pick.tipped(text, found)], phrase


def test_the_briefs_deeper_playbooks_are_the_crewmates_ones_the_deeper_step_runs_on():
    """`queue add` asks a brief of each of `parse.DEEPER` for its `Read:` and `Instruments:`
    lines, which the home's deeper step writes, so a crewmate's playbook added to the step's
    `case` list and not to `DEEPER` is never asked for them."""
    case = re.search(r"^\s*(investigation \|[^)\n]*)\)$", HANDING.read_text(), re.M)
    crewmates = {row.name for row in pick.rows() if row.runner == pick.CREW.runner}
    assert {name.strip() for name in case.group(1).split("|")} & crewmates == set(parse.DEEPER)
