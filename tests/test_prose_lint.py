"""One sentence per line, for new prose: `scripts/prose_lint.py <base>` is run here as
`make check-fast` runs it, with `python3 -I -S`, in a repo made from `tests/fixtures/prose/`,
with a pull request's commit on top of it. A prose line the commit adds or changes fails when
it holds more than one sentence, and a line it leaves alone is never judged. `sentences`, the
one function that says what a sentence is, is tested on its own."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "scripts" / "prose_lint.py"
OLD = REPO / "tests" / "fixtures" / "prose" / "old.md"
SPEC = importlib.util.spec_from_file_location("prose_lint", SCRIPT)
lint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lint)

LONG = "This old paragraph line holds three sentences. It was written before the rule."


def git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path):
    """A repo whose `main` holds the old page at `docs/old.md`, on a branch `pr` from it."""
    (tmp_path / "docs").mkdir()
    shutil.copy(OLD, tmp_path / "docs" / "old.md")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "old")
    git(tmp_path, "checkout", "-q", "-b", "pr")
    return tmp_path


def change(repo, path, edit):
    page = repo / path
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(edit(page.read_text() if page.exists() else ""))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "pr")


def check(repo):
    ran = subprocess.run(
        [sys.executable, "-I", "-S", str(SCRIPT), "main"], cwd=repo, capture_output=True, text=True
    )
    return ran.returncode, ran.stdout.splitlines()


def numbered(repo, path, text):
    return (repo / path).read_text().splitlines().index(text) + 1


def test_a_new_line_of_two_sentences_fails_and_names_its_place_and_says_to_break_it(repo):
    line = "A new paragraph. It holds two sentences."
    change(repo, "docs/old.md", lambda text: text + "\n" + line + "\n")
    code, said = check(repo)
    at = numbered(repo, "docs/old.md", line)
    assert code == 1
    assert said[0] == f"docs/old.md:{at}: more than one sentence, break it at sentence ends: {line}"
    assert len(said) == 2


def test_the_same_text_one_sentence_a_line_passes(repo):
    change(repo, "docs/old.md", lambda text: text + "\nA new paragraph.\nIt holds two sentences.\n")
    assert check(repo) == (0, [])


def test_a_change_to_the_neighbour_of_an_old_long_line_leaves_the_old_line_alone(repo):
    change(
        repo,
        "docs/old.md",
        lambda text: text.replace("its neighbour, one sentence", "its neighbour, still one"),
    )
    assert check(repo) == (0, [])


def test_an_edit_inside_an_old_long_line_fails_for_that_line_alone(repo):
    change(repo, "docs/old.md", lambda text: text.replace("Nobody rewraps it.", "Nobody does."))
    code, said = check(repo)
    at = numbered(repo, "docs/old.md", LONG + " Nobody does.")
    assert code == 1
    assert [one.split(": ")[0] for one in said[:-1]] == [f"docs/old.md:{at}"]


def test_each_fault_is_its_own_line(repo):
    change(repo, "skills/new/SKILL.md", lambda _: "One. Two.\n\nFine.\n\n- Three. Four.\n")
    code, said = check(repo)
    assert code == 1
    assert [one.split(": ")[0] for one in said[:-1]] == [
        "skills/new/SKILL.md:1",
        "skills/new/SKILL.md:5",
    ]


NOT_PROSE = """\
---
description: Front matter. Two sentences.
---

# A heading. Two sentences.

Task: a field. Its value holds two.
Done when:
- an item under the field. It holds two.
  and its next line. Two as well.

| A cell. Two. | Another. Two. |
| --- | --- |

```sh
echo "In a fence. Two."
```

<!-- A comment. Two sentences.
Still the comment. Two. -->
"""


def test_fences_tables_front_matter_fields_headings_and_comments_are_not_judged(repo):
    change(repo, "playbooks/new.md", lambda _: NOT_PROSE)
    assert check(repo) == (0, [])


def test_only_markdown_of_the_four_folders_is_judged(repo):
    change(repo, "src/notes.md", lambda _: "One. Two.\n")
    change(repo, "templates/new.txt", lambda _: "One. Two.\n")
    change(repo, "README.md", lambda _: "One. Two.\n")
    assert check(repo) == (0, [])
    change(repo, "templates/new.md", lambda _: "One. Two.\n")
    assert check(repo)[0] == 1


def test_a_removed_line_is_never_judged(repo):
    change(repo, "docs/old.md", lambda text: text.replace(LONG + " Nobody rewraps it.\n", ""))
    assert check(repo) == (0, [])


def test_a_base_that_is_not_a_commit_fails_and_says_git_failed(repo):
    ran = subprocess.run(
        [sys.executable, "-I", "-S", str(SCRIPT), "nowhere"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert ran.returncode != 0 and "git diff failed" in ran.stderr


@pytest.mark.parametrize(
    "line, count",
    [
        ("One sentence.", 1),
        ("One. Two.", 2),
        ("Is it? Yes! And then.", 3),
        ("Use a lock, e.g. The heavy one.", 1),
        ("It is so, i.e. Nothing more.", 1),
        ("Pens, paper, etc. All of it.", 1),
        ("A run of 1.5 seconds. Then 2.25 more.", 2),
        ("Read docs/jbus.md. Then skills/crew/SKILL.md.", 2),
        ("Read docs/jbus.md and skills/crew/SKILL.md for it.", 1),
        ("Run `make check. Then` once.", 1),
        ("Run `a`. Then `b`.", 2),
        ("See [the page](docs/a.b. C.md) here.", 1),
        ('He said "stop." Then left.', 2),
        ("It ends (as it should.) Then more.", 2),
        ("It ends. then a lower case word.", 1),
        ("A list ends here: one, two.", 1),
        ("", 0),
    ],
)
def test_sentences_ends_a_sentence_only_where_one_ends(line, count):
    assert len(lint.sentences(line)) == count


def test_sentences_keeps_the_text_as_written():
    assert lint.sentences("Run `a. B`. Then go.") == ["Run `a. B`.", "Then go."]
