"""jbus sends nothing into a usage cap (sends-hold-capped). A message sent while its thread's
instance is capped starts a turn that ends at once on the limit, so it is spent: on 2026-10-26, 105
runs ended so (day-audit-1026-2). Each send below waits instead in `jbus.outbox`, under its usual
key, with one `wait` line a pass that names its template, and the first pass after the reset sends
it once. The tests
replay small made-up rows through the real pass against the kitchen's fakes, with the cap written
in the ledger (`jroles.ledger`) as the usage hooks write it."""

from datetime import timedelta

from jbus import children
from jroles import ledger
from test_jbus_chains import queue_add
from test_jbus_expedite import Short, later
from test_jbus_failover import PRIME
from test_jbus_github import failed, pull
from test_jbus_held import REASON, Held
from test_jbus_kitchen import NOW, SELECTION
from test_jbus_leftover import ended as leaves
from test_jbus_leftover import home, stalls
from test_jbus_main_moved import checks, move, tip
from test_jbus_main_moved import pull as red
from test_jbus_queue import add, brief, go
from test_jbus_row_ends import listed
from test_jbus_stack import LINK
from test_jbus_stack import pulls as stack

RESETS = NOW + timedelta(minutes=40)
"""The reset of the cap: after every pass a test runs inside it, and before the one after."""


def cap(*instances, resets=RESETS):
    """Write each instance's five-hour window full until `resets`."""
    for instance in instances:
        ledger.file_of(instance).write_text(f"five_hour 100 {int(resets.timestamp())}\n")


def sent(kitchen, kind):
    """Return the keys of the messages of one kind that went to T3 Code."""
    return [given["clientRequestId"] for given in sends(kitchen, kind)]


def sends(kitchen, kind):
    """Return the messages of one kind that went to T3 Code."""
    every = (given for tool, given in kitchen.t3.calls if tool == "t3_thread_send")
    return [given for given in every if given["clientRequestId"].split("|")[0] == kind]


def waits(said, slug, what=""):
    """Return the lines of a pass that say a message to the slug, about `what`, waits for the
    reset."""
    return [
        line
        for line in said
        if line.startswith(f"wait {slug}: ") and "capped" in line and what in line
    ]


def until(kitchen, *minutes):
    """Run a pass at each minute after NOW, and return what each one said."""
    return [kitchen.poll(NOW + timedelta(minutes=minute)) for minute in minutes]


def ended(kitchen):
    """Alpha is a row that a first pass launched, and its thread's turn has ended."""
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - timedelta(minutes=30))
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"


def holds_then_sends_once(kitchen, kind, slug, what):
    """Two passes in the cap send nothing of the kind and each says once that it waits; the
    first pass after the reset sends it once, and the next sends it no more."""
    for said in until(kitchen, 0, 3):
        assert sent(kitchen, kind) == []
        assert len(waits(said, slug, what)) == 1, said
    until(kitchen, 41, 44)
    assert len(sent(kitchen, kind)) == 1


def test_a_rebase_message_waits_for_the_reset(kitchen):
    ended(kitchen)
    kitchen.set("jmerge.txt", "wait 7 https://example.test/pull/7: it conflicts with its base\n")
    kitchen.set("open.json", [pull(kitchen, mergeable="CONFLICTING")])
    cap("claudeAgent")
    holds_then_sends_once(kitchen, "rebase", "alpha", "its rebase message")


def test_a_failed_check_message_waits_for_the_reset(kitchen):
    ended(kitchen)
    kitchen.set("open.json", [pull(kitchen, [failed()])])
    cap("claudeAgent")
    holds_then_sends_once(kitchen, "failed", "alpha", "its failed message")


def test_a_restack_message_waits_for_the_reset(kitchen):
    """`two` builds on `one` (#10) and is stacked on its branch, as `test_jbus_stack` sets it up,
    and the head of `one` moved."""
    kitchen.word()
    kitchen.config(max_running=8)
    assert queue_add(kitchen, "one")[0] == 0 and go(kitchen, "one")[0] == 0
    built = brief("two", "Builds on: one: the table one adds\n")
    assert queue_add(kitchen, "two", "--depends", "one", text=built)[0] == 0
    assert go(kitchen, "two")[0] == 0
    kitchen.poll(NOW - timedelta(minutes=30))
    kitchen.set("open.json", [kitchen.opened("one", 10)])
    kitchen.poll(NOW - timedelta(minutes=27))
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"
    stacked = kitchen
    stack(stacked, base="e" * 40)
    cap("claudeAgent")
    holds_then_sends_once(stacked, "restack", "two", "its restack message")
    assert sent(stacked, "restack") == [f"restack|two|{LINK[:12]}|{'e' * 12}"]


def test_a_main_moved_message_waits_for_the_reset(kitchen):
    """Main was red when alpha launched, and goes green with alpha's pull request red."""
    checks(kitchen, tip(kitchen), "failure")
    ended(kitchen)
    launched = kitchen
    launched.set("open.json", [red(launched, "alpha", 7, "FAILURE")])
    main = move(launched)
    cap("claudeAgent")
    holds_then_sends_once(launched, "mainmoved", "alpha", "its mainmoved message")
    assert sent(launched, "mainmoved") == [f"mainmoved|alpha|#7|{main[:12]}"]


def test_a_crew_carry_on_waits_for_the_reset(kitchen):
    """The clock's carry-on to a crew that stopped before its Result named the pull request."""
    short = Short(kitchen)
    short.out("no brief has a Result that names it", result="", review=False)
    (kitchen.home / "tasks/alpha.md").write_text(short.launched)
    cap("claudeAgent", resets=later(15))
    said = short.passes(15)
    assert sent(kitchen, "clock") == [] and waits(said, "alpha")
    short.passes(15)
    assert len(sent(kitchen, "clock")) == 1


def test_the_clock_s_line_to_the_home_waits_for_the_home_s_reset(kitchen):
    """The crew is carried on, and the second miss is the home's: the home's instance is capped
    while the crew's is not, so the line waits for the home's reset."""
    short = Short(kitchen)
    desk = home(kitchen)
    desk["selection"] = {**SELECTION, "instanceId": PRIME}
    short.out("no brief has a Result that names it", result="", review=False)
    (kitchen.home / "tasks/alpha.md").write_text(short.launched)
    short.passes(10)
    assert len(sent(kitchen, "clock")) == 1
    cap(PRIME, resets=later(30))
    said = short.passes(20)
    assert sent(kitchen, "clock-home") == [] and waits(said, "alpha")
    short.passes(5)
    assert len(sent(kitchen, "clock-home")) == 1


def test_a_hold_stall_line_waits_for_the_reset(kitchen):
    held = Held(kitchen)
    cap("claudeAgent")
    held.until(31)
    for said in until(kitchen, 32, 35):
        rows = "one (#11), two (#12), three (#13), four (#14)"
        assert len(waits(said, rows, "its hold-stall message")) == 1, said
    held.minute = 36
    held.until(39)
    assert held.told() == [] and kitchen.lines("hold-stall") == []
    held.until(44)
    (told,) = held.told()
    assert REASON in told


def test_with_the_whole_pool_capped_a_quiet_child_is_neither_nudged_nor_logged(kitchen):
    home(kitchen)
    found = home(kitchen, "sc", idle=timedelta(hours=6))
    (kitchen.home / "sc" / "plan.md").write_text("# sc: plan\n")
    add(kitchen, "sc-alpha", text=brief("sc-alpha").replace("Home: mcp:a-home", "Home: sc"))
    kitchen.poll(NOW)
    (crew,) = [one for one in kitchen.t3.threads if one["title"] == "crew: sc-alpha"]
    kitchen.t3.at_work.discard(crew["threadId"])
    kitchen.forget()
    patience = children.PATIENCE
    cap("claudeAgent", PRIME, resets=NOW + timedelta(minutes=patience + 30))
    for said in until(kitchen, patience, patience + 10, patience + 20):
        assert sent(kitchen, children.STALL) == []
        assert kitchen.events(children.STALL) == []
        assert len(waits(said, "sc")) == 1, said
    until(kitchen, patience + 31, patience + 35)
    (nudge,) = sends(kitchen, children.STALL)
    assert nudge["threadId"] == found["threadId"]


def test_a_leftover_waits_for_its_home_s_reset_and_is_not_the_users_meanwhile(kitchen):
    """Alpha ended with something left, and its home's thread is capped: the leftover stays the
    home's, so it is not on the user's list while it waits, and goes to the home once after the
    reset."""
    home(kitchen)
    leaves(kitchen)
    cap("claudeAgent")
    for said in until(kitchen, 0, 3):
        assert sent(kitchen, "leftover") == []
        assert len(waits(said, "alpha", "its leftover message")) == 1, said
        assert listed(kitchen) == [] and kitchen.waiting() == []
    until(kitchen, 41, 44)
    assert len(sent(kitchen, "leftover")) == 1
    assert listed(kitchen) == [] and stalls(kitchen) == []
