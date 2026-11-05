"""The interrogate skill: it prints the repo's root. From that root it reads two questions out
of the pr-review skill."""

import pytest

from skill_blocks import (
    block,
    home,
    linked,
    prints_the_root_and_names_only_files_under_it,
    repo,
    run,
    says_it_is_no_link_into_the_repo,
)

__all__ = ["home", "repo"]


def stand_in(tmp_path, home, text):
    """A repo whose pr-review skill has `text` in "The review". The user's home links the
    interrogate skill to the repo's interrogate folder."""
    skills = tmp_path / "other" / "skills"
    (skills / "interrogate").mkdir(parents=True)
    (skills / "pr-review").mkdir()
    (skills / "pr-review" / "the-review.md").write_text(text)
    linked(home, "interrogate", to=skills / "interrogate")
    return skills / "pr-review" / "the-review.md"


def test_a_linked_interrogate_prints_the_root_and_every_file_it_names_is_under_it(repo, home):
    prints_the_root_and_names_only_files_under_it("interrogate", repo, home)


def test_an_interrogate_that_is_no_link_into_the_repo_says_so(repo, home):
    says_it_is_no_link_into_the_repo("interrogate", repo, home)


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
