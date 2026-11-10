"""`jbus queue add` checks what a brief's lines mean, and `jbus queue check` runs the same check
and writes nothing.

`add` once checked only that a line was filled in. A `Review: standard` was queued, then read as
`review` by the crew, and a `Review: none` with a pull request to open sat at the merge waiting
for the user's word with nobody told. Now `Review:` takes `twice`, `review` or `none`, research,
perf, analysis and outcome work carries `Read:` and `Instruments:`, and `none` with a pull
request is a warning. `check` lets a home or a bot see that before it adds.

A follow-up is also told of each live row that may already hold its fault (`jbus.asks._twins`):
#1267 was filed and built while its twin stood at `pr`, and `add` refuses only the same text.

The tests run the real command against the kitchen.
"""

import json

import pytest

from jbriefs import parse
from test_jbus_kitchen import Kitchen, complete, go

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


REVIEW_FAULT = "brief's Review: line says standard (review or none)"


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
    assert f"- brief's Review: line says {word} (review or none)" in out.splitlines()


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
    text = said("alpha", "Review", "standard").replace("Home: uncategorized\n", "")
    text = text.replace("Size: S", "Size: XL")
    _, added = adds(kitchen, "alpha", text)
    code, out = checks(kitchen, text)
    assert code == 1
    assert out.splitlines() == [line.removeprefix("- ") for line in added.splitlines()[1:]]
    assert len(out.splitlines()) == 3
    assert "brief has no Home: line" in out


def test_check_refuses_a_for_that_is_not_the_briefs_home(kitchen):
    (kitchen.home / "flow").mkdir()
    (kitchen.home / "flow" / "plan.md").write_text("# a plan\n")
    (kitchen.home / "flow" / "home-id").write_text("t3:flow\n")
    code, out = checks(kitchen, complete("alpha"), "--for", "flow")
    assert (code, out) == (1, "--for flow, and alpha's brief is the uncategorized home's\n")
    assert checks(kitchen, complete("alpha"), "--for", "uncategorized") == (0, "")
    assert checks(kitchen, complete("alpha"), "--for", "root") == (
        1,
        "--for root, and alpha's brief is the uncategorized home's\n",
    )


def test_check_reads_the_slug_from_the_title_or_takes_one_given(kitchen):
    (kitchen.home / "flow").mkdir()
    (kitchen.home / "flow" / "plan.md").write_text("# a plan\n")
    (kitchen.home / "flow" / "home-id").write_text("t3:flow\n")
    text = complete("alpha")
    assert checks(kitchen, text, "--for", "flow") == (
        1,
        "--for flow, and alpha's brief is the uncategorized home's\n",
    )
    assert checks(kitchen, text, "beta", "--for", "flow") == (
        1,
        "--for flow, and beta's brief is the uncategorized home's\n",
    )


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
    text = text.replace(
        "Home: uncategorized\n", "Home: uncategorized\nRead: `src/alpha/`, the code\n"
    )
    fault = DEEPER_FAULT.format(where="Task: line", kind="analysis", lines="Instruments: line")
    assert checks(kitchen, text) == (1, f"{fault}\n")


def test_deeper_work_with_read_and_instruments_is_queued(kitchen):
    text = said("alpha", "Playbook", "perf-issue") + DEEPER
    assert checks(kitchen, text) == (0, "")
    assert adds(kitchen, "alpha", text)[0] == 0


def test_a_feature_brief_needs_no_read_or_instruments_line(kitchen):
    assert "Read:" not in complete("alpha")
    assert checks(kitchen, complete("alpha")) == (0, "")


DONE_WHEN = (
    "warning: alpha's brief's Done when: has 1 of 1 items that run nothing, the first: {first} "
    "(in each, a command in backticks that starts with a runner, a `tests/...py[::name]` path, "
    "or `judged: <why>`)"
)
RUNS = "- `uv run pytest -q tests/test_alpha.py` passes"


def test_add_warns_of_a_done_when_in_prose_alone_and_still_queues(kitchen):
    text = complete("alpha").replace("- `make check` passes", "- the page reads well")
    code, out = adds(kitchen, "alpha", text)
    assert code == 0, out
    assert DONE_WHEN.format(first="the page reads well (in none)") in out.splitlines()
    assert queued(kitchen) == ["alpha"]
    assert checks(kitchen, text) == (
        0,
        DONE_WHEN.format(first="the page reads well (in none)") + "\n",
    )


@pytest.mark.parametrize(
    "item", [RUNS, "- tests/test_alpha.py::test_it passes", "- judged: only the user can say"]
)
def test_add_queues_a_runnable_or_judged_done_when_with_no_warning(kitchen, item):
    text = complete("alpha").replace("- `make check` passes", item)
    assert checks(kitchen, text) == (0, "")
    code, out = adds(kitchen, "alpha", text)
    assert code == 0 and "warning:" not in out, out


def test_an_approved_row_gets_no_new_fault_once_the_done_when_check_refuses(kitchen, monkeypatch):
    """`_new_faults` grandfathers a row whose go holds: a lint that refuses its brief now, as the
    Done when check will once it leaves `parse.WARNED`, never refuses the brief it approved, while
    a new row with the same brief is refused."""
    text = complete("alpha").replace("- `make check` passes", "- the page reads well")
    assert adds(kitchen, "alpha", text)[0] == 0
    assert go(kitchen, "alpha")[0] == 0
    monkeypatch.setattr(parse, "WARNED", ())
    code, out = adds(kitchen, "alpha", text)
    assert code == 0, out
    assert checks(kitchen, text)[0] == 0
    code, out = adds(kitchen, "beta", text.replace("alpha", "beta"))
    assert code == 1
    assert "- brief's Done when: has 1 of 1 items that run nothing" in out


RETRIES = (
    "# sa-follow-add-retries: the green move enables and starts a unit it linked whose enable was "
    "refused, so a refusal is retried by the next move\n"
    "Green main: 7c7c4fdb58eefdf2b21b1444b6a848d4cc3215b7\n"
    "Follows: sa-follow-runs-live\n"
    "Task: sa-follow-runs-live's Units.add (features/jinstall/src/jinstall/kinds.py, Units.add) "
    "picks the units to add by whether a link exists, and Agents.add "
    "(features/jinstall/src/jinstall/agents.py, Agents.add) by whether the plist exists. A move "
    "that linked a unit and then had daemon-reload or enable --now refused leaves a link that no "
    "later move enables again, so the follower stays stopped until a jinstall run. Fix: pick each "
    "unit that is to be on and is either unlinked, or linked as the install's and not enabled "
    "(systemctl is-enabled, where the manager answers), or for launchd has the install's plist "
    "and is not loaded; then link, daemon-reload and enable --now (bootstrap) those. A manager "
    "that does not answer keeps today's choice by the link alone.\n"
    "Done when:\n"
    "- a second Units.add after a refused enable --now enables and starts the unit, and one after "
    "a taken enable makes no enable call (in `features/jinstall/src/jinstall/kinds.py`)\n"
    "- Agents.add bootstraps an agent whose plist it wrote but whose bootstrap was refused, and "
    "does nothing on a second call (in `features/jinstall/src/jinstall/agents.py`)\n"
    "- tests for both (in `features/jinstall/tests`)\n"
    "- the check command passes (in none)\n"
    "Proves it: the tests failing at origin/main and passing on the branch\n"
    "Size: S\n"
    "Where: `features/jinstall/src/jinstall`, `features/jinstall/tests`\n"
    "Do not touch: `features/jbus/src/jbus/follow.py`, `features/jbus/src/jbus/threads.py`; run "
    "no systemctl, launchctl or jinstall on the live machine\n"
    "Decisions: noticed in sa-follow-runs-live, its review's F1 (Consider), left for a follow-up\n"
    "Design: none, Units.add and Agents.add are the shapes\n"
    "Skills: principle-make-operations-idempotent\n"
    "Pull request: open one when done\n"
    "Review: review\n"
    "Playbook: none\n"
    "Home: uncategorized\n"
)
"""sa-follow-add-retries's brief as it was queued, its `Home:` the kitchen's catch-all: the row
that stood at `pr` while its twin was filed and built."""

ENABLE = (
    "# sa-follow-add-retries-enable: a unit whose enable the manager refused is linked, enabled "
    "and started again on the next pass\n"
    "Green main: 269cb479d9dac40eefc4eda2b4854d96a692cf1b\n"
    'Task: "Push + self-heal": `jinstall.kinds.Units.add` '
    "(features/jinstall/src/jinstall/kinds.py:1251) links each new unit into "
    "`~/.config/systemd/user` before it runs `systemctl --user enable --now`, and picks the units "
    "to add by whether that link exists. When the manager refuses the enable, the link stays, so "
    "every later call of `jinstall.green.live` (which `jbus.green` now asks on each pass until it "
    "holds) finds the unit linked and adds nothing: the follower stays stopped though jbus asks "
    "again. Fix: have `add` take back the link (and the wanted link) of a unit whose enable was "
    "refused, so the next call adds it again, and the same for `jinstall.agents.Agents.add` on "
    "launchd.\n"
    "Done when:\n"
    "- after an enable systemd refuses, the next `add` links, enables and starts that unit again "
    "(in `features/jinstall/src/jinstall/kinds.py`)\n"
    "- a test of it fails at main and passes at the head (in `features/jinstall/tests`)\n"
    "Proves it: the new test, base exit 1 and head exit 0, and CI's `check` job\n"
    "Size: S\n"
    "Where: `features/jinstall/src/jinstall/kinds.py`, "
    "`features/jinstall/src/jinstall/agents.py`, `features/jinstall/tests`\n"
    "Do not touch: run no jinstall, and no systemctl that starts, stops, enables or restarts a "
    "unit on this machine\n"
    "Decisions: noticed in sa-follow-live-each-pass\n"
    "Design: none, one unlink on a refused enable\n"
    "Skills: tdd\n"
    "Pull request: open one when done\n"
    "Review: review\n"
    "Playbook: feature\n"
    "Home: uncategorized\n"
)
"""sa-follow-add-retries-enable's brief, the follow-up filed and built as #1267 while its twin
stood at `pr`, its `Home:` the kitchen's catch-all and its `Playbook:` and `Skills:` ones `add`
takes."""

TWIN = "sa-follow-add-retries (pr, pull request #1262)"


def live(kitchen, slug, text, **columns):
    """Queue a row with `text` for its brief, and set the columns a pass would set."""
    assert adds(kitchen, slug, complete(slug))[0] == 0
    (kitchen.state / "briefs" / f"{slug}.md").write_text(text)
    rows = json.loads((kitchen.state / "queue.json").read_text())
    for row in rows:
        if row["slug"] == slug:
            row.update(columns)
    (kitchen.state / "queue.json").write_text(json.dumps(rows))


def twins(out):
    return [line for line in out.splitlines() if "may be the fault" in line]


@pytest.mark.parametrize(
    "follow_up",
    [
        pytest.param(ENABLE, id="noticed-in"),
        pytest.param(
            ENABLE.replace(
                "Decisions: noticed in sa-follow-live-each-pass", "Decisions: none"
            ).replace("Task:", "Follows: sa-follow-live-each-pass\nTask:"),
            id="follows",
        ),
    ],
)
def test_a_follow_up_is_told_each_live_row_of_the_same_fault(kitchen, follow_up):
    alone = checks(kitchen, follow_up)
    live(kitchen, "sa-follow-add-retries", RETRIES, status="pr", pr="#1262")
    code, out = checks(kitchen, follow_up)
    assert len(twins(out)) == 1 and TWIN in twins(out)[0], out
    assert (code, [line for line in out.splitlines() if line not in twins(out)]) == (
        alone[0],
        alone[1].splitlines(),
    )
    code, out = adds(kitchen, "sa-follow-add-retries-enable", follow_up)
    assert code == 0, out
    assert len(twins(out)) == 1 and TWIN in twins(out)[0], out
    assert "sa-follow-add-retries-enable" in queued(kitchen)


def test_a_shared_file_alone_names_no_twin(kitchen):
    alone = checks(kitchen, ENABLE)
    live(kitchen, "sa-follow-add-retries", RETRIES, status="pr", pr="#1262")
    quieter = RETRIES.replace(RETRIES.split("\n")[0], "# sa-quiet: the green move says less")
    quieter = quieter.replace(RETRIES.split("\n")[3], "Task: make the green move quieter")
    live(kitchen, "sa-quiet", quieter, status="running")
    code, out = checks(kitchen, ENABLE)
    assert [TWIN in line for line in twins(out)] == [True], out
    assert (code, [line for line in out.splitlines() if line not in twins(out)]) == (
        alone[0],
        alone[1].splitlines(),
    )
    code, out = adds(kitchen, "sa-follow-add-retries-enable", ENABLE)
    assert code == 0 and [TWIN in line for line in twins(out)] == [True], out
    rows = json.loads((kitchen.state / "queue.json").read_text())
    added = next(row for row in rows if row["slug"] == "sa-follow-add-retries-enable")
    assert not added.get("held") and added.get("status", "queued") == "queued"


def test_a_brief_that_follows_nothing_names_no_twin(kitchen):
    alone = ENABLE.replace("Decisions: noticed in sa-follow-live-each-pass", "Decisions: none")
    live(kitchen, "sa-follow-add-retries", RETRIES, status="pr", pr="#1262")
    assert twins(checks(kitchen, alone)[1]) == []


def test_a_finished_row_is_no_twin(kitchen):
    live(kitchen, "sa-follow-add-retries", RETRIES, status="merged", pr="#1262")
    assert twins(checks(kitchen, ENABLE)[1]) == []


def test_a_queue_that_does_not_parse_names_no_twin_and_check_still_answers(kitchen):
    kitchen.state.mkdir(parents=True, exist_ok=True)
    (kitchen.state / "queue.json").write_text("not json")
    code, out = checks(kitchen, ENABLE)
    assert code == 0 and twins(out) == [], out
