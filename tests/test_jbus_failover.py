"""A thread whose last turn failed on a usage limit goes on, once, on the next instance of its
role's pool with headroom, with its model and options, and the limit is in the ledger for the
instance the run was on. Run as `tests/test_jbus_resume.py` runs: the real pass against the
fakes, with a clock the test moves.

The replays are the caps of 2026-10-16 and 2026-10-17. On the 16th at 22:15 ET a home failed
on claudeAgent's weekly limit, which reset on the 18th at 4pm ET. It was moved to
claudeAgent_claude_prime by hand the next day at about 15:39 ET, and prime hit its five-hour
window about 9 minutes later."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jroles import ledger
from test_jbus_kitchen import NOW, SELECTION, approved, sends
from test_jbus_resume import THREAD, crew

PRIME = "claudeAgent_claude_prime"
POOL = f"claudeAgent,{PRIME}"
WEEKLY = "You've hit your weekly limit · resets Oct 18, 4pm (America/New_York)"
SESSION = "You've hit your session limit · resets 11pm (America/New_York)"
WEEKLY_RESET = datetime(2026, 10, 18, 20, 0, tzinfo=UTC)
FAILED_16TH = datetime(2026, 10, 17, 2, 15, tzinfo=UTC)
MOVED_17TH = datetime(2026, 10, 17, 19, 39, tzinfo=UTC)
PRIME_CAPPED = MOVED_17TH + timedelta(minutes=9)
SESSION_RESET = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)
AFTER = WEEKLY_RESET + timedelta(minutes=1)


@pytest.fixture(autouse=True)
def pools(jstack_config, request):
    """The role map gives the crew and the home one pool, claudeAgent first. The kitchen's
    plan is on the real clock, and these tests on the replayed one: they start with no plan."""
    if "kitchen" in request.fixturenames:
        request.getfixturevalue("kitchen").machine(plan=None)
    roles = jstack_config.parent / "roles"
    roles.write_text(
        f"crew: claudeAgent claude-sonnet-5-5 {POOL}\nhome: claudeAgent claude-opus-5-5 {POOL}\n"
    )
    return roles


def failed_on(thread, text, run="run-1", ran_on="claudeAgent", notice=None, at=None, **more):
    """The thread's last turn ended on `text`, as T3 Code shows one: an assistant message with
    the limit, the error, and, where `notice` gives its window and reset, the system notice
    whose itemId carries them."""
    items = [
        {"runId": run, "itemId": f"{run}:1", "type": "assistant_message", "text": text},
        {"runId": run, "itemId": f"{run}:2", "type": "error", "text": "Usage limit reached"},
    ]
    if notice:
        window, at = notice
        notice_id = f"{run}:usage-limit:{window}:{int(at.timestamp())}"
        items.append({"runId": run, "itemId": notice_id, "type": "system_notice", "text": ""})
    thread.update(
        status="failed",
        latestRunId=run,
        itemCount=len(items) + 2,
        runs=[{"runId": run, "providerInstanceId": ran_on, "completedAt": at and at.isoformat()}],
        read_items=items,
        **more,
    )


def configures(kitchen):
    return [given for tool, given in kitchen.t3.calls if tool == "t3_thread_configure"]


def failovers(kitchen):
    return kitchen.lines("failover")


def kept(instance, now):
    return ledger.capped_until(ledger.read([instance]), instance, now)


def test_the_16th_weekly_failure_moves_the_thread_once_to_prime_with_its_model(kitchen):
    thread = crew(kitchen)
    failed_on(thread, WEEKLY, notice=("seven_day", WEEKLY_RESET))
    said = kitchen.poll(FAILED_16TH)
    assert configures(kitchen) == [
        {"threadId": THREAD, "modelSelection": {**SELECTION, "instanceId": PRIME}}
    ]
    (carry,) = sends(kitchen)
    assert carry["threadId"] == THREAD and carry["mode"] == "queue"
    assert carry["clientRequestId"] == f"failover|{THREAD}|run-1"
    assert WEEKLY in carry["message"] and f"now on {PRIME}" in carry["message"]
    brief = kitchen.home / "tasks" / "alpha.md"
    assert f"read `{brief}`" in carry["message"]
    assert "features/crew/SKILL.md" in carry["message"]
    assert f"jbriefs --skills {brief}" in carry["message"]
    line = (
        f"failover alpha: seven_day limit until {WEEKLY_RESET.isoformat()}, carry-on on "
        f"claudeAgent to {PRIME}, model claude-sonnet-5-5, effort=high, fastMode=True"
    )
    assert failovers(kitchen) == [line] and line in said
    assert kept("claudeAgent", FAILED_16TH) == WEEKLY_RESET and kept(PRIME, FAILED_16TH) is None
    assert kitchen.lines("resume") == []


def test_the_itemid_is_read_before_the_text(kitchen):
    """The notice's window and reset win over what the text says."""
    thread = crew(kitchen)
    other = datetime(2026, 10, 19, 4, 0, tzinfo=UTC)
    failed_on(thread, WEEKLY, notice=("five_hour", other))
    kitchen.poll(FAILED_16TH)
    assert ledger.read(["claudeAgent"])[("claudeAgent", "five_hour")].resets == other.timestamp()
    assert ("claudeAgent", "seven_day") not in ledger.read(["claudeAgent"])


def test_the_17th_prime_cap_stalls_once_then_carries_on_at_the_first_reset(kitchen):
    thread = crew(kitchen)
    failed_on(thread, WEEKLY)
    kitchen.poll(MOVED_17TH)
    assert thread["selection"]["instanceId"] == PRIME
    failed_on(thread, SESSION, run="run-2", ran_on=PRIME, at=PRIME_CAPPED)
    for minutes in (0, 3, 6, 60):
        kitchen.poll(PRIME_CAPPED + timedelta(minutes=minutes))
    assert len(sends(kitchen)) == 1 and len(configures(kitchen)) == 1
    (stall,) = kitchen.lines("stall")
    assert stall == (
        f"capped alpha: claudeAgent and {PRIME} are both capped until "
        f"{SESSION_RESET.isoformat()}; it is sent on at the first reset"
    )
    assert kitchen.lines("resume") == []
    kitchen.poll(SESSION_RESET + timedelta(minutes=1))
    kitchen.poll(SESSION_RESET + timedelta(minutes=4))
    assert [given["clientRequestId"] for given in sends(kitchen)] == [
        f"failover|{THREAD}|run-1",
        f"failover|{THREAD}|run-2",
    ]
    assert len(configures(kitchen)) == 1 and thread["selection"]["instanceId"] == PRIME
    assert len(kitchen.lines("stall")) == 1


def test_the_same_failure_seen_on_two_passes_acts_once(kitchen):
    thread = crew(kitchen)
    failed_on(thread, WEEKLY)
    for minutes in (0, 3, 6):
        kitchen.poll(FAILED_16TH + timedelta(minutes=minutes))
    assert len(sends(kitchen)) == 1 and len(configures(kitchen)) == 1
    assert len(failovers(kitchen)) == 1 and kitchen.lines("resume") == []
    assert thread["selection"]["instanceId"] == PRIME


def test_a_thread_with_no_cap_is_never_moved(kitchen):
    thread = crew(kitchen)
    thread.update(status="failed", latestRunId="run-1", itemCount=2)
    thread["read_items"] = [{"runId": "run-1", "type": "error", "text": "Claude API overloaded"}]
    for minutes in (0, 3):
        kitchen.poll(FAILED_16TH + timedelta(minutes=minutes))
    assert configures(kitchen) == [] and failovers(kitchen) == []
    assert kitchen.lines("resume")[0] == "resume alpha: told the crew to carry on (failed, 1 of 2)"


def test_a_thread_already_on_the_chosen_instance_is_not_moved_again(kitchen):
    thread = crew(kitchen)
    thread["selection"] = {**SELECTION, "instanceId": PRIME}
    failed_on(thread, SESSION, ran_on="claudeAgent")
    kitchen.poll(FAILED_16TH)
    assert configures(kitchen) == []
    (carry,) = sends(kitchen)
    assert f"now on {PRIME}" in carry["message"]


def test_a_limit_failure_is_no_carry_on_of_the_resume_path(kitchen):
    """The two carry-ons of a thread are for a thread that ended, not for a capped one."""
    thread = crew(kitchen)
    failed_on(thread, WEEKLY)
    kitchen.poll(FAILED_16TH)
    failed_on(thread, WEEKLY, run="run-2", ran_on=PRIME)
    kitchen.poll(AFTER)
    assert [given["clientRequestId"] for given in sends(kitchen)] == [
        f"failover|{THREAD}|run-1",
        f"failover|{THREAD}|run-2",
    ]
    assert not any(key.startswith("resume|") for key in kitchen.marks())


def test_after_the_reset_the_next_cap_goes_to_the_first_instance_again(kitchen):
    """Sticky, not round: a thread moves only on a cap, and then to the first with headroom."""
    thread = crew(kitchen)
    failed_on(thread, WEEKLY)
    kitchen.poll(FAILED_16TH)
    failed_on(thread, SESSION, run="run-2", ran_on=PRIME)
    kitchen.poll(AFTER)
    assert configures(kitchen)[-1]["modelSelection"] == SELECTION | {"instanceId": "claudeAgent"}
    assert failovers(kitchen)[-1].endswith(
        f"carry-on on {PRIME} to claudeAgent, model claude-sonnet-5-5, effort=high, fastMode=True"
    )


def test_a_home_thread_is_moved_in_the_home_pool_and_told_to_carry_on_from_its_handoff(kitchen):
    home = kitchen.t3.thread("home", "failed", title="home: demo")
    (kitchen.home / "home-id").write_text(f"{home['threadId']} 2026-10-12\n")
    failed_on(home, WEEKLY)
    kitchen.poll(FAILED_16TH)
    (given,) = configures(kitchen)
    assert given["threadId"] == home["threadId"]
    assert given["modelSelection"]["instanceId"] == PRIME
    (carry,) = sends(kitchen)
    assert "read your handoff" in carry["message"]


WHO = ("crew", "home", "scoped home")


def mover(kitchen, who):
    """A thread failover reads, and the name its lines give it: a crew a brief names, the
    root home's thread in `home-id`, or a scoped home's in `<scope>/home-id`."""
    if who == "crew":
        return crew(kitchen), "alpha"
    home = kitchen.t3.thread("home", "failed", title="home: demo")
    where = kitchen.home if who == "home" else kitchen.home / "infra"
    where.mkdir(parents=True, exist_ok=True)
    (where / "home-id").write_text(f"{home['threadId']} 2026-10-20\n")
    return home, "home"


@pytest.mark.parametrize("who", WHO)
@pytest.mark.parametrize(("ran_on", "other"), [("claudeAgent", PRIME), (PRIME, "claudeAgent")])
def test_a_capped_thread_moves_to_the_other_instance_either_way(kitchen, who, ran_on, other):
    thread, name = mover(kitchen, who)
    thread["selection"] = {**SELECTION, "instanceId": ran_on}
    failed_on(thread, SESSION, ran_on=ran_on, notice=("five_hour", SESSION_RESET))
    kitchen.poll(FAILED_16TH)
    assert configures(kitchen) == [
        {"threadId": thread["threadId"], "modelSelection": {**SELECTION, "instanceId": other}}
    ]
    (carry,) = sends(kitchen)
    assert f"now on {other}" in carry["message"]
    (line,) = failovers(kitchen)
    assert line.startswith(f"failover {name}: five_hour limit until {SESSION_RESET.isoformat()}")
    assert f"carry-on on {ran_on} to {other}, model " in line
    assert kept(ran_on, FAILED_16TH) == SESSION_RESET and kept(other, FAILED_16TH) is None


@pytest.mark.parametrize("who", WHO)
@pytest.mark.parametrize(("ran_on", "other"), [("claudeAgent", PRIME), (PRIME, "claudeAgent")])
def test_with_both_capped_a_thread_stalls_once_and_carries_on_at_the_first_reset(
    kitchen, who, ran_on, other
):
    """The other instance resets first: the thread waits for it, said once, then moves there."""
    first = SESSION_RESET - timedelta(hours=2)
    ledger.write(ledger.Record(other, "five_hour", 100, int(first.timestamp())))
    thread, name = mover(kitchen, who)
    thread["selection"] = {**SELECTION, "instanceId": ran_on}
    failed_on(thread, SESSION, ran_on=ran_on, notice=("five_hour", SESSION_RESET))
    for minutes in (0, 3, 6, 60):
        kitchen.poll(FAILED_16TH + timedelta(minutes=minutes))
    assert configures(kitchen) == [] and sends(kitchen) == []
    assert kitchen.lines("stall") == [
        f"capped {name}: claudeAgent and {PRIME} are both capped until {first.isoformat()}; "
        "it is sent on at the first reset"
    ]
    kitchen.poll(first + timedelta(minutes=1))
    kitchen.poll(first + timedelta(minutes=4))
    assert configures(kitchen) == [
        {"threadId": thread["threadId"], "modelSelection": {**SELECTION, "instanceId": other}}
    ]
    (carry,) = sends(kitchen)
    assert f"now on {other}" in carry["message"]
    assert len(kitchen.lines("stall")) == 1 and kitchen.lines("resume") == []


def test_a_thread_no_brief_and_no_home_names_is_left_alone(kitchen):
    other = kitchen.t3.thread("stray", "failed", title="a chat")
    failed_on(other, WEEKLY)
    kitchen.poll(FAILED_16TH)
    assert configures(kitchen) == [] and sends(kitchen) == []
    assert ledger.read(["claudeAgent", "stray"]) == {}


def test_a_thread_on_an_instance_outside_its_pool_is_never_moved_into_it(kitchen, pools):
    """Codex and Cursor take no Claude work, and a Claude thread goes to no other provider:
    an instance the pool does not name is a pool of one, and waits for its own reset."""
    thread = crew(kitchen)
    thread["selection"] = {"instanceId": "cursor", "model": "grok-4.7"}
    failed_on(thread, WEEKLY, ran_on="cursor")
    kitchen.poll(FAILED_16TH)
    assert configures(kitchen) == [] and sends(kitchen) == []
    assert kitchen.lines("stall") == [
        f"capped alpha: cursor is capped until {WEEKLY_RESET.isoformat()}; "
        "it is sent on at the first reset"
    ]
    assert kept("claudeAgent", FAILED_16TH) is None


def test_a_pool_of_one_waits_for_its_reset_and_then_carries_on_where_it_is(kitchen, pools):
    pools.write_text("crew: claudeAgent claude-sonnet-5-5 claudeAgent\n")
    thread = crew(kitchen)
    failed_on(thread, WEEKLY)
    kitchen.poll(FAILED_16TH)
    assert sends(kitchen) == [] and len(kitchen.lines("stall")) == 1
    kitchen.poll(AFTER)
    assert configures(kitchen) == [] and len(sends(kitchen)) == 1


def test_the_ledger_keeps_the_later_reset_and_holds_a_blind_limit_for_an_hour(tmp_path):
    base = tmp_path / "limits"
    late = ledger.cap_of([{"text": WEEKLY}], NOW)
    soon = ledger.cap_of([{"text": "You've hit your 5-hour limit"}], NOW)
    assert (late.window, late.resets) == ("seven_day", WEEKLY_RESET)
    assert (soon.window, soon.resets) == ("five_hour", NOW + ledger.BLIND)
    assert ledger.write(late.record("claudeAgent"), base)
    assert not ledger.write(late.record("claudeAgent"), base)
    assert ledger.write(soon.record(PRIME), base)
    assert base.read_text() == f"seven_day 100 {int(WEEKLY_RESET.timestamp())}\n"
    assert (tmp_path / f"limits.{PRIME}").read_text() == (
        f"five_hour 100 {int((NOW + ledger.BLIND).timestamp())}\n"
    )
    earlier = ledger.Record("claudeAgent", "seven_day", 100, int(NOW.timestamp()))
    assert not ledger.write(earlier, base)
    assert ledger.cap_of([{"text": "Claude API rate limit reached."}], NOW) is None


CHOSEN = {
    "provider": "claudeAgent",
    "model": "claude-sonnet-5-5",
    "options": [{"id": "effort", "value": "medium"}],
}


def cap(instance, text=WEEKLY):
    ledger.write(ledger.cap_of([{"text": text}], NOW).record(instance))


def test_a_launch_takes_the_crew_line_of_the_role_map_on_the_first_instance(kitchen):
    approved(kitchen, "alpha")
    said = kitchen.poll()
    (given,) = kitchen.t3.launches
    assert given["modelSelection"] == {**CHOSEN, "instanceId": "claudeAgent"}
    (line,) = [line for line in said if line.startswith("launched alpha")]
    assert " on " not in line


def test_a_launch_while_claude_agent_is_capped_starts_on_prime_and_says_why(kitchen):
    cap("claudeAgent")
    approved(kitchen, "alpha")
    said = kitchen.poll()
    (given,) = kitchen.t3.launches
    assert given["modelSelection"] == {**CHOSEN, "instanceId": PRIME}
    (line,) = [line for line in said if line.startswith("launched alpha")]
    assert line.endswith(f" on {PRIME}, claudeAgent is capped until {WEEKLY_RESET.isoformat()}")


def test_launches_stay_on_the_first_instance_until_it_is_capped_then_go_back(kitchen):
    kitchen.config(max_running=3)
    approved(kitchen, "alpha")
    kitchen.poll()
    cap("claudeAgent")
    approved(kitchen, "beta", priority=2)
    kitchen.poll(NOW + timedelta(minutes=1))
    approved(kitchen, "gamma", priority=3)
    kitchen.poll(AFTER)
    chosen = [given["modelSelection"]["instanceId"] for given in kitchen.t3.launches]
    assert chosen == ["claudeAgent", PRIME, "claudeAgent"]


def test_a_launch_with_the_whole_pool_capped_waits_and_says_so_once(kitchen):
    cap("claudeAgent")
    cap(PRIME, "You've hit your weekly limit · resets Oct 20, 4pm (America/New_York)")
    approved(kitchen, "alpha")
    first = kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert kitchen.t3.launches == []
    assert [line for line in first if line.startswith("wait alpha")] == [
        f"wait alpha: no launch: claudeAgent and {PRIME} are both capped until "
        f"{WEEKLY_RESET.isoformat()}"
    ]
    assert len(kitchen.lines("stall")) == 1
    kitchen.poll(AFTER)
    assert [given["modelSelection"]["instanceId"] for given in kitchen.t3.launches] == [
        "claudeAgent"
    ]


def test_a_role_map_that_names_no_crew_line_launches_with_no_selection(kitchen, pools):
    pools.write_text("crew: inherit\n")
    approved(kitchen, "alpha")
    kitchen.poll()
    (given,) = kitchen.t3.launches
    assert "modelSelection" not in given


RECORDED = Path(__file__).parent / "fixtures" / "usage-limit-2026-10-20.json"
TONIGHT = json.loads(RECORDED.read_text())
TONIGHT_RESET = 1792470600
AT_0416 = datetime(2026, 10, 20, 4, 16, tzinfo=UTC)
CLAUDE_POOL = (
    f"crew: claudeAgent claude-opus-5-5 {POOL}\n"
    "review: codex gpt-6-sol effort=xhigh\n"
    "review: cursor grok-4.7 effort=xhigh fast=off\n"
)


def tonight(kitchen, on="claudeAgent"):
    """The 12 threads of project jstack that got tonight's cap, as T3 Code recorded them at
    04:13:31Z to 04:15:27Z, each failed on its latest run, which ran on `on`. The fixture is
    the 15 `system_notice` items of `~/.t3/userdata/statev2.sqlite` whose itemId ends
    `:five_hour:1792470600`, with each one's thread title and run."""
    made = {}
    for at, recorded in TONIGHT["threads"].items():
        runs = [{**run, "providerInstanceId": on} for run in recorded["runs"]]
        items = [item for item in TONIGHT["items"] if item["threadId"] == at]
        selection = {**runs[-1]["modelSelection"], "instanceId": on}
        made[at] = kitchen.t3.thread(
            "",
            "failed",
            threadId=at,
            title=recorded["title"],
            latestRunId=runs[-1]["runId"],
            itemCount=len(items),
            runs=runs,
            read_items=items,
            selection=selection,
            snoozed=False,
        )
    return made


@pytest.mark.parametrize(("ran_on", "other"), [("claudeAgent", PRIME), (PRIME, "claudeAgent")])
def test_tonights_caps_move_all_twelve_threads_to_the_other_account_once(
    kitchen, pools, ran_on, other
):
    """9 crews and 3 scoped reviewers whose `review` lines name Codex and Cursor: each one is
    on the crew's Claude pool, moves to the other account with its model and options, and is
    told to carry on once."""
    pools.write_text(CLAUDE_POOL)
    made = tonight(kitchen, on=ran_on)
    assert sorted(t["title"].split(":")[0] for t in made.values()) == ["crew"] * 9 + ["review"] * 3
    kitchen.poll(AT_0416)
    assert sorted(configures(kitchen), key=lambda given: given["threadId"]) == [
        {
            "threadId": at,
            "modelSelection": {
                **TONIGHT["threads"][at]["runs"][-1]["modelSelection"],
                "instanceId": other,
            },
        }
        for at, thread in sorted(made.items())
    ]
    assert sorted(given["threadId"] for given in sends(kitchen)) == sorted(made)
    assert all(f"now on {other}" in given["message"] for given in sends(kitchen))
    assert all(thread["selection"]["instanceId"] == other for thread in made.values())
    assert ledger.file_of(ran_on).read_text() == f"five_hour 100 {TONIGHT_RESET}\n"
    assert not ledger.file_of(other).exists()
    assert len(failovers(kitchen)) == 12
    kitchen.poll(AT_0416 + timedelta(minutes=3))
    assert len(sends(kitchen)) == 12 and len(configures(kitchen)) == 12


def test_a_reviewer_is_told_to_carry_on_its_review_and_logged_under_its_own_thread(kitchen, pools):
    pools.write_text(CLAUDE_POOL)
    made = tonight(kitchen)
    kitchen.poll(AT_0416)
    (reviewer,) = [t for t in made.values() if t["title"].startswith("review: hot-semantic")]
    (carry,) = [given for given in sends(kitchen) if given["threadId"] == reviewer["threadId"]]
    brief = kitchen.home / "tasks" / "hot-semantic-lines.md"
    assert f"read `{brief}` and the pull request first" in carry["message"]
    assert "features/pr-review/SKILL.md" in carry["message"]
    (line,) = [one for one in failovers(kitchen) if one.startswith("failover review hot-sem")]
    assert line.startswith("failover review hot-semantic-lines: five_hour limit until ")
    assert [e["slug"] for e in kitchen.events("failover") if e["line"] == line] == [
        reviewer["threadId"]
    ]


def test_a_scout_moves_and_reads_its_request(kitchen):
    thread = kitchen.t3.thread("probe", "failed", title="scout: probe")
    failed_on(thread, SESSION, notice=("five_hour", SESSION_RESET))
    kitchen.poll(FAILED_16TH)
    (given,) = configures(kitchen)
    assert given["modelSelection"]["instanceId"] == PRIME
    (carry,) = sends(kitchen)
    assert f"read `{kitchen.home / 'scouts' / 'probe.md'}` first" in carry["message"]
    assert failovers(kitchen)[0].startswith("failover scout probe: five_hour limit")


REVIEWED = "## Review\nHead: abc\nVerdict: findings\n"
REPORTED = "## Report\nThe answer.\n"
DONE = "## Result\nStatus: done\nLeft: none\nBranch: alpha, no pull request\n"


@pytest.mark.parametrize(
    ("title", "kind", "text"),
    [
        ("crew: alpha", "tasks", DONE),
        ("review: alpha", "tasks", DONE + REVIEWED),
        ("review: alpha, scoped", "tasks", DONE + REVIEWED),
        ("review: alpha, 2", "tasks", DONE + REVIEWED),
        ("scout: alpha", "scouts", REPORTED),
    ],
)
def test_a_thread_that_owes_nothing_is_left_alone(kitchen, title, kind, text):
    kitchen.brief("alpha", text, kind=kind)
    thread = kitchen.t3.thread("alpha", "failed", title=title)
    failed_on(thread, SESSION, notice=("five_hour", SESSION_RESET))
    kitchen.poll(FAILED_16TH)
    assert configures(kitchen) == [] and sends(kitchen) == [] and failovers(kitchen) == []


def test_a_home_titled_thread_no_home_id_holds_is_left_alone(kitchen):
    thread = kitchen.t3.thread("home", "failed", title="home: demo")
    failed_on(thread, SESSION, notice=("five_hour", SESSION_RESET))
    kitchen.poll(FAILED_16TH)
    assert configures(kitchen) == [] and sends(kitchen) == []


def test_a_crew_of_every_project_of_the_config_moves(kitchen):
    side = kitchen.second()
    thread = kitchen.t3.thread("beta", "failed", project=side.project)
    failed_on(thread, SESSION, notice=("five_hour", SESSION_RESET))
    kitchen.poll(FAILED_16TH)
    (given,) = configures(kitchen)
    assert given == {
        "threadId": thread["threadId"],
        "modelSelection": SELECTION | {"instanceId": PRIME},
    }
    (carry,) = sends(kitchen)
    assert f"read `{side.home / 'tasks' / 'beta.md'}`" in carry["message"]


def test_a_claude_reviewer_moves_in_the_crew_pool_and_one_on_codex_stays(kitchen, pools):
    pools.write_text(CLAUDE_POOL)
    claude = kitchen.t3.thread("alpha", "failed", title="review: alpha")
    codex = kitchen.t3.thread("beta", "failed", title="review: beta")
    codex["selection"] = {"instanceId": "codex", "model": "gpt-6-sol"}
    failed_on(claude, SESSION, notice=("five_hour", SESSION_RESET))
    failed_on(codex, SESSION, ran_on="codex", run="run-2", notice=("five_hour", SESSION_RESET))
    kitchen.poll(FAILED_16TH)
    assert configures(kitchen) == [
        {"threadId": claude["threadId"], "modelSelection": SELECTION | {"instanceId": PRIME}}
    ]
    assert kitchen.lines("stall") == [
        f"capped review beta: codex is capped until {SESSION_RESET.isoformat()}; "
        "it is sent on at the first reset"
    ]


def replayed(kitchen, *more):
    return kitchen.main("--project", "demo", "failover", "--replay", str(RECORDED), *more)


def scratch(kitchen, on="claudeAgent"):
    thread = kitchen.t3.thread("scratch", "completed", title="crew: scratch")
    thread["selection"] = {**SELECTION, "instanceId": on}
    return thread


@pytest.mark.parametrize(("on", "other"), [("claudeAgent", PRIME), (PRIME, "claudeAgent")])
def test_the_replay_moves_a_live_thread_once_and_leaves_the_ledger_alone(kitchen, on, other):
    thread = scratch(kitchen, on)
    code, out = replayed(kitchen, "--thread", thread["threadId"])
    assert code == 0, out
    assert configures(kitchen) == [
        {"threadId": thread["threadId"], "modelSelection": SELECTION | {"instanceId": other}}
    ]
    (carry,) = sends(kitchen)
    assert f"now on {other}" in carry["message"]
    assert carry["clientRequestId"].startswith(f"failover|{thread['threadId']}|replay:")
    assert "failover scratch: five_hour limit until " in out
    assert f"carry-on on {on} to {other}, model claude-sonnet-5-5" in out
    assert ledger.read(["claudeAgent", PRIME]) == {}
    code, again = replayed(kitchen, "--thread", thread["threadId"])
    assert code == 0 and again.startswith("already replayed")
    assert len(sends(kitchen)) == 1 and len(configures(kitchen)) == 1


def test_the_replay_moves_the_recorded_reset_to_now(kitchen):
    """`resets in 17m` at 04:15:27Z is as many minutes after the replay."""
    thread = scratch(kitchen)
    before = datetime.now(UTC)
    code, out = replayed(kitchen, "--thread", thread["threadId"], "--dry-run")
    after = datetime.now(UTC)
    last = datetime(2026, 10, 20, 4, 15, 27, 240000, tzinfo=UTC)
    left = datetime.fromtimestamp(TONIGHT_RESET, UTC) - last
    until = datetime.fromisoformat(out.split("limit until ")[1].split(",")[0])
    assert before + left <= until <= after + left


def test_a_dry_run_replay_prints_the_move_and_writes_nothing(kitchen):
    thread = scratch(kitchen)
    code, out = replayed(kitchen, "--thread", thread["threadId"], "--dry-run")
    assert code == 0
    assert out.startswith("dry run, nothing written: failover scratch: five_hour limit until ")
    assert f"carry-on on claudeAgent to {PRIME}" in out
    written = {"t3_thread_configure", "t3_thread_send", "t3_thread_organize"}
    assert not [tool for tool, _ in kitchen.t3.calls if tool in written]
    assert ledger.read(["claudeAgent", PRIME]) == {}
    assert not [key for key in kitchen.marks() if key.startswith("failover|")]


def test_the_replay_refuses_a_thread_that_is_no_role_of_the_project(kitchen):
    other = kitchen.t3.thread("chat", "completed", title="a chat")
    code, out = replayed(kitchen, "--thread", other["threadId"])
    assert code == 1
    assert (
        out.strip() == f"refused: {other['threadId']} is no crew, reviewer, scout or home of demo"
    )
    assert configures(kitchen) == [] and sends(kitchen) == []


def test_the_replay_fills_the_window_the_ledger_has_running(kitchen):
    """The status line keeps claudeAgent's five-hour window at 42% with a reset later than the
    recording's moved to now: the cap fills that window, as a real cap would, and the thread
    moves."""
    running = datetime.now(UTC) + timedelta(hours=4)
    ledger.write(ledger.Record("claudeAgent", "five_hour", 42, int(running.timestamp())))
    thread = scratch(kitchen)
    code, out = replayed(kitchen, "--thread", thread["threadId"], "--dry-run")
    assert code == 0
    until = datetime.fromtimestamp(int(running.timestamp()), UTC).isoformat()
    assert f"five_hour limit until {until}, carry-on on claudeAgent to {PRIME}" in out


@pytest.mark.parametrize("title", ["review: alpha, scoped", "review: alpha, second pass"])
def test_a_scoped_or_second_reviewer_of_a_task_still_out_moves_though_a_verdict_is_written(
    kitchen, title
):
    """Such a reviewer is launched because the brief has a verdict: it owes its own pass
    until the task is over."""
    kitchen.brief("alpha", REVIEWED)
    thread = kitchen.t3.thread("alpha", "failed", title=title)
    failed_on(thread, SESSION, notice=("five_hour", SESSION_RESET))
    kitchen.poll(FAILED_16TH)
    (given,) = configures(kitchen)
    assert given["modelSelection"]["instanceId"] == PRIME
    assert len(sends(kitchen)) == 1


def test_a_numbered_reviewer_is_told_to_read_its_brief(kitchen):
    thread = kitchen.t3.thread("alpha", "failed", title="review: alpha, 2")
    failed_on(thread, SESSION, notice=("five_hour", SESSION_RESET))
    kitchen.poll(FAILED_16TH)
    (carry,) = sends(kitchen)
    assert f"read `{kitchen.home / 'tasks' / 'alpha.md'}` and the pull request" in carry["message"]
    assert f"jbriefs --skills {kitchen.home / 'tasks' / 'alpha.md'}" in carry["message"]
    assert failovers(kitchen)[0].startswith("failover review alpha: five_hour limit")
