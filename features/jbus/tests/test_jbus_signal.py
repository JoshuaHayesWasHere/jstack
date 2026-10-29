"""jbus decides which events are worth telling the user. Each event kind has one loudness, and an
event wakes no thread: a home hears only of the open items of the one list. When a failure
repeats, jbus raises it once as an open item with an owner, and logs its end, `recovered`, as a
quiet event that asks the user nothing. This kitchen has no infra project, so an alert of the
machine's goes to the desk alone.

Every test runs the real pass, the real command or the real `alert` functions against the faked T3
Code server of `test_jbus_kitchen`. Nothing reaches the network.
"""

import ast
import json
import pathlib
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest

import jbus
import jsettings
from jbus import alert, alive, item, passes, poll, wake
from test_jbus_kitchen import ASK, NOW, REFUSED
from test_jbus_kitchen import HOME as HOME_THREAD
from test_jbus_wake_failing import OWNED, refusing

SRC = pathlib.Path(jbus.__file__).parent
GATE = ASK


def decide(kitchen):
    """Log one decision, as `jbus decide` does."""
    config = jbus.load()
    wake.Box(kitchen.state, config.project("demo")).send(
        "alpha", "decision", "decision alpha: which one?"
    )


ET = jsettings.Settings(zone=ZoneInfo("America/New_York"), label="ET")


def later(minutes):
    return NOW + timedelta(minutes=minutes)


def open_lines(kitchen, now=NOW):
    """The line of each open alert, by key."""
    return {one.key: one.line for one in alert.open_items(kitchen.state_dir, now)}


@pytest.fixture
def desk(monkeypatch):
    """What a test outside the kitchen raised on the desk."""
    shown = []
    monkeypatch.setattr(wake, "notify", shown.append)
    return shown


def told(state, key):
    """Raise the alert a streak returned, as a caller of `alert.failed` does."""
    config = jbus.Config.__new__(jbus.Config)
    object.__setattr__(config, "state_dir", state)
    object.__setattr__(config, "projects", ())
    object.__setattr__(config, "infra", jbus.INFRA)
    alert.raise_(config, key, f"alert: {key}", now=NOW)


def streak_lines(kitchen):
    """Every alert and recovered line the log holds, oldest first."""
    return [one["line"] for one in kitchen.events() if one["event"] in ("alert", "recovered")]


def test_every_event_has_its_kind_s_loudness_and_only_a_decision_is_for_the_user():
    made = {
        kind: wake.event("demo", "alpha", kind, f"{kind} alpha: a line") for kind in wake.LOUDNESS
    }
    assert {kind: one["loud"] for kind, one in made.items()} == wake.LOUDNESS
    assert not [one for one in made.values() if "say" in one]
    assert [kind for kind, loud in wake.LOUDNESS.items() if loud == "user"] == ["decision"]
    assert wake.LOUDNESS["alert"] == "quiet" and wake.LOUDNESS["home-stall"] == "quiet"
    assert wake.LOUDNESS["drops"] == "quiet" and wake.LOUDNESS["heartbeat"] == "quiet"
    assert wake.LOUDNESS["stall"] == "quiet" and wake.LOUDNESS["rereview"] == "quiet"
    assert wake.LOUDNESS["gate"] == "quiet" and wake.LOUDNESS["waiting"] == "quiet"
    assert wake.LOUDNESS["merged"] == "quiet" and wake.LOUDNESS["condition"] == "quiet"
    assert wake.LOUDNESS["expedite"] == "quiet" and wake.LOUDNESS["waiting-on-user"] == "quiet"
    lowered = wake.event("demo", "", "waiting", "waiting demo: a line", loud="quiet")
    assert lowered["loud"] == "quiet"


def test_a_level_given_is_held_to_the_kind_s_and_never_raises_it():
    with pytest.raises(KeyError, match="shouting"):
        wake.event("demo", "", "shouting", "shouting: a line", loud="quiet")
    with pytest.raises(ValueError, match="note is quiet"):
        wake.event("demo", "", "note", "note: a line", loud="user")
    with pytest.raises(ValueError):
        wake.event("demo", "", "result", "result: a line", loud="chef")
    assert wake.event("demo", "", "gate", "gate: a line", loud="quiet")["loud"] == "quiet"


def test_a_kind_the_table_does_not_name_is_refused(tmp_path):
    with pytest.raises(KeyError, match="shouting"):
        wake.event("demo", "alpha", "shouting", "a line")
    project = jbus.Project("demo", tmp_path / "checkout", "demo", "project-1", "", "")
    with pytest.raises(KeyError, match="shouting"):
        wake.Box(tmp_path / "state", project).send("alpha", "shouting", "a line")


def test_a_keyed_finding_of_an_unknown_kind_leaves_no_key_so_it_is_refused_again(kitchen):
    run = passes.Pass(jbus.load(), jbus.load().projects[0], NOW)
    run.find("alpha", "result", "result alpha: done")
    before = (kitchen.state / "sent.json").read_text()
    for _ in range(2):
        with pytest.raises(KeyError, match="shouting"):
            run.find("alpha", "shouting", "a line")
    assert (kitchen.state / "sent.json").read_text() == before
    assert [one["event"] for one in kitchen.events()] == ["result"]


PASSED_AS = {
    ("stall.py", "EVENT"): (),
    ("rebase.py", "ask.kind"): (("Ask", 0), ("_asked", 0)),
    ("mirror.py", "what"): (("_found", 0), ("_gates", 1)),
    ("wake.py", "kind"): (),
    ("passes.py", "kind"): (),
    ("item.py", "kind(verb)"): (),
    ("alert.py", "kind"): (("_log", 2),),
}


def sent_kinds(source: pathlib.Path) -> dict[str, set[str]]:
    """Return every kind that a file of jbus sends, named as the sending call names it.

    A call that sends is `<...>.find(slug, kind, ...)`, `<...>.send(slug, kind, ...)`,
    `<...>box.record(kind, ...)` or `event(project, slug, kind, ...)`. A kind is a string, a name
    the module sets to a string, or a name that `PASSED_AS` knows. This refuses any other kind,
    since nothing here could say what it is. `outbox.send` sends a message to a thread, not an
    event, so it has no kind.
    """
    tree = ast.parse(source.read_text())
    constants = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
        for target in node.targets
        if isinstance(target, ast.Name) and isinstance(node.value.value, str)
    }

    def written(name: str, at: int) -> set[str]:
        made = [
            node.args
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == name
        ]
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                made += [inner.elts for inner in ast.walk(node) if isinstance(inner, ast.Tuple)]
        places = [parts[at] for parts in made if len(parts) > at]
        return {one.value for one in places if isinstance(one, ast.Constant)}

    kinds: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", getattr(node.func, "id", ""))
        at = {"find": 1, "send": 1, "event": 2, "record": 0}.get(name)
        if name == "record" and not ast.unparse(getattr(node.func, "value", node)).endswith("box"):
            continue
        if ast.unparse(node.func) == "outbox.send":
            continue
        named = [word.value for word in node.keywords if word.arg == "kind"]
        if at is None or (len(node.args) <= at and not named):
            continue
        kind = named[0] if named else node.args[at]
        said = ast.unparse(kind)
        if isinstance(kind, ast.Constant):
            found = {kind.value}
        elif said in constants:
            found = {constants[said]}
        else:
            where = PASSED_AS.get((source.name, said))
            assert where is not None, f"{source.name}: a kind is passed as `{said}`, unread here"
            found = set().union(*(written(*one) for one in where))
        kinds.setdefault(said, set()).update(found)
    return kinds


def sent_in(directory: pathlib.Path) -> dict[tuple[str, str], set[str]]:
    return {
        (path.name, said): kinds
        for path in sorted(directory.glob("*.py"))
        for said, kinds in sent_kinds(path).items()
    }


def unknown(directory: pathlib.Path) -> set[str]:
    return set().union(*sent_in(directory).values()) - set(wake.LOUDNESS)


def test_every_kind_jbus_sends_is_in_the_table_and_the_table_names_no_other():
    """`word` is the one kind that jbus sends and the table lacks. `word.py` logs it by
    `Box.record`, and `record` does not check the kind against the table."""
    sent = sent_in(SRC)
    assert sent[("stall.py", "EVENT")] == {"waiting-on-user"}
    assert sent[("waiting.py", "EVENT")] == {"waiting"}
    assert sent[("stall.py", "STALL")] == {"stall"}
    assert sent[("expedite.py", "EXPEDITE")] == {"expedite"}
    assert sent[("expedite.py", "STALL")] == {"stall"}
    assert sent[("clock.py", "CLOCK")] == {"clock"}
    assert sent[("clock.py", "STALL")] == {"stall"}
    assert sent[("rebase.py", "ask.kind")] == {
        "rebase",
        "rereview",
        "drops",
        "failed",
        "conflict",
        "refailed",
        "green",
    }
    assert sent[("mirror.py", "what")] == {"result", "review", "report", "gate", "gate answered"}
    assert sent[("wake.py", "kind")] == set()
    assert sent[("passes.py", "kind")] == set()
    assert sent[("passes.py", "CONDITION")] == {"condition"}
    assert sent[("record.py", "'heartbeat'")] == {"heartbeat"}
    assert sent[("item.py", "kind(verb)")] == set()
    every = set().union(*sent.values()) | {item.kind(verb) for verb in item.Verb}
    assert unknown(SRC) == {"word"}
    assert set(wake.LOUDNESS) - every == set()


def test_the_walk_fails_on_a_kind_the_table_lacks_and_on_one_it_cannot_read(tmp_path):
    (tmp_path / "new.py").write_text(
        'def tell(run):\n    run.find("alpha", "shouting", "a line")\n'
    )
    (tmp_path / "old.py").write_text('def tell(run):\n    run.gate_of.find("alpha", "gate", "a")\n')
    assert unknown(tmp_path) == {"shouting"}
    (tmp_path / "new.py").write_text(
        'def tell(run):\n    run.find("alpha", line="a line", kind="yelling")\n'
    )
    assert unknown(tmp_path) == {"yelling"}
    (tmp_path / "odd.py").write_text("def tell(run, kind):\n    run.box.send('alpha', kind, 'a')\n")
    with pytest.raises(AssertionError, match="odd.py: a kind is passed as `kind`"):
        sent_kinds(tmp_path / "odd.py")


def test_a_pass_whose_only_events_are_quiet_posts_nothing_and_the_log_keeps_them(kitchen):
    kitchen.set("jmerge.txt", "wait 7 its check has not passed\n")
    said = kitchen.poll(NOW)
    said += kitchen.poll(later(6))
    kitchen.set("jmerge.txt", "wait 7 its review is not written\n")
    said += kitchen.poll(later(61))
    assert kitchen.wakes.listed == []
    assert not [line for line in said if line.startswith("wakes")]
    assert [(one["event"], one["loud"]) for one in kitchen.events()] == [
        ("jmerge", "quiet"),
        ("jmerge", "quiet"),
    ]


def test_one_gate_that_holds_is_one_line_of_the_one_list_and_not_the_quiet_events_beside_it(
    kitchen,
):
    kitchen.set("jmerge.txt", "wait 7 its check has not passed\n")
    kitchen.poll(NOW)
    assert kitchen.main("gate", "alpha", stdin=GATE)[0] == 0
    safe = "Holds: rewrites history\nFail-safe: a bundle of the old history at ~/old.bundle\n"
    holds = GATE.replace("which one?", "may I rewrite it?")
    holds = holds.replace("Undo: pick the other\n", f"Undo: pick the other\n{safe}")
    assert kitchen.main("gate", "alpha", stdin=holds)[0] == 0
    asked = "question 2: may I rewrite it, it holds (rewrites history) for your answer"
    assert f"wakes demo: told {HOME_THREAD} of {asked}" in kitchen.poll(later(1))
    assert kitchen.wakes.listed == [[asked]]
    (made,) = kitchen.events("decision")
    reply = 'Reply: "demo question 2: default"'
    assert (made["loud"], made["line"]) == ("user", f"decision alpha: {asked}. {reply}")


def test_a_result_piped_to_jbus_done_is_logged_and_starts_no_post(kitchen):
    kitchen.poll(NOW)
    assert kitchen.main("done", "alpha", stdin="Status: done\n") == (0, "queued\n")
    assert not [line for line in kitchen.poll(later(1)) if line.startswith("wakes")]
    assert kitchen.wakes.listed == [] and kitchen.lines("result") == ["result alpha: Status: done"]


def test_the_third_failure_in_a_row_alerts_once_and_the_first_success_recovers_once(tmp_path, desk):
    def fail(minute):
        return alert.failed(tmp_path, "pass", "it broke", now=later(minute), user=ET)

    assert [fail(0), fail(5)] == [None, None]
    assert fail(10) == "alert: pass failed 3 times in a row since 11:00 ET: it broke"
    told(tmp_path, "pass")
    assert [fail(15), fail(20)] == [None, None]
    kept = alert.Streak("pass", 5, NOW.isoformat(), True, line="alert: pass", why="it broke")
    assert alert.streak(tmp_path, "pass") == kept
    assert jbus.read_json(tmp_path / "streaks.json", {}) == {
        "pass": {
            "key": "pass",
            "count": 5,
            "since": NOW.isoformat(),
            "alerted": True,
            "owner": alert.MACHINE,
            "line": "alert: pass",
            "ends": "",
            "why": "it broke",
        }
    }
    assert alert.ok(tmp_path, "pass", user=ET) == "recovered: pass after 5 failures since 11:00 ET"
    alert.retire(tmp_path, "pass")
    assert alert.ok(tmp_path, "pass", user=ET) is None and alert.streak(tmp_path, "pass") is None
    assert [fail(30), fail(35), alert.ok(tmp_path, "pass", user=ET), fail(40), fail(45)] == [
        None
    ] * 5
    assert fail(50) == "alert: pass failed 3 times in a row since 11:40 ET: it broke"


def test_a_streak_is_its_key_s_own_and_the_threshold_can_be_given(tmp_path, desk):
    assert alert.failed(tmp_path, "jmerge demo", "no", after=1, now=NOW, user=ET) == (
        "alert: jmerge demo failed 1 times in a row since 11:00 ET: no"
    )
    told(tmp_path, "jmerge demo")
    assert alert.failed(tmp_path, "home thread demo", "no", now=NOW, user=ET) is None
    assert alert.ok(tmp_path, "home thread demo", user=ET) is None
    assert (
        alert.ok(tmp_path, "jmerge demo", user=ET)
        == "recovered: jmerge demo after 1 failures since 11:00 ET"
    )


def test_a_line_is_owed_until_it_is_raised_so_one_that_was_never_raised_is_given_again(
    tmp_path, desk
):
    def fail(minute):
        return alert.failed(tmp_path, "pass", "it broke", now=later(minute), user=ET)

    assert [fail(0), fail(1)] == [None, None]
    assert fail(2) == "alert: pass failed 3 times in a row since 11:00 ET: it broke"
    assert fail(3) == "alert: pass failed 4 times in a row since 11:00 ET: it broke"
    told(tmp_path, "pass")
    assert fail(4) is None
    recovered = "recovered: pass after 5 failures since 11:00 ET"
    assert [alert.ok(tmp_path, "pass", user=ET), alert.ok(tmp_path, "pass", user=ET)] == [
        recovered,
        recovered,
    ]
    alert.retire(tmp_path, "pass")
    assert alert.ok(tmp_path, "pass", user=ET) is None and alert.streak(tmp_path, "pass") is None


def test_an_alarm_that_cannot_raise_its_alert_alerts_again_on_the_next_one(kitchen, monkeypatch):
    """The test stops the third alarm where it raises the line, as a kill stops a process."""
    alarm(NOW), alarm(later(1))
    with monkeypatch.context() as stopped:
        stopped.setattr(alert, "raise_", lambda *_, **__: (_ for _ in ()).throw(KeyboardInterrupt))
        with pytest.raises(KeyboardInterrupt):
            alive.alarm(jbus.load(), later(2), lambda _: None)
    assert open_lines(kitchen) == {}
    assert jbus.read_json(kitchen.state_dir / "streaks.json", {})["pass"]["alerted"] is False
    fourth = PASS.replace("3 times", "4 times")
    assert alarm(later(3)) == ["pass failed: 4 in a row", fourth]
    assert open_lines(kitchen) == {"pass": fourth}
    assert alarm(later(4)) == ["pass failed: 5 in a row"]
    assert kitchen.log("notify") == [f"jbus | {fourth}"]


def test_a_recovery_that_could_not_be_written_is_owed_to_the_next_pass(kitchen, monkeypatch):
    for minute in range(3):
        alarm(later(minute))
    end = alert.end
    with monkeypatch.context() as broken:
        broken.setattr(alert, "end", lambda *_, **__: (_ for _ in ()).throw(OSError("full")))
        said = []
        poll.poll(jbus.load(), later(10), said.append)
    assert kitchen.status()["streaks"]["pass"]["alerted"] is True
    assert alert.end is end
    said = kitchen.poll(later(11))
    assert "recovered: pass after 3 failures since 11:00 ET" in said
    assert kitchen.status()["streaks"] == {} and open_lines(kitchen, later(11)) == {}


def test_jbus_status_prints_the_streaks_as_they_are_and_not_as_the_last_pass_left_them(kitchen):
    kitchen.poll(NOW)
    assert kitchen.status()["streaks"] == {}
    for minute in range(1, 4):
        alarm(later(minute))
    code, printed = kitchen.main("status")
    printed = json.loads(printed)
    del printed["pass"]
    (streak,) = printed.pop("streaks").values()
    assert code == 0 and printed == {
        key: value for key, value in kitchen.status().items() if key != "streaks"
    }
    assert (streak["key"], streak["count"], streak["alerted"]) == ("pass", 3, True)
    assert kitchen.status()["streaks"] == {}


def test_a_later_streak_that_makes_the_same_lines_is_raised_again(kitchen):
    """The line has the minute and no day, so the same streak a day later makes the same text."""
    said = []
    for day in range(2):
        for minute in range(3):
            said += alarm(later(24 * 60 * day + minute))
        said += kitchen.poll(later(24 * 60 * day + 10))
    recovered = "recovered: pass after 3 failures since 11:00 ET"
    assert [line for line in said if line in (PASS, recovered)] == [PASS, recovered] * 2
    assert kitchen.log("notify") == [f"jbus | {PASS}"] * 2


PASS = (
    "alert: pass failed 3 times in a row since 11:00 ET: "
    "the last pass did not finish (see journalctl --user -u jbus)"
)


def alarm(now):
    said = []
    assert alive.alarm(jbus.load(), now, said.append) == 0
    return said


def test_the_pass_streak_alerts_at_the_third_alarm_on_the_desk_and_a_pass_ends_it(kitchen):
    said = alarm(NOW) + alarm(later(1))
    assert said == ["pass failed: 1 in a row", "pass failed: 2 in a row"]
    assert kitchen.events() == [] and open_lines(kitchen) == {}
    said = alarm(later(2)) + alarm(later(3)) + alarm(later(60))
    assert said == [
        "pass failed: 3 in a row",
        PASS,
        "pass failed: 4 in a row",
        "pass failed: 5 in a row",
    ]
    assert open_lines(kitchen, later(60)) == {"pass": PASS}
    said = kitchen.poll(later(65))
    assert "recovered: pass after 5 failures since 11:00 ET" in said
    assert open_lines(kitchen, later(65)) == {} and kitchen.status()["streaks"] == {}
    assert kitchen.wakes.listed == []
    assert kitchen.log("notify") == [f"jbus | {PASS}"]


HOME = (
    "alert: home thread demo failed 3 times in a row since 11:00 ET: "
    f"T3 Code did not take the wake: t3_thread_send: {REFUSED}"
)


def test_the_home_thread_streak_alerts_through_the_desk_and_its_end_is_logged(kitchen):
    refusing(kitchen)
    for number in range(2):
        kitchen.poll(later(5 * number))
    assert (
        kitchen.log("notify") == []
        and open_lines(kitchen, later(5)).get("home thread demo") is None
    )
    for number in range(2, 6):
        kitchen.poll(later(5 * number))
    assert kitchen.log("notify") == [f"jbus | {HOME}"]
    streak = kitchen.status()["streaks"]["home thread demo"]
    assert (streak["count"], streak["since"], streak["alerted"]) == (6, NOW.isoformat(), True)
    assert streak["owner"] == alert.MACHINE
    assert kitchen.status()["projects"]["demo"]["failed_wakes"] == 6
    kitchen.wakes.refused = ""
    said = kitchen.poll(later(30))
    assert "demo: recovered: home thread demo after 6 failures since 11:00 ET" in said
    assert kitchen.wakes.said == [OWNED]
    kitchen.poll(later(35))
    assert kitchen.wakes.said == [OWNED]
    assert kitchen.log("notify") == [f"jbus | {HOME}"]
    assert "home thread demo" not in kitchen.status()["streaks"]


JMERGE = "alert: jmerge demo failed 3 times in a row since 11:00 ET: jmerge: it broke"


def test_the_jmerge_streak_is_the_project_s_own_item_and_ends_when_one_runs(kitchen):
    kitchen.set("jmerge-dies", "jmerge: it broke")
    said = kitchen.poll(NOW) + kitchen.poll(later(1))
    assert said.count("wait demo: jmerge did not run (jmerge: it broke)") == 2
    assert kitchen.lines("alert") == []
    said = kitchen.poll(later(2))
    assert f"wakes demo: told {HOME_THREAD} of {JMERGE}" in said
    assert kitchen.wakes.said == [JMERGE]
    for number in range(3, 9):
        kitchen.poll(later(number))
    assert kitchen.lines("alert") == [JMERGE] and kitchen.wakes.said == [JMERGE]
    (kitchen.stub / "jmerge-dies").unlink()
    kitchen.poll(later(9))
    kitchen.poll(later(10))
    recovered = "recovered: jmerge demo after 9 failures since 11:00 ET"
    assert kitchen.wakes.said == [JMERGE]
    assert streak_lines(kitchen) == [JMERGE, recovered]
    assert kitchen.log("notify") == []


def test_a_list_of_paths_jmerge_cannot_read_is_a_condition_and_no_failure_of_the_streak(kitchen):
    kitchen.set("jmerge-dies", "jmerge: /x/protected.txt cannot be read")
    for number in range(4):
        kitchen.poll(later(number))
    assert kitchen.lines("alert") == [] and kitchen.status()["streaks"] == {}
    assert len(kitchen.lines("condition")) == 1 and kitchen.wakes.listed == []
