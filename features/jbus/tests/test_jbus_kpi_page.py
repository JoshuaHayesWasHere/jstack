"""`jbus kpis` builds a static page from the telemetry store: each KPI against its target, this
week and last.

The tests write two projects' records as jbus writes them, compile them with the real
`jbus telemetry`, build the page with the real `jbus kpis`, and read the page as its reader
does: its table's cells. A KPI the store measures shows its target, each week's value and
whether it met the target; one the store has no instrument for says so. The page holds no text a
record carried, no project's name and no path, `jleak` finds nothing in it, and building it
calls no `gh`.
"""

import contextlib
import io
import json
from datetime import timedelta
from html.parser import HTMLParser

import pytest

from jbus import cli
from jbus.telemetry import kpis
from jleak import cli as jleak_cli
from test_jbus_telemetry import NOW, SECRET, T3, Machine, act_citing, job, records, snapshots

THIS = "2026-10-28"
"""A day of the fixture's this week, which starts on Sunday 2026-10-25."""


class Cells(HTMLParser):
    """The text of each row of the page's KPI table, by the KPI's name in its first cell."""

    def __init__(self):
        super().__init__()
        self.rows: dict[str, list[str]] = {}
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._in_body = False

    def handle_starttag(self, tag, attrs):
        if tag == "tbody":
            self._in_body = True
        elif tag == "tr" and self._in_body:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "tbody":
            self._in_body = False
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row:
            self.rows[self._row[0]] = self._row
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["kpis", *argv])
    return code, out.getvalue()


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """Two projects with one merged row each, `beta`'s last week and `alpha`'s this week, and a
    door `alpha`'s home opened this week; a `gh` on PATH that leaves a mark if anything runs it."""
    found = Machine(tmp_path, monkeypatch)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(f"#!/bin/sh\ntouch {tmp_path / 'gh-ran'}\nexit 1\n")
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    last = NOW - timedelta(days=7)
    records(found, "alpha", NOW, "alpha-one", 10)
    snapshots(found, "alpha", [("alpha-one", 10, NOW + timedelta(hours=1))])
    records(found, "beta", last, "beta-one", 11)
    snapshots(found, "beta", [("beta-one", 11, last + timedelta(hours=1))])
    found.append(
        "alpha",
        "acts.jsonl",
        {
            "action": {"doors": ["deletes data"], "subject": "alpha-one", "verb": "answer"},
            "at": NOW.isoformat(timespec="seconds"),
            "evidence": {"words": SECRET, "source": "typed"},
            "id": "act-door",
            "line": SECRET,
            "outcome": "done",
            "party": {"kind": "home", "name": "", "route": "cli"},
        },
    )
    found.build()
    return found


def page(machine):
    out = machine.root / "page" / "kpis.html"
    code, said = run("--week", THIS, "--out", str(out))
    assert code == 0, said
    cells = Cells()
    cells.feed(out.read_text())
    return out, cells.rows, said


def test_the_page_shows_each_kpi_with_its_target_this_week_last_week_and_met_or_not(machine):
    _, rows, said = page(machine)

    assert list(rows) == [kpi.name for kpi in kpis.KPIS]
    assert len(rows) == 23
    lead = rows["Lead time, go to merge, median (DORA)"]
    assert lead[3] == "≤ 30 min"
    assert lead[4] == "59 min n 1 missed"
    assert lead[5].endswith("n 1 missed")
    opened = rows["PR open to merge, median"]
    assert opened[4] == "0 min n 1 met"
    assert opened[5] == "0 min n 1 met"
    doors = rows["Doors opened without your own word"]
    assert doors[3] == "≤ 0"
    assert doors[4] == "0 n 0 met"
    assert doors[5] == "1 n 1 missed"
    assert rows["Time to restore main, median (DORA)"][5] == "n/a n 0 no data"
    assert rows["Change failure rate, push checks (DORA)"][5] == "0% n 1 met"
    assert rows["Merges a week (DORA frequency)"][5] == "1 n 1 tracked"
    assert rows["Crew first-round share"][5] == (
        "n/a n 0 not covered: jmerge's waits labelled as a crew's fix round have no line yet"
    )
    assert "2026-10-25" in said


def fix_round(machine, at, number=99):
    """A wait of jmerge's on a crew's fix round, logged at `at`."""
    machine.append(
        "alpha",
        "merge.log",
        f"{at:%Y-%m-%d %H:%M} wait {number} https://example.test/pull/{number}: {SECRET} [no-fixed]",
        home=True,
    )


def checked(machine, project, run, pr, conclusion, at):
    """A pull_request check of `pr` that ended `conclusion`, as `jbus ci` keeps it."""
    one = job(run, f"c{run}", pr, conclusion, at)
    machine.append(project, "ci.jsonl", {**one, "event": "pull_request", "branch": f"pr-{pr}"})


def test_a_pull_request_with_a_red_check_or_a_wait_on_a_crews_fix_is_not_first_round(machine):
    fix_round(machine, NOW - timedelta(days=20))
    fix_round(machine, NOW, number=10)
    checked(machine, "alpha", 4, 10, "success", NOW)
    checked(machine, "beta", 5, 11, "failure", NOW - timedelta(days=7))
    machine.build()

    _, rows, _ = page(machine)

    assert rows["Crew first-round share"][4] == "0% n 1 missed"
    assert rows["Crew first-round share"][5] == "0% n 1 missed"


def test_a_week_that_begins_before_the_first_fix_round_label_shows_no_value_and_says_why(machine):
    fix_round(machine, NOW - timedelta(days=6))
    checked(machine, "alpha", 4, 10, "success", NOW)
    checked(machine, "beta", 5, 11, "success", NOW - timedelta(days=7))
    machine.build()

    _, rows, _ = page(machine)

    first = rows["Crew first-round share"]
    assert first[4] == (
        "n/a n 0 not covered: jmerge's waits labelled as a crew's fix round begin on "
        "2026-10-22, after the week does"
    )
    assert first[5] == "100% n 1 met"


def test_a_merged_pull_request_with_no_check_kept_is_not_counted(machine):
    fix_round(machine, NOW - timedelta(days=20))
    records(machine, "alpha", NOW, "alpha-two", 12)
    snapshots(machine, "alpha", [("alpha-one", 10, NOW), ("alpha-two", 12, NOW)])
    checked(machine, "alpha", 4, 10, "success", NOW)
    machine.build()

    _, rows, _ = page(machine)

    assert rows["Crew first-round share"][5] == "100% n 1 met"


def test_the_pass_time_is_each_weeks_median_of_the_passes_jbus_recorded(machine):
    with open(machine.state_dir / "passes.jsonl", "a") as handle:
        for seconds, when in ((20, NOW), (40, NOW), (90, NOW), (50, NOW - timedelta(days=7))):
            handle.write(json.dumps({"at": when.isoformat(timespec="seconds"), "seconds": seconds}))
            handle.write("\n")
    machine.build()

    _, rows, _ = page(machine)

    assert rows["jbus pass, median seconds"][4] == "50 s n 1 missed"
    assert rows["jbus pass, median seconds"][5] == "40 s n 3 missed"


def test_the_ask_ledger_gives_typed_messages_per_merged_row_and_the_lost_asks(machine):
    t3, home, crew = T3(), "mcp:home-a", "mcp:crew-a"
    t3.thread(home, "alpha-id")
    t3.thread(crew, "alpha-id")
    t3.say("m-row", home, NOW)
    act_citing(machine, "alpha", home, "m-row", NOW + timedelta(minutes=1))
    t3.say("m-lost", home, NOW + timedelta(hours=1))
    t3.say("m-resume", crew, NOW + timedelta(hours=2), text="continue where you left off.")
    t3.say("r-resume", crew, NOW + timedelta(hours=2, seconds=5), role="assistant")
    machine.build()

    _, rows, _ = page(machine)

    typed = rows["Your typed messages per merged row"]
    assert typed[4] == "0 n 1 met"
    assert typed[5] == "2 n 1 missed"
    lost = rows["Lost asks (S3)"]
    assert lost[4] == "0 n 0 met"
    assert lost[5] == "1 n 3 missed"
    assert SECRET not in (machine.root / "page" / "kpis.html").read_text()


def test_a_kpi_with_no_instrument_yet_says_so(machine):
    _, rows, _ = page(machine)

    dollars = rows["Dollars per merged row"]
    assert dollars[4].startswith("no instrument yet: needs ")
    lacking = [name for name, row in rows.items() if row[4].startswith("no instrument yet")]
    assert len(lacking) == sum(isinstance(kpi.source, kpis.Lacks) for kpi in kpis.KPIS)


def test_the_page_holds_no_record_text_no_project_and_no_path_and_jleak_finds_nothing(machine):
    out, _, _ = page(machine)
    text = out.read_text()

    assert SECRET not in text
    for private in ("alpha", "beta", str(machine.root)):
        assert private not in text
    patterns = machine.root / "outbound.toml"
    patterns.write_text(
        f"[patterns]\nproject = '\\b(?:alpha|beta)\\b'\nhome-path = '{machine.root}'\n"
        f"said = '{SECRET}'\n"
    )
    with contextlib.redirect_stdout(io.StringIO()):
        assert jleak_cli.main(["--patterns", str(patterns), str(out)]) == 0


def test_building_the_page_calls_no_gh(machine):
    page(machine)

    assert not (machine.root / "gh-ran").exists()


def test_with_no_store_it_refuses_and_writes_nothing(tmp_path, monkeypatch):
    Machine(tmp_path, monkeypatch)
    out = tmp_path / "kpis.html"

    code, said = run("--out", str(out))

    assert code == 2
    assert said.startswith("refused: no telemetry store")
    assert not out.exists()
