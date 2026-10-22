"""The grilling skill: the home's pointer to it resolves, and its round format is a round."""

import re

from test_home_thread import as_read
from test_writing import skill_problems
from testing.layouts import assembled
from testing.paths import REPO

SKILL = REPO / "features" / "grilling" / "SKILL.md"
HOME = REPO / "features" / "home" / "skills" / "home" / "SKILL.md"
THIRD_PARTY = REPO / "THIRD_PARTY.md"
QUESTION = re.compile(r"^❓ \*\*Q(\d+)\*\* - \*\*.+?\*\*: .+$", re.M)
ANSWER = re.compile(r"^➡️ .+$", re.M)


def planning():
    return as_read(HOME).split("\n## Planning\n", 1)[1].split("\n## ", 1)[0]


def round_problems(text):
    """What stops `text` from being one round: numbered questions, each with its answer."""
    asked = [part for part in text.split("\n---\n") if part.strip()]
    found = []
    numbers = []
    for part in asked:
        questions = QUESTION.findall(part)
        if len(questions) != 1:
            found.append(f"a part has {len(questions)} questions")
            continue
        numbers.append(int(questions[0]))
        answers = [m.start() for m in ANSWER.finditer(part)]
        if len(answers) != 1:
            found.append(f"Q{questions[0]} has {len(answers)} recommended answers")
        elif answers[0] < QUESTION.search(part).start():
            found.append(f"Q{questions[0]} has its answer before the question")
    if numbers != list(range(1, len(numbers) + 1)):
        found.append(f"the questions are numbered {numbers}")
    return found


def the_format():
    (shown,) = re.findall(r"^```\n(.*?)^```$", SKILL.read_text(), re.M | re.S)
    return shown


def test_the_skill_loads_only_when_typed():
    assert skill_problems(SKILL) == []


def test_the_home_plans_by_a_skill_file_that_is_there():
    (named,) = re.findall(r"`\$T/\.\./(skills/[^`]+\.md)`", planning())
    templates = assembled() / "templates"
    assert (templates / ".." / named).resolve() == SKILL
    assert skill_problems(templates / ".." / named) == []


def test_the_round_the_skill_shows_is_a_round():
    assert round_problems(the_format()) == []


def test_a_round_with_a_question_and_no_answer_is_a_problem():
    without = ANSWER.sub("", the_format(), count=1)
    assert round_problems(without) == ["Q1 has 0 recommended answers"]


def test_a_round_numbered_out_of_order_is_a_problem():
    assert round_problems(the_format().replace("**Q2**", "**Q3**")) == [
        "the questions are numbered [1, 3]"
    ]


def test_lint_third_party_names_the_skill():
    assert "`features/grilling/SKILL.md`" in THIRD_PARTY.read_text()
