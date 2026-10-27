"""The user's go is given to a plan entry once, and each row filed under it is approved by rule.

`jbus plan go <entry> --message <thread>/<message>` keeps the user's own message as the go of the
entry, bound to its head (its heading and its `Done when:` lines). Under the setting `go = "entry"`,
the default, jbus approves a row queued with `--entry <entry>` when it is queued and on each pass,
an edit of its brief too, while the go holds. The go stops holding when the head changes, when the
entry closes, or on `jbus plan stop`. A row whose brief names a case of `gates.md` on a `Holds:`
line waits for the user under every setting.

Under `go = "silence"`, a home parks its pick for a row as a gate whose default is `approve`. The
gate stays open for `go_quiet_minutes`, and its close by silence approves a row of size S or M with
one pull request. The tests run the real commands and the real pass against the kitchen's fakes.
"""

import json
from datetime import datetime, timedelta

import pytest

import jbus
from jbus import questions, queue
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import brief, rows, widened

HOME, MESSAGE = "mcp:a-home", "a-go-of-his"
HEARD_AT = "2026-10-12 10:30 ET"
PLAN = """\
# demo: plan

## epic: one path for each fact
Stage: planned
Size: M
Done when:
- it works
Decisions:
- "go on it"

## other: another entry
Stage: planned
Done when:
- it also works
"""
GATE = (
    "## Gate <n>: start {slug}?\nStatus: open\nAsked by: home, thread mcp:a-home\n"
    "Default: approve\nBuilt on it: nothing yet\nUndo: hold the row\n"
    "Option: start it (default, recommended): the row launches\nOption: wait: it waits\n"
)


class Frozen(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


@pytest.fixture
def kitchen(tmp_path, monkeypatch, jstack_config):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "plan.md").write_text(PLAN)
    monkeypatch.setattr(questions, "datetime", Frozen)
    made.settings = jstack_config
    yield made
    made.close()


def queued(kitchen, slug, entry="epic", text=None):
    argv = ["queue", "add", slug, "--priority", "1", *(["--entry", entry] if entry else [])]
    code, said = kitchen.main(*argv, stdin=text or brief(slug))
    assert code == 0, said
    return said


def plan_go(kitchen, entry="epic", message=MESSAGE, **more):
    kitchen.t3.says(HOME, message, "go on the epic", **more)
    return kitchen.main("plan", "go", entry, "--message", f"{HOME}/{message}")


def basis(kitchen, slug):
    """Return the basis and the reference of the row's go, or nothing for a row with none."""
    row = rows(kitchen)[slug]
    made = row.get("approval") or {}
    return (made.get("basis"), made.get("ref")) if row["approved"] else ()


def launched(kitchen, slug, status="running"):
    table = kitchen.state / "queue.json"
    listed = json.loads(table.read_text())
    for row in listed:
        if row["slug"] == slug:
            row.update(status=status, thread=f"mcp:crew-{slug}")
    table.write_text(json.dumps(listed))


def test_an_entry_go_approves_each_row_filed_under_it_and_an_edit_with_no_second_word(kitchen):
    code, said = plan_go(kitchen)
    assert code == 0, said
    assert said.startswith("went epic: your go for the plan entry epic, 2026-10-12 10:30 ET")
    assert "approved alpha" in queued(kitchen, "alpha")
    queued(kitchen, "beta")
    queued(kitchen, "gamma", entry="other")
    assert basis(kitchen, "alpha") == basis(kitchen, "beta") == (queue.ENTRY, "epic")
    assert basis(kitchen, "gamma") == ()
    made = rows(kitchen)["alpha"]["approval"]
    assert (made["message"], made["words"], made["said_at"]) == (
        f"{HOME}/{MESSAGE}",
        "go on the epic",
        HEARD_AT,
    )
    assert rows(kitchen)["alpha"]["approved"].startswith(
        f"your go for the plan entry epic, {HEARD_AT}, in home: demo; run "
    )
    queued(kitchen, "alpha", text=widened("alpha"))
    assert basis(kitchen, "alpha") == (queue.ENTRY, "epic")
    assert rows(kitchen)["alpha"]["brief_sha"] == queue.brief_sha(widened("alpha"))
    code, said = kitchen.main("plan")
    assert code == 0, said
    (line,) = [one for one in said.splitlines() if one.startswith("epic |")]
    assert line.endswith(f"| go {HEARD_AT}")
    assert [one for one in said.splitlines() if one.startswith("other |")] == [
        "other | another entry | 0 of 1 merged, 1 queued not approved"
    ]


def test_a_row_queued_before_the_go_is_approved_on_the_next_pass(kitchen):
    queued(kitchen, "alpha")
    assert basis(kitchen, "alpha") == ()
    assert plan_go(kitchen)[0] == 0
    kitchen.poll()
    assert basis(kitchen, "alpha") == (queue.ENTRY, "epic")
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]


def test_a_message_that_is_not_the_users_own_gives_no_go(kitchen):
    code, said = plan_go(kitchen, createdBy="agent", creationSource="agent", type="agent_message")
    assert code == 1 and said.startswith(f"refused: message {HOME}/{MESSAGE} is not user's own")
    queued(kitchen, "alpha")
    assert basis(kitchen, "alpha") == ()


def test_a_go_for_an_entry_the_plan_does_not_have_is_refused(kitchen):
    code, said = plan_go(kitchen, entry="nope")
    assert code == 1 and said.startswith("refused: ") and "has no entry nope" in said


def stop(kitchen):
    code, said = kitchen.main("plan", "stop", "epic")
    assert code == 0, said
    return said


def changed_head(kitchen):
    path = kitchen.home / "plan.md"
    path.write_text(path.read_text().replace("- it works\n", "- it works, and fast\n"))


def closed(kitchen):
    path = kitchen.home / "plan.md"
    path.write_text(
        path.read_text().split("## epic:")[0] + "## other:" + PLAN.split("## other:")[1]
    )


@pytest.mark.parametrize("end", [stop, changed_head, closed])
def test_a_go_that_ends_leaves_an_unlaunched_row_waiting_and_a_launched_one_going_on(kitchen, end):
    assert plan_go(kitchen)[0] == 0
    queued(kitchen, "alpha")
    queued(kitchen, "beta")
    launched(kitchen, "beta")
    end(kitchen)
    kitchen.poll()
    assert basis(kitchen, "alpha") == ()
    assert not rows(kitchen)["alpha"].get("held")
    assert basis(kitchen, "beta") == (queue.ENTRY, "epic")
    assert "crew: alpha" not in [launch["title"] for launch in kitchen.t3.launches]
    queued(kitchen, "gamma")
    assert basis(kitchen, "gamma") == ()


def test_plan_stop_says_which_rows_wait_again_and_plan_shows_the_stop(kitchen):
    assert plan_go(kitchen)[0] == 0
    queued(kitchen, "alpha")
    said = stop(kitchen)
    assert said.startswith("stopped epic's go") and "alpha waits for the user's go" in said
    assert basis(kitchen, "alpha") == ()
    (line,) = [one for one in kitchen.main("plan")[1].splitlines() if one.startswith("epic |")]
    assert "| go stopped " in line
    assert plan_go(kitchen, message="a-second-go")[0] == 0
    kitchen.poll()
    assert basis(kitchen, "alpha") == (queue.ENTRY, "epic")


def test_a_row_whose_brief_is_a_case_of_gates_md_waits_under_the_entry_go(kitchen):
    assert plan_go(kitchen)[0] == 0
    queued(kitchen, "alpha", text=brief("alpha", "Holds: spends money\n"))
    kitchen.poll()
    assert basis(kitchen, "alpha") == ()


def test_a_case_added_to_a_brief_with_a_go_takes_the_go_back(kitchen):
    assert plan_go(kitchen)[0] == 0
    queued(kitchen, "alpha")
    queued(kitchen, "alpha", text=brief("alpha", "Holds: deletes data\n"))
    kitchen.poll()
    assert basis(kitchen, "alpha") == ()


def silence(kitchen, minutes=30):
    kitchen.settings.write_text(
        kitchen.settings.read_text() + f'go = "silence"\ngo_quiet_minutes = {minutes}\n'
    )


def gate(kitchen, slug):
    code, said = kitchen.main("gate", slug, stdin=GATE.format(slug=slug))
    assert code == 0, said
    return int(said.split()[-1])


def waits_on_user(kitchen):
    kept = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    return [one["key"] for one in kept if one["kind"] == "gate"]


def test_under_silence_a_gated_s_row_is_approved_after_the_window_and_not_before(kitchen):
    silence(kitchen)
    assert plan_go(kitchen)[0] == 0
    queued(kitchen, "alpha")
    assert basis(kitchen, "alpha") == ()
    number = gate(kitchen, "alpha")
    kitchen.poll(NOW + timedelta(minutes=29))
    assert basis(kitchen, "alpha") == ()
    assert waits_on_user(kitchen) == [f"gate:q{number}"]
    assert kitchen.t3.launches == []
    kitchen.poll(NOW + timedelta(minutes=31))
    assert basis(kitchen, "alpha") == ("answer", str(number))
    made = rows(kitchen)["alpha"]["approval"]
    assert made["closed_by"] == questions.SILENCE
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]


def test_under_silence_an_l_row_and_a_case_wait_after_the_window(kitchen):
    silence(kitchen)
    queued(kitchen, "alpha", text=brief("alpha").replace("Size: S\n", "Size: L\n"))
    queued(kitchen, "beta", text=brief("beta", "Holds: publishes\n"))
    gate(kitchen, "alpha")
    gate(kitchen, "beta")
    kitchen.poll(NOW + timedelta(minutes=31))
    assert basis(kitchen, "alpha") == basis(kitchen, "beta") == ()


def test_under_silence_an_answer_that_differs_approves_nothing(kitchen):
    silence(kitchen, minutes=5)
    queued(kitchen, "alpha")
    number = gate(kitchen, "alpha")
    code, said = kitchen.main(
        "answer", str(number), "--by", "user", "--at", "2026-10-12 11:01 ET", "--differs", "wait"
    )
    assert code == 0, said
    kitchen.poll(NOW + timedelta(minutes=31))
    assert basis(kitchen, "alpha") == ()


def test_under_the_entry_setting_a_go_gate_approves_nothing(kitchen):
    queued(kitchen, "alpha")
    gate(kitchen, "alpha")
    kitchen.poll(NOW + timedelta(minutes=31))
    assert basis(kitchen, "alpha") == ()
