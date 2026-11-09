"""`jbus queue add` and `jbus queue check` warn of a brief whose `Asked:` line names no file under
the home's `asked/`, and of a quote on its `Task:` line whose words that file does not hold. The
file keeps the user's whole request once, so a quote on `Task:` can be checked against it. Both are
warnings: the brief is queued all the same.

The tests run the real command against the kitchen, with small made-up briefs and requests.
"""

import json

import pytest

from test_jbus_kitchen import Kitchen, complete

ASKED = (
    "## Asked\n"
    "2026-01-02 10:00, message t3:alpha/1\n"
    "Make the queue page show each row's home, so I can tell\n"
    "which scope owns a row at a glance.\n"
)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "asked").mkdir()
    (made.home / "asked" / "page.md").write_text(ASKED)
    yield made
    made.close()


def asked(task, line="Asked: $H/asked/page.md"):
    """`complete("alpha")` with `task` on its `Task:` line and `line` under it."""
    text = complete("alpha", f"{line}\n" if line else "")
    return text.replace('Task: "do alpha"', f"Task: {task}")


def check(kitchen, text):
    return kitchen.main("queue", "check", stdin=text)


def test_check_warns_of_a_quote_on_task_whose_words_the_asked_file_lacks(kitchen):
    code, out = check(kitchen, asked('"show each row\'s priority" on the queue page'))
    assert code == 0
    assert out.splitlines() == [
        "warning: alpha's brief's Task: quotes \"show each row's priority\", "
        "which $H/asked/page.md does not hold: a quote holds only words the user typed"
    ]


@pytest.mark.parametrize(
    "task",
    [
        '"show each row\'s home": the home adds a column',
        "“Make the queue page show each row’s home, so I can tell which scope owns a row”",
        '"which scope owns ... at a glance", and `"not a quote"` stays code',
        "the home's own words, with no quote",
    ],
)
def test_check_says_nothing_of_a_quote_the_asked_file_holds(kitchen, task):
    assert check(kitchen, asked(task)) == (0, "")


@pytest.mark.parametrize(
    "line",
    [
        "Asked: $H/asked/gone.md",
        "Asked: `$H/tasks/alpha.md`",
        "Asked: $H/asked/../tasks/alpha.md",
    ],
)
def test_check_warns_of_an_asked_path_that_is_no_file_under_the_homes_asked(kitchen, line):
    (kitchen.home / "tasks" / "alpha.md").write_text(ASKED)
    path = line.removeprefix("Asked: ").strip("`")
    code, out = check(kitchen, asked('"show each row\'s priority"', line))
    assert code == 0
    assert out.splitlines() == [
        f"warning: alpha's brief's Asked: {path} is no file under the home's asked/: "
        "the home writes the user's request there once, as $H/asked/<entry>.md"
    ]


def test_a_brief_with_no_asked_line_is_not_warned_of_its_quotes(kitchen):
    assert check(kitchen, asked('"words nobody kept"', line="")) == (0, "")


def test_add_queues_a_brief_it_warns_of(kitchen):
    text = asked('"show each row\'s priority"')
    code, out = kitchen.main("queue", "add", "alpha", "--priority", "1", stdin=text)
    assert code == 0
    assert "warning: alpha's brief's Task: quotes \"show each row's priority\"" in out
    rows = json.loads((kitchen.state / "queue.json").read_text())
    assert [row["slug"] for row in rows] == ["alpha"]
