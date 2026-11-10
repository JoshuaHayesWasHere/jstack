"""The capped minutes: each read of which instances are capped is a line of a log, the KPI page sums
the minutes in which every instance was capped from those lines, and the store's
`jbus.telemetry.views.weekly_capped_any` the minutes in which one or more was.

`jgauge limits` and jbus's pass each read the ledger and append the read
(`jgauge.limits.note`). The tests run the real `jgauge limits` reader against a stand-in for the
usage endpoint, and the pass's own chore, then build the store with the real `jbus telemetry`, whose
`jbus.telemetry.machine` makes a row of each read, and read the page `jbus kpis` makes, as its
reader does.
"""

import contextlib
import json
from datetime import timedelta

import pytest

from jbus import kpis as pass_kpis
from jbus.telemetry.views import capped_any_spells
from jgauge import limits
from test_jbus_kpi_page import Cells, run
from test_jbus_telemetry import NOW, Machine

CAPPED = "Capped minutes (every instance capped)"
PRIME = "claude_prime"


class Accounts:
    """Two Claude homes signed in, the inventory that names both, and the ledger, under a HOME
    of the test's own; `answers` is what the usage endpoint says of each, by its token."""

    def __init__(self, root, monkeypatch):
        home = root / "home"
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.delenv("T3CODE_HOME", raising=False)
        monkeypatch.setenv("LIMITS", str(root / "ledger" / "limits"))
        monkeypatch.setenv("JGAUGE_USAGE_URL", "http://127.0.0.1:1/usage")
        settings = home / ".t3" / "userdata" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(
            json.dumps(
                {
                    "providerInstances": {
                        "claudeAgent": {"driver": "claudeAgent", "enabled": True},
                        PRIME: {"driver": "claudeAgent", "config": {"homePath": "~/.claude_prime"}},
                    }
                }
            )
        )
        for instance, where in (("claudeAgent", ".claude"), (PRIME, ".claude_prime")):
            (home / where).mkdir()
            oauth = {
                "accessToken": instance,
                "expiresAt": int((NOW + timedelta(days=30)).timestamp() * 1000),
            }
            (home / where / ".credentials.json").write_text(json.dumps({"claudeAiOauth": oauth}))
        self.answers: dict[str, float] = {}

    def get(self, _url, token):
        reset = (NOW + timedelta(hours=5)).isoformat()
        return {
            "five_hour": {"utilization": self.answers[token], "resets_at": reset},
            "seven_day": None,
        }

    def read(self, at, **used):
        """`jgauge limits` at `at`, the endpoint giving each instance the share it is given."""
        self.answers = {"claudeAgent": used.get("main", 0), PRIME: used.get("prime", 0)}
        said = limits.run(at, self.get)
        assert not any(line.startswith("stale") for line in said), said


def pass_reads(at):
    """The pass's chore that reads which instances are capped, at `at`."""
    (chore,) = (one for one in pass_kpis.CHORES if one.name == "the capped read")
    chore.run(None, None, at, lambda _: None)


@pytest.fixture
def machine(tmp_path, monkeypatch):
    found = Machine(tmp_path, monkeypatch)
    found.accounts = Accounts(tmp_path, monkeypatch)
    return found


def cells(machine, week="2026-10-28"):
    machine.build()
    out = machine.root / "page" / "kpis.html"
    code, said = run("--week", week, "--out", str(out), project="alpha")
    assert code == 0, said
    found = Cells()
    found.feed(out.read_text())
    return found.rows[CAPPED]


def test_each_read_appends_the_time_and_which_instances_are_capped(machine):
    machine.accounts.read(NOW, main=100, prime=40)
    pass_reads(NOW + timedelta(minutes=1))

    lines = [json.loads(line) for line in (machine.state_dir / "capped.jsonl").open()]

    assert [(one["at"], one["reader"]) for one in lines] == [
        ("2026-10-28T15:00:00+00:00", "limits"),
        ("2026-10-28T15:01:00+00:00", "pass"),
    ]
    assert all(one["instances"] == ["claudeAgent", PRIME] for one in lines)
    assert all(list(one["capped"]) == ["claudeAgent"] for one in lines)


def test_two_reads_an_hour_apart_give_60_minutes_of_a_spell(machine):
    machine.accounts.read(NOW, main=100, prime=100)
    machine.accounts.read(NOW + timedelta(hours=1), main=5, prime=5)

    row = cells(machine)

    assert row[5].startswith("60 min n 2 missed")


def test_the_two_readers_reads_of_the_same_minutes_count_them_once(machine):
    for minute in range(60):
        at = NOW + timedelta(minutes=minute)
        if minute % 2 == 0:
            machine.accounts.read(at, main=100, prime=100)
        pass_reads(at)
    pass_reads(NOW + timedelta(minutes=30, seconds=30))
    machine.accounts.read(NOW + timedelta(hours=1), main=5, prime=5)

    row = cells(machine)

    assert row[5].startswith("60 min n 92 missed")


def test_a_spell_needs_every_instance_capped(machine):
    machine.accounts.read(NOW, main=100, prime=99)
    machine.accounts.read(NOW + timedelta(hours=1), main=100, prime=5)

    row = cells(machine)

    assert row[5].startswith("0 min n 2 met")


def test_a_capped_read_with_no_later_read_holds_only_up_to_the_first_reset(machine):
    machine.accounts.read(NOW, main=100, prime=100)

    row = cells(machine)

    assert row[5].startswith("300 min n 1 missed")


def test_this_week_counts_from_the_day_the_reads_begin_and_last_week_is_not_covered(machine):
    machine.accounts.read(NOW, main=5, prime=5)

    row = cells(machine)

    assert row[4] == (
        "n/a n 0 not covered: the reads of which instances are capped begin on 2026-10-28, "
        "after the week does"
    )
    assert row[5] == (
        "0 min n 1 met: from 2026-10-28, the day the reads of which instances are capped begin"
    )


def test_with_no_read_yet_neither_week_is_covered(machine):
    row = cells(machine)

    assert row[5] == "n/a n 0 not covered: the reads of which instances are capped have no line yet"


def weekly(machine, view):
    """Each week's capped minutes in the store's `view`, as a reader of the store reads them."""
    machine.build()
    with contextlib.closing(machine.store()) as store:
        return dict(store.execute(f"SELECT week, minutes FROM {view} WHERE project = ''"))


def test_a_read_with_one_account_capped_holds_at_most_5_minutes_up_to_a_read_an_hour_on(machine):
    machine.accounts.read(NOW, main=100, prime=40)
    machine.accounts.read(NOW + timedelta(hours=1), main=5, prime=40)

    assert weekly(machine, "weekly_capped_any") == {"2026-10-25": capped_any_spells.HOLD}


def test_reads_2_minutes_apart_with_one_account_capped_count_each_minute_once(machine):
    for read in range(30):
        machine.accounts.read(NOW + timedelta(minutes=2 * read), main=100, prime=40)
    machine.accounts.read(NOW + timedelta(hours=1), main=5, prime=40)

    assert weekly(machine, "weekly_capped_any") == {"2026-10-25": 60}
    assert weekly(machine, "weekly_capped") == {"2026-10-25": 0}
