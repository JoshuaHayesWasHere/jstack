"""A replay of the snapshot failure of 2026-10-29 08:33 EDT, run through the snapshot and a pass.

`fixtures/replay/2026-10-29/outbox.jsonl` holds the four lines of that day's `outbox.jsonl` that
sent the snapshot alert, one to each of four homes: infra, jstack, Winnifred and case-console.
gitleaks had found a secret in a file of the jstack home, and the alarm, a process of its own, could
not know which. The replay sets up those four projects, each home with the thread the day woke,
makes gitleaks name a jstack file, takes the snapshot and runs one pass. The alert is an open item
whose owner is the file's first path segment, so it reaches the jstack home and no other."""

import json
import os
from datetime import timedelta
from pathlib import Path

import jbus
from jbus import poll, snapshot
from test_jbus_kitchen import NOW
from test_jbus_snapshot import tree

DAY = Path(__file__).parent / "fixtures" / "replay" / "2026-10-29"
FOUND = "jstack/reports/routing/census.md"


def woken():
    """The thread the day sent the snapshot alert to, by project."""
    lines = [json.loads(line) for line in (DAY / "outbox.jsonl").read_text().splitlines()]
    return {one["row"]: one["thread"] for one in lines if one["template"] == "wake"}


def gitleaks(kitchen, monkeypatch):
    """A gitleaks that finds one secret, in `FOUND`, and writes it to the report it is asked for."""
    stand_in = kitchen.root / "gitleaks-finds"
    stand_in.mkdir()
    script = stand_in / "gitleaks"
    report = json.dumps([{"File": FOUND, "RuleID": "github-pat", "Secret": "REDACTED"}])
    script.write_text(
        "#!/bin/sh\n"
        'while [ $# -gt 0 ]; do [ "$1" = --report-path ] && shift && '
        f"printf '%s' '{report}' > \"$1\"; shift; done\n"
        "exit 1\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stand_in}{os.pathsep}{os.environ['PATH']}")


def told(kitchen):
    """The threads a pass sent a message that names the snapshot's failure."""
    return [
        given["threadId"]
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send" and "snapshot" in given["message"]
    ]


def test_the_snapshot_alert_of_2026_10_29_reaches_the_one_home_whose_file_failed(
    kitchen, monkeypatch
):
    homes = tree(kitchen, monkeypatch)
    day = woken()
    assert sorted(day) == ["Winnifred", "case-console", "infra", "jstack"]
    for name, thread in day.items():
        side = kitchen.second(name)
        (side.home / "home-id").write_text(f"{thread}\n")
        kitchen.t3.thread(
            name,
            "idle",
            idle=timedelta(hours=1),
            title=f"home: {name}",
            threadId=thread,
            project=side.project,
        )
    kitchen.config(home_thread=None)
    (homes / "jstack" / "reports" / "routing").mkdir(parents=True)
    (homes / FOUND).write_text("a token\n")
    gitleaks(kitchen, monkeypatch)
    said = []
    assert snapshot.snapshot(jbus.load(), NOW, said.append, warn=said.append) == 1
    poll.poll(jbus.load(), NOW, said.append)
    assert told(kitchen) == [day["jstack"]]
