"""`jbus brief new|set|append` (`jbus.brief`) is the one writer of a brief: each write takes the
brief's lock and replaces the file through a temp file, so writers that run at once all keep their
lines."""

import os
import resource
import subprocess
import sys
import time

import pytest

from jbus import brief as briefs

BRIEF = """# alpha: a task
Green main: abc
Task: do it
Done when:
- one
- two
"""

STARTED = """# alpha: a task
Task: do it
Thread: mcp:1

## Result
Status: done
Left: some

## Review
Verdict: clean
"""

CHILD = """
import os, sys, time
from jbus import brief, cli
fast = brief._write
brief._write = lambda path, text: (time.sleep(0.05), fast(path, text))
os.close(os.open(sys.argv[1], os.O_RDONLY))
sys.exit(cli.main(sys.argv[2:]))
"""


def jbus(*argv, stdin=""):
    done = subprocess.run(
        [sys.executable, "-m", "jbus", *argv], input=stdin, capture_output=True, text=True
    )
    return done.returncode, done.stdout


@pytest.fixture
def brief(tmp_path):
    path = tmp_path / "tasks" / "alpha.md"
    path.parent.mkdir()
    return path


def started(brief):
    brief.write_text(STARTED)
    return brief


def at_once(brief, writes):
    """Start one process per write, its stdin a file it can read at once, and let them all go at
    the same moment.

    A child (`CHILD`) blocks opening the go pipe for reading, and the one open of it for writing
    frees all of them together. That open is read-write, which Linux never blocks, so a child that
    died before it opened the pipe does not hang the test. A child's disk is slow: each write of the
    brief starts 50 ms after its read, so without the lock every child reads the brief before any
    writes it."""
    go = brief.parent.parent / "go"
    os.mkfifo(go)
    children = []
    for at, (argv, rest, stdin) in enumerate(writes):
        given = brief.parent.parent / f"stdin-{at}"
        given.write_text(stdin)
        with given.open() as handle:
            children.append(
                subprocess.Popen(
                    [sys.executable, "-c", CHILD, str(go), "brief", *argv, str(brief), *rest],
                    stdin=handle,
                    stdout=subprocess.PIPE,
                    text=True,
                )
            )
    time.sleep(1)
    os.close(os.open(go, os.O_RDWR))
    outs = [child.communicate(timeout=60)[0] for child in children]
    assert [child.returncode for child in children] == [0] * len(children), outs


def test_new_writes_the_whole_brief_and_prints_what_it_wrote(brief):
    assert jbus("brief", "new", str(brief), stdin=BRIEF) == (0, "wrote: tasks/alpha.md, 6 lines\n")
    assert brief.read_text() == BRIEF


def test_new_replaces_a_brief_no_thread_took_up_and_refuses_one_a_thread_did(brief):
    brief.write_text("# alpha: an older draft\n")
    assert jbus("brief", "new", str(brief), stdin=BRIEF)[0] == 0
    assert brief.read_text() == BRIEF

    started(brief)
    code, said = jbus("brief", "new", str(brief), stdin=BRIEF)
    assert (code, said.split(",")[0]) == (1, f"refused: a thread has taken up {brief}")
    assert brief.read_text() == STARTED


def test_set_replaces_the_head_line_of_its_label(brief):
    brief.write_text(BRIEF)
    assert jbus("brief", "set", str(brief), "Green main:", "def") == (
        0,
        "set: Green main: def, in the head of tasks/alpha.md\n",
    )
    assert brief.read_text() == BRIEF.replace("Green main: abc", "Green main: def")


def test_set_adds_a_new_label_above_the_first_section(brief):
    started(brief)
    assert jbus("brief", "set", str(brief), "Review:", "review")[0] == 0
    assert brief.read_text() == STARTED.replace(
        "Thread: mcp:1\n", "Thread: mcp:1\nReview: review\n"
    )


def test_set_result_changes_the_line_in_the_last_result_and_not_in_a_review_after_it(brief):
    started(brief)
    assert jbus("brief", "set", str(brief), "--result", "Left:", "none") == (
        0,
        "set: Left: none, in ## Result of tasks/alpha.md\n",
    )
    assert jbus("brief", "set", str(brief), "--result", "Fixed:", "abc123")[0] == 0
    assert brief.read_text() == STARTED.replace("Left: some\n", "Left: none\nFixed: abc123\n")


def test_set_says_unchanged_where_the_line_is_already_there(brief):
    started(brief)
    assert jbus("brief", "set", str(brief), "Thread:", "mcp:1") == (
        0,
        "unchanged: Thread: mcp:1, in the head of tasks/alpha.md\n",
    )


def test_set_refuses_a_label_that_heads_a_list(brief):
    brief.write_text(BRIEF)
    assert jbus("brief", "set", str(brief), "Done when:", "x") == (
        1,
        "refused: Done when: heads a list, and set writes one line\n",
    )
    assert brief.read_text() == BRIEF


def test_append_adds_lines_to_the_end_of_the_last_result_before_a_review(brief):
    started(brief)
    assert jbus("brief", "append", str(brief), stdin="Checked: a\nChecked: b\n") == (
        0,
        "appended: 2 lines, to ## Result of tasks/alpha.md\n",
    )
    assert brief.read_text() == STARTED.replace(
        "Left: some\n", "Left: some\nChecked: a\nChecked: b\n"
    )


def test_append_puts_a_section_at_the_end_of_the_brief(brief):
    started(brief)
    section = "## Result, follow-up (2026-11-09, review)\nStatus: done\n"
    assert jbus("brief", "append", str(brief), stdin=section) == (
        0,
        "appended: ## Result, follow-up (2026-11-09, review), at the end of tasks/alpha.md\n",
    )
    assert brief.read_text() == STARTED + "\n" + section
    assert jbus("brief", "append", str(brief), stdin="Left: none\n")[0] == 0
    assert brief.read_text().endswith(section + "Left: none\n")


def test_append_to_a_brief_with_no_result_goes_at_its_end(brief):
    brief.write_text(BRIEF)
    assert jbus("brief", "append", str(brief), stdin="Note: x\n") == (
        0,
        "appended: 1 line, at the end of tasks/alpha.md\n",
    )
    assert brief.read_text() == BRIEF + "Note: x\n"


def test_new_trims_blank_lines_at_the_end_and_says_unchanged_for_the_same_brief(brief):
    assert jbus("brief", "new", str(brief), stdin=BRIEF + "\n\n")[0] == 0
    assert brief.read_text() == BRIEF
    assert jbus("brief", "new", str(brief), stdin=BRIEF) == (
        0,
        "unchanged: tasks/alpha.md holds these 6 lines\n",
    )


@pytest.mark.parametrize(
    ("argv", "stdin"),
    [(("set", "--result", "Left:", "none"), ""), (("append",), "Checked: a\n")],
    ids=["set", "append"],
)
def test_a_write_keeps_a_line_that_holds_a_carriage_return_or_a_line_separator(brief, argv, stdin):
    """Readers split a brief at newlines alone, so a write leaves every other line as it was."""
    odd = "Proof: bar\r50% done \x0c\u2028 and on"
    brief.write_text(STARTED.replace("Status: done\n", f"Status: done\n{odd}\n"))
    form, rest = argv[0], argv[1:]
    assert jbus("brief", form, str(brief), *rest, stdin=stdin)[0] == 0
    assert odd in brief.read_text(newline="").split("\n")


def test_append_drops_blank_lines_around_its_lines(brief):
    started(brief)
    assert jbus("brief", "append", str(brief), stdin="\n\nChecked: a\n\n")[0] == 0
    assert brief.read_text() == STARTED.replace("Left: some\n", "Left: some\nChecked: a\n")


@pytest.mark.parametrize(
    ("argv", "stdin", "said"),
    [
        (("new",), "\n", "refused: stdin holds no brief"),
        (("append",), "\n\n", "refused: stdin holds no lines to append"),
        (
            ("append",),
            "Checked: a\n## Review\n",
            "refused: stdin starts with lines and then has a section: append the lines and the "
            "section apart",
        ),
        (
            ("set", "Thread", "x"),
            "",
            'refused: "Thread" is no label, which is a capital, then letters, digits or spaces, '
            "then a colon, as in Thread: or Scoped reviewer:",
        ),
        (("set", "Thread:", " "), "", "refused: the value of Thread: is one line, and not blank"),
        (
            ("set", "--result", "Left:", "x"),
            "",
            "refused: the brief has no Result to set a line in",
        ),
    ],
    ids=["new-empty", "append-empty", "append-mixed", "set-label", "set-blank", "set-no-result"],
)
def test_a_write_the_verb_cannot_place_is_refused_and_the_brief_kept(brief, argv, stdin, said):
    brief.write_text(BRIEF)
    form, rest = argv[0], argv[1:]
    assert jbus("brief", form, str(brief), *rest, stdin=stdin) == (1, said + "\n")
    assert brief.read_text() == BRIEF


def test_a_path_that_is_no_brief_is_refused(tmp_path):
    other = tmp_path / "notes.md"
    other.write_text(BRIEF)
    assert jbus("brief", "set", str(other), "Thread:", "x") == (
        1,
        f"refused: {other} is no brief, which is <home>/tasks/<slug>.md or "
        "<home>/scouts/<slug>.md\n",
    )


def test_a_write_that_fails_part_way_leaves_the_brief_whole_and_no_temp_file(brief):
    """A full disk, here a limit on a file's size, stops the write after part of the text."""
    brief.write_text(BRIEF)
    soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    resource.setrlimit(resource.RLIMIT_FSIZE, (len(BRIEF) * 2, hard))
    try:
        with pytest.raises(OSError):
            briefs.new(brief, BRIEF + "Note: a long line\n" * 100)
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, (soft, hard))
    assert brief.read_text() == BRIEF
    assert sorted(one.name for one in brief.parent.iterdir()) == ["alpha.md"]


@pytest.mark.parametrize(
    ("argv", "stdin"),
    [(("set", "Thread:", "x"), ""), (("append",), "Checked: x\n")],
    ids=["set", "append"],
)
def test_set_and_append_refuse_a_brief_that_is_not_there(brief, argv, stdin):
    form, rest = argv[0], argv[1:]
    assert jbus("brief", form, str(brief), *rest, stdin=stdin) == (
        1,
        f"refused: no brief at {brief}\n",
    )
    assert not brief.exists()


def test_twenty_appends_at_once_keep_all_twenty_lines(brief):
    started(brief)
    at_once(brief, [(("append",), (), f"Checked: {n}\n") for n in range(20)])
    lines = brief.read_text().splitlines()
    assert sorted(one for one in lines if one.startswith("Checked:")) == sorted(
        f"Checked: {n}" for n in range(20)
    )
    assert lines[-2:] == ["## Review", "Verdict: clean"]


def test_a_set_beside_appends_keeps_both(brief):
    started(brief)
    writes = [(("append",), (), f"Checked: {n}\n") for n in range(5)]
    writes.insert(2, (("set",), ("Review:", "review"), ""))
    at_once(brief, writes)
    text = brief.read_text()
    assert "Review: review\n\n## Result" in text
    assert all(f"Checked: {n}\n" in text for n in range(5))
