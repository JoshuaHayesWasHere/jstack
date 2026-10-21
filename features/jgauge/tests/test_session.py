import json
import shutil

import pytest

from jgauge import cli, session
from testing.paths import REPO

PROJECTS = REPO / "tests" / "fixtures" / "projects"
PLAIN = PROJECTS / "-tmp-plain-thread" / "11111111-1111-4111-8111-111111111111.jsonl"
AGENT = PROJECTS / "-tmp-small-agent" / "33333333-3333-4333-8333-333333333333.jsonl"


def counts(row: dict) -> dict:
    names = ("calls", "tokens_in", "cache_write", "cache_read", "tokens_out", "total")
    return {name: row[name] for name in (*names, "peak_context")}


def test_a_plain_thread_is_counted_from_its_transcript_alone():
    report = session.of_transcript(PLAIN)
    (row,) = report["rows"]
    assert (row["role"], row["session"]) == ("session", PLAIN.stem)
    assert counts(row) == {
        "calls": 2,
        "tokens_in": 5,
        "cache_write": 120,
        "cache_read": 100,
        "tokens_out": 47,
        "total": 272,
        "peak_context": 123,
    }
    assert counts(report["total"]) == counts(row)
    assert (row["first_ts"], row["last_ts"]) == (
        "2026-01-01T00:00:02.000Z",
        "2026-01-01T00:00:07.000Z",
    )


def test_a_threads_subagents_are_rows_of_their_own_and_in_the_total(tmp_path):
    path = tmp_path / PLAIN.name
    shutil.copy(PLAIN, path)
    agents = path.with_suffix("") / "subagents"
    agents.mkdir(parents=True)
    shutil.copy(AGENT, agents / "agent-a1.jsonl")
    report = session.of_transcript(path)
    assert [(row["role"], row["agent"]) for row in report["rows"]] == [
        ("session", None),
        ("subagent", "a1"),
    ]
    assert "subagent a1" in session.render(report)
    assert counts(report["rows"][1])["total"] == 38
    assert (report["total"]["calls"], report["total"]["total"]) == (3, 310)
    assert report["total"]["peak_context"] == 123


def test_a_message_id_in_a_thread_and_in_its_subagent_is_counted_once(tmp_path):
    path = tmp_path / PLAIN.name
    shutil.copy(PLAIN, path)
    agents = path.with_suffix("") / "subagents"
    agents.mkdir(parents=True)
    shutil.copy(PLAIN, agents / "agent-a1.jsonl")
    report = session.of_transcript(path)
    assert [row["calls"] for row in report["rows"]] == [2, 0]
    assert (report["total"]["calls"], report["total"]["total"]) == (2, 272)


def test_a_call_with_no_finished_line_is_in_the_total_as_a_flagged_floor(tmp_path):
    entries = [json.loads(line) for line in PLAIN.read_text().splitlines()]
    path = tmp_path / "cut.jsonl"
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries[:3]))
    row = session.of_transcript(path)["total"]
    assert (row["tokens_out"], row["out_floor"], row["out_floor_calls"]) == (0, 3, 1)
    assert row["total"] == 2 + 100 + 3
    assert "floor" in session.render(session.of_transcript(path))


def test_the_session_command_prints_the_table_or_json(capsys):
    assert cli.main(["session", str(PLAIN)]) == 0
    out = capsys.readouterr().out
    assert "272" in out and "123" in out and "Peak context" in out
    assert cli.main(["session", str(PLAIN), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["total"]["total"] == 272


def test_the_session_command_ends_with_a_reason_when_there_is_nothing_to_count(tmp_path):
    with pytest.raises(SystemExit) as missing:
        cli.main(["session", str(tmp_path / "none.jsonl")])
    assert "missing" in str(missing.value)


def test_the_run_command_is_gone(capsys):
    with pytest.raises(SystemExit) as refused:
        cli.main(["run", "01TESTRUN0000000000000000A"])
    assert refused.value.code == 2
    assert "invalid choice: 'run'" in capsys.readouterr().err


def test_an_agent_a_workflow_started_is_a_subagent_row_too(tmp_path):
    path = tmp_path / PLAIN.name
    shutil.copy(PLAIN, path)
    workflow = path.with_suffix("") / "subagents" / "workflows" / "wf_1"
    workflow.mkdir(parents=True)
    shutil.copy(AGENT, workflow / "agent-w1.jsonl")
    (workflow / "journal.jsonl").write_text('{"type": "assistant"}\n')
    (workflow / "agent-w1.meta.json").write_text("{}")
    report = session.of_transcript(path)
    assert [(row["role"], row["agent"]) for row in report["rows"]] == [
        ("session", None),
        ("subagent", "w1"),
    ]
    assert (report["total"]["calls"], report["total"]["total"]) == (3, 310)
