"""What waits on the user: a pass follows each approved row that cannot move to its root, sends
one `waiting-on-user` event per root per hour, and keeps the roots in the list that `jbus
queue show` prints (`tests/test_jbus_digest.py` has the list's other kinds). Run as
`tests/test_jbus.py` runs: the real command and the real pass, against a faked T3 Code
server, `gh`, `jmerge` and webhook."""

import json
import shlex
import stat
from datetime import timedelta

import pytest

from test_jbus_kitchen import KEY, NOW, RESULT, Kitchen, asking
from test_jbus_queue import add, brief, go, sha12, widened

URL = "https://example.test/pull/286"
WHY = "needs user, touches skills/crew/SKILL.md"
HOLD = f"hold 286 {URL}: {WHY}\n"
ROWS = ["jbus-a", "jbus-b", "jbus-c", "jbus-d"]
STAMP = '--by user --at "<YYYY-MM-DD HH:MM ET>"'
BASES = (
    "with --word <id>, --answer <number>, --message <thread id>/<message id> or --page "
    "<session key>/<entry id>"
)
HEAD = "c" * 40
SAFE = f"safe because 41 passed (proven at {HEAD[:12]})"
ACCEPTED = f"ready 286 {HEAD} ps-agnostic ps-agnostic, accepted: {WHY}, {SAFE}\n"
UNBLOCKS = " · unblocks jbus-a, jbus-b, jbus-c, jbus-d · since 11:00 ET"
HAND = f"hand-merge #286 {URL}: {WHY}; {SAFE}; jmerge --accept 286 {STAMP}"
MERGE = f"waiting-on-user demo: {HAND}{UNBLOCKS}"
SET = (
    "set webhook_url and webhook_key for demo in its [[project]] table, "
    "or at the top of ~/.config/jbus/config.toml for every project"
)
WEBHOOK = f"waiting-on-user demo: {SET} · unblocks events to the Chef · since 11:00 ET"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def later(minutes):
    return NOW + timedelta(minutes=minutes)


def waits(kitchen):
    return kitchen.lines("waiting-on-user")


def shown(kitchen):
    return json.loads((kitchen.state / "waiting-on-user.json").read_text())


def held(kitchen, accept=ACCEPTED):
    """20:31, 2026-10-11: four approved rows behind a pull request only the user may merge,
    while another slug's crew is running."""
    kitchen.config(max_running=6)
    kitchen.brief("ps-agnostic", RESULT)
    kitchen.set("accept.txt", accept)
    kitchen.set("open.json", [kitchen.opened("ps-agnostic", 286)])
    kitchen.set("jmerge.txt", HOLD)
    kitchen.brief("other")
    kitchen.t3.thread("other", "running")
    for priority, slug in enumerate(ROWS, start=1):
        add(kitchen, slug, priority=priority, depends="ps-agnostic")


def test_four_rows_behind_a_held_pull_request_are_one_root_beside_a_running_crew(kitchen):
    held(kitchen)
    kitchen.poll()
    assert waits(kitchen) == [MERGE]
    assert [event["slug"] for event in kitchen.events("waiting-on-user")] == ["#286"]
    assert kitchen.t3.launches == []


NO_FACT = f"no proven safety fact at {HEAD[:12]} (blast-radius, review step 5)"
MOVED = f"its hold was at {'d' * 12}, and its head is {HEAD[:12]}"


@pytest.mark.parametrize(
    "said, short",
    [
        (f"refused 286 {URL}: {NO_FACT}\n", NO_FACT),
        (f"refused 286 {URL}: {MOVED}\n", MOVED),
        (f"wait 286 {URL}: auto-merge is off for this repo\n", "auto-merge is off for this repo"),
        ("", "jmerge --accept 286 --check did not answer"),
    ],
)
def test_a_held_pull_request_that_accept_would_refuse_gets_no_command(kitchen, said, short):
    """The line says what is short instead: there is nothing for the user to run yet."""
    held(kitchen, said)
    kitchen.poll()
    assert waits(kitchen) == [
        f"waiting-on-user demo: hand-merge #286 {URL}: {WHY}; not yet, {short}{UNBLOCKS}"
    ]
    assert kitchen.log("jmerge").count("--accept 286 --check") == 1


def test_a_chain_that_ends_at_a_row_with_no_approval_is_one_root_to_approve_it(kitchen):
    add(kitchen, "alpha", depends="beta")
    add(kitchen, "beta", depends="gamma")
    add(kitchen, "gamma", approve=False)
    kitchen.poll()
    command = f"jbus --project demo queue approve gamma --sha {sha12(brief('gamma'))} {BASES}"
    assert waits(kitchen) == [
        f"waiting-on-user demo: approve gamma: {command} · unblocks alpha, beta · since 11:00 ET"
    ]
    assert [event["slug"] for event in kitchen.events("waiting-on-user")] == ["approve:gamma"]
    typed = [*shlex.split(command.removesuffix(BASES)), "--word", kitchen.word()]
    assert kitchen.main(*typed[1:])[0] == 0
    assert "cleared approve:gamma" in kitchen.poll(later(3))
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: gamma"]


def test_a_brief_changed_after_the_go_is_a_root_to_approve_it_again(kitchen):
    add(kitchen, "alpha")
    changed = widened("alpha")
    add(kitchen, "alpha", approve=False, text=changed)
    add(kitchen, "beta", depends="alpha")
    kitchen.poll()
    now, was = sha12(changed), sha12(brief("alpha"))
    assert waits(kitchen) == [
        f"waiting-on-user demo: re-approve alpha (brief now {now}, approved {was}): "
        f"jbus --project demo queue approve alpha --sha {now} {BASES}"
        " · unblocks alpha, beta · since 11:00 ET"
    ]
    assert [event["slug"] for event in kitchen.events("waiting-on-user")] == ["re-approve:alpha"]


@pytest.mark.parametrize("end", ["a running crew", "a wait", "the limit", "a gate", "no row"])
def test_a_chain_that_ends_at_progress_or_at_a_gate_is_no_root(kitchen, end):
    kitchen.config(max_running=1 if end == "the limit" else 6)
    add(kitchen, "alpha", depends="beta")
    if end == "a running crew":
        kitchen.brief("beta")
        kitchen.t3.thread("beta", "running")
    elif end == "a wait":
        kitchen.brief("beta", RESULT)
        kitchen.set("open.json", [kitchen.opened("beta", 8)])
        kitchen.set("jmerge.txt", "wait 8 https://example.test/pull/8: its review is not written\n")
    elif end == "the limit":
        add(kitchen, "beta")
        kitchen.brief("other")
        kitchen.t3.thread("other", "running")
    elif end == "a gate":
        add(kitchen, "beta")
        kitchen.t3.thread("beta", "failed", settled=True)
    kitchen.poll()
    assert waits(kitchen) == []
    assert [one["key"] for one in shown(kitchen)] == ["row:beta"] * (end == "a gate")
    assert not (kitchen.state / "stall.json").exists()


def test_two_rows_that_depend_on_each_other_end_with_no_root(kitchen):
    add(kitchen, "alpha", depends="beta")
    add(kitchen, "beta", depends="alpha")
    kitchen.poll()
    assert waits(kitchen) == [] and shown(kitchen) == []


def test_a_pass_that_could_not_ask_github_keeps_the_roots_it_had(kitchen):
    held(kitchen)
    kitchen.poll()
    (kitchen.stub / "gh-down").touch()
    said = kitchen.poll(later(3))
    assert not any(line.startswith("cleared") for line in said)
    assert [one["line"] for one in shown(kitchen)] == [HAND]


def test_a_row_that_takes_the_last_slot_does_not_hide_the_chain_behind_it(kitchen):
    held(kitchen)
    kitchen.poll()
    kitchen.config(max_running=1)
    add(kitchen, "ready", priority=0)
    changed = widened("jbus-d")
    add(kitchen, "jbus-d", priority=4, depends="ps-agnostic", approve=False, text=changed)
    said = kitchen.poll(later(3))
    assert any(
        line.startswith("max_running is 1 across all projects: ready waits, since ")
        for line in said
    )
    assert not any(line.startswith("cleared") for line in said)
    assert [one["key"] for one in shown(kitchen)] == ["re-approve:jbus-d", "#286"]
    assert shown(kitchen)[1]["unblocks"] == ROWS[:3]
    assert kitchen.lines("gate") == [] and kitchen.lines("jmerge") == [HOLD.strip()]


@pytest.mark.parametrize("silent", ["jmerge did not run", "the home merges", "a stop file"])
def test_a_pass_that_does_not_judge_a_held_pull_request_keeps_its_root(kitchen, silent):
    held(kitchen)
    kitchen.poll()
    if silent == "jmerge did not run":
        (kitchen.stub / "jmerge-dies").write_text("jmerge: could not ask GitHub")
    elif silent == "the home merges":
        (kitchen.home / "home-thread").write_text("mcp:the-home\n")
    else:
        (kitchen.state_dir / "stop").touch()
    said = kitchen.poll(later(3))
    assert not any(line.startswith("cleared") for line in said)
    assert [one["line"] for one in shown(kitchen)] == [HAND]
    assert (
        json.loads((kitchen.state / "stall.json").read_text())["#286"]["since"] == NOW.isoformat()
    )


@pytest.mark.parametrize("root", ["#286", "approve:gamma", "re-approve:alpha"])
def test_a_root_the_user_dealt_with_while_the_stop_file_stands_is_cleared(kitchen, root):
    if root == "#286":
        held(kitchen)
    elif root == "approve:gamma":
        add(kitchen, "alpha", depends="gamma")
        add(kitchen, "gamma", approve=False)
    else:
        add(kitchen, "alpha")
        add(kitchen, "alpha", approve=False, text=widened("alpha"))
    kitchen.poll()
    assert [one["key"] for one in shown(kitchen)] == [root]
    (kitchen.state_dir / "stop").touch()
    assert not any(line.startswith("cleared") for line in kitchen.poll(later(3)))
    if root == "#286":
        kitchen.set("open.json", [])
        kitchen.set("merged.json", [kitchen.merged("ps-agnostic", 286, "a" * 40)])
    else:
        assert go(kitchen, root.partition(":")[2])[0] == 0
    assert f"cleared {root}" in kitchen.poll(later(6))
    assert shown(kitchen) == [] and kitchen.main("queue", "show")[1].startswith("| slug |")


def test_a_root_is_sent_once_an_hour_while_it_stands_and_is_dropped_when_it_clears(kitchen):
    held(kitchen)
    said = kitchen.poll()
    assert waits(kitchen) == [MERGE]
    said += kitchen.poll(later(3))
    assert waits(kitchen) == [MERGE]
    said += kitchen.poll(later(61))
    assert waits(kitchen) == [MERGE, MERGE]
    kept = json.loads((kitchen.state / "stall.json").read_text())
    assert kept == {"#286": {"since": NOW.isoformat(), "sent": later(61).isoformat()}}
    assert not any("cleared" in line or "waiting-on-user" in line for line in said)
    kitchen.set("open.json", [])
    kitchen.set("merged.json", [kitchen.merged("ps-agnostic", 286, "a" * 40)])
    kitchen.set("jmerge.txt", "")
    said = kitchen.poll(later(64))
    assert "cleared #286" in said and waits(kitchen) == [MERGE, MERGE]
    assert json.loads((kitchen.state / "stall.json").read_text()) == {}
    assert shown(kitchen) == []
    assert kitchen.log("notify") == [f"jbus | {MERGE}"] * 2


def test_no_line_and_no_file_holds_the_webhooks_url_or_its_key(kitchen):
    held(kitchen)
    kitchen.webhook.status = 500
    said = kitchen.poll() + kitchen.poll(later(61))
    code, table = kitchen.main("queue", "show")
    everything = "\n".join(
        [
            *said,
            table,
            *kitchen.log("notify"),
            (kitchen.state / "stall.json").read_text(),
            (kitchen.state / "waiting-on-user.json").read_text(),
        ]
    )
    assert MERGE in everything
    assert kitchen.webhook.url not in everything and KEY not in everything
    assert "127.0.0.1" not in everything


def test_queue_show_prints_what_waits_on_the_user_above_the_table(kitchen):
    held(kitchen)
    code, table = kitchen.main("queue", "show")
    assert code == 0 and table.startswith("| slug |")
    kitchen.poll()
    assert shown(kitchen) == [
        {
            "kind": "hold",
            "key": "#286",
            "line": HAND,
            "number": 286,
            "url": URL,
            "since": NOW.isoformat(),
            "unblocks": ROWS,
        }
    ]
    assert stat.S_IMODE((kitchen.state / "waiting-on-user.json").stat().st_mode) == 0o600
    code, said = kitchen.main("queue", "show")
    assert code == 0 and said.startswith(f"waiting on user:\n{HAND}\n\n| slug |")
    assert said.count(HAND) == 1
    kitchen.set("open.json", [])
    kitchen.set("merged.json", [kitchen.merged("ps-agnostic", 286, "a" * 40)])
    kitchen.poll(later(3))
    assert kitchen.main("queue", "show")[1].startswith("| slug |")


def test_a_webhook_that_is_not_set_is_a_root_said_in_the_journal_and_on_the_desk(kitchen):
    kitchen.config(url="")
    said = kitchen.poll() + kitchen.poll(later(3))
    assert said.count(WEBHOOK) == 1 and kitchen.log("notify") == [f"jbus | {WEBHOOK}"]
    assert waits(kitchen) == [WEBHOOK]
    assert [(one["key"], one["line"]) for one in shown(kitchen)] == [("config:demo", SET)]
    assert kitchen.waiting() == []
    assert (said + kitchen.poll(later(61))).count(WEBHOOK) == 2
    kitchen.config()
    assert "cleared config:demo" in kitchen.poll(later(64))
    assert shown(kitchen) == []


def test_with_no_sign_in_the_root_is_to_sign_in_and_it_unblocks_the_rows_that_wait(kitchen):
    add(kitchen, "alpha")
    (kitchen.config_dir / "t3.json").unlink()
    kitchen.poll()
    assert waits(kitchen) == [
        "waiting-on-user demo: run jbus t3 login · unblocks alpha · since 11:00 ET"
    ]


def test_a_webhook_whose_last_post_failed_has_each_root_in_the_journal_each_hour(kitchen):
    held(kitchen)
    kitchen.main(
        "gate",
        "alpha",
        stdin=asking(default="one"),
    )
    kitchen.webhook.status = 500
    said = kitchen.poll()
    assert MERGE not in said and "wake failed demo: the webhook answered 500" in said
    assert MERGE not in kitchen.poll(later(30))
    assert kitchen.poll(later(61)).count(MERGE) == 1
    assert kitchen.webhook.posts == [] and waits(kitchen) == [MERGE, MERGE]


GUARDED = f"guarded (touches src/jbus/alert.py), no proven safety fact at {HEAD[:12]}"
STALLED = (
    f"stall alpha: #286 {URL} has waited 10 passes at {HEAD[:12]}, {GUARDED}; "
    "its crew's thread is mcp:crew"
)


def guarded(kitchen, head=HEAD, short=GUARDED):
    kitchen.brief("alpha", "Thread: mcp:crew\n" + RESULT)
    kitchen.set("open.json", [{**kitchen.opened("alpha", 286), "headRefOid": head}])
    kitchen.set("jmerge.txt", f"wait 286 {URL}: {short}\n")


def stalls(kitchen):
    return kitchen.lines("stall")


def test_a_guarded_wait_is_a_stall_at_its_tenth_pass_at_one_head_and_only_then(kitchen):
    guarded(kitchen)
    for minute in range(9):
        kitchen.poll(later(minute))
    assert stalls(kitchen) == []
    kitchen.poll(later(9))
    assert stalls(kitchen) == [STALLED]
    (event,) = kitchen.events("stall")
    assert (event["slug"], event["loud"]) == ("alpha", "user")
    assert kitchen.webhook.said == [[f"demo: {STALLED}"]]
    kitchen.poll(later(10))
    assert stalls(kitchen) == [STALLED]


def test_a_scoped_reviewer_launched_for_the_head_starts_a_longer_count_once(kitchen):
    guarded(kitchen)
    for minute in range(6):
        kitchen.poll(later(minute))
    brief = kitchen.home / "tasks/alpha.md"
    brief.write_text(brief.read_text() + f"Scoped reviewer: mcp:3333-cccc, of {HEAD}\n")
    for minute in range(6, 35):
        kitchen.poll(later(minute))
    assert stalls(kitchen) == []
    for minute in (35, 36):
        kitchen.poll(later(minute))
    assert stalls(kitchen) == [
        STALLED.replace("10 passes", "30 passes").replace(
            f"at {HEAD[:12]},", f"at {HEAD[:12]}, with a scoped reviewer launched,"
        )
    ]


def test_a_session_that_could_launch_no_scoped_reviewer_is_not_a_reviewer_launched(kitchen):
    guarded(kitchen)
    brief = kitchen.home / "tasks/alpha.md"
    none = f"Scoped reviewer: none, no launch tool in this session, of {HEAD}\n"
    brief.write_text(brief.read_text() + none)
    for minute in range(10):
        kitchen.poll(later(minute))
    assert stalls(kitchen) == [STALLED]


def test_a_new_head_or_another_reason_starts_the_count_of_a_stall_again(kitchen):
    guarded(kitchen)
    for minute in range(9):
        kitchen.poll(later(minute))
    moved = GUARDED.replace(HEAD[:12], "d" * 12)
    guarded(kitchen, head="d" * 40, short=moved)
    for minute in range(9, 18):
        kitchen.poll(later(minute))
    assert stalls(kitchen) == []
    kitchen.poll(later(18))
    assert stalls(kitchen) == [STALLED.replace(HEAD[:12], "d" * 12)]
    guarded(kitchen, head="d" * 40, short="guarded (touches a.py), its check has no start time")
    for minute in range(19, 28):
        kitchen.poll(later(minute))
    assert len(stalls(kitchen)) == 1


def test_a_wait_that_is_not_a_guarded_one_and_a_pass_jmerge_said_nothing_in_are_not_counted(
    kitchen,
):
    guarded(kitchen, short="its check has not passed")
    for minute in range(12):
        kitchen.poll(later(minute))
    assert stalls(kitchen) == []
    guarded(kitchen)
    for minute in range(12, 21):
        kitchen.poll(later(minute))
    kitchen.set("jmerge.txt", "")
    kitchen.poll(later(21))
    guarded(kitchen)
    kitchen.poll(later(22))
    assert stalls(kitchen) == []
