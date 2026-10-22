"""The note lint: `features/jpack/src/jpack/lint-notes.sh` is run here on a made-up expert's
folder in a temporary directory, by itself and by the block the `expert-study` playbook gives.
"""

import re
import subprocess
import sys

import pytest

from testing.layouts import assembled
from testing.paths import REPO

LINT = REPO / "features" / "jpack" / "src" / "jpack" / "lint-notes.sh"
PLAYBOOK = REPO / "features" / "expert" / "playbooks" / "expert-study.md"

CLEAN = """\
# How long does the kettle take to boil?

## Answer
Four minutes from cold, for one litre.

## Sources
- `docs/boiling.md:12` at teapot `3f9c2ab`: "one litre boils in four minutes"
- `teapot --time 1l`, run 2026-03-04 10:15: prints `240s`

## Confidence
Direct: the document says it and the command agrees.

## Not checked
- a kettle that is not descaled
"""
NO_SOURCE = """\
# What colour is the kettle?

## Answer
Blue.

## Sources

## Confidence
Speculative: nothing was read.

## Not checked
- none
"""
NO_SOURCES_PART = """\
# Which whistle does the kettle have?

- It whistles in C. Source: `docs/whistle.md:3` at teapot `3f9c2ab`.
"""
NO_REVISION = """\
# Where is the lid kept?

## Answer
On the shelf above the stove.

## Sources
- `docs/boiling.md:12` at teapot `3f9c2ab`: the lid is named
- `docs/lid.md:4`: "the lid is kept on the shelf
  above the stove"

## Confidence
Direct: the document says it.

## Not checked
- none
"""
UNREVISED = (
    "a source with no revision, in it or above the four parts "
    "(a commit id in backticks or after at, or a date as YYYY-MM-DD): "
)
LID = '- `docs/lid.md:4`: "the lid is kept on the shelf'
INDEX = """\
# Notes index
- `boil-time.md`: how long does the kettle take to boil, at teapot `3f9c2ab`
"""


def folder(tmp_path, notes, index=INDEX):
    expert = tmp_path / "_sage"
    (expert / "notes").mkdir(parents=True)
    for name, text in notes.items():
        (expert / "notes" / name).write_text(text)
    if index is not None:
        (expert / "notes" / "INDEX.md").write_text(index)
    return expert


def lint(expert):
    done = subprocess.run(["sh", str(LINT), str(expert)], capture_output=True, text=True)
    return done.returncode, done.stdout.splitlines()


def listed(*names):
    lines = [f"- `{name}`: a question, at teapot `3f9c2ab`\n" for name in names]
    return "# Notes index\n" + "".join(lines)


def test_a_folder_in_order_passes_and_prints_nothing(tmp_path):
    assert lint(folder(tmp_path, {"boil-time.md": CLEAN})) == (0, [])


def test_a_folder_with_no_note_yet_passes(tmp_path):
    assert lint(folder(tmp_path, {})) == (0, [])


@pytest.mark.parametrize("note", [NO_SOURCE, NO_SOURCES_PART])
def test_a_note_with_no_source_fails(tmp_path, note):
    expert = folder(tmp_path, {"colour.md": note}, listed("colour.md"))
    assert lint(expert) == (
        1,
        ["colour.md: no source, no list item (- or *) is under a Sources heading"],
    )


def test_a_source_with_no_revision_fails_and_is_named(tmp_path):
    expert = folder(tmp_path, {"lid.md": NO_REVISION}, listed("lid.md"))
    assert lint(expert) == (
        1,
        [f"lid.md: {UNREVISED}{LID}"],
    )


def test_a_note_not_in_the_index_fails(tmp_path):
    expert = folder(tmp_path, {"boil-time.md": CLEAN, "spout.md": CLEAN})
    assert lint(expert) == (1, ["spout.md: no line in notes/INDEX.md"])


def test_a_folder_with_no_index_fails_each_note(tmp_path):
    expert = folder(tmp_path, {"boil-time.md": CLEAN}, index=None)
    assert lint(expert) == (1, ["boil-time.md: no line in notes/INDEX.md"])


def test_every_note_that_fails_is_named_in_one_run(tmp_path):
    notes = {"boil-time.md": CLEAN, "colour.md": NO_SOURCE, "lid.md": NO_REVISION}
    code, said = lint(folder(tmp_path, notes, listed("boil-time.md", "lid.md")))
    assert code == 1
    assert said == [
        "colour.md: no line in notes/INDEX.md",
        "colour.md: no source, no list item (- or *) is under a Sources heading",
        f"lid.md: {UNREVISED}{LID}",
    ]


@pytest.mark.parametrize(
    ("source", "revised"),
    [
        ("- `docs/a.md:1` at teapot `3f9c2ab`", True),
        ("- `docs/a.md:1` at 3f9c2ab4d5e6f708192a3b4c5d6e7f8091a2b3c4", True),
        ("- https://example.com/kettles, read 2026-03-04", True),
        ("* `docs/a.md:1`, which goes on\n  to the next line at `3f9c2ab`", True),
        ("- https://example.com/kettles", False),
        ("- `docs/a.md:1` at teapot `main`", False),
        ("- `docs/a.md:1` at the defaced one", False),
        ("- `docs/a.md:1` at `3f9c2a`", False),
        ("- https://example.com/blog/2025-01-15-kettles", False),
        ("- `docs/2026-03-04-meeting.md:12`", False),
        ("- https://example.com/issues/1234567", False),
        ('- `docs/a.md:4`: "shipped on 2019-06-01"', False),
        ('- `docs/a.md:4`: "shipped on 2019-06-01", read (2026-03-04).', True),
        ("- `teapot --time 1l`, run Oct 12 2026 10:15", False),
        ("- docs/limits.md:3: the body limit is 1048576 bytes", False),
        ("- `docs/a.md:1`, read 20261012", False),
        ("- `docs/a.md:1` at teapot 3f9c2ab", False),
        ("- `docs/a.md:1` at 1048576", True),
        ("- `docs/a.md:1` (`3f9c2ab`).", True),
        ("- `git diff --stat 1b6d44ff 997ffc7 -- docs`, run here: 4 files", True),
        ("- `docs/a.md:1` and `docs/b.md:2` hold 1048576 between them", False),
    ],
)
def test_a_revision_is_a_commit_id_or_a_date(tmp_path, source, revised):
    note = f"# A question\n\n## Answer\nYes.\n\n## Sources\n{source}\n\n## Confidence\nDirect.\n"
    code, said = lint(folder(tmp_path, {"a.md": note}, listed("a.md")))
    assert (code, len(said)) == ((0, 0) if revised else (1, 1))


STATED_ONCE = """\
# Where does the spout point?

{above}

## Answer
Away from the handle. {answer}

## Sources
- `docs/spout.md:7` the spout is opposite the handle
- `teapot --spout`, 10:15: prints `east`

## Confidence
Direct: the document says it.
"""


@pytest.mark.parametrize(
    "above",
    [
        "Syllabus A4. Read at `507361bc73` (teapot), in the evening.",
        "Read 2026-03-04 10:15 to 10:18. Paths are from the teapot checkout.",
    ],
)
def test_a_revision_above_the_four_parts_is_the_revision_of_every_source(tmp_path, above):
    note = STATED_ONCE.format(above=above, answer="")
    assert lint(folder(tmp_path, {"spout.md": note}, listed("spout.md"))) == (0, [])


def test_a_revision_in_the_title_or_inside_a_part_is_not_the_notes_own(tmp_path):
    note = STATED_ONCE.format(above="Syllabus A4.", answer="It was turned on 2026-03-04.")
    note = note.replace("# Where", "# On 2026-03-04, where")
    code, said = lint(folder(tmp_path, {"spout.md": note}, listed("spout.md")))
    assert (code, said) == (
        1,
        [
            f"spout.md: {UNREVISED}- `docs/spout.md:7` the spout is opposite the handle",
            f"spout.md: {UNREVISED}- `teapot --spout`, 10:15: prints `east`",
        ],
    )


@pytest.mark.parametrize(
    "line",
    ["`docs/a.md:2` at teapot `3f9c2ab`", "1. `docs/a.md:2` at teapot `3f9c2ab`"],
)
def test_a_line_under_sources_that_is_no_list_item_is_named(tmp_path, line):
    note = f"## Sources\n- `docs/a.md:1` at teapot `3f9c2ab`\n\n{line}\n\n## Confidence\nDirect.\n"
    code, said = lint(folder(tmp_path, {"a.md": note}, listed("a.md")))
    assert (code, said) == (
        1,
        [f"a.md: a line under Sources that is no list item (- or *): {line}"],
    )


def test_a_heading_inside_a_fence_does_not_end_the_sources(tmp_path):
    note = "## Sources\n- `run.sh`, as it is:\n\n```sh\n# prints the time\n```\n\n- `docs/a.md:1`\n"
    code, said = lint(folder(tmp_path, {"a.md": note}, listed("a.md")))
    assert (code, said) == (
        1,
        [
            f"a.md: {UNREVISED}- `run.sh`, as it is:",
            f"a.md: {UNREVISED}- `docs/a.md:1`",
        ],
    )


def test_a_folder_that_is_not_an_experts_is_refused(tmp_path):
    done = subprocess.run(["sh", str(LINT), str(tmp_path)], capture_output=True, text=True)
    assert (done.returncode, done.stdout) == (2, "")
    assert done.stderr == f"lint-notes.sh: {tmp_path} has no notes folder\n"


def test_no_folder_named_is_refused():
    done = subprocess.run(["sh", str(LINT)], capture_output=True, text=True)
    assert (done.returncode, done.stderr) == (
        2,
        "usage: lint-notes.sh <the expert's folder, or a context pack>\n",
    )


def step_six():
    """The shell block of the playbook's step that checks the pass."""
    step = PLAYBOOK.read_text().split("\n6. Check the pass.")[1].split("\n7. ")[0]
    return re.search(r"```sh\n(.*?)```", step, re.S).group(1)


@pytest.mark.parametrize(
    ("notes", "said"),
    [
        ({"boil-time.md": CLEAN}, ""),
        ({"spout.md": CLEAN}, "spout.md: no line in notes/INDEX.md\n"),
        (
            {"boil-time.md": CLEAN, "lid.md": NO_REVISION},
            f"lid.md: no line in notes/INDEX.md\nlid.md: {UNREVISED}{LID}\n",
        ),
    ],
)
def test_the_study_playbook_runs_the_lint_on_the_whole_folder(tmp_path, notes, said):
    """The pass wrote the first note only: the other is one an earlier pass left."""
    expert = folder(tmp_path, notes)
    block = step_six().replace("<the notes of this pass>", next(iter(notes)))
    bin = tmp_path / "bin"
    bin.mkdir()
    (bin / "jpack").write_text(
        f'#!/bin/sh\nPYTHONPATH={REPO / "src"} exec {sys.executable} -m jpack "$@"\n'
    )
    (bin / "jpack").chmod(0o755)
    copy = assembled()
    done = subprocess.run(
        ["sh", "-c", block],
        env={"PATH": f"{bin}:/usr/bin:/bin", "E": str(expert), "T": str(copy / "templates")},
        capture_output=True,
        text=True,
    )
    assert (done.stdout, done.stderr) == (said, "")
