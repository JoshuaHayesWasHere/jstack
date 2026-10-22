"""A message that names a head goes only while that is still the pull request's head and
its crew's thread is not at work, and one conflict is one message. Run as
`features/jbus/tests/test_jbus_guarded_ask.py` runs: the real pass, against the fakes, over commits that
are really there."""

from datetime import timedelta

import pytest

import jbus
from jbus import mainmoved, merge, rebase, t3, wake, watch
from test_jbus_expedite import NO_FIXED, Short
from test_jbus_guarded_ask import URL, Fixed
from test_jbus_kitchen import NOW
from test_jbus_kitchen import review as findings
from test_jbus_main_moved import checks, move, pull, tip
from test_jbus_questions import answer, ask
from test_jbus_queue import add
from test_jbus_remarks import one
from test_jbus_rereview import unsaid, waits
from test_jbus_unlock import CHANGED, sends

KINDS = ("rebase", "rereview", "drops", "proof", "mainmoved")
CONFLICT = "it conflicts with its base"


def later(minutes):
    return NOW + timedelta(minutes=minutes)


def marks(kitchen, kind):
    sent = jbus.read_json(kitchen.state / "sent.json", [])
    return [key for key in sent if key.startswith(f"{kind}|")]


class Due:
    """Alpha, launched by a pass, whose thread ended its turn with pull request #7 open, and
    main moved since. `at` makes one message of the kind due about a head."""

    def __init__(self, kitchen, kind):
        self.kitchen, self.kind = kitchen, kind
        checks(kitchen, tip(kitchen), "failure")
        self.fixed = Fixed(kitchen)
        self.thread, self.head = self.fixed.thread, self.fixed.head
        move(kitchen)

    def at(self, head, mergeable="MERGEABLE"):
        kitchen, red = self.kitchen, self.kind == "mainmoved"
        says = {
            "rebase": f"{CHANGED}: it needs a rebase",
            "rereview": waits(head),
            "drops": unsaid(head),
        }
        if self.kind == "proof":
            return self.fixed.out(head=head)
        opened = pull(kitchen, "alpha", 7, "FAILURE" if red else "SUCCESS", mergeable)
        kitchen.set("open.json", [{**opened, "headRefOid": head}])
        kitchen.set("jmerge.txt", "" if red else f"wait 7 {URL}: {says[self.kind]}\n")


@pytest.mark.parametrize("kind", KINDS)
def test_a_head_the_pull_request_left_since_the_list_is_told_nothing(kitchen, kind):
    due = Due(kitchen, kind)
    pushed = due.fixed.commit("pushed while the pass ran")
    due.at(due.head)
    kitchen.set("head-now.json", {"7": {"headRefOid": pushed}})
    kitchen.poll()
    assert sends(kitchen) == [] and marks(kitchen, kind) == []
    (kitchen.stub / "head-now.json").unlink()
    due.at(pushed)
    for minutes in (3, 6):
        kitchen.poll(later(minutes))
    (given,) = sends(kitchen)
    assert given["clientRequestId"].startswith(f"{kind}|alpha|")
    assert pushed[:12] in given["message"] and due.head[:12] not in given["message"]


def held_while(kitchen, kind, status):
    """One pass with the thread in this status and the message due, then two with it ended."""
    due = Due(kitchen, kind)
    due.at(due.head)
    due.thread["status"] = status
    kitchen.poll()
    assert sends(kitchen) == [] and marks(kitchen, kind) == []
    due.thread["status"] = "completed"
    for minutes in (3, 6):
        kitchen.poll(later(minutes))
    (given,) = sends(kitchen)
    assert given["clientRequestId"].startswith(f"{kind}|alpha|")
    assert due.head[:12] in given["message"]


@pytest.mark.parametrize("kind", KINDS)
def test_a_thread_whose_turn_is_running_is_told_nothing_and_is_told_once_it_ended(kitchen, kind):
    held_while(kitchen, kind, "running")


@pytest.mark.parametrize("status", sorted(set(watch.LIVE) - {"running"}))
def test_a_thread_that_starts_or_waits_on_a_request_is_at_work_too(kitchen, status):
    held_while(kitchen, "rebase", status)


def stale(kitchen, state="SUCCESS", mergeable="CONFLICTING", says=CONFLICT):
    """A pull request `jmerge` calls stale, in conflict or red, in a pass in which main moved."""
    due = Due(kitchen, "rebase")
    opened = {**pull(kitchen, "alpha", 7, state, mergeable), "headRefOid": due.head}
    kitchen.set("open.json", [opened])
    kitchen.set("jmerge.txt", f"wait 7 {URL}: {says}\n")
    return due


RED = {"state": "FAILURE", "mergeable": "MERGEABLE", "says": f"{CHANGED}: it needs a rebase"}


@pytest.mark.parametrize("first", ["rebase", "mainmoved"])
@pytest.mark.parametrize("how", [{}, RED], ids=["in conflict", "red"])
def test_one_stale_head_is_one_message_in_whichever_order_the_two_are_reached(kitchen, first, how):
    due = stale(kitchen, **how)
    config = jbus.load()
    run = wake.Pass(config, config.projects[0], NOW, lambda _: None)
    client = t3.Client(config.server, config.token_path)
    world = watch.look(run, client, []).world
    said = merge.Said(kitchen.stub.joinpath("jmerge.txt").read_text().splitlines())
    tells = {
        "rebase": lambda: rebase.tell(run, client, world, said),
        "mainmoved": lambda: mainmoved.tell(run, client, world),
    }
    for name in sorted(tells, key=lambda name: name != first):
        tells[name]()
    (given,) = sends(kitchen)
    told = first if how else "rebase"
    assert given["clientRequestId"].startswith(f"{told}|alpha|")
    for minutes in (3, 6):
        kitchen.poll(later(minutes))
    assert len(sends(kitchen)) == 1
    assert f"rebase|alpha|{due.head[:12]}" in jbus.read_json(kitchen.state / "sent.json", [])


@pytest.mark.parametrize("how", [{}, RED], ids=["in conflict", "red"])
def test_a_pass_tells_a_stale_head_main_moved_under_by_the_rebase_message_alone(kitchen, how):
    due = stale(kitchen, **how)
    for minutes in (0, 3, 6):
        kitchen.poll(later(minutes))
    (given,) = sends(kitchen)
    assert given["clientRequestId"] == f"rebase|alpha|{due.head[:12]}"
    assert kitchen.lines("mainmoved") == []


def test_a_thread_another_message_of_the_pass_started_is_at_work(kitchen):
    """T3 Code lists the thread as ended when the pass starts, and as running once a message
    of the pass went to it: the status is asked again at the send."""
    due = Due(kitchen, "rebase")
    due.at(due.head)
    asked = []

    def started():
        asked.append(1)
        due.thread["status"] = "completed" if len(asked) == 1 else "running"

    kitchen.t3.on_list = started
    kitchen.poll()
    assert sends(kitchen) == [] and marks(kitchen, "rebase") == []
    kitchen.t3.on_list = None
    due.thread["status"] = "completed"
    kitchen.poll(later(3))
    assert len(sends(kitchen)) == 1


@pytest.mark.parametrize("kind", ["rebase", "mainmoved"])
def test_a_github_that_does_not_give_the_head_again_holds_the_message_back(kitchen, kind):
    due = Due(kitchen, kind)
    due.at(due.head)
    kitchen.set("head-now.json", {"7": {"headRefOid": ""}})
    said = kitchen.poll()
    assert sends(kitchen) == [] and marks(kitchen, kind) == []
    line = "wait alpha: #7 could not be asked for its head, so its crew is not told of "
    assert line + due.head[:12] in said
    (kitchen.stub / "head-now.json").unlink()
    kitchen.poll(later(3))
    assert len(sends(kitchen)) == 1


def test_a_message_held_back_holds_up_no_other_pull_request(kitchen):
    """Alpha is red and at work when main moves, and beta is green. Beta turns red later,
    for its own reasons: it was not red at the move, and is told of its failed check alone."""
    kitchen.config(max_running=2)
    due = Due(kitchen, "mainmoved")
    kitchen.set("jmerge.txt", "")
    add(kitchen, "beta", priority=2)
    kitchen.poll(NOW - timedelta(minutes=10))
    kitchen.t3.threads[1]["status"] = "completed"
    move(kitchen, "failure")
    kitchen.poll(NOW - timedelta(minutes=5))
    main = move(kitchen)
    alpha = {**pull(kitchen, "alpha", 7, "FAILURE"), "headRefOid": due.head}
    kitchen.set("open.json", [alpha, pull(kitchen, "beta", 8)])
    kitchen.set("jmerge.txt", "")
    due.thread["status"] = "running"
    kitchen.poll()
    kept = jbus.read_json(kitchen.state / "main.json", {})
    assert sends(kitchen) == [] and (kept["main"], kept["held"]) == (main, ["alpha"])
    kitchen.set("open.json", [alpha, pull(kitchen, "beta", 8, "FAILURE")])
    kitchen.poll(later(3))
    assert [given["clientRequestId"] for given in sends(kitchen)] == ["failed|beta|cccccccccccc"]
    due.thread["status"] = "completed"
    for minutes in (6, 9):
        kitchen.poll(later(minutes))
    assert [given["clientRequestId"] for given in sends(kitchen)] == [
        "failed|beta|cccccccccccc",
        f"mainmoved|alpha|#7|{main[:12]}",
    ]
    assert "held" not in jbus.read_json(kitchen.state / "main.json", {})


def test_what_a_pull_request_is_short_of_is_not_said_of_a_head_it_left(kitchen):
    short = Short(kitchen)
    short.out(NO_FIXED)
    kitchen.set("head-now.json", {"7": {"headRefOid": short.saw}})
    short.passes(4)
    assert sends(kitchen) == [] and marks(kitchen, "unfixed") == []
    (kitchen.stub / "head-now.json").unlink()
    short.passes(2)
    (given,) = sends(kitchen)
    assert given["clientRequestId"] == f"unfixed|alpha|{short.head[:12]}"


def running(kitchen, text=""):
    """Alpha's crew at work in a turn, with its pull request #7 open."""
    thread = kitchen.t3.thread("alpha", "running")
    kitchen.brief("alpha", f"Thread: {thread['threadId']}\n{text}")
    kitchen.set("open.json", [pull(kitchen, "alpha", 7)])
    return thread["threadId"]


def test_findings_the_reviewer_could_not_deliver_go_to_a_thread_at_work(kitchen):
    thread = running(kitchen, findings())
    kitchen.poll()
    (given,) = sends(kitchen)
    assert given["threadId"] == thread and given["clientRequestId"].startswith("relayed|alpha|")


def test_what_the_owner_wrote_goes_to_a_thread_at_work(kitchen):
    thread = running(kitchen)
    kitchen.set("repo.json", {"owner": {"login": "ada"}})
    kitchen.set("remarks.json", {"issues/7/comments": [one(1, "ada", "use a table here")]})
    kitchen.poll()
    (given,) = sends(kitchen)
    assert given["threadId"] == thread and given["clientRequestId"].startswith("remark|alpha|")


def test_an_answer_that_differs_goes_to_a_thread_at_work(kitchen):
    thread = running(kitchen)
    kitchen.quiet()
    ask(kitchen)
    kitchen.poll()
    answer(kitchen, 1, "coffee")
    kitchen.poll(later(10))
    (given,) = sends(kitchen)
    assert (given["threadId"], given["clientRequestId"]) == (thread, "answer|alpha|1")
