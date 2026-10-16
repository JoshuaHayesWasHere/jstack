"""Every thread that is out is in `pass.json` with its liveness, and a hung turn is said once.

`live.judge` is walked over every combination of what it is given. The rest runs the real
pass against the faked T3 Code server, `gh` and `jmerge` of `test_jbus_kitchen`. Nothing reaches
the network.
"""

import itertools
import json
from datetime import timedelta

import pytest

from jbus import live, t3
from test_jbus_kitchen import NOW, PROJECT, approved, complete, iso

QUIET, HUNG = 10, 20
STATUSES = (
    "idle",
    "preparing",
    "queued",
    "starting",
    "running",
    "waiting",
    "completed",
    "interrupted",
    "failed",
    "cancelled",
    "rolled_back",
    "a status nobody named",
)
SILENT = (None, -1, 0, QUIET - 0.1, QUIET, HUNG - 0.1, HUNG, 600)
ADDRESS = "http://127.0.0.1:4387/session/"


def test_the_thresholds_are_ten_and_twenty_minutes_each_a_named_constant():
    assert (live.QUIET_MINUTES, live.HUNG_MINUTES) == (10, 20)
    assert live.LIVENESS == ("moving", "quiet", "hung", "waiting", "ended", "unknown")


def test_every_combination_of_what_judge_is_given_keeps_what_the_rule_promises():
    """What must hold of every combination, stated and not worked out a second time."""
    turning = ("preparing", "queued", "starting", "running")
    walked, words = 0, set()
    for status, silent, queued, pending, page in itertools.product(
        STATUSES, SILENT, (0, 1, 3), (0, 1), (False, True)
    ):
        facts = live.Facts(status, silent, queued, pending, page)
        found = live.judge(facts)
        word = found.word
        assert word in live.LIVENESS and found.facts == facts
        if word == "moving":
            assert status in turning and silent is not None and silent < QUIET, facts
        if silent is not None and silent >= QUIET:
            assert word != "moving", facts
        if page or pending:
            assert word not in ("hung", "quiet"), facts
        if word == "hung":
            assert status in turning and silent >= QUIET and (queued or silent >= HUNG), facts
        if word == "quiet":
            assert status in turning and QUIET <= silent < HUNG and not queued, facts
        if status in turning and silent is not None and silent >= HUNG and not (page or pending):
            assert word == "hung", facts
        if status == "a status nobody named" or (silent is None and status in turning):
            assert word == "unknown", facts
        assert (word == "ended") == (status not in (*turning, "waiting", STATUSES[-1])), facts
        walked += 1
        words.add(word)
    assert walked == 12 * 8 * 3 * 2 * 2 and words == set(live.LIVENESS)


@pytest.mark.parametrize(
    ("facts", "word"),
    [
        (live.Facts("running", 9.9), "moving"),
        (live.Facts("running", 10), "quiet"),
        (live.Facts("running", 19.9), "quiet"),
        (live.Facts("running", 10, queued=1), "hung"),
        (live.Facts("running", 20), "hung"),
        (live.Facts("running", 9.9, queued=4), "moving"),
        (live.Facts("running", 240, page=True), "waiting"),
        (live.Facts("running", 240, queued=2, page=True), "waiting"),
        (live.Facts("running", 25, pending=1), "waiting"),
        (live.Facts("waiting", 90), "waiting"),
        (live.Facts("completed", 0), "ended"),
        (live.Facts("running", None), "unknown"),
        (live.Facts("paused", 0), "unknown"),
    ],
)
def test_each_sentence_of_the_rule_holds(facts, word):
    assert live.judge(facts) == live.Liveness(word, facts)


def written(kitchen, key="threads"):
    return json.loads((kitchen.state_dir / "pass.json").read_text())["projects"]["demo"][key]


def reads(kitchen):
    return [given for tool, given in kitchen.t3.calls if tool == "t3_thread_read"]


def run(at, status="running", minutes=30):
    """One run of a thread as T3 Code lists it, asked for this many minutes ago."""
    asked = iso(NOW - timedelta(minutes=minutes))
    began = None if status == "queued" else asked
    return {"runId": f"run-{at}", "ordinal": at, "status": status} | {
        "requestedAt": asked,
        "startedAt": began,
        "completedAt": None,
    }


def hanging(kitchen, slug="alpha", minutes=25, queued=2, **more):
    """A crew whose turn has written nothing for so long, with runs queued behind it."""
    runs = [run(1), *(run(2 + at, "queued", 5) for at in range(queued))]
    made = {"activeRunId": "run-1", "latestRunId": f"run-{len(runs)}", "runs": runs}
    made["itemCount"] = 40
    return kitchen.t3.thread(slug, idle=timedelta(minutes=minutes), **(made | more))


def test_a_pass_leaves_every_unsettled_thread_once_with_its_role_and_its_liveness(kitchen):
    for at, (title, status, idle) in enumerate(
        [
            ("crew: alpha", "running", 2),
            ("review: alpha, second pass", "waiting", 40),
            ("scout: look", "completed", 3),
            ("home: demo", "running", 12),
            ("a thread he opened", "running", 1),
        ]
    ):
        kitchen.t3.thread(f"t{at}", status, title=title, idle=timedelta(minutes=idle))
    kitchen.t3.thread("old", "completed", settled=True)
    kitchen.t3.thread("t0", title="an explorer", parentThreadId="mcp:thread-1")
    kitchen.poll()
    found = written(kitchen)
    assert [
        (t["id"], t["title"], t["role"], t["slug"], t["status"], t["updatedAt"], t["live"])
        for t in found
    ] == [
        ("mcp:thread-1", "crew: alpha", "crew", "alpha", "running", iso(NOW - 2 * MIN), "moving"),
        (
            "mcp:thread-2",
            "review: alpha, second pass",
            "reviewer",
            "alpha",
            "waiting",
            iso(NOW - 40 * MIN),
            "waiting",
        ),
        ("mcp:thread-3", "scout: look", "scout", "look", "completed", iso(NOW - 3 * MIN), "ended"),
        ("mcp:thread-4", "home: demo", "home", "demo", "running", iso(NOW - 12 * MIN), "quiet"),
        ("mcp:thread-5", "a thread he opened", "other", "", "running", iso(NOW - MIN), "moving"),
    ]
    assert found[3] == {
        "id": "mcp:thread-4",
        "title": "home: demo",
        "role": "home",
        "slug": "demo",
        "status": "running",
        "createdAt": iso(NOW - 5 * MIN),
        "updatedAt": iso(NOW - 12 * MIN),
        "items": None,
        "wrote": iso(NOW - 12 * MIN),
        "live": "quiet",
        "silent": 12,
        "run": None,
        "run_started": None,
        "queued": 0,
        "pending": 0,
        "page": False,
    }


MIN = timedelta(minutes=1)


def test_a_status_no_rule_names_is_unknown_with_what_was_given(kitchen):
    kitchen.t3.thread("alpha", "paused", title="scout: alpha", idle=timedelta(minutes=3))
    kitchen.poll()
    (found,) = written(kitchen)
    assert (found["live"], found["status"], found["silent"]) == ("unknown", "paused", 3)
    assert (found["queued"], found["pending"], found["page"]) == (0, 0, False)


def test_a_pass_with_nothing_quiet_reads_no_thread(kitchen):
    kitchen.t3.thread("alpha", "running", idle=timedelta(minutes=9))
    kitchen.t3.thread("beta", "waiting", idle=timedelta(minutes=50), title="review: beta")
    kitchen.t3.thread("gamma", "completed", idle=timedelta(minutes=90), title="scout: gamma")
    kitchen.poll()
    assert reads(kitchen) == []
    lists = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_list"]
    assert lists == [
        {"projectId": PROJECT, "titleContains": "crew: ", "limit": 100},
        {"projectId": PROJECT, "limit": 100, "settled": False},
    ]
    assert {tool for tool, _ in kitchen.t3.calls} == {"t3_thread_list"}


def test_only_a_thread_already_quiet_is_read_once_a_pass(kitchen):
    kitchen.t3.thread("alpha", "running", idle=timedelta(minutes=9))
    quiet = kitchen.t3.thread("beta", "running", idle=timedelta(minutes=10))
    asked = hanging(kitchen, "gamma", minutes=11, queued=1, pendingRequestCount=0)
    waits = hanging(kitchen, "delta", minutes=45, queued=0, pendingRequestCount=1)
    kitchen.poll()
    assert reads(kitchen) == [
        {"threadId": one["threadId"], "limit": 1, "runLimit": 20} for one in (quiet, asked, waits)
    ]
    found = {t["slug"]: t for t in written(kitchen)}
    assert {slug: t["live"] for slug, t in found.items()} == {
        "alpha": "moving",
        "beta": "quiet",
        "gamma": "hung",
        "delta": "waiting",
    }
    assert (found["gamma"]["run"], found["gamma"]["queued"]) == ("run-1", 1)
    assert found["gamma"]["run_started"] == iso(NOW - 30 * MIN)
    assert (found["delta"]["pending"], found["beta"]["run"], found["alpha"]["run"]) == (
        1,
        None,
        None,
    )


def test_a_thread_that_cannot_be_read_is_judged_by_what_the_list_gave(kitchen):
    kitchen.t3.thread("alpha", "running", idle=timedelta(minutes=12))
    kitchen.t3.lose_read = True
    said = kitchen.poll()
    (line,) = [line for line in said if line.startswith("wait alpha")]
    assert line.startswith("wait alpha: its thread could not be read (T3 Code at /mcp ")
    assert written(kitchen)[0]["live"] == "quiet"


def test_a_read_lost_on_one_pass_and_made_on_the_next_is_still_one_stall(kitchen):
    """The list names a thread's newest run, a queued one here, so only a read names the
    run that hangs: a thread that could not be read is quiet at most, and is not said."""
    kitchen.quiet()
    thread = hanging(kitchen)
    kitchen.t3.lose_read = True
    kitchen.poll()
    (found,) = written(kitchen)
    assert (found["live"], found["run"], found["silent"]) == ("quiet", None, 25)
    assert kitchen.lines("stall") == [] and hung(kitchen) == []
    kitchen.t3.lose_read = False
    kitchen.poll(NOW + MIN)
    kitchen.poll(NOW + 2 * MIN)
    assert len(kitchen.lines("stall")) == 1
    assert [(one["thread"], one["run"]) for one in hung(kitchen)] == [(thread["threadId"], "run-1")]


def test_a_hung_call_is_on_record_before_its_event_and_a_record_that_fails_sends_none(kitchen):
    kitchen.quiet()
    hanging(kitchen)
    (kitchen.state / "hung.jsonl").mkdir()
    said = kitchen.poll()
    (line,) = [line for line in said if "hung.jsonl" in line]
    assert line.startswith("wait demo: hung.jsonl could not be written (")
    assert kitchen.lines("stall") == [] and kitchen.status()["projects"]["demo"]["last_error"] == ""
    (kitchen.state / "hung.jsonl").rmdir()
    kitchen.poll(NOW + MIN)
    assert len(kitchen.lines("stall")) == 1 and len(hung(kitchen)) == 1


def test_a_call_whose_run_is_older_than_the_runs_read_stands_while_that_run_is_active(kitchen):
    thread = hanging(kitchen, queued=0)
    kitchen.poll()
    thread["runs"] = [run(at, "queued", 5) for at in range(2, 30)]
    kitchen.poll(NOW + MIN)
    assert [one.get("became") for one in hung(kitchen)] == [None]
    thread |= {"activeRunId": "run-2"}
    kitchen.poll(NOW + 2 * MIN)
    assert [one.get("became") for one in hung(kitchen)][:2] == [None, "ended"]


def test_each_open_row_has_its_threads_liveness(kitchen):
    for slug in ("alpha", "beta"):
        text = complete(slug)
        assert kitchen.main("queue", "add", slug, "--priority", "1", stdin=text)[0] == 0
    hanging(kitchen)
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll()
    rows = written(kitchen, "rows")
    assert (rows["alpha"]["live"], rows["beta"]["live"]) == ("hung", None)
    assert (rows["alpha"]["gone"], rows["beta"]["gone"]) == (False, False)


STALL = 'stall alpha: thread "crew: alpha" has written nothing for 25 min, 2 runs wait behind it'


def hung(kitchen):
    path = kitchen.state / "hung.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_a_thread_that_turns_hung_is_one_loud_event_for_that_thread_and_that_run(kitchen):
    kitchen.quiet()
    thread = hanging(kitchen)
    kitchen.poll()
    assert kitchen.lines("stall") == [STALL]
    assert [one["loud"] for one in kitchen.events("stall")] == ["user"]
    assert [one["line"] for post in kitchen.webhook.posts for one in post] == [STALL]
    kitchen.poll(NOW + MIN)
    kitchen.poll(NOW + 2 * MIN)
    assert kitchen.lines("stall") == [STALL]
    assert hung(kitchen) == [
        {
            "at": iso(NOW),
            "thread": thread["threadId"],
            "title": "crew: alpha",
            "role": "crew",
            "slug": "alpha",
            "run": "run-1",
            "silent": 25,
            "queued": 2,
        }
    ]
    thread["runs"] = [run(1, "interrupted"), run(2, "running", 20), run(3, "queued", 5)]
    wrote = iso(NOW + 3 * MIN - timedelta(minutes=12))
    thread |= {"activeRunId": "run-2", "updatedAt": wrote, "itemCount": 41}
    kitchen.poll(NOW + 3 * MIN)
    assert len(kitchen.lines("stall")) == 2
    assert kitchen.lines("stall")[1].endswith("written nothing for 12 min, 1 run waits behind it")
    assert [(one["run"], one.get("became")) for one in hung(kitchen)] == [
        ("run-1", None),
        ("run-1", "interrupted"),
        ("run-2", None),
    ]


def test_a_message_queued_to_a_silent_thread_is_no_write(kitchen):
    """T3 Code moves a thread's `updatedAt` when a message is queued to it, and not its count
    of items: measured on 2026-10-13, on a thread whose turn ran one long command. The
    message here is a real send to the faked server, which does the same."""
    thread = hanging(kitchen, minutes=8, queued=0)
    kitchen.poll()
    assert (written(kitchen)[0]["live"], kitchen.lines("stall")) == ("moving", [])
    client = t3.Client(kitchen.t3.url, kitchen.config_dir / "t3.json")
    client.recipients = frozenset({thread["threadId"]})
    sent = {"threadId": thread["threadId"], "message": "a wake", "mode": "queue"}
    client.call("t3_thread_send", sent | {"clientRequestId": "a-key"})
    assert thread["updatedAt"] > iso(NOW + 30 * MIN)
    thread["runs"].append(run(2, "queued", 0))
    kitchen.poll(NOW + 2 * MIN)
    (found,) = written(kitchen)
    assert (found["live"], found["silent"], found["queued"]) == ("hung", 10, 1)
    assert (found["wrote"], found["items"]) == (iso(NOW - 8 * MIN), 40)
    assert [line.partition(" for ")[2] for line in kitchen.lines("stall")] == [
        "10 min, 1 run waits behind it"
    ]
    thread["itemCount"] = 41
    kitchen.poll(NOW + 3 * MIN)
    assert written(kitchen)[0]["live"] == "moving"
    assert [one.get("became") for one in hung(kitchen)] == [None, "wrote again"]


def test_one_run_behind_and_none_are_said_in_their_own_words(kitchen):
    hanging(kitchen, "alpha", minutes=10, queued=1)
    hanging(kitchen, "beta", minutes=20, queued=0)
    kitchen.poll()
    assert sorted(line.partition(" for ")[2] for line in kitchen.lines("stall")) == [
        "10 min, 1 run waits behind it",
        "20 min, no run waits behind it",
    ]


@pytest.mark.parametrize(
    ("after", "became"),
    [
        pytest.param(
            {"updatedAt": iso(NOW + MIN), "itemCount": 41}, "wrote again", id="wrote again"
        ),
        pytest.param({"updatedAt": iso(NOW + MIN)}, None, id="a message was queued to it"),
        pytest.param({"runs": [run(1, "interrupted")], "status": "interrupted"}, "interrupted"),
        pytest.param({"runs": [run(1, "cancelled")], "status": "cancelled"}, "interrupted"),
        pytest.param({"runs": [run(1, "completed")], "status": "completed"}, "ended"),
        pytest.param({"runs": [run(1, "failed")], "status": "failed"}, "ended"),
        pytest.param({"settled": True}, "ended", id="settled"),
        pytest.param({}, None, id="still silent"),
    ],
)
def test_a_later_pass_adds_what_became_of_a_hung_call_once(kitchen, after, became):
    thread = hanging(kitchen, queued=0)
    kitchen.poll()
    thread |= after
    kitchen.poll(NOW + MIN)
    kitchen.poll(NOW + 2 * MIN)
    closed = [
        {"at": iso(NOW + MIN), "thread": thread["threadId"], "run": "run-1", "became": became}
    ]
    assert hung(kitchen)[1:] == (closed if became else [])
    assert len(kitchen.lines("stall")) == 1


def test_a_scout_whose_page_still_waits_is_never_hung(kitchen):
    page = f"reports/look.html, {ADDRESS}ab12"
    kitchen.brief("look", f"\n## Report\nStatus: done\nBrief: none   Page: {page}\n", kind="scouts")
    kitchen.t3.thread("look", title="scout: look", idle=timedelta(hours=3))
    kitchen.lavish(ab12=(kitchen.home / "reports" / "look.html", "open"))
    kitchen.poll()
    (found,) = written(kitchen)
    assert (found["live"], found["page"], found["silent"]) == ("waiting", True, 180)
    assert kitchen.lines("stall") == [] and hung(kitchen) == []
    kitchen.lavish(ab12=(kitchen.home / "reports" / "look.html", "ended"))
    kitchen.t3.threads[0]["settled"] = False
    kitchen.brief("look", "", kind="scouts")
    kitchen.poll(NOW + MIN)
    assert written(kitchen)[0]["live"] == "hung"


def test_jbus_interrupts_nothing():
    assert t3.TOOLS == (
        "t3_thread_launch",
        "t3_thread_list",
        "t3_thread_read",
        "t3_thread_send",
        "link_pull_request",
        "t3_thread_organize",
    )
    assert not [tool for tool in t3.TOOLS if "interrupt" in tool]


def test_a_launched_row_whose_thread_t3_no_longer_lists_and_that_wrote_nothing_is_gone(kitchen):
    for slug in ("alpha", "beta", "gamma"):
        text = complete(slug)
        assert kitchen.main("queue", "add", slug, "--priority", "1", stdin=text)[0] == 0
    launches = kitchen.state_dir / "launches" / "demo"
    for slug in ("alpha", "beta", "gamma"):
        (launches / slug).mkdir(parents=True)
        made = {"key": "k", "state": "launched", "thread": f"mcp:{slug}", "at": iso(NOW - MIN)}
        (launches / slug / "abc.json").write_text(json.dumps(made))
    kitchen.brief("beta", "\n## Result\nStatus: done\nBranch: beta\nLeft: none\n")
    kitchen.t3.thread("gamma", "completed", settled=True)
    kitchen.poll()

    def gone():
        return {slug: row["gone"] for slug, row in written(kitchen, "rows").items()}

    assert gone() == {"alpha": True, "beta": False, "gamma": False}
    kitchen.t3.thread("alpha", "running")
    kitchen.t3.thread("alpha", "running")
    kitchen.poll(NOW + MIN)
    assert gone()["alpha"] is False


def test_a_row_launched_in_this_pass_is_not_gone_and_is_once_its_thread_is(kitchen):
    approved(kitchen, "alpha")
    said = kitchen.poll()
    assert [line for line in said if line.startswith("launched alpha")]
    assert written(kitchen, "rows")["alpha"]["gone"] is False
    kitchen.poll(NOW + MIN)
    assert written(kitchen, "rows")["alpha"]["gone"] is False
    kitchen.t3.threads.clear()
    kitchen.poll(NOW + 2 * MIN)
    assert written(kitchen, "rows")["alpha"]["gone"] is True


@pytest.mark.parametrize(("items", "silent"), [(41, 0), (40, 0)])
def test_a_turn_just_started_on_a_thread_that_ended_long_ago_is_not_hung(kitchen, items, silent):
    """A queued message starts a turn and does not move the count of items, so the silence
    of the turn before would be carried into it: it is counted from the run's start."""
    old = run(1, "completed", 90)
    made = {"itemCount": 40, "activeRunId": None, "latestRunId": "run-1", "runs": [old]}
    thread = kitchen.t3.thread("alpha", "completed", idle=timedelta(minutes=60), **made)
    kitchen.poll()
    assert written(kitchen)[0]["live"] == "ended"
    began = iso(NOW + timedelta(seconds=30))
    new = run(2) | {"requestedAt": began, "startedAt": began}
    thread |= {"status": "running", "activeRunId": "run-2", "latestRunId": "run-2"}
    thread |= {"runs": [old, new], "updatedAt": began, "itemCount": items}
    kitchen.poll(NOW + MIN)
    (found,) = written(kitchen)
    assert (found["live"], found["silent"], found["wrote"]) == ("moving", silent, began)
    assert kitchen.lines("stall") == []
    kitchen.poll(NOW + 25 * MIN)
    assert (written(kitchen)[0]["live"], written(kitchen)[0]["silent"]) == ("hung", 24)
