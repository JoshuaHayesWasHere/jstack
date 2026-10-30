"""`jbus queue add` checks what a brief's lines mean, and `jbus queue check` runs the same check
and writes nothing.

`add` once checked only that a line was filled in. A `Review: standard` was queued, then read as
`review` by the crew, and a `Review: none` with a pull request to open sat at the merge waiting
for the user's word with nobody told. Now `Review:` takes `twice`, `review` or `none`, research,
perf, analysis and outcome work carries `Read:` and `Instruments:`, and `none` with a pull
request is a warning. `check` lets a home or a bot see that before it adds.

The tests run the real command against the kitchen.
"""

import json

import pytest

from test_jbus_kitchen import Kitchen, complete

DEEPER = "Read: `src/x.py:10`, the loop\nInstruments: `py-spy record -- python -m x`\n"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def said(slug, line, by):
    """`complete(slug)` with its `<line>:` line saying `by` in place of what it said."""
    return "".join(
        f"{line}: {by}\n" if one.startswith(f"{line}:") else one
        for one in complete(slug).splitlines(keepends=True)
    )


def adds(kitchen, slug, text):
    return kitchen.main("queue", "add", slug, "--priority", "1", stdin=text)


def checks(kitchen, text, *more):
    return kitchen.main("queue", "check", *more, stdin=text)


def queued(kitchen):
    path = kitchen.state / "queue.json"
    return [row["slug"] for row in json.loads(path.read_text())] if path.exists() else []


def files(kitchen):
    """Every file under the kitchen's state and home, with its bytes."""
    roots = (kitchen.state_dir, kitchen.home)
    return {path: path.read_bytes() for root in roots for path in root.rglob("*") if path.is_file()}


REVIEW_FAULT = "brief's Review: line says standard (twice, review or none)"


def test_add_refuses_a_review_word_that_is_not_one_of_the_three(kitchen):
    code, out = adds(kitchen, "alpha", said("alpha", "Review", "standard"))
    assert (code, out.splitlines()) == (
        1,
        ["refused: alpha's brief has 1 fault, and nothing is queued", f"- {REVIEW_FAULT}"],
    )
    assert "alpha" not in queued(kitchen)


@pytest.mark.parametrize("word", ["none, docs only", "review twice", "once"])
def test_add_refuses_a_review_line_that_says_more_or_other_than_one_word(kitchen, word):
    code, out = adds(kitchen, "alpha", said("alpha", "Review", word))
    assert code == 1
    assert f"- brief's Review: line says {word} (twice, review or none)" in out.splitlines()


@pytest.mark.parametrize("word", ["twice", "review", "none"])
def test_add_queues_each_of_the_three_review_words(kitchen, word):
    code, _ = adds(kitchen, "alpha", said("alpha", "Review", word))
    assert code == 0
    assert queued(kitchen) == ["alpha"]


def test_check_refuses_a_bad_review_word_with_one_fault_a_line_and_writes_nothing(kitchen):
    before = files(kitchen)
    code, out = checks(kitchen, said("alpha", "Review", "standard"))
    assert (code, out.splitlines()) == (1, [REVIEW_FAULT])
    assert files(kitchen) == before


def test_check_says_nothing_and_exits_0_for_a_good_brief_and_writes_nothing(kitchen):
    before = files(kitchen)
    assert checks(kitchen, complete("alpha")) == (0, "")
    assert files(kitchen) == before


def test_check_gives_every_fault_add_gives_the_home_line_included(kitchen):
    text = said("alpha", "Review", "standard").replace("Home: root\n", "")
    text = text.replace("Size: S", "Size: XL")
    _, added = adds(kitchen, "alpha", text)
    code, out = checks(kitchen, text)
    assert code == 1
    assert out.splitlines() == [line.removeprefix("- ") for line in added.splitlines()[1:]]
    assert len(out.splitlines()) == 3
    assert "brief has no Home: line" in out


def test_check_refuses_a_for_that_is_not_the_briefs_home(kitchen):
    (kitchen.home / "flow").mkdir()
    (kitchen.home / "flow" / "home-id").write_text("t3:flow\n")
    code, out = checks(kitchen, complete("alpha"), "--for", "flow")
    assert (code, out) == (1, "--for flow, and alpha's brief is the root home's\n")
    assert checks(kitchen, complete("alpha"), "--for", "root") == (0, "")


def test_check_reads_the_slug_from_the_title_or_takes_one_given(kitchen):
    text = complete("alpha").replace("# alpha: a task", "# a task with no slug")
    assert checks(kitchen, text, "alpha")[0] == 0


def test_check_of_a_queued_rows_edit_refuses_what_add_refuses(kitchen):
    assert adds(kitchen, "alpha", complete("alpha"))[0] == 0
    edit = said("alpha", "Review", "standard")
    assert checks(kitchen, edit) == (1, f"{REVIEW_FAULT}\n")
    assert adds(kitchen, "alpha", edit)[0] == 1


NONE_PR = (
    "warning: alpha's brief says Review: none and Pull request: open one when done: no reviewer "
    "runs, and jmerge leaves the pull request to wait for the user's word"
)


def test_add_warns_on_review_none_with_a_pull_request_and_still_queues(kitchen):
    code, out = adds(kitchen, "alpha", said("alpha", "Review", "none"))
    assert code == 0
    assert NONE_PR in out.splitlines()
    assert queued(kitchen) == ["alpha"]


def test_check_warns_on_review_none_with_a_pull_request_and_exits_0(kitchen):
    assert checks(kitchen, said("alpha", "Review", "none")) == (0, f"{NONE_PR}\n")


def test_review_none_that_asks_first_is_no_warning(kitchen):
    text = said("alpha", "Review", "none").replace(
        "Pull request: open one when done", "Pull request: ask first"
    )
    assert checks(kitchen, text) == (0, "")


def test_a_batch_add_warns_as_add_does(kitchen):
    text = said("alpha", "Review", "none")
    batch = f"add alpha --priority 1\n--- brief alpha\n{text}--- end\n"
    code, out = kitchen.main("queue", "apply", stdin=batch)
    assert code == 0, out
    assert NONE_PR in out.splitlines()


DEEPER_FAULT = (
    "brief's {where} names {kind} work, and the brief has no filled-in {lines} (Read: the rawest "
    "material to start from, Instruments: each method with the command that runs it here)"
)


@pytest.mark.parametrize("playbook", ["perf-issue", "hillclimb"])
def test_add_and_check_refuse_a_deeper_playbook_with_no_read_and_instruments(kitchen, playbook):
    text = said("alpha", "Playbook", playbook)
    fault = DEEPER_FAULT.format(
        where="Playbook: line", kind=playbook, lines="Read: and Instruments: lines"
    )
    assert checks(kitchen, text) == (1, f"{fault}\n")
    code, out = adds(kitchen, "alpha", text)
    assert (code, out.splitlines()[1:]) == (1, [f"- {fault}"])


def test_a_task_that_names_analysis_needs_its_instruments_line_too(kitchen):
    text = complete("alpha").replace('Task: "do alpha"', 'Task: "run a full analysis of alpha"')
    text = text.replace("Home: root\n", "Home: root\nRead: `src/alpha/`, the code\n")
    fault = DEEPER_FAULT.format(where="Task: line", kind="analysis", lines="Instruments: line")
    assert checks(kitchen, text) == (1, f"{fault}\n")


def test_deeper_work_with_read_and_instruments_is_queued(kitchen):
    text = said("alpha", "Playbook", "perf-issue") + DEEPER
    assert checks(kitchen, text) == (0, "")
    assert adds(kitchen, "alpha", text)[0] == 0


def test_a_feature_brief_needs_no_read_or_instruments_line(kitchen):
    assert "Read:" not in complete("alpha")
    assert checks(kitchen, complete("alpha")) == (0, "")
