"""`jgauge spend` over a small T3 Code store: units, kinds, windows and the all-capped span.

A run spends TOKENS unless it says otherwise: 3,000,000 input tokens (1,800,000 read from cache,
600,000 written to it) and 30,000 output, so 600,000 x1 + 600,000 x1.25 + 1,800,000 x0.1 +
30,000 x5 = 1,680,000 units, x5/3 on Opus.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pytest

from jgauge import cli

SCHEMA = """
create table projection_projects (project_id text primary key, title text not null);
create table orchestration_v2_projection_threads (
    thread_id text primary key, project_id text not null, title text not null);
create table orchestration_v2_projection_runs (
    run_id text primary key, thread_id text not null, ordinal integer not null,
    provider text not null, status text not null, requested_at text not null,
    completed_at text, payload_json text not null, provider_instance_id text);
create table orchestration_v2_projection_run_attempts (
    attempt_id text primary key, thread_id text not null, run_id text not null,
    payload_json text not null);
create table orchestration_v2_projection_provider_turns (
    provider_turn_id text primary key, thread_id text not null, run_attempt_id text,
    payload_json text not null);
create table orchestration_v2_projection_turn_items (
    turn_item_id text primary key, thread_id text not null, run_id text, type text not null,
    status text not null, payload_json text not null);
"""

TOKENS = (3_000_000, 1_800_000, 600_000, 30_000)
SONNET = 1.68
OPUS = 2.8


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self.db.execute("insert into projection_projects values ('p1', 'jstack'), ('p2', 'other')")
        self.runs = 0

    def run(
        self,
        title: str,
        start: str,
        *,
        ordinal: int = 1,
        instance: str = "claudeAgent",
        model: str = "claude-opus-5-5",
        tokens: tuple[int, int, int, int] = TOKENS,
        message: str = "",
        text: str = "",
        status: str = "completed",
        cap: tuple[str, str] | None = None,
        project: str = "p1",
    ) -> None:
        """One run of a thread titled `title`, started at `start` (UTC); `cap` is a usage-limit
        failure, its time and its reset, and its limit is a five-hour one."""
        self.runs += 1
        run, thread = f"run{self.runs}", f"thread-{title}"
        self.db.execute(
            "insert or ignore into orchestration_v2_projection_threads values (?, ?, ?)",
            (thread, project, title),
        )
        payload = {
            "modelSelection": {"instanceId": instance, "model": model},
            "userMessageId": message,
            "requestedAt": start,
            "startedAt": start,
            "completedAt": start,
        }
        self.db.execute(
            "insert into orchestration_v2_projection_runs values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run, thread, ordinal, instance, status, start, start, json.dumps(payload), instance),
        )
        self.db.execute(
            "insert into orchestration_v2_projection_run_attempts values (?, ?, ?, '{}')",
            (f"{run}-a", thread, run),
        )
        given, cached, written, output = tokens
        usage = {
            "inputTokens": given,
            "cachedInputTokens": cached,
            "cacheCreationTokens": written,
            "outputTokens": output,
            "usageStatus": "partial" if cap else "complete",
        }
        self.db.execute(
            "insert into orchestration_v2_projection_provider_turns values (?, ?, ?, ?)",
            (f"{run}-t", thread, f"{run}-a", json.dumps({"turnTokenUsage": usage})),
        )
        if text:
            self._item(run, thread, "user_message", "completed", messageId=message, text=text)
        if cap:
            at, reset = cap
            epoch = int(datetime.fromisoformat(reset.replace("Z", "+00:00")).timestamp())
            native = f"usage-limit:turn:five_hour:{epoch}"
            self._item(
                run, thread, "system_notice", "completed", nativeItemRef={"nativeId": native}
            )
            failure = {"class": "usage_limit", "resetAt": reset}
            self._item(run, thread, "error", "failed", startedAt=at, failure=failure)

    def _item(self, run: str, thread: str, kind: str, status: str, **payload) -> None:
        self.db.execute(
            "insert into orchestration_v2_projection_turn_items values (?, ?, ?, ?, ?, ?)",
            (f"{run}-{kind}", thread, run, kind, status, json.dumps(payload)),
        )

    def close(self) -> None:
        self.db.commit()
        self.db.close()


@pytest.fixture
def eastern(monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture
def store(tmp_path, eastern):
    made = Store(tmp_path / "statev2.sqlite")
    yield made
    made.db.close()


def spend(store: Store, capsys, *args: str) -> list[str]:
    store.close()
    assert cli.main(["spend", "--store", str(store.path), *args]) == 0
    return capsys.readouterr().out.splitlines()


def section(lines: list[str], header: str) -> list[str]:
    start = next(i for i, line in enumerate(lines) if line.startswith(header)) + 1
    end = next((i for i in range(start, len(lines)) if not lines[i].startswith("  ")), len(lines))
    return [line.strip() for line in lines[start:end]]


def by_kind(lines: list[str]) -> dict[str, float]:
    rows = (line.rsplit(maxsplit=2) for line in section(lines, "by kind:"))
    return {name: float(spent.rstrip("M")) for name, spent, _share in rows}


def thread_send(key: str) -> str:
    return f"message:mcp:client%3Ax:thread-send:{key}%7Cslug%7Cabc"


def test_units_weigh_each_token_and_opus(store, capsys):
    store.run("crew: one", "2026-10-26T14:00:00.000Z")
    store.run("crew: two", "2026-10-26T14:10:00.000Z", model="claude-sonnet-5-5")

    lines = spend(store, capsys, "--day", "2026-10-26")

    assert (
        lines[0]
        == f"spend 2026-10-26 00:00 to 2026-10-27 00:00 EDT: {OPUS + SONNET:.1f}M units, 2 runs"
    )
    assert by_kind(lines)["first crew run"] == pytest.approx(OPUS + SONNET, abs=0.05)


def test_each_run_has_its_kind(store, capsys):
    at = "2026-10-26T15:00:00.000Z"
    store.run("crew: a", at)
    store.run("crew: a", at, ordinal=2, message=thread_send("failed"))
    store.run("crew: a", at, ordinal=3, message=thread_send("rebase"))
    store.run("crew: a", at, ordinal=4, message="m4", text="a: review of the pull request")
    store.run("crew: a", at, ordinal=5, message="m5", text="Continue where you left off.")
    store.run("review: a, 1", at)
    store.run("home: jstack", at)
    store.run("scout: day-audit", at)
    store.run("crew: b", at, ordinal=2, status="failed", cap=(at, "2026-10-26T16:30:00.000Z"))

    kinds = by_kind(spend(store, capsys, "--day", "2026-10-26"))

    assert kinds == {
        "first crew run": OPUS,
        "reviews": OPUS,
        "fix rounds": 2 * OPUS,
        "jbus sends": 2 * OPUS,
        "homes": OPUS,
        "scouts": OPUS,
        "capped failures": OPUS,
    }


def test_the_period_and_the_project_choose_the_runs(store, capsys):
    """A run at 23:59 EDT the day before, and one in another project, are left out."""
    store.run("crew: in", "2026-10-26T14:00:00.000Z")
    store.run("crew: before", "2026-10-26T03:59:00.000Z")
    store.run("crew: elsewhere", "2026-10-26T14:00:00.000Z", project="p2")

    lines = spend(
        store,
        capsys,
        "--since",
        "2026-10-26T00:00",
        "--until",
        "2026-10-26T12:00",
        "--project",
        "jstack",
    )

    assert lines[0].endswith(f": {OPUS}M units, 1 runs")


def test_an_unknown_project_is_refused(store, capsys):
    store.close()
    with pytest.raises(SystemExit, match="no project 'nope'"):
        cli.main(["spend", "--store", str(store.path), "--project", "nope"])


def capped(store: Store, title: str, instance: str, at: str, reset: str) -> None:
    """A run that failed on the usage limit at `at`, spending nothing, until `reset`."""
    store.run(
        title,
        at,
        ordinal=2,
        instance=instance,
        tokens=(0, 0, 0, 0),
        status="failed",
        cap=(at, reset),
    )


def test_minutes_with_every_instance_capped(store, capsys):
    """A is capped 09:09 to 12:30 EDT, B 08:46 to 16:00 EDT: both from 09:09 to 12:30."""
    store.run("crew: a", "2026-10-26T11:30:00.000Z")
    capped(store, "crew: a", "claudeAgent", "2026-10-26T13:08:58.000Z", "2026-10-26T16:30:00.000Z")
    capped(store, "crew: b", "prime", "2026-10-26T12:46:00.000Z", "2026-10-26T20:00:00.000Z")

    lines = spend(store, capsys, "--day", "2026-10-26")

    assert section(lines, "every instance capped (claudeAgent, prime):") == [
        "2026-10-26  201 min  09:09 to 12:30"
    ]
    windows = section(lines, "by five-hour window:")
    assert (
        f"claudeAgent                2026-10-26 07:30 to 12:30 (reset)     {OPUS}M, capped at 09:09"
        in windows
    )


def test_one_instance_capped_leaves_no_capped_minute(store, capsys):
    store.run("crew: a", "2026-10-26T14:00:00.000Z")
    capped(store, "crew: b", "prime", "2026-10-26T13:00:00.000Z", "2026-10-26T18:00:00.000Z")

    lines = spend(store, capsys, "--day", "2026-10-26")

    assert section(lines, "every instance capped (claudeAgent, prime):") == ["2026-10-26    0 min"]


def test_the_store_is_left_as_it_was(store, capsys):
    store.run("crew: a", "2026-10-26T14:00:00.000Z")
    store.close()
    before = store.path.read_bytes()

    assert cli.main(["spend", "--store", str(store.path), "--day", "2026-10-26"]) == 0

    assert store.path.read_bytes() == before
    assert sorted(p.name for p in store.path.parent.iterdir()) == ["statev2.sqlite"]
