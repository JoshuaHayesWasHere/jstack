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

import jbus
from jbus import questions, queue, stop, stopverbs
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
    assert "a door stop carries only a one-way door" in said
    assert "features/home/templates/gates.md" in said
    assert "goes to the root as --kind decision" in said
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


ENTRY = "fl-epic"
FLOW_PLAN = f"# a plan\n\n## {ENTRY}: one goal\nStage: planned\nDone when:\n- it lands\n"


def asks(kitchen, kind, *subject, by=FLOW, what=WHAT, extra=()):
    """Run a decision's or a go's stop: `subject` is the own row, or `--entry <entry>`."""
    return kitchen.main("stop", *subject, "--kind", kind, *extra, "--from", by, *what)


def passes(kitchen, *text, scope=SCOPE, subject="fl-mine", by=ROOT):
    return kitchen.main("stop", "pass", scope, subject, *text, "--from", by)


@pytest.fixture
def planned(kitchen):
    (kitchen.home / SCOPE / "plan.md").write_text(FLOW_PLAN)
    return kitchen


@pytest.mark.parametrize("kind", ["decision", "go"])
def test_a_decision_or_a_go_on_the_scopes_own_row_goes_to_the_root_with_no_door(kitchen, kind):
    code, said = asks(kitchen, kind, "fl-mine")
    assert (code, said) == (
        0,
        f"stopped: stop|flow|fl-mine|a {kind}, sent to the root home at {ROOT}\n",
    )
    assert sent(kitchen) == [(ROOT, "stop")]
    (text,) = texts(kitchen)
    assert f"the flow home escalates a {kind} on fl-mine" in text
    assert "the train is red on a root fix" in text
    assert "jbus stop answer flow fl-mine" in text
    assert "jbus stop pass flow fl-mine" in text
    assert "one-way door" not in text
    assert asks(kitchen, kind, "fl-mine")[1] == (
        f"refused: the stop stop|flow|fl-mine|a {kind} is already open, and the root has it\n"
    )


def test_a_go_on_an_entry_of_the_scopes_plan_names_the_roots_standing_go(planned):
    code, said = asks(planned, "go", "--entry", ENTRY)
    assert (code, said) == (
        0,
        f"stopped: stop|flow|entry {ENTRY}|a go, sent to the root home at {ROOT}\n",
    )
    (text,) = texts(planned)
    assert f"the flow home escalates a go on the entry {ENTRY} of its plan" in text
    assert f"jbus plan go {ENTRY} --scope flow --standing --from" in text
    assert f"jbus stop pass flow {ENTRY}" in text


@pytest.mark.parametrize(
    ("subject", "extra", "why"),
    [
        (("fl-mine",), DOOR, "refused: a decision or a go holds for no door"),
        (("fl-mine",), ("--on", "fix-root"), "refused: a decision or a go names no --on"),
        (("fl-mine",), ("--outside", "the disk"), "refused: a decision or a go names no --on"),
        (("vw-board",), (), "refused: vw-board is the view home's row"),
        (("fl-landed",), (), "refused: fl-landed is merged"),
        (("--entry", "nothing-here"), (), "refused: the flow home's plan has no entry"),
    ],
)
def test_a_decision_that_is_not_on_the_scopes_own_open_row_or_entry_is_refused(
    planned, subject, extra, why
):
    code, said = asks(planned, "decision", *subject, extra=extra)
    assert (code, said.startswith(why)) == (1, True), said
    assert sent(planned) == []
    assert stop.load(planned.state) == stop.Kept()


def test_a_door_on_an_entry_is_refused_since_a_door_keeps_todays_checks(planned):
    code, said = planned.main(
        "stop", "--entry", ENTRY, "--on", "fix-root", *DOOR, "--from", FLOW, *WHAT
    )
    assert (code, said) == (1, "refused: a door stop is on the home's own row, not on --entry\n")


def test_a_stop_with_no_door_points_the_home_at_a_decision_for_the_root(kitchen):
    code, said = stops(kitchen, "fl-mine", "--on", "fix-root", door=())
    assert code == 1
    assert "--kind decision" in said
    assert "tell the user directly" not in said


def test_the_roots_answer_to_a_decision_is_its_word_for_the_scope_to_act_on(kitchen):
    assert asks(kitchen, "decision", "fl-mine")[0] == 0
    code, said = answers(kitchen, "take", "the", "smaller", "one")
    assert (code, said) == (
        0,
        f"answered: stop|flow|fl-mine|a decision, closed, the answer sent to {FLOW}\n",
    )
    answer = texts(kitchen)[1]
    assert "answer to the flow home's decision on fl-mine: take the smaller one" in answer
    assert "act on it" in answer
    assert "gate for the door" not in answer


def held(kitchen):
    return [one for one in questions.load(kitchen.state) if one.answer is None]


def test_a_passed_decision_closes_the_stop_and_parks_a_gate_that_holds_for_the_user(kitchen):
    assert asks(kitchen, "decision", "fl-mine")[0] == 0
    code, said = passes(kitchen, "the", "smaller", "one")
    (gate,) = held(kitchen)
    assert (code, said) == (
        0,
        f"passed: stop|flow|fl-mine|a decision, closed, question {gate.number} holds for the "
        f"user, and the flow home is told at {FLOW}\n",
    )
    assert [one.closed for one in stop.load(kitchen.state).stops] == ["passed"]
    assert gate.slug == f"home-{SCOPE}"
    assert gate.question.startswith("the train is red on a root fix (decision on fl-mine")
    assert gate.holds == stop.PASSED
    assert "the root recommends: the smaller one" in gate.default
    told = texts(kitchen)[1]
    assert f"passed the flow home's decision on fl-mine to the user, as question {gate.number}" in (
        told
    )
    kitchen.poll()
    kitchen.poll()
    assert [one.number for one in held(kitchen)] == [gate.number]
    code, out = kitchen.main("needs")
    assert code == 0, out
    assert f"question {gate.number}: the train is red on a root fix" in out
    assert f"it holds ({stop.PASSED}) for your answer" in out
    assert passes(kitchen)[1] == "refused: the flow home has no open decision or go on fl-mine\n"


def test_a_passed_go_on_an_entry_parks_its_gate_on_the_scopes_own_slug(planned):
    assert asks(planned, "go", "--entry", ENTRY)[0] == 0
    code, said = passes(planned, subject=ENTRY)
    assert code == 0, said
    (gate,) = held(planned)
    assert (gate.slug, gate.holds) == (f"home-{SCOPE}", stop.PASSED)
    assert "nothing is done on it until you answer" in gate.default
    planned.poll()
    code, out = planned.main("needs", "--home", str(planned.home / SCOPE))
    assert f"question {gate.number}:" in out, out


def test_only_the_root_passes_and_a_door_stop_is_never_passed(kitchen):
    assert asks(kitchen, "decision", "fl-mine")[0] == 0
    code, said = passes(kitchen, by=FLOW)
    assert (code, said.startswith(f"refused: --from {FLOW} is not the root home's thread")) == (
        1,
        True,
    )
    assert stops(kitchen, "fl-sibling", "--on", "fix-root")[0] == 0
    code, said = passes(kitchen, subject="fl-sibling")
    assert (code, said) == (
        1,
        "refused: the flow home has no open decision or go on fl-sibling: a door stop is the "
        "user's already, through the home's own gate, so answer it\n",
    )
    assert held(kitchen) == []


@pytest.mark.parametrize("left", ["closed", "archived"])
def test_an_entry_stop_closes_itself_once_the_entry_leaves_the_plan(planned, left):
    assert asks(planned, "go", "--entry", ENTRY)[0] == 0
    if left == "closed":
        (planned.home / SCOPE / "plan.md").write_text("# a plan\n")
    else:
        (planned.home / SCOPE / "plan.md").unlink()
    planned.poll()
    (one,) = stop.load(planned.state).stops
    assert one.closed == "closed"
    assert sent(planned) == [(ROOT, "stop")]


def test_the_users_answer_to_a_passed_decision_reaches_the_scope_once(kitchen):
    from test_jbus_acts import REF, now

    assert asks(kitchen, "decision", "fl-mine")[0] == 0
    assert passes(kitchen, "the", "smaller", "one")[0] == 0
    (gate,) = held(kitchen)
    now(kitchen, f"question {gate.number}: take the bigger one")
    code, said = kitchen.main(
        "--as", "user", "answer", str(gate.number), "--differs", "--message", REF
    )
    assert code == 0, said
    kitchen.poll()
    kitchen.poll()
    assert sent(kitchen) == [(ROOT, "stop"), (FLOW, "stop-answer"), (FLOW, "stop-answer")]
    told = texts(kitchen)[-1]
    assert f"the user answered question {gate.number}, the flow home's decision on fl-mine" in told
    assert "take the bigger one" in told


def test_the_gate_of_a_passed_stop_clears_once_its_row_merges(kitchen):
    assert asks(kitchen, "decision", "fl-mine")[0] == 0
    assert passes(kitchen)[0] == 0
    (gate,) = held(kitchen)
    status(kitchen, "fl-mine", "merged")
    kitchen.poll()
    assert held(kitchen) == []
    cleared = questions.question(kitchen.state, gate.number).answer
    assert (cleared.closed_by, cleared.words) == ("cleared", "the stop's row fl-mine is merged")
    kitchen.poll()
    assert sent(kitchen) == [(ROOT, "stop"), (FLOW, "stop-answer")]


@pytest.mark.parametrize(
    ("argv", "why"),
    [
        (("stop", "answer", SCOPE, "fl-mine", "--from", ROOT), "refused: an answer is jbus stop"),
        (("stop", "pass", SCOPE, "--from", ROOT), "refused: an answer is jbus stop"),
        (("stop", "pass", SCOPE, "fl-mine", "--kind", "go", "--from", ROOT), "refused: an answer"),
        (("stop", "--kind", "decision", "--from", FLOW), "refused: a stop is on this home's own"),
        (("stop", "answer", SCOPE, "fl-mine", " ", "--from", ROOT), "refused: an answer has the"),
    ],
)
def test_a_reply_or_a_stop_the_verb_cannot_read_is_refused(kitchen, argv, why):
    code, said = kitchen.main(*argv)
    assert (code, said.startswith(why)) == (1, True), said
    assert sent(kitchen) == []


def test_a_stop_taken_with_no_sign_in_waits_for_a_pass_that_has_one(kitchen):
    token = jbus.load().token_path
    kept = token.read_text()
    token.unlink()
    code, said = asks(kitchen, "decision", "fl-mine")
    assert (code, said) == (
        0,
        "stopped: stop|flow|fl-mine|a decision, sent to nobody yet, jbus is not signed in to "
        "T3 Code\n",
    )
    token.write_text(kept)
    token.chmod(0o600)
    kitchen.poll()
    assert sent(kitchen) == [(ROOT, "stop")]


def test_a_stops_json_that_does_not_parse_raises_a_gate_and_the_pass_goes_on(kitchen):
    stop.path(kitchen.state).write_text("not json")
    kitchen.poll()
    assert kitchen.lines("condition") == ["condition demo: stops.json does not parse"]
    assert stopverbs.VERBS[0].name == "stop"
