"""`jbus flow` measures a window from the records and writes nothing.

The tests write fixture records as jbus writes them: a project's `events.jsonl` with the queue's
table in its `queue` events, jbus's journal as `journalctl -o short-iso` prints it, and GitHub's
Actions runs (the recording `ci_replay` replays, and runs made here). They run the verb through
`jbus.cli.main` and read what it prints.
"""

import contextlib
import io
import json
from datetime import UTC, datetime, timedelta

import pytest

from ci_replay import FOLDER
from jbus import cli
from jbus.flow import machine, rows, runs

START = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
COLUMNS = (
    "slug priority depends merge_after approved brief_sha entry status thread pr checks "
    "updated why since"
).split()
GO = "his word, 2026-10-20 08:00 EDT"


def at(hours):
    return (START + timedelta(hours=hours)).isoformat()


def line(slug, status, why="", checks="", approved=GO, pr=""):
    cells = dict.fromkeys(COLUMNS, "")
    cells.update(slug=slug, status=status, why=why, checks=checks, approved=approved, pr=pr)
    return "| " + " | ".join(cells[name] for name in COLUMNS) + " |"


def changed(hours, *lines):
    """Return a `queue` event as a pass writes it: what changed, then the table of those rows."""
    text = "\n".join(
        [
            "a: status queued -> launched",
            "",
            "| " + " | ".join(COLUMNS) + " |",
            "| " + " | ".join("---" for _ in COLUMNS) + " |",
            *lines,
        ]
    )
    return {
        "at": at(hours),
        "event": "queue",
        "line": "queue demo: the table changed",
        "text": text,
    }


EVENTS = [
    changed(0, line("a", "queued", approved="")),
    changed(1, line("a", "launched")),
    changed(2, line("a", "running")),
    changed(4, line("a", "pr", "wait: it has no review yet", "passed")),
    changed(7, line("a", "pr", "wait: check has not passed", "failed")),
    changed(
        8, line("a", "pr", "wait: main is red at 0123456789ab, its fix merges first", "failed")
    ),
    changed(9, line("a", "merged")),
    changed(1, line("b", "pr", "wait: its queue row is held: approve it again", "passed")),
    {"at": at(6), "event": "item.dropped", "line": "item demo: w2 dropped: row b was removed"},
    changed(2, line("c", "pr", "wait: something new jbus says", "passed")),
    changed(3, line("d", "merged")),
    {"at": at(3), "event": "heartbeat", "line": "heartbeat"},
    {"at": "not a time", "event": "queue", "text": ""},
]


def state_with(tmp_path, events, name="demo"):
    state = tmp_path / "state"
    (state / name).mkdir(parents=True)
    (state / name / "events.jsonl").write_text(
        "".join(json.dumps(one) + "\n" for one in events) + "{broken\n"
    )
    (state / "launches").mkdir()
    return state


def flow(monkeypatch, tmp_path, state, *args, config=None):
    monkeypatch.setenv("JBUS_STATE_DIR", str(state))
    folder = tmp_path / "config"
    folder.mkdir(exist_ok=True)
    if config is not None:
        (folder / "config.toml").write_text(config)
        (folder / "config.toml").chmod(0o600)
    monkeypatch.setenv("JBUS_CONFIG_DIR", str(folder))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["flow", *args])
    return code, out.getvalue()


def numbers(monkeypatch, tmp_path, events=EVENTS, journal=""):
    state = state_with(tmp_path, events)
    lines = tmp_path / "journal.txt"
    lines.write_text(journal)
    code, said = flow(
        monkeypatch,
        tmp_path,
        state,
        "--since",
        at(-1),
        "--until",
        at(10),
        "--offline",
        "--journal",
        str(lines),
        "--json",
        "--rows",
    )
    assert code == 0
    return json.loads(said)


def test_a_merged_row_s_time_from_approved_to_merged_is_split_into_working_and_waiting(
    monkeypatch, tmp_path
):
    led = numbers(monkeypatch, tmp_path)["lead"]
    assert led["merged"] == 1
    (one,) = led["rows"]
    assert (one["slug"], one["hours"], one["working"], one["waiting"]) == ("a", 8.0, 3.0, 5.0)
    assert (one["worst"], one["worst_hours"]) == ("first review not written", 3.0)


def test_the_wait_reasons_are_ranked_by_the_row_hours_they_cost(monkeypatch, tmp_path):
    ranked = numbers(monkeypatch, tmp_path)["pareto"]
    assert [(one["reason"], one["hours"], one["rows"]) for one in ranked][:3] == [
        ("pr: wait", 8.0, 1),
        ("held for his word", 5.0, 1),
        ("first review not written", 3.0, 1),
    ]
    assert {one["reason"]: one["hours"] for one in ranked[3:]} == {
        "check failed, nobody acting": 1.0,
        "main or its train is red": 1.0,
    }
    assert [one["cumulative"] for one in ranked][:2] == [0.444, 0.722]
    assert ranked[-1]["cumulative"] == 1.0


def test_a_state_no_rule_places_is_counted_unexplained_and_its_share_printed(monkeypatch, tmp_path):
    found = numbers(monkeypatch, tmp_path)
    assert found["unexplained"] == {"row_hours": 8.0, "waiting_row_hours": 18.0, "share": 0.444}
    assert found["stages"]["work"] == 3.0


def test_a_removed_row_stops_its_clock_and_a_row_first_seen_merged_has_none(monkeypatch, tmp_path):
    held = [
        one
        for one in numbers(monkeypatch, tmp_path)["pareto"]
        if one["reason"] == "held for his word"
    ]
    assert held[0]["hours"] == 5.0
    walked = {row.slug: row for row in rows.walk("demo", EVENTS, START + timedelta(hours=10))}
    assert set(walked) == {"a", "b", "c"}
    assert (walked["b"].end, walked["a"].end, walked["c"].end) == ("removed", "merged", "")


def test_a_jmerge_line_about_a_row_s_pull_request_is_its_why_until_the_next_line():
    events = [
        changed(0, line("e", "pr", "wait: it has no review yet", "passed", pr="#7")),
        {
            "at": at(1),
            "event": "jmerge",
            "line": "hold 7 https://example.test/o/r/pull/7: needs JoshuaHayesWasHere, touches x",
        },
        {"at": at(2), "event": "jmerge", "line": "wait 8 https://example.test/o/r/pull/8: draft"},
        changed(3, line("e", "merged", pr="#7")),
    ]
    (row,) = rows.walk("demo", events, START + timedelta(hours=4))
    assert [(span.name, span.hours) for span in row.spans] == [
        ("first review not written", 1.0),
        ("held for his word", 2.0),
    ]


def test_main_red_holds_up_the_rows_that_wait_on_it(monkeypatch, tmp_path):
    red = numbers(monkeypatch, tmp_path)["main_red"]
    assert (red["rows_held"], red["row_hours_held"]) == (1, 1.0)


def test_the_part_of_the_window_before_the_first_event_is_said(monkeypatch, tmp_path):
    kept = numbers(monkeypatch, tmp_path)["records"]
    assert kept["events_missing_hours"] == {"demo": 1.0}
    assert kept["github_not_asked"] == {"demo": "--offline"}


JOURNAL = "\n".join(
    [
        "2026-10-20T08:00:00-04:00 host systemd[1]: Starting jbus: launch what was approved...",
        "2026-10-20T08:00:01-04:00 host jbus[2]: wait a: no room: load 30.1 is at or over 85%"
        " of 24 cores",
        "2026-10-20T08:00:01-04:00 host jbus[2]: wait b: no room: load 31.9 is at or over 85%"
        " of 24 cores",
        "2026-10-20T08:01:00-04:00 host systemd[1]: Starting jbus: launch what was approved...",
        "2026-10-20T08:01:01-04:00 host jbus[3]: wait scout s: no launch: claudeAgent and codex are"
        " both capped until 2026-10-20T13:00:00+00:00",
        "2026-10-20T08:01:02-04:00 host jbus[3]: wake failed demo: the webhook answered 404",
        "2026-10-20T08:03:00-04:00 host systemd[1]: Starting jbus: launch what was approved...",
        "2026-10-20T08:03:05-04:00 host systemd[1]: jbus.service: Failed with result 'exit-code'.",
        "2026-10-20T08:04:00-04:00 host systemd[1]: Starting jbus: launch what was approved...",
        "2026-10-20T08:04:01-04:00 host jbus[4]: wait demo: could not ask GitHub: gh exited 1",
        "a line that is not the journal's",
        "2026-10-20T09:00:00-04:00 host systemd[1]: Starting jbus: launch what was approved...",
    ]
)


def test_the_journal_gives_the_hours_with_no_room_by_why_and_the_passes_that_failed(
    monkeypatch, tmp_path
):
    room = numbers(monkeypatch, tmp_path, journal=JOURNAL)["machine"]
    assert room["by_why"] == {
        "no launch: every account capped": {"hours": 0.0, "passes": 1},
        "no room: load at or over 85% of the cores": {"hours": 0.0, "passes": 1},
    }
    assert room["rows_told_no_room"] == {"a": 1, "b": 1}
    assert (room["passes_failed"], room["passes_github_unreachable"]) == (1, 1)
    assert room["wakes_failed"] == {"demo: the webhook answered N": 1}


def test_a_pass_s_reason_holds_until_the_next_pass_and_no_longer_than_the_hold():
    until = datetime(2026, 10, 20, 13, 1, tzinfo=UTC)
    made = machine.machine(JOURNAL.splitlines(), START - timedelta(hours=8), until)
    assert made.passes == 5
    spans = {why: end - start for start, end, why in made.no_room}
    assert spans == {
        "no room: load at or over 85% of the cores": timedelta(minutes=1),
        "no launch: every account capped": timedelta(minutes=2),
    }
    assert [(end - start, why) for start, end, why in made.down] == [
        (timedelta(minutes=1), "the pass failed"),
        (timedelta(minutes=46), "no pass ran"),
    ]


def run(name, branch, event, conclusion, created, started, ended, attempt=1, number=0):
    return {
        "id": number or hash((name, created, ended)) % 10**9,
        "name": name,
        "head_branch": branch,
        "event": event,
        "status": "completed",
        "conclusion": conclusion,
        "created_at": created,
        "run_started_at": started,
        "updated_at": ended,
        "run_attempt": attempt,
    }


RUNS = [
    run(
        "check",
        "main",
        "push",
        "success",
        "2026-10-20T10:00:00Z",
        "2026-10-20T10:02:00Z",
        "2026-10-20T10:10:00Z",
        number=1,
    ),
    run(
        "check",
        "main",
        "push",
        "failure",
        "2026-10-20T11:00:00Z",
        "2026-10-20T11:01:00Z",
        "2026-10-20T11:10:00Z",
        number=2,
    ),
    run(
        "check",
        "pr-1",
        "pull_request",
        "failure",
        "2026-10-20T11:20:00Z",
        "2026-10-20T11:21:00Z",
        "2026-10-20T11:30:00Z",
        number=3,
    ),
    run(
        "check",
        "main",
        "push",
        "cancelled",
        "2026-10-20T11:40:00Z",
        "2026-10-20T11:41:00Z",
        "2026-10-20T11:50:00Z",
        number=4,
    ),
    run(
        "check",
        "main",
        "push",
        "success",
        "2026-10-20T12:00:00Z",
        "2026-10-20T12:05:00Z",
        "2026-10-20T13:10:00Z",
        attempt=3,
        number=5,
    ),
    run(
        "release",
        "main",
        "push",
        "failure",
        "2026-10-20T12:30:00Z",
        "2026-10-20T12:30:00Z",
        "2026-10-20T12:31:00Z",
        number=6,
    ),
]


def test_main_is_red_from_a_failed_run_to_the_next_passed_run_of_the_same_workflow():
    found = runs.red(RUNS, "main", datetime(2026, 10, 20, 14, tzinfo=UTC))
    assert [
        (start.hour, start.minute, end.hour, end.minute, name) for start, end, name in found
    ] == [
        (11, 10, 13, 10, "check"),
        (12, 31, 14, 0, "release"),
    ]


def test_the_runs_give_queue_time_run_time_cancels_reruns_and_pull_requests_run_red():
    made = runs.count("o/r", RUNS, "main", datetime(2026, 10, 20, 14, tzinfo=UTC))
    assert (made.runs, made.failed, made.cancelled, made.rerun, made.attempts) == (6, 3, 1, 1, 2)
    assert sorted(made.queued) == [0.0, 1.0, 1.0, 1.0, 2.0, 5.0]
    assert made.ran_red == 1
    assert runs.spread(made.queued).startswith("median 1.0 min, p90 5.0 min")


def test_runs_are_asked_one_day_a_call_and_each_kept_once():
    recorded = json.loads((FOLDER / "runs.json").read_text())
    asked = []

    def ask(path):
        asked.append(path)
        return [{"workflow_runs": recorded}]

    since = datetime(2026, 10, 14, 4, tzinfo=UTC)
    until = datetime(2026, 10, 17, 22, 15, tzinfo=UTC)
    kept = runs.fetch(ask, "o/r", since, until)
    assert [path.split("created=")[1].split("&")[0] for path in asked] == [
        "2026-10-14",
        "2026-10-15",
        "2026-10-16",
        "2026-10-17",
    ]
    inside = {one["id"] for one in recorded if since <= runs.when(one["created_at"]) <= until}
    assert {one["id"] for one in kept} == inside and len(kept) == len(inside)


def test_it_writes_nothing_under_the_state(monkeypatch, tmp_path):
    state = state_with(tmp_path, EVENTS)
    (tmp_path / "none.txt").write_text(JOURNAL)
    before = {path: path.read_bytes() for path in state.rglob("*") if path.is_file()}
    code, said = flow(
        monkeypatch,
        tmp_path,
        state,
        "--since",
        at(-1),
        "--until",
        at(10),
        "--offline",
        "--journal",
        str(tmp_path / "none.txt"),
    )
    assert code == 0 and said.startswith("jbus flow: ")
    after = {path: path.read_bytes() for path in state.rglob("*") if path.is_file()}
    assert after == before


SECRET = "https://example.test/hidden-path-of-the-hook"


def test_a_secret_of_the_config_never_reaches_the_output(monkeypatch, tmp_path):
    state = state_with(tmp_path, [changed(0, line("a", "pr", f"wait: posted to {SECRET}"))])
    (tmp_path / "journal.txt").write_text(
        "2026-10-20T08:00:00-04:00 host systemd[1]: Starting jbus...\n"
        f"2026-10-20T08:00:01-04:00 host jbus[2]: wake failed demo: the webhook {SECRET} is down\n"
    )
    config = "\n".join(
        [
            'server = "http://127.0.0.1:1/"',
            "[[project]]",
            'name = "demo"',
            f'checkout = "{tmp_path}"',
            'projectId = "p"',
            f'webhook_url = "{SECRET}"',
            'webhook_key = "the-key-of-the-hook"',
        ]
    )
    code, said = flow(
        monkeypatch,
        tmp_path,
        state,
        "--since",
        at(-1),
        "--until",
        at(10),
        "--offline",
        "--journal",
        str(tmp_path / "journal.txt"),
        config=config,
    )
    assert code == 0 and "wake failed demo: the webhook" in said
    assert "hidden-path" not in said and "example.test" not in said


def test_a_journal_file_that_cannot_be_read_is_refused(monkeypatch, tmp_path):
    code, said = flow(monkeypatch, tmp_path, tmp_path, "--offline", "--journal", "/nowhere")
    assert (code, said) == (
        2,
        "refused: the journal file cannot be read: No such file or directory\n",
    )


def test_a_window_that_ends_before_it_starts_is_refused(monkeypatch, tmp_path):
    code, said = flow(
        monkeypatch, tmp_path, tmp_path, "--since", at(2), "--until", at(1), "--offline"
    )
    assert (code, said) == (2, "refused: --since is not before --until\n")


@pytest.mark.parametrize(
    ("status", "why", "checks", "named"),
    [
        ("running", "", "", ("work", "crew at work")),
        (
            "pr",
            "wait: its second review is not written at 0123456789ab",
            "",
            ("review", "second or scoped review not written"),
        ),
        ("pr", "wait: a fresh check is queued", "pending", ("check", "check running or queued")),
        (
            "pr",
            "wait: train/macos is red at 0123456789ab: its latest check failed",
            "",
            ("main", "main or its train is red"),
        ),
        (
            "gate",
            "brief changed after approval, now 0123456789ab",
            "",
            ("josh", "approval voided, brief changed"),
        ),
        ("queued", "depends on mv-21-why", "", ("queue", "depends on another row")),
        (
            "pr",
            "wait: jgauge test-slot -- make check fails on 0123456789ab over today's main 0123",
            "passed",
            ("check", "fresh check over today's main failed"),
        ),
        ("stale", "", "", ("stopped", "thread ended with no Result")),
    ],
)
def test_each_status_and_why_the_table_shows_has_its_stage(status, why, checks, named):
    assert rows.classify(rows.State(status, why, checks, True)) == named
