"""The five skills that name files outside their own directory: each prints the repo's root,
and interrogate reads two questions out of the pr-review skill from it."""

import re

import pytest

from test_understanding_skills import COPY, block, home, repo, run

__all__ = ["home", "repo"]

ROOTED = ["architect", "interrogate", "no-comments", "tdd", "typescript-best-practices"]
FROM_ROOT = re.compile(r"`((?:playbooks|principles|skills)/[^`<>*\s]+\.md)`")


def linked(home, name, to=None):
    """A skill where a user has it: a link from `~/.claude/skills` into the harness copy."""
    link = home / ".claude" / "skills" / name
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(to or COPY / "skills" / name)


def stand_in(tmp_path, home, text):
    """A repo whose pr-review skill has `text` in "The review", with interrogate linked to it."""
    skills = tmp_path / "other" / "skills"
    (skills / "interrogate").mkdir(parents=True)
    (skills / "pr-review").mkdir()
    (skills / "pr-review" / "the-review.md").write_text(text)
    linked(home, "interrogate", to=skills / "interrogate")
    return skills / "pr-review" / "the-review.md"


@pytest.mark.parametrize("name", ROOTED)
def test_a_linked_skill_prints_the_root_and_every_file_it_names_is_under_it(name, repo, home):
    linked(home, name)
    (root,) = run(block(name, "no root:"), repo, home)
    assert root == str(COPY)
    named = {
        path
        for file in (COPY / "skills" / name).rglob("*.md")
        for path in FROM_ROOT.findall(file.read_text())
    }
    assert named != set()
    assert sorted(path for path in named if not (COPY / path).is_file()) == []


@pytest.mark.parametrize("name", ROOTED)
def test_a_skill_that_is_no_link_into_the_repo_says_so(name, repo, home):
    said = f"no root: ~/.claude/skills/{name} is not a link into the repo this skill lives in"
    assert run(block(name, "no root:"), repo, home) == [said]
    (home / ".claude" / "skills" / name).mkdir(parents=True)
    assert run(block(name, "no root:"), repo, home) == [said]


def test_interrogate_prints_the_two_questions_the_pr_review_skill_holds(repo, home):
    linked(home, "interrogate")
    said = run(block("interrogate", "no questions"), repo, home)
    fifth = said.index(next(line for line in said if line.startswith("5. ")))
    assert said[0].startswith("4. Is it correct?")
    assert said[fifth].startswith("5. Could it be done more simply or cheaply?")
    assert [line[:5] for line in said[1:fifth]] == ["   - "] * 6
    assert [line[:5] for line in said[fifth + 1 :]] == ["   - "] * 5


def test_interrogate_says_so_when_there_are_no_questions_to_print(repo, home, tmp_path):
    body = block("interrogate", "no questions")
    rest = (
        "has no questions 4 and 5 in a SCOPE text, "
        "so the reviewers get the rubric and the lens alone"
    )
    assert run(body, repo, home) == [f"no questions: no root/skills/pr-review/the-review.md {rest}"]
    skill = stand_in(tmp_path, home, "4. A step of a list that is no question.\n   - an item\n")
    assert run(body, repo, home) == [f"no questions: {skill} {rest}"]


@pytest.mark.parametrize("after", ["   When the remedy is elsewhere, say so.\n", ""])
def test_interrogate_reads_only_the_fourth_and_fifth_of_the_scope_text(repo, home, tmp_path, after):
    stand_in(
        tmp_path,
        home,
        "4. Before the text.\nSCOPE=$(cat <<'SCOPE'\n3. Before.\n4. Is it so?\n   - one\n"
        f"5. Simpler?\n{after}6. After.\nSCOPE\n)\n4. Later.\n",
    )
    assert run(block("interrogate", "no questions"), repo, home) == [
        "4. Is it so?",
        "   - one",
        "5. Simpler?",
    ]
