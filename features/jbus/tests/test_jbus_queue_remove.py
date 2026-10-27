"""`jbus queue remove` takes a row out of the queue for good: the slug is in `removed.json`, and
no later pass finds anything for it. Like `test_jbus_queue.py`, the tests run the real command
and the real pass against a faked T3 Code server, `gh` and `jmerge`."""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import digest, queue, waiting, wake
from jbus.view import state as view
from test_jbus_blocking import relayed
from test_jbus_kitchen import GATE, NOW, RESULT, Kitchen, Webhook
from test_jbus_kitchen import review as review_of
from test_jbus_queue import add, brief, rows, sha12
from test_jbus_resume import crew, sends
from test_jbus_row_history import transitions

AT = "2026-10-12 10:58 ET"
LATER = NOW + timedelta(minutes=3)
WORD = ("--by", "user", "--at", AT)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    monkeypatch.setattr(queue, "clock", lambda: NOW)
    yield made
    made.close()


def remove(kitchen, slug, *word):
    return kitchen.main("--project", "demo", "queue", "remove", slug, *(word or WORD))


def aside(kitchen, slug, text):
    return kitchen.state / "removed" / f"{slug}.{sha12(text)}.md"


def about(kitchen, slug):
    """Return every event of the slug, and every other event whose line names it."""
    return [one["line"] for one in kitchen.events() if slug in (one["slug"], *one["line"].split())]


def test_remove_takes_the_row_out_logs_it_and_moves_the_stored_brief_aside(kitchen):
    add(kitchen, "alpha", priority=2, approve=False)
    add(kitchen, "beta", approve=False)
    mine = kitchen.brief("alpha", "the home's own copy\n")
    was = rows(kitchen)["alpha"]
    kept = aside(kitchen, "alpha", brief("alpha"))
    code, said = remove(kitchen, "alpha")
    assert code == 0
    assert said.splitlines()[0] == f"removed alpha: was queued, {AT} by user, brief kept at {kept}"
    assert kitchen.main("queue", "show")[1] == "\n".join(said.splitlines()[1:]) + "\n"
    assert list(rows(kitchen)) == ["beta"]
    assert kept.read_text() == brief("alpha")
    assert not (kitchen.state / "briefs" / "alpha.md").exists()
    assert mine.read_text() == "# alpha: a task\nWhere: `src/alpha/`\nthe home's own copy\n"
    assert transitions(kitchen) == [
        {
            "slug": "alpha",
            "from": "queued",
            "to": "removed",
            "at": "2026-10-12T15:00:00+00:00",
            "by": "user",
            "said": AT,
            "row": was,
            "brief": str(kept),
        }
    ]
    assert jbus.read_json(kitchen.state / "removed.json", {}) == {"alpha": {"at": AT, "by": "user"}}
    assert [(one["slug"], one["event"], one["loud"], one["line"]) for one in kitchen.events()] == [
        ("alpha", "queue", "quiet", f"queue demo: removed alpha, {AT} by user")
    ]
    assert kitchen.webhook.posts == [] and kitchen.t3.messages == {}


def ended(kitchen, removed):
    """Make a row whose thread ended with no Result, and run the pass that follows, whether or
    not the test removed the row first."""
    kitchen.quiet()
    add(kitchen, "alpha", approve=False)
    kitchen.brief("alpha")
    kitchen.t3.thread("alpha", "completed")
    if removed:
        assert remove(kitchen, "alpha")[0] == 0
        jbus.write_json(kitchen.state / "outbox.json", [])
    kitchen.poll()
    return kitchen.lines("stale")


def test_a_finished_thread_of_a_row_still_there_is_stale_and_of_a_removed_one_is_not(
    tmp_path, kitchen
):
    assert ended(kitchen, removed=True) == []
    kitchen.close()
    other = Kitchen(tmp_path / "other", kitchen.monkeypatch)
    try:
        assert ended(other, removed=False) == ["stale alpha: thread completed with no Result"]
    finally:
        other.close()


def test_no_pass_after_brings_the_slug_back_from_its_brief_its_thread_or_a_gate(kitchen):
    kitchen.quiet()
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    kitchen.poll()
    listed = {one["key"] for one in jbus.read_json(kitchen.state / "waiting-on-user.json", [])}
    assert listed == {"approve:alpha", "approve:beta"}
    assert remove(kitchen, "alpha")[0] == 0
    told = about(kitchen, "alpha")
    assert told[-1] == f"queue demo: removed alpha, {AT} by user"
    kitchen.webhook.posts.clear()
    own = kitchen.brief(
        "alpha", RESULT + GATE.format(n="<n>", asked="red?", status="open", slug="-")
    )
    (kitchen.home / "gates.md").write_text(
        GATE.format(n=4, asked="blue or green?", status="open", slug="alpha")
        + GATE.format(n=5, asked="left or right?", status="open", slug="beta")
    )
    kitchen.t3.thread("alpha", "completed")
    before = own.read_text()
    for now in (LATER, LATER + timedelta(minutes=3)):
        kitchen.poll(now)
    assert about(kitchen, "alpha") == told
    assert kitchen.lines("gate") == ["gate beta: left or right?"]
    assert sends(kitchen) == [] and own.read_text() == before
    shown = kitchen.main("queue", "show")[1]
    assert "alpha" not in shown and "approve beta" in shown
    kept = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    assert sorted(one["key"].partition(":")[0] for one in kept) == ["approve", "gate"]
    assert "alpha" not in json.dumps(kept)
    built = digest.build(jbus.load(), now=LATER)["projects"]["demo"]
    assert "alpha" not in json.dumps({name: built[name] for name in ("rows", "waiting", "pulls")})
    sources = view.Sources(state_dir=kitchen.state_dir, home_dir=kitchen.root / "home")
    page = view.build(sources, "demo", LATER, lambda _: {"runs": [], "at": None})
    feed = page["bus"].pop("events")
    assert [one["line"] for one in feed if one["slug"] == "alpha"] == told
    assert "alpha" not in json.dumps({name: page[name] for name in ("tasks", "waiting", "gates")})
    assert [one["number"] for one in page["gates"]] == ["5"]


def test_the_waiting_list_drops_a_removed_row_at_once_and_sends_no_event_for_it(kitchen):
    kitchen.quiet()
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    assert "approve alpha" in kitchen.main("queue", "show")[1]
    assert remove(kitchen, "alpha")[0] == 0
    assert "alpha" not in kitchen.main("queue", "show")[1]
    kitchen.webhook.posts.clear()
    kitchen.poll(LATER)
    assert kitchen.webhook.posts == [] and kitchen.t3.messages == {}
    listed, removed = kitchen.lines()
    assert listed == "waiting demo: 1 wait on user, 1 new (approve alpha), 0 gone"
    assert removed == f"queue demo: removed alpha, {AT} by user"


def test_a_removal_that_lands_during_a_pass_raises_no_approve_decision(kitchen, monkeypatch):
    kitchen.quiet()
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    kept = waiting.keep

    def removed_first(*args, **kwargs):
        assert remove(kitchen, "alpha")[0] == 0
        return kept(*args, **kwargs)

    monkeypatch.setattr(waiting, "keep", removed_first)
    kitchen.poll()
    monkeypatch.setattr(waiting, "keep", kept)
    kitchen.poll(LATER)
    assert [line.split(":")[0] for line in kitchen.lines("decision")] == ["decision beta"]
    listed = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    assert [one["key"] for one in listed] == ["approve:beta"]


@pytest.mark.parametrize("emptied", [True, False], ids=["empty", "missing"])
def test_a_row_whose_brief_is_missing_or_empty_raises_no_approve_decision(kitchen, emptied):
    second = Webhook()
    try:
        relayed(kitchen, second)
        add(kitchen, "alpha", approve=False)
        add(kitchen, "beta", approve=False)
        stored = kitchen.state / "briefs" / "alpha.md"
        stored.write_text("") if emptied else stored.unlink()
        kitchen.poll(LATER)
        kitchen.poll(LATER + timedelta(minutes=1))
        assert [line.split(":")[0] for line in kitchen.lines("decision")] == ["decision beta"]
        listed = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
        assert [one["key"] for one in listed] == ["approve:beta"]
        (opened,) = second.bodies
        assert sorted(one["key"] for one in opened["items"]) == ["approve:beta", "brief:alpha"]
    finally:
        second.close()


def test_a_removed_rows_thread_that_failed_is_not_told_to_carry_on(kitchen):
    crew(kitchen)
    assert remove(kitchen, "alpha")[0] == 0
    kitchen.poll()
    assert sends(kitchen) == [] and kitchen.lines("resume") == []


@pytest.mark.parametrize(
    "scene, says",
    [
        ("depended", "refused: beta, gamma wait on alpha: remove them first"),
        ("running", "refused: alpha is out: its thread mcp:thread-1 is running"),
        ("open", "refused: alpha is out: its pull request #9 is open"),
        ("merged", "refused: alpha merged as #9, and a merged row stays"),
        ("none", "refused: the queue has no row nope"),
        ("other", "refused: alpha launched, and only user removes a row that launched, not Chef"),
        ("when", 'refused: --at is "<YYYY-MM-DD HH:MM ET>"'),
        ("silent", "refused: T3 Code could not be asked whether alpha's thread is out"),
        (
            "github",
            "refused: GitHub could not be asked whether alpha has a pull request"
            ": gh exited 1: HTTP 502: Bad Gateway",
        ),
    ],
)
def test_a_row_that_is_out_merged_or_waited_on_is_refused_and_nothing_changes(kitchen, scene, says):
    add(kitchen, "alpha", approve=False)
    slug, word = "alpha", WORD
    if scene == "depended":
        add(kitchen, "gamma", depends="alpha", approve=False)
        add(kitchen, "beta", depends="alpha,delta", approve=False)
    elif scene == "running":
        kitchen.t3.thread("alpha", "running")
    elif scene == "open":
        kitchen.set("open.json", [kitchen.opened("alpha", 9)])
    elif scene == "merged":
        kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40)])
    elif scene == "none":
        slug = "nope"
    elif scene == "other":
        table = rows(kitchen)
        table["alpha"].update(status="running", thread="mcp:thread-1")
        jbus.write_json(kitchen.state / "queue.json", list(table.values()))
        word = ("--by", "Chef", "--at", AT)
    elif scene == "when":
        word = ("--by", "user", "--at", "yesterday")
    elif scene == "silent":
        (kitchen.config_dir / "t3.json").unlink()
    elif scene == "github":
        (kitchen.stub / "gh-down").write_text("HTTP 502: Bad Gateway\n")
    before = (kitchen.state / "queue.json").read_text()
    code, said = remove(kitchen, slug, *word)
    assert (code, said.splitlines()[0][: len(says)]) == (1, says)
    assert (kitchen.state / "queue.json").read_text() == before
    assert (kitchen.state / "briefs" / "alpha.md").exists()
    assert transitions(kitchen) == [] and kitchen.waiting() == []
    assert not (kitchen.state / "removed.json").exists()


def test_a_thread_that_ended_or_was_settled_stops_no_removal(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.t3.thread("alpha", "completed")
    kitchen.t3.thread("alpha", "running", settled=True)
    kitchen.t3.thread("alpha-two", "running")
    assert remove(kitchen, "alpha")[0] == 0
    assert list(rows(kitchen)) == []


def test_a_row_whose_dependents_are_merged_or_removed_first_is_removed(kitchen):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", depends="alpha", approve=False)
    add(kitchen, "gamma", depends="alpha", approve=False)
    table = rows(kitchen)
    table["gamma"]["status"] = "merged"
    jbus.write_json(kitchen.state / "queue.json", list(table.values()))
    said = f'remove beta --by user --at "{AT}"\nremove alpha --by user --at "{AT}"\n'
    code, said = kitchen.main("queue", "apply", stdin=said)
    assert (code, [line.split(":")[0] for line in said.splitlines()]) == (
        0,
        ["removed beta", "removed alpha"],
    )
    assert list(rows(kitchen)) == ["gamma"]
    assert [one["line"] for one in kitchen.events()] == [
        f"queue demo: removed beta, {AT} by user",
        f"queue demo: removed alpha, {AT} by user",
    ]


def test_a_batch_with_a_remove_that_is_refused_removes_nothing(kitchen):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    kitchen.t3.thread("beta", "waiting")
    before = (kitchen.state / "queue.json").read_text()
    said = f'remove alpha --by user --at "{AT}"\nremove beta --by user --at "{AT}"\n'
    assert kitchen.main("queue", "apply", stdin=said) == (
        1,
        "refused: line 2: beta is out: its thread mcp:thread-1 is waiting, "
        "and nothing in the batch was applied\n",
    )
    assert (kitchen.state / "queue.json").read_text() == before
    assert (kitchen.state / "briefs" / "alpha.md").exists()
    assert transitions(kitchen) == [] and kitchen.waiting() == []
    assert kitchen.main("queue", "apply", stdin="remove alpha --by user\n") == (
        1,
        "refused: line 1: remove needs --at, and nothing in the batch was applied\n",
    )


def test_a_removed_slug_is_not_added_again_and_says_who_removed_it(kitchen):
    add(kitchen, "alpha", approve=False)
    assert remove(kitchen, "alpha")[0] == 0
    gone = f"alpha was removed {AT} by user"
    code, said = kitchen.main("queue", "add", "alpha", "--priority", "1", stdin=brief("alpha"))
    assert (code, said) == (1, f"refused: {gone}, and a removed slug is not added again\n")
    assert remove(kitchen, "alpha") == (1, f"refused: the queue has no row alpha: {gone}\n")
    assert kitchen.main("queue", "hold", "alpha") == (
        1,
        f"refused: the queue has no row alpha: {gone}\n",
    )
    assert list(rows(kitchen)) == []


def test_a_removal_that_died_before_the_table_was_written_is_still_a_removal(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta", priority=2, approve=False)
    jbus.write_json(kitchen.state / "removed.json", {"alpha": {"at": AT, "by": "user"}})
    assert "alpha" not in kitchen.main("queue", "show")[1]
    kitchen.poll()
    assert kitchen.t3.launches == [] and about(kitchen, "alpha") == []
    gone = f"refused: the queue has no row alpha: alpha was removed {AT} by user\n"
    assert remove(kitchen, "alpha") == (1, gone)
    assert kitchen.main("queue", "hold", "beta")[0] == 0
    assert list(rows(kitchen)) == ["beta"] and transitions(kitchen) == []


@pytest.mark.parametrize("written", ["{", "[]", '{"alpha": "gone"}'])
def test_a_removed_json_that_does_not_parse_stops_every_verb_and_launch_and_is_kept(
    kitchen, written
):
    kitchen.quiet()
    add(kitchen, "beta", priority=2, approve=False)
    kitchen.poll()
    kitchen.forget()
    add(kitchen, "alpha")
    file = kitchen.state / "removed.json"
    file.write_text(written)
    said = f"refused: {file} does not parse"
    assert remove(kitchen, "beta") == (1, f"{said}, and nothing writes it\n")
    assert kitchen.main("queue", "hold", "alpha") == (1, f"{said}, and nothing writes it\n")
    assert kitchen.main("queue", "show") == (1, f"{said}\n")
    kitchen.brief("gamma", RESULT)
    kitchen.t3.thread("gamma", "completed")
    kitchen.t3.thread("delta", "interrupted")
    (kitchen.home / "gates.md").write_text(
        GATE.format(n=4, asked="blue or green?", status="open", slug="gamma")
    )
    listed = (kitchen.state / "waiting-on-user.json").read_text()
    kitchen.poll()
    assert kitchen.t3.launches == [] and sends(kitchen) == []
    assert kitchen.lines() == ["condition demo: removed.json does not parse"]
    assert (kitchen.state / "waiting-on-user.json").read_text() == listed
    assert file.read_text() == written and sorted(rows(kitchen)) == ["alpha", "beta"]


def test_a_row_a_pass_launches_while_remove_asks_what_is_out_is_refused(kitchen):
    add(kitchen, "alpha", approve=False)
    record = kitchen.state_dir / "launches" / "demo" / "alpha" / "0123456789ab.json"

    def launch():
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text('{"state": "launched", "thread": "mcp:a-thread"}')

    kitchen.t3.on_list = launch
    assert remove(kitchen, "alpha") == (
        1,
        "refused: alpha is out: a pass launched it just now\n",
    )
    kitchen.t3.on_list = None
    assert list(rows(kitchen)) == ["alpha"] and not (kitchen.state / "removed.json").exists()


def test_a_row_whose_launch_t3_code_has_not_answered_is_refused(kitchen):
    add(kitchen, "alpha", approve=False)
    record = kitchen.state_dir / "launches" / "demo" / "alpha" / "0123456789ab.json"
    record.parent.mkdir(parents=True)
    record.write_text('{"state": "intent"}')
    assert remove(kitchen, "alpha") == (
        1,
        f"refused: alpha is out: its launch has no answer yet ({record})\n",
    )
    assert list(rows(kitchen)) == ["alpha"]


def test_a_removal_whose_event_cannot_be_queued_is_a_removal_with_its_brief_aside(kitchen):
    add(kitchen, "alpha", approve=False)
    kept = aside(kitchen, "alpha", brief("alpha"))

    def full(*_, **__):
        raise OSError("no space left")

    kitchen.monkeypatch.setattr(wake.Box, "send", full)
    with pytest.raises(OSError):
        remove(kitchen, "alpha")
    kitchen.monkeypatch.undo()
    assert kept.read_text() == brief("alpha")
    assert [(one["slug"], one["brief"]) for one in transitions(kitchen)] == [("alpha", str(kept))]
    assert not (kitchen.state / "briefs" / "alpha.md").exists()


def test_a_slug_that_was_removed_is_not_depended_on_again(kitchen):
    add(kitchen, "alpha", approve=False)
    assert remove(kitchen, "alpha")[0] == 0
    argv = ["queue", "add", "beta", "--priority", "1", "--depends", "alpha"]
    assert kitchen.main(*argv, stdin=brief("beta")) == (
        1,
        f"refused: beta cannot depend on alpha: alpha was removed {AT} by user\n",
    )
    assert list(rows(kitchen)) == []


def test_findings_of_a_pull_request_opened_later_reach_its_crew_once(kitchen):
    kitchen.quiet()
    add(kitchen, "alpha", approve=False)
    assert remove(kitchen, "alpha")[0] == 0
    review = review_of("findings", "not sent, jbus tells the crew when it owes a line")
    kitchen.brief("alpha", "Thread: mcp:a-crew\n" + RESULT + review)
    kitchen.set("open.json", [kitchen.opened("alpha", 9)])
    for now in (NOW, LATER):
        kitchen.poll(now)
    assert [one["threadId"] for one in sends(kitchen)] == ["mcp:a-crew"]
    assert about(kitchen, "alpha") == [f"queue demo: removed alpha, {AT} by user"]


def asked(kitchen, words="red?"):
    """Pipe a question from alpha to `jbus gate`, with its thread in the home's brief."""
    kitchen.brief("alpha", "Thread: mcp:a-crew\n")
    asks = GATE.format(n="<n>", asked=words, status="open", slug="alpha")
    assert kitchen.main("gate", "alpha", stdin=asks) == (0, "queued: question 1\n")


def test_a_removed_slug_asks_nothing_and_its_open_question_is_on_no_list(kitchen):
    kitchen.quiet()
    add(kitchen, "alpha", approve=False)
    asked(kitchen)
    assert remove(kitchen, "alpha")[0] == 0
    kitchen.forget()
    kept = (kitchen.state / "questions.json").read_text()
    asks = GATE.format(n="<n>", asked="blue?", status="open", slug="alpha")
    assert kitchen.main("gate", "alpha", stdin=asks) == (
        1,
        f"refused: alpha was removed {AT} by user, and a removed slug asks nothing\n",
    )
    assert (kitchen.state / "questions.json").read_text() == kept
    kitchen.poll()
    assert about(kitchen, "alpha") == []
    assert "alpha" not in (kitchen.state / "waiting-on-user.json").read_text()
    assert "red?" not in kitchen.main("queue", "show")[1]


@pytest.mark.parametrize("broken", [False, True])
def test_an_answer_to_a_removed_slugs_question_reaches_no_thread(kitchen, broken):
    kitchen.quiet()
    add(kitchen, "alpha", approve=False)
    asked(kitchen)
    assert kitchen.main("answer", "1", *WORD, "--differs", "green")[0] == 0
    assert remove(kitchen, "alpha")[0] == 0
    if broken:
        (kitchen.state / "removed.json").write_text("{")
    for now in (NOW, LATER):
        kitchen.poll(now)
    assert sends(kitchen) == []
