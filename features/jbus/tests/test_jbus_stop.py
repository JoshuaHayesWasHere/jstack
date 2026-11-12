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
from test_jbus_kitchen import NOW, Kitchen, sends
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
        (made.home / scope / "plan.md").write_text("# a plan\n")
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
    them: `(slug, home, status, pr)`, where an empty home is the catch-all's, `uncategorized`."""
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


DOOR = ("--holds", "touches prod or real users")


def stops(kitchen, row="fl-mine", *held, by=FLOW, what=WHAT, door=DOOR):
    return kitchen.main("stop", row, *held, *door, "--from", by, *what)


def answers(kitchen, *text, scope=SCOPE, row="fl-mine", by=ROOT):
    return kitchen.main("stop", "answer", scope, row, *text, "--from", by)


def sent(kitchen):
    """Return `(thread, key)` of each message that went to T3 Code, but for the wakes of the home
    thread."""
    return [(given["threadId"], given["clientRequestId"].split("|")[0]) for given in sends(kitchen)]


def texts(kitchen):
    return [given["message"] for given in sends(kitchen)]


def test_a_stop_on_another_homes_open_row_goes_to_the_root_once(kitchen):
    code, said = stops(kitchen, "fl-mine", "--on", "fix-root")
    assert (code, said) == (
        0,
        f"stopped: stop|flow|fl-mine|fix-root, sent to the root home at {ROOT}\n",
    )
    assert sent(kitchen) == [(ROOT, "stop")]
    (text,) = texts(kitchen)
    assert "stopped at a one-way door, touches prod or real users" in text
    assert "answer the stop with your recommendation" in text
    assert "which adds it to its own gate for the door" in text
    assert "The root writes nothing into the flow home's files" in text
    assert "fl-mine is held by fix-root, the uncategorized home's row" in text
    assert "the train is red on a root fix" in text
    assert "jbus stop answer flow fl-mine" in text
    kitchen.poll()
    kitchen.poll()
    assert sent(kitchen) == [(ROOT, "stop")]
    logged = [json.loads(line) for line in (kitchen.state / "outbox.jsonl").open()]
    (stop,) = [one for one in logged if one["template"] == "stop"]
    assert (stop["needs"], stop["went"]) == ("decide", "sent")


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
    assert stop.load(kitchen.state) == stop.Kept()


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
        (
            "fix-root",
            ("--on", "vw-board"),
            FLOW,
            "refused: fix-root is the uncategorized home's row",
        ),
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


@pytest.mark.parametrize(
    ("door", "named"),
    [
        ((), "refused: this stop has no --holds; "),
        (
            ("--holds", "needs steering"),
            "refused: --holds 'needs steering' is no case of the table; ",
        ),
        (("--holds", "deletes"), "refused: --holds 'deletes' is no case of the table; "),
    ],
)
def test_a_stop_that_is_no_one_way_door_is_refused_and_told_to_the_user_directly(
    kitchen, door, named
):
    code, said = stops(kitchen, "fl-mine", "--on", "fix-root", door=door)
    assert code == 1
    assert said.startswith(named), said
    assert "a stop carries only a one-way door" in said
    assert "features/home/templates/gates.md" in said
    assert "tell the user directly from this home's own thread" in said
    assert sent(kitchen) == []
    assert stop.load(kitchen.state) == stop.Kept()


@pytest.mark.parametrize(
    "case",
    [
        "deletes data",
        "rewrites history",
        "spends money",
        "touches prod or real users",
        "changes access or secrets",
        "publishes",
    ],
)
def test_a_stop_at_each_one_way_door_of_the_gates_table_is_taken(kitchen, case):
    code, said = stops(kitchen, "fl-mine", "--on", "fix-root", door=("--holds", case))
    assert (code, said) == (
        0,
        f"stopped: stop|flow|fl-mine|fix-root, sent to the root home at {ROOT}\n",
    )
    assert f"stopped at a one-way door, {case}." in texts(kitchen)[0]


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
    answer = texts(kitchen)[1]
    assert "on fl-mine: rebase on main once fix-root merges" in answer
    assert "as the root's recommendation, to your own gate for the door" in answer
    kitchen.poll()
    assert sent(kitchen) == [(ROOT, "stop"), (FLOW, "stop-answer")]
    code, said = answers(kitchen, "again")
    assert (code, said) == (1, "refused: the flow home has no open stop on fl-mine\n")
    assert stops(kitchen, "fl-mine", "--on", "fix-root")[0] == 0
    assert sent(kitchen)[-1] == (ROOT, "stop")


def test_one_answer_to_a_row_held_twice_closes_both_stops_and_reaches_the_scope_once(kitchen):
    assert stops(kitchen, "fl-mine", "--on", "fix-root")[0] == 0
    assert stops(kitchen, "fl-mine", "--on", "vw-board")[0] == 0
    code, said = answers(kitchen, "both", "clear", "today")
    assert (code, said) == (
        0,
        "answered: stop|flow|fl-mine|fix-root, stop|flow|fl-mine|vw-board, closed, the answer "
        f"sent to {FLOW}\n",
    )
    kitchen.poll()
    assert sent(kitchen) == [(ROOT, "stop"), (ROOT, "stop"), (FLOW, "stop-answer")]
    assert [one.closed for one in stop.load(kitchen.state).stops] == ["answered", "answered"]


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
    (one,) = stop.load(kitchen.state).stops
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
    assert (code, said.endswith(f"sent to nobody yet, {stop.HELD}\n")) == (0, True), said
    assert sent(kitchen) == []


def tells(kitchen, *text, to=SCOPE, by=ROOT):
    return kitchen.main("tell", to, *text, "--from", by)


def test_the_roots_tell_reaches_the_scope_once_signed_as_the_roots_and_not_the_users(kitchen):
    code, said = tells(kitchen, "rebase", "fl-mine", "before", "you", "start")
    assert (code, said) == (0, f"told: flow, sent to {FLOW}\n")
    assert sent(kitchen) == [(FLOW, "tell")]
    (text,) = texts(kitchen)
    assert text.startswith("jbus: the root home's own message to the flow home")
    assert "not the user's word" in text
    assert "rebase fl-mine before you start" in text
    kitchen.poll()
    kitchen.poll()
    assert sent(kitchen) == [(FLOW, "tell")]
    logged = [json.loads(line) for line in (kitchen.state / "outbox.jsonl").open()]
    (told,) = [one for one in logged if one["template"] == "tell"]
    assert (told["needs"], told["went"]) == ("act", "sent")


def test_a_tell_to_every_scope_keeps_one_record_for_each_and_sends_each_once(kitchen):
    code, said = tells(kitchen, "pause", "new", "rows", to="every")
    assert (code, said) == (0, f"told: flow, sent to {FLOW}\ntold: view, sent to {VIEW}\n")
    kitchen.poll()
    assert sent(kitchen) == [(FLOW, "tell"), (VIEW, "tell")]
    assert [(one.scope, one.text) for one in stop.load(kitchen.state).tells] == [
        (SCOPE, "pause new rows"),
        (OTHER, "pause new rows"),
    ]


def test_the_same_tell_again_is_held_and_sent_no_second_time(kitchen):
    assert tells(kitchen, "pause", "new", "rows")[0] == 0
    code, said = tells(kitchen, "pause  new", "rows")
    assert (code, said) == (0, "held: flow, it already has this message from the root\n")
    assert sent(kitchen) == [(FLOW, "tell")]
    assert len(stop.load(kitchen.state).tells) == 1


@pytest.mark.parametrize(
    ("to", "text", "by", "why"),
    [
        (SCOPE, ("go",), FLOW, f"refused: --from {FLOW} is not the root home's thread"),
        (SCOPE, ("go",), NEXT, f"refused: --from {NEXT} is not the root home's thread"),
        ("nowhere", ("go",), ROOT, "refused: nowhere is no scoped home of demo"),
        (SCOPE, (), ROOT, "refused: a tell has the root's words"),
    ],
)
def test_a_tell_not_from_the_root_or_to_no_scope_is_refused_and_keeps_nothing(
    kitchen, to, text, by, why
):
    code, said = tells(kitchen, *text, to=to, by=by)
    assert (code, said.startswith(why)) == (1, True), said
    assert sent(kitchen) == []
    assert stop.load(kitchen.state) == stop.Kept()


def test_a_tell_to_a_scope_with_no_home_id_waits_and_goes_on_the_pass_after_its_start(kitchen):
    (kitchen.home / SCOPE / "home-id").unlink()
    code, said = tells(kitchen, "pick", "up", "fl-mine")
    assert (code, said) == (
        0,
        "told: flow, sent to nobody yet, the flow home is not running, its home-id holds no "
        "thread\n",
    )
    kitchen.poll()
    assert sent(kitchen) == []
    (kitchen.home / SCOPE / "home-id").write_text(f"{NEXT}\n")
    kitchen.poll()
    kitchen.poll()
    assert sent(kitchen) == [(NEXT, "tell")]
    assert "pick up fl-mine" in texts(kitchen)[0]


def test_a_stops_file_kept_before_tells_still_parses(kitchen):
    stop.path(kitchen.state).write_text(json.dumps({"stops": [], "answers": []}))
    assert stop.load(kitchen.state) == stop.Kept()
    assert tells(kitchen, "go")[0] == 0


def test_a_tell_to_every_scope_of_a_project_with_none_is_refused(kitchen):
    for scope in (SCOPE, OTHER):
        (kitchen.home / scope / "plan.md").unlink()
        (kitchen.home / scope / "home-id").unlink()
        (kitchen.home / scope).rmdir()
    code, said = tells(kitchen, "go", to="every")
    assert (code, said) == (1, "refused: demo has no scoped home for every\n")
    assert stop.load(kitchen.state) == stop.Kept()
