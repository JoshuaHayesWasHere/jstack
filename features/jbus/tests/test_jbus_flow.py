"""`jbus flow` measures how work flowed in a window from the records, and writes nothing.

The tests drive the readers and the measure on fixture records: an event log, journal text and
GitHub's run objects written here, with no command run. The last tests run the real command in
the kitchen of `test_jbus_kitchen`, with the journal and GitHub answered by a fake `ask`.

`ALPHA` is a row approved at 10:00 EDT, which is `T`, that waits behind the rows in front of it
for an hour, works with a cap in the middle, waits for its review and for a red main, and merges
four hours after its approval. `BETA` was never approved and never launched, so it is no work
of the window.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from jbus import flow
from jbus.flow import measure, records
from test_jbus_kitchen import KEY, Kitchen

T = datetime(2026, 10, 20, 14, 0, tzinfo=UTC)
TABLE = (
    "| slug | priority | depends | merge_after | approved | brief_sha | entry | status | thread "
    "| pr | checks | updated | why | since |\n| --- | --- | --- | --- | --- | --- | --- | --- "
    "| --- | --- | --- | --- | --- | --- |\n"
)


def at(hours):
    return T + timedelta(hours=hours)


def event(when, kind, line="", text="", slug="", loud="quiet"):
    stamp = when.isoformat(timespec="seconds")
    record = {"at": stamp, "event": kind, "line": line, "text": text, "slug": slug, "loud": loud}
    return json.dumps(record)


def table(when, slug, status, *, checks="", why="", pr="", thread="", approved=""):
    """Return a `queue` event whose table shows the row as given."""
    cells = [slug, "1", "", "", approved, "", "", status, thread, pr, checks, "", why, ""]
    row = "| " + " | ".join(cells) + " |\n"
    return event(when, "queue", "queue demo: the table changed", f"{slug}: changed\n\n{TABLE}{row}")


def item(when, slug, said):
    return event(when, "item.queued", f"item demo: w1 queued: row {slug} {said}")


ALPHA = [
    item(at(0), "alpha", "has a go: your word, 2026-10-20 10:00 EDT, in home: demo"),
    item(at(0), "alpha", "is behind"),
    item(at(1), "alpha", "is launching"),
    table(at(1) + timedelta(minutes=1), "alpha", "running", thread="mcp:t-alpha"),
    event(
        at(1) + timedelta(minutes=10),
        "stall",
        f"capped alpha: claudeAgent is capped until {at(1.5).isoformat()}",
        loud="user",
    ),
    table(at(2), "alpha", "pr", checks="pending", pr="#7", thread="mcp:t-alpha"),
    event(at(2.5), "jmerge", "wait 7 https://example.test/pull/7: it has no review yet"),
    table(at(2.5), "alpha", "pr", checks="passed", pr="#7", thread="mcp:t-alpha"),
    event(at(3), "jmerge", "wait 7 https://example.test/pull/7: main is red at abc123def456"),
    event(at(4), "merged", "merged alpha #7 0123456789ab"),
    table(at(4), "alpha", "merged", checks="passed", pr="#7"),
]
BETA = [item(at(0), "beta", "is unapproved"), table(at(0), "beta", "queued", why="not approved")]


def project(lines=ALPHA + BETA):
    return records.events("demo", lines)


def test_a_row_is_cut_into_its_working_and_its_waits():
    row = measure.row_spans(project(), "alpha", at(-48), at(48), {})
    spans = [(span.what, round(span.hours, 2)) for span in row.spans]
    assert spans == [
        ("ordering", 1.0),
        ("crew at work", 0.17),
        ("account cap", 0.33),
        ("crew at work", 0.5),
        ("checks running", 0.5),
        ("review not written", 0.5),
        ("main red", 1.0),
    ]
    assert row.approved == at(0) and row.merged == at(4)
    assert round(row.hours(True), 2) == 1.17 and round(row.hours(False), 2) == 2.83


def test_github_merge_time_wins_over_the_log():
    row = measure.row_spans(project(), "alpha", at(-48), at(48), {"7": at(3.5)})
    assert row.merged == at(3.5)
    assert row.spans[-1].what == "main red" and row.spans[-1].end == at(3.5)


def test_a_row_never_approved_is_left_out():
    assert measure.row_spans(project(), "beta", at(-48), at(48), {}) is None


def test_a_removed_row_ends_where_it_was_removed():
    gone = [item(at(0), "gamma", "has a go: your word, 2026-10-20 10:00 EDT")]
    gone += [item(at(0), "gamma", "is behind"), item(at(2), "gamma", "was removed")]
    row = measure.row_spans(records.events("demo", gone), "gamma", at(-48), at(48), {})
    assert [(span.what, span.hours) for span in row.spans] == [("ordering", 2.0)]
    assert row.merged is None


def test_the_window_clips_a_row():
    row = measure.row_spans(project(), "alpha", at(2.75), at(3.5), {})
    assert [(span.what, span.start, span.end) for span in row.spans] == [
        ("review not written", at(2.75), at(3)),
        ("main red", at(3), at(3.5)),
    ]
    assert row.merged is None


def test_a_row_approved_before_any_record_waits_on_no_record():
    late = [
        table(
            at(2),
            "gamma",
            "pr",
            checks="failed",
            pr="#9",
            approved="his word, 2026-10-20 09:00 EDT",
        )
    ]
    row = measure.row_spans(records.events("demo", late), "gamma", at(-48), at(3), {})
    assert [(span.what, span.hours) for span in row.spans] == [
        ("no record", 3.0),
        ("check failed", 1.0),
    ]


def test_the_pareto_ranks_the_waits_and_marks_what_is_unexplained():
    found = measure.rows([project()], at(-48), at(48), {})
    ranked = measure.pareto(found)
    assert [one["class"] for one in ranked] == [
        "ordering",
        "main red",
        "review not written",
        "account cap",
    ]
    assert ranked[0]["cumulative"] < ranked[-1]["cumulative"] == 1.0
    assert not any(one["unexplained"] for one in ranked)


@pytest.mark.parametrize(
    ("why", "checks", "named"),
    [
        ("wait: main is red at abc, its fix merges first", "", "main red"),
        ("wait: it has no review yet", "", "review not written"),
        (
            "wait: its findings are not handled: the Result has no Fixed line",
            "",
            "findings not fixed",
        ),
        ("hold: needs JoshuaHayesWasHere, touches policy/tailnet.hujson", "", "owner: hand-merge"),
        ("wait: check has not passed", "failed", "check failed"),
        ("wait: check has not passed", "pending", "checks running"),
        ("wait: a fresh check is queued", "", "fresh check queued"),
        ("depends on ft-main-contract", "", "ordering"),
    ],
)
def test_why_a_row_waits_names_its_class(why, checks, named):
    assert measure.why_class(why, checks) == named


LOAD = "no room: load 30.1 is at or over 85% of 24 cores"
STARTING = "systemd[1]: Starting jbus: launch what was approved"
JOURNAL = "\n".join(
    [
        f"2026-10-20T10:00:01-04:00 host {STARTING}",
        f"2026-10-20T10:00:05-04:00 host jbus[2]: wait alpha: {LOAD}",
        f"2026-10-20T10:01:05-04:00 host jbus[2]: wait alpha: {LOAD}",
        f"2026-10-20T10:01:00-04:00 host {STARTING}",
        f"2026-10-20T10:30:00-04:00 host {STARTING}",
        f"2026-10-20T10:30:05-04:00 host jbus[3]: wait beta: {LOAD}",
        "2026-10-20T10:31:00-04:00 host systemd[1]: Failed to start jbus: launch what was approved",
        "2026-10-20T10:32:00-04:00 host jbus[4]: capped beta: claudeAgent_x is capped until "
        "2026-10-20T15:02:00+00:00",
        "not a line of the journal",
    ]
)


def test_the_journal_gives_no_room_caps_and_the_passes():
    lines = records.journal(JOURNAL)
    room = measure.no_room(lines, at(-1), at(2))
    assert room["spans"] == 2 and room["rows_held"] == 2
    assert room["hours"] == round((2 + 1) / 60, 1)
    assert list(room["by_reason"]) == ["load over 85% of the cores"]
    bus = measure.jbus_down(lines, at(-1), at(2))
    assert bus["passes"] == 3 and bus["failed_passes"] == 1 and bus["gaps_over_10_min"] == 1
    cap = measure.caps([project([])], lines, at(-1), at(2))
    assert cap["by_account"] == {"claudeAgent_x": 0.5} and cap["rows_held"] == 1


def run(number, when, conclusion, *, branch="main", event="push", minutes=5, attempt=1):
    return {
        "id": number,
        "name": "check",
        "event": event,
        "head_branch": branch,
        "conclusion": conclusion,
        "run_attempt": attempt,
        "created_at": when.isoformat(),
        "run_started_at": when.isoformat(),
        "updated_at": (when + timedelta(minutes=minutes)).isoformat(),
    }


def test_main_is_red_from_a_failed_check_to_the_next_that_passes():
    listed = [
        run(1, at(0), "success"),
        run(2, at(1), "failure"),
        run(3, at(2), "failure"),
        run(4, at(3), "success"),
        run(5, at(2), "failure", branch="topic", event="pull_request", attempt=2),
    ]
    jobs = {
        5: [
            {
                "created_at": at(2).isoformat(),
                "started_at": at(2.25).isoformat(),
                "completed_at": at(2.5).isoformat(),
                "labels": ["self-hosted"],
            }
        ]
    }
    found = records.runs("o/demo", listed, jobs)
    found_rows = measure.rows([project()], at(-48), at(48), {})
    red = measure.main_red(found, found_rows, {"o/demo": {"7": at(1.5), "8": at(5)}})
    assert red["repos"]["o/demo"] == {
        "gate": "check",
        "red_hours": 2.0,
        "red_spans": 1,
        "merges_while_red": 1,
    }
    assert red["rows_held"] == 1 and red["row_hours_held"] == 1.0
    said = measure.ci(found)["o/demo"]
    assert (said["runs"], said["failure"], said["reruns"], said["jobs"]) == (5, 3, 1, 1)
    assert said["queue_hours"] == 0.2 and said["queue_self_hosted_hours"] == 0.2


def test_jobs_are_refused_when_they_would_spend_half_the_budget(monkeypatch):
    listed = [json.dumps(run(n, at(0), "success")) for n in range(30)]

    def ask(command, cwd=None):
        if command[:3] == ["gh", "api", "rate_limit"]:
            return "50\n"
        return "\n".join(listed)

    monkeypatch.setattr(records, "ask", ask)
    with pytest.raises(records.Unaffordable):
        records.github_runs("o/demo", at(-1), at(1), jobs=True)
    assert len(records.github_runs("o/demo", at(-1), at(1), jobs=False)) == 30


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def test_the_command_prints_the_measure_writes_nothing_and_holds_no_secret(kitchen, monkeypatch):
    secret = table(
        at(2.6),
        "delta",
        "pr",
        pr="#8",
        why=f"wait: see {KEY}",
        approved="his word, 2026-10-20 10:00 EDT",
    )
    kitchen.state.mkdir(parents=True, exist_ok=True)
    (kitchen.state / "events.jsonl").write_text("\n".join([*ALPHA, *BETA, secret]) + "\n")
    asked = []

    def ask(command, cwd=None):
        asked.append(command[0])
        return JOURNAL if command[0] == "journalctl" else None

    monkeypatch.setattr(records, "ask", ask)
    before = {path: path.stat().st_mtime_ns for path in kitchen.state_dir.rglob("*")}
    code, out = kitchen.main(
        "flow", "--since", "2026-10-20T00:00", "--until", "2026-10-21T00:00", "--json"
    )
    assert code == 0, out
    said = json.loads(out)
    assert KEY not in out
    assert {path: path.stat().st_mtime_ns for path in kitchen.state_dir.rglob("*")} == before
    assert said["rows"] == 2 and said["lead_times"]["merged"] == 1
    assert said["no_room"]["spans"] == 2
    assert said["unexplained_share"] > 0
    assert asked.count("journalctl") == 1
    code, out = kitchen.main("flow", "--since", "2026-10-20T00:00", "--until", "2026-10-21T00:00")
    assert code == 0 and "waiting by class" in out and KEY not in out


def test_the_command_refuses_a_window_that_ends_before_it_starts(kitchen):
    code, out = kitchen.main("flow", "--since", "2026-10-21", "--until", "2026-10-20")
    assert code == 1 and out.startswith("refused:")


def test_flow_is_a_verb():
    assert [verb.name for verb in flow.VERBS] == ["flow"]
