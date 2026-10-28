"""A replay of what woke the root home on 2026-10-27 after 15:00 EDT, run through the pass's own
one list (`jbus.wakes.tell`).

`fixtures/replay/2026-10-27/` holds trimmed copies of that day's `outbox.jsonl` (the 13 messages
that woke the root's thread) and `events.jsonl` (the events behind them: its stalls, its rows to
approve and their go, its leftover). `replay.json` holds what the log does not: the rows and
their heads, the browser runs of the branches the root's wakes name with the failing tests each
log names, the moment main was first told red, and the text of the leftover, which the copy of
the log does not keep. At each of the 13 moments the test sets the kitchen to what it was then and
runs `tell`, which reads the project as the view does (`wrong_items`, `_woken`, `_url`,
`_fixes`), asks the fakes for each red run's jobs and logs, and sends the root what is new to it.
The snapshot alert is a home-thread wake the list does not hold, so it stays as the day had it."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import jbus
from jbus import blockers, leftover, passes, queue, t3, wakes
from test_jbus_kitchen import Kitchen, sends
from test_jbus_queue import add, go

DAY = Path(__file__).parent / "fixtures" / "replay" / "2026-10-27"
REPLAY = json.loads((DAY / "replay.json").read_text())
ROOT = REPLAY["root"]
NEWS = {
    "2026-10-27T19:59": "the first browser red, 15:59 EDT",
    "2026-10-27T21:35": "the snapshot alert, 17:35 EDT",
    "2026-10-27T23:15": "the #576/#579/#580 circle, 19:15 EDT",
}


def lines(name):
    return [json.loads(line) for line in (DAY / name).read_text().splitlines()]


def failing(run):
    return sorted({test for part in run["tests"].split("+") for test in REPLAY["sets"][part]})


def github(kitchen, at):
    """The browser runs GitHub lists at `at`, each failed one's job and the log that names its
    failing tests."""
    runs = [run for run in REPLAY["runs"] if run["created"][:19] <= at]
    listed = [
        {
            "id": run["id"],
            "head_branch": run["branch"],
            "name": "browser",
            "status": "completed",
            "conclusion": run["conclusion"],
            "created_at": run["created"],
            "run_started_at": run["created"],
            "updated_at": run["created"],
            "html_url": f"https://example.test/o/r/actions/runs/{run['id']}",
        }
        for run in runs
    ]
    kitchen.set("runs.json", {"workflow_runs": listed})
    red = [run for run in runs if run["conclusion"] == "failure"]
    job = {"status": "completed", "conclusion": "failure"}
    kitchen.set("run-jobs.json", {str(run["id"]): [{**job, "id": run["id"]}] for run in red})
    logs = {str(run["id"]): "".join(f"FAILED {test}\n" for test in failing(run)) for run in red}
    kitchen.set("logs.json", logs)


def logged(at):
    """The events a pass at `at` reads: a pass of the day logged its lines up to a minute after
    its send, as the outbox and the log show (the root's own row to approve, its leftover and
    its stall), so its moment takes the log up to a minute after it."""
    until = (datetime.fromisoformat(at) + PASS).isoformat()[:19]
    return [one for one in lines("events.jsonl") if one["at"][:19] <= until]


PASS = timedelta(minutes=1)


def approving(events):
    """The rows the log raised a decision to approve of, by slug, with when, and no go since."""
    raised = {
        one["slug"]: one["at"]
        for one in events
        if one["event"] == "decision"
        and one["line"].startswith(f"decision {one['slug']}: approve ")
    }
    for one in events:
        if one["event"] == "item.approved":
            raised.pop(one["line"].split("row ", 1)[1].split()[0], None)
    return raised


def day(kitchen, at):
    """Set the kitchen's state to what it was at `at`, for the sources `tell` reads, and return
    the rows to approve that stand then, as `waiting.keep` lists them: listed past their grace
    before the pass that raised their decision."""
    github(kitchen, at)
    events = logged(at)
    (kitchen.state / "events.jsonl").write_text("".join(f"{json.dumps(one)}\n" for one in events))
    standing = approving(events)
    for slug in ROWS_TO_APPROVE - set(standing):
        row, _ = queue.current(kitchen.state, slug)
        if row and not row.get("approved"):
            assert go(kitchen, slug)[0] == 0
    if at >= REPLAY["main"]["from"]:
        red = REPLAY["main"]["red"].ljust(40, "0")
        jbus.write_json(kitchen.state / "main.json", {"at": at, "main": red, "check": "failed"})
    told = {one["slug"] for one in events if one["event"] == "leftover"}
    left = {slug: {"left": said, "thread": ROOT} for slug, said in REPLAY["left"].items()}
    jbus.write_json(leftover.path(kitchen.state), {slug: left[slug] for slug in told & set(left)})
    grace = timedelta(seconds=blockers.APPROVE_GRACE_SECONDS)
    return [
        {"kind": "approve", "key": f"approve:{slug}", "slug": slug}
        | {"since": (datetime.fromisoformat(since) - grace - PASS).isoformat()}
        | {"line": f"approve {slug}: jbus --project demo queue approve {slug}"}
        for slug, since in standing.items()
    ]


ROWS_TO_APPROVE = {"fl-slot-holder-busy", "red-fix-by-evidence"}
"""The rows the day raised a decision to approve of, after 15:00 EDT."""


def replay(kitchen):
    """Return each old wake's moment, and the lines of the one list's message the root got then.
    The snapshot alert is no item of the list: it is a home-thread wake that stays, as the day
    had it."""
    kitchen.t3.thread("demo", "completed", title="home: demo", threadId=ROOT)
    (kitchen.home / "home-id").write_text(ROOT + "\n")
    for slug, row in REPLAY["rows"].items():
        add(kitchen, slug)
        kitchen.brief(slug, f"Task: {row.get('task', '')}\n")
    rows = json.loads((kitchen.state / "queue.json").read_text())
    for one in rows:
        if one["slug"] in REPLAY["rows"]:
            one |= {"status": "pr", "thread": REPLAY["rows"][one["slug"]]["thread"]}
    (kitchen.state / "queue.json").write_text(json.dumps(rows))
    heads = {slug: {"head": row["head"].ljust(40, "0")} for slug, row in REPLAY["rows"].items()}
    jbus.write_json(kitchen.state / "expedite.json", heads)
    for slug in sorted(ROWS_TO_APPROVE):
        add(kitchen, slug, approve=False)
        kitchen.brief(slug)
    jbus.write_json(kitchen.state / "wake.json", {"began": "2026-10-27T18:00:00+00:00"})
    config = jbus.load()
    client = t3.Client(config.server, config.token_path)
    woken = []
    for sent in lines("outbox.jsonl"):
        at = sent["at"][:19]
        standing = day(kitchen, at)
        now = datetime.fromisoformat(sent["at"])
        before = len(sends(kitchen))
        wakes.tell(passes.Pass(config, config.projects[0], now), client, standing)
        said = [given["message"] for given in sends(kitchen)[before:] if given["threadId"] == ROOT]
        told = [line[2:] for one in said for line in one.splitlines() if line.startswith("- ")]
        stays = ["alert snapshot"] if sent["key"] == ALERT else []
        woken.append((at, told + stays))
    return woken


ALERT = "wake|jstack|340e04e230291b13"
"""The outbox's key of the snapshot alert, which reached the root on the home-thread route."""


def test_the_day_woke_the_root_13_times_after_15_00_edt():
    sent = lines("outbox.jsonl")
    assert len(sent) == 13 and {one["thread"] for one in sent} == {ROOT}
    assert all("2026-10-27T19:00" <= one["at"] for one in sent)


@pytest.fixture
def woken(tmp_path, monkeypatch):
    kitchen = Kitchen(tmp_path, monkeypatch)
    yield replay(kitchen)
    kitchen.close()


def test_under_the_one_list_the_root_wakes_4_times_and_each_news_wake_once(woken):
    said = [(at, told) for at, told in woken if told]
    assert len(said) <= 4
    for minute, news in NEWS.items():
        assert len([at for at, _ in said if at.startswith(minute)]) == 1, news
    stall = next(one["line"] for one in lines("events.jsonl") if one["slug"] == "browser-pin")
    assert said == [
        ("2026-10-27T19:59:18", ["ci fl-msg-no-wrong: browser failed"]),
        (
            "2026-10-27T21:31:14",
            [f"left main-red-d1e3bd5e4c77: {REPLAY['left']['main-red-d1e3bd5e4c77']}"],
        ),
        ("2026-10-27T21:35:00", ["alert snapshot"]),
        ("2026-10-27T23:15:50", [stall]),
    ]


def test_each_wake_the_rule_drops_is_dropped_for_its_own_reason(woken):
    """The root's own row to approve, the same red on main, a red main into the red at its tip,
    the same red on main again, an approval that left the list, the root's own row to approve
    again, a stall of a row whose own red is open, twice, and an approval that left the list."""
    assert [at[:16] for at, told in woken if not told] == [
        "2026-10-27T19:04",
        "2026-10-27T21:27",
        "2026-10-27T21:32",
        "2026-10-27T21:38",
        "2026-10-27T22:05",
        "2026-10-27T22:10",
        "2026-10-27T23:45",
        "2026-10-27T23:47",
        "2026-10-27T23:51",
    ]


def test_a_stall_folds_into_its_rows_red_unless_the_row_is_that_reds_fix():
    red = wakes.Item(key="red|a", to=ROOT, line="ci main: browser failed")
    mine = wakes.Item(key="red|a", to="", line="ci alpha: browser failed", row="alpha")
    stall = wakes.Item(key="stall|alpha", to=ROOT, line="stall alpha", row="alpha", of="red|a")
    assert wakes.pick([red, mine, stall], {"red|a": {}}, ROOT) == []
    fix = wakes.fixes("alpha", 'Task: from jbus "ci main: browser failed"\n', {red.line: red.key})
    circle = wakes.Item(**{**stall.__dict__, "fixes": fix})
    assert wakes.pick([red, mine, circle], {"red|a": {}}, ROOT) == [circle]


def test_an_item_that_leaves_the_list_wakes_no_one_and_its_return_is_news():
    one = wakes.Item(key="main|main|red", to=ROOT, line="main main: red")
    seen = wakes.kept([one], {}, wakes.pick([one], {}, ROOT), "t1")
    assert wakes.pick([], seen, ROOT) == []
    seen = wakes.kept([], seen, [], "t2")
    assert seen == {} and wakes.pick([one], seen, ROOT) == [one]


def test_an_item_the_home_s_own_thread_caused_does_not_wake_it():
    own = wakes.Item(key="approve:alpha", to=ROOT, line="approve alpha", by=ROOT)
    other = wakes.Item(key="approve:beta", to=ROOT, line="approve beta", by="mcp:flow")
    assert wakes.pick([own, other], {}, ROOT) == [other]
