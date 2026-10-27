"""A scoped home reaches the root only by `jbus stop`, which jbus takes only when the home's own
open row is held by something the home cannot clear (fl-msg-scope-stop).

Of 28 sends from a scoped home to the root in a week, 7 were needed, and each needed one was a home
stuck on a row it could not clear, a decision, or a word. So jbus checks the queue, not the words:
a stop names the scope's own open row and the other home's open row that holds it, or something no
home owns. The tests run the real command against the kitchen's faked T3 Code server, with rows
written into the queue as a pass leaves them.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from jbus import queue, stop
from test_jbus_capped_sends import cap
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_word import thread

ROOT, FLOW, VIEW, NEXT = thread("a"), thread("f"), thread("d"), thread("e")
SCOPE, OTHER = "flow", "view"
WHAT = ("the", "train", "is", "red", "on", "a", "root", "fix")


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "home-id").write_text(f"{ROOT}\n")
    for scope, id in ((SCOPE, FLOW), (OTHER, VIEW)):
        (made.home / scope).mkdir()
        (made.home / scope / "home-id").write_text(f"{id}\n")
    rows(
        made,
        ("fl-mine", SCOPE, "pr", "#11"),
        ("fl-sibling", SCOPE, "running", ""),
        ("fl-landed", SCOPE, "merged", "#9"),
        ("fix-root", "", "pr", "#12"),
        ("vw-board", OTHER, "running", ""),
        ("fix-old", "", "merged", "#8"),
    )
    yield made
    made.close()


def rows(kitchen, *made):
    """Write each row into the queue, with its stored brief naming its home, as a pass leaves
    them: `(slug, home, status, pr)`, where an empty home is the root's."""
    table = []
    for slug, home, status, pr in made:
        text = f"# {slug}: a task\n" + (f"Home: {home}\n" if home else "")
        queue.brief_path(kitchen.state, slug).parent.mkdir(parents=True, exist_ok=True)
        queue.brief_path(kitchen.state, slug).write_text(text)
        table.append({"slug": slug, "priority": 1, "status": status, "pr": pr})
    queue.path(kitchen.state).write_text(json.dumps(table))


def status(kitchen, slug, to):
    """Move a row to a status, as a pass's `derive` does."""
    table = json.loads(queue.path(kitchen.state).read_text())
    for row in table:
        if row["slug"] == slug:
            row["status"] = to
    queue.path(kitchen.state).write_text(json.dumps(table))


def stops(kitchen, row="fl-mine", *held, by=FLOW, what=WHAT):
    return kitchen.main("stop", row, *held, "--from", by, *what)


def answers(kitchen, *text, scope=SCOPE, row="fl-mine", by=ROOT):
    return kitchen.main("stop", "answer", scope, row, *text, "--from", by)


def sent(kitchen):
    """Return `(thread, key)` of each message that went to T3 Code."""
    return [
        (given["threadId"], given["clientRequestId"].split("|")[0])
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send"
    ]


def texts(kitchen):
    return [given["message"] for tool, given in kitchen.t3.calls if tool == "t3_thread_send"]


def test_a_stop_on_another_homes_open_row_goes_to_the_root_once(kitchen):
    code, said = stops(kitchen, "fl-mine", "--on", "fix-root")
    assert (code, said) == (
        0,
        f"stopped: stop|flow|fl-mine|fix-root, sent to the root home at {ROOT}\n",
    )
    assert sent(kitchen) == [(ROOT, "stop")]
    (text,) = texts(kitchen)
    assert "fl-mine is held by fix-root, the root home's row" in text
    assert "the train is red on a root fix" in text
    assert "jbus stop answer flow fl-mine" in text
    kitchen.poll()
    kitchen.poll()
    assert sent(kitchen) == [(ROOT, "stop")]
    (logged,) = [json.loads(line) for line in (kitchen.state / "outbox.jsonl").open()]
    assert (logged["needs"], logged["went"], logged["template"]) == ("decide", "sent", "stop")


def test_a_stop_on_another_scopes_row_or_on_a_pull_request_number_is_taken(kitchen):
    assert stops(kitchen, "fl-mine", "--on", "vw-board")[0] == 0
    code, said = stops(kitchen, "fl-sibling", "--on", "#12")
    assert (code, said) == (
        0,
        f"stopped: stop|flow|fl-sibling|fix-root, sent to the root home at {ROOT}\n",
    )
    assert sent(kitchen) == [(ROOT, "stop"), (ROOT, "stop")]


def test_a_stop_on_the_scopes_own_row_only_is_refused(kitchen):
    code, said = stops(kitchen, "fl-mine", "--on", "fl-sibling")
    assert code == 1
    assert said.startswith("refused: fl-sibling is the flow home's own row, which it clears itself")
    assert stops(kitchen, "fl-mine", "--on", "#11")[0] == 1
    assert sent(kitchen) == []
    assert stop.load(kitchen.state) == []


def test_a_stop_on_a_merged_own_row_is_refused(kitchen):
    code, said = stops(kitchen, "fl-landed", "--on", "fix-root")
    assert (code, said) == (
        1,
        "refused: fl-landed is merged, so it holds nothing and nothing holds it\n",
    )
    assert sent(kitchen) == []


@pytest.mark.parametrize(
    ("row", "held", "by", "why"),
    [
        ("fl-mine", ("--on", "fix-old"), FLOW, "refused: fix-old is merged"),
        ("fl-mine", ("--on", "nothing-here"), FLOW, "refused: the queue has no row nothing-here"),
        ("fl-mine", ("--on", "#99"), FLOW, "refused: --on #99 is the pull request of no row"),
        ("fix-root", ("--on", "vw-board"), FLOW, "refused: fix-root is the root home's row"),
        ("vw-board", ("--on", "fix-root"), FLOW, "refused: vw-board is the view home's row"),
        ("fl-mine", ("--on", "fix-root"), ROOT, "refused: --from is the root home's thread"),
        ("fl-mine", ("--on", "fix-root"), NEXT, f"refused: --from {NEXT} is no scoped home's"),
        ("fl-mine", (), FLOW, "refused: a stop names what holds its row"),
    ],
)
def test_a_stop_that_is_not_a_scopes_own_open_row_held_by_another_home_is_refused(
    kitchen, row, held, by, why
):
    code, said = stops(kitchen, row, *held, by=by)
    assert (code, said.startswith(why)) == (1, True), said
    assert sent(kitchen) == []


def test_a_stop_says_what_the_root_must_clear(kitchen):
    code, said = stops(kitchen, "fl-mine", "--on", "fix-root", what=())
    assert (code, said) == (1, "refused: a stop says what the root must clear\n")


def test_the_same_stop_again_is_refused_as_already_open(kitchen):
    assert stops(kitchen, "fl-mine", "--on", "fix-root")[0] == 0
    code, said = stops(kitchen, "fl-mine", "--on", "#12")
    assert (code, said) == (
        1,
        "refused: the stop stop|flow|fl-mine|fix-root is already open, and the root has it\n",
    )
    assert sent(kitchen) == [(ROOT, "stop")]


def test_a_stop_outside_every_home_is_taken_and_counted_per_scope_in_the_digest(kitchen):
    held = ("--outside", "the machine's disk is full")
    code, said = stops(kitchen, "fl-mine", *held)
    assert (code, said) == (
        0,
        f"stopped: stop|flow|fl-mine|outside, sent to the root home at {ROOT}\n",
    )
    assert "held by the machine's disk is full, which no home owns" in texts(kitchen)[0]
    assert stops(kitchen, "fl-mine", *held)[0] == 1
    code, said = kitchen.main("digest", "--json", "--since", NOW.date().isoformat())
    assert code == 0, said
    told = json.loads(said)["projects"]["demo"]["stops"]
    assert told["outside"] == {SCOPE: 1}
    assert [(one["row"], one["outside"]) for one in told["open"]] == [
        ("fl-mine", "the machine's disk is full")
    ]


def test_an_answer_reaches_the_scope_once_and_closes_the_stop(kitchen):
    assert stops(kitchen, "fl-mine", "--on", "fix-root")[0] == 0
    code, said = answers(kitchen, "rebase", "on", "main", "once", "fix-root", "merges")
    assert (code, said) == (
        0,
        f"answered: stop|flow|fl-mine|fix-root, closed, the answer sent to {FLOW}\n",
    )
    assert sent(kitchen) == [(ROOT, "stop"), (FLOW, "stop-answer")]
    assert texts(kitchen)[1].endswith("on fl-mine: rebase on main once fix-root merges")
    kitchen.poll()
    assert sent(kitchen) == [(ROOT, "stop"), (FLOW, "stop-answer")]
    code, said = answers(kitchen, "again")
    assert (code, said) == (1, "refused: the flow home has no open stop on fl-mine\n")
    assert stops(kitchen, "fl-mine", "--on", "fix-root")[0] == 0
    assert sent(kitchen)[-1] == (ROOT, "stop")


def test_only_the_root_answers_a_stop(kitchen):
    assert stops(kitchen, "fl-mine", "--on", "fix-root")[0] == 0
    code, said = answers(kitchen, "I", "answer", "myself", by=FLOW)
    assert (code, said.startswith(f"refused: --from {FLOW} is not the root home's thread")) == (
        1,
        True,
    )
    assert sent(kitchen) == [(ROOT, "stop")]


@pytest.mark.parametrize("ended", ["merged", "done", "removed"])
def test_a_stop_whose_own_row_ends_closes_itself_with_no_message(kitchen, ended):
    assert stops(kitchen, "fl-mine", "--on", "fix-root")[0] == 0
    if ended == "removed":
        queue.removed_path(kitchen.state).write_text(json.dumps({"fl-mine": {"at": "", "by": ""}}))
    else:
        status(kitchen, "fl-mine", ended)
    kitchen.poll()
    (one,) = stop.load(kitchen.state)
    assert one.closed == ended
    assert sent(kitchen) == [(ROOT, "stop")]
    assert answers(kitchen, "too", "late")[0] == 1
    assert sent(kitchen) == [(ROOT, "stop")]


def test_a_stop_with_no_root_running_waits_for_the_next_root_and_never_reaches_the_old_one(
    kitchen,
):
    (kitchen.home / "handoff.md").write_text(f"Was home: {ROOT}\n")
    code, said = stops(kitchen, "fl-mine", "--on", "fix-root")
    assert (code, said) == (
        0,
        "stopped: stop|flow|fl-mine|fix-root, sent to nobody yet, no root home is running, "
        "its home-id holds no thread\n",
    )
    kitchen.poll()
    assert sent(kitchen) == []
    (kitchen.home / "home-id").write_text(f"{NEXT}\n")
    kitchen.poll()
    kitchen.poll()
    assert sent(kitchen) == [(NEXT, "stop")]


def test_a_stop_into_a_capped_root_waits_for_the_reset(kitchen):
    cap("claudeAgent", resets=datetime.now(UTC) + timedelta(hours=1))
    kitchen.t3.thread("root", threadId=ROOT)
    code, said = stops(kitchen, "fl-mine", "--on", "fix-root")
    assert (code, said.endswith("sent to nobody yet, its thread is capped\n")) == (0, True), said
    assert sent(kitchen) == []
