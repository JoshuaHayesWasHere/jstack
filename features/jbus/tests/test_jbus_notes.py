"""A dated line that lands in a home's `notes.md` wakes that home, so the file takes no new entries.

The user's word (2026-10-28): homes add no entries to `notes.md`; a standing rule goes to the
plan, a brief or code. A home's file is one item of the one list, keyed `notes:<file>`, whose words
name the newest dated line the pass found new. The first pass that sees a file tells its home of
every dated line already there, through the newest, so a home with old entries learns of them. A
pass that finds no new line says nothing new, and wakes nobody. The tests run the real pass against
the kitchen's fakes.
"""

from datetime import timedelta

import pytest

from jbus import wakes
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_leftover import home

OLD = "- 2026-10-13: AWS for this repo: dev is the HayesApps account"
NEW = "- 2026-11-02 10:01 EST, word 53334f6970be: merge the green PR, the other two snoozed"
LATER = "- 2026-11-02 11:30 EST: the runner label is Winnifred-ephemeral"
ASK = "Move each entry into the plan, a brief or code"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


@pytest.fixture
def homes(kitchen):
    """The root home and the scope jview, each with a thread."""
    root, scoped = home(kitchen), home(kitchen, "jview")
    return kitchen, root["threadId"], scoped["threadId"]


def notes_wakes(kitchen, thread):
    """The messages of the one list to the thread that name a home's notes."""
    return [
        given["message"]
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send"
        and given["threadId"] == thread
        and given["clientRequestId"].startswith("wakes|")
        and "- notes:" in given["message"]
    ]


def append(path, line):
    path.write_text((path.read_text() if path.exists() else "") + line + "\n")


def test_a_new_dated_line_wakes_its_home_once_naming_the_line(homes):
    kitchen, root, scoped = homes
    notes = kitchen.home / "notes.md"
    notes.write_text(f"# demo: notes\n\n{OLD}\n")
    kitchen.poll(NOW)
    (first,) = notes_wakes(kitchen, root)
    assert f"- notes:notes.md: {OLD}" in first and ASK in first
    append(notes, NEW)
    kitchen.poll(NOW + timedelta(minutes=1))
    _, said = notes_wakes(kitchen, root)
    assert f"- notes:notes.md: {NEW}" in said and OLD not in said and ASK in said
    kitchen.poll(NOW + timedelta(minutes=2))
    assert len(notes_wakes(kitchen, root)) == 2
    assert notes_wakes(kitchen, scoped) == []


def test_a_notes_md_with_no_new_line_wakes_nothing(homes):
    kitchen, root, _ = homes
    notes = kitchen.home / "notes.md"
    notes.write_text(f"# demo: notes\n\n{OLD}\n{NEW}\n")
    kitchen.poll(NOW)
    assert len(notes_wakes(kitchen, root)) == 1
    append(notes, "an undated line, which is no entry")
    kitchen.poll(NOW + timedelta(minutes=1))
    notes.write_text(notes.read_text().replace(NEW + "\n", ""))
    kitchen.poll(NOW + timedelta(minutes=2))
    kitchen.poll(NOW + wakes.KEEP + timedelta(minutes=3))
    assert len(notes_wakes(kitchen, root)) == 1


def test_a_notes_md_with_no_dated_line_wakes_nobody(homes):
    kitchen, root, _ = homes
    (kitchen.home / "notes.md").write_text("# demo: notes\n\n- CI: one check job only\n")
    kitchen.poll(NOW)
    kitchen.poll(NOW + timedelta(minutes=1))
    assert notes_wakes(kitchen, root) == []


def test_a_scope_line_wakes_that_scope_and_a_later_line_wakes_it_again(homes):
    kitchen, root, scoped = homes
    notes = kitchen.home / "jview" / "notes.md"
    kitchen.poll(NOW)
    append(notes, NEW)
    kitchen.poll(NOW + timedelta(minutes=1))
    (said,) = notes_wakes(kitchen, scoped)
    assert f"- notes:jview/notes.md: {NEW}" in said
    append(notes, LATER)
    kitchen.poll(NOW + timedelta(minutes=2))
    _, again = notes_wakes(kitchen, scoped)
    assert f"- notes:jview/notes.md: {LATER}" in again
    assert notes_wakes(kitchen, root) == []


def test_the_pass_deletes_no_notes_md_and_an_emptied_one_leaves_the_list(homes):
    kitchen, root, _ = homes
    notes = kitchen.home / "notes.md"
    notes.write_text(f"{OLD}\n")
    kitchen.poll(NOW)
    notes.write_text("# demo: notes\n")
    kitchen.poll(NOW + timedelta(minutes=1))
    kitchen.poll(NOW + wakes.KEEP + timedelta(minutes=2))
    assert notes.read_text() == "# demo: notes\n"
    assert len(notes_wakes(kitchen, root)) == 1
    append(notes, OLD)
    kitchen.poll(NOW + wakes.KEEP + timedelta(minutes=3))
    assert len(notes_wakes(kitchen, root)) == 2
