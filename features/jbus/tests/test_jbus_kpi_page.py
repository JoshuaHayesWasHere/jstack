"""`jbus kpis` builds a static page from the telemetry store: each KPI against its target, this
week and last.

The tests write two projects' records as jbus writes them, compile them with the real
`jbus telemetry`, build the page with the real `jbus kpis`, and read the page as its reader
does: its table's cells. A KPI the store measures shows its target, each week's value and
whether it met the target; one the store has no instrument for says so. The page holds no text a
record carried, no row and no path, and names only the projects a KPI says it covers, the projects
whose push checks of main the change failure rate counts. `jleak` finds nothing else in it, and
building it calls no `gh`.
"""

import contextlib
import importlib
import io
import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser

import pytest

import test_jbus_telemetry_tokens as token_records
from jbus import cli
from jbus.telemetry import kpis
from jgauge import spend
from jleak import cli as jleak_cli
from test_jbus_telemetry import (
    NOW,
    SECRET,
    T3,
    Machine,
    act_citing,
    iso,
    job,
    records,
    snapshots,
    wait,
)
from test_jbus_telemetry_gate_labels import S, W, gates, label

THIS = "2026-10-28"
"""A day of the fixture's this week, which starts on Sunday 2026-10-25."""
FIRST = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
"""The fixture's first row record, a Wednesday: the week of 2026-10-11 begins before it."""


def first_item(at):
    return {"at": at.isoformat(timespec="seconds"), "id": "w0.1", "item": "w0", "verb": "proposed"}


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
    found.append("beta", "items.jsonl", first_item(FIRST))
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
    return page_of(machine, THIS)


def page_of(machine, week):
    out = machine.root / "page" / "kpis.html"
    code, said = run("--week", week, "--out", str(out))
    assert code == 0, said
    cells = Cells()
    cells.feed(out.read_text())
    return out, cells.rows, said


ORDER = (
    "PR open to merge, median",
    "Lead time, go to merge, median (DORA)",
    "Change failure rate, push checks (DORA)",
    "Time to restore main, median (DORA)",
    "Merges a week (DORA frequency)",
    "Your typed messages per merged row",
    "'What needs me' asks",
    "Rows finished with no further word",
    "Gates closed by silence that were wrong (S8)",
    "Doors opened without your own word",
    "Spend per merged row (M units)",
    "Coordination share of spend",
    "Dollars per merged row",
    "Crew first-round share",
    "Redo rate",
    "Capped minutes (every instance capped)",
    "Capped-failure share of spend",
    "Stall minutes per merged row",
    "Lost asks (S3)",
    "jbus pass, median seconds",
    "Waiting for jmerge, PR p50 minutes",
    "Crew first load, KB (jstack's own)",
    "Drift: standing words broken (S4)",
)
"""The page's KPIs as it showed them on 2026-11-03, the order of the telemetry-plane scout's
report: a KPI added since may come anywhere among them, and these keep their order."""


def test_the_kpis_keep_the_order_of_the_scouts_report():
    names = [kpi.name for kpi in kpis.KPIS]
    assert [name for name in names if name in ORDER] == list(ORDER)


def package_with(tmp_path, monkeypatch, name, files):
    """A copy of the KPIs' package named `name`, with these modules added, imported."""
    root = tmp_path / "packages"
    shutil.copytree(kpis.__path__[0], root / name, ignore=shutil.ignore_patterns("__pycache__"))
    for file, text in files.items():
        (root / name / file).write_text(text)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.setattr(sys, "modules", dict(sys.modules))
    return importlib.import_module(name)


def added(name):
    return (
        "from jbus.telemetry.kpis import Kpi, Lacks\n\n"
        f"KPI = Kpi({name!r}, 'speed', 'what it counts', '', None, 'lower', Lacks('a record'))\n"
    )


def test_a_kpi_is_added_by_a_module_and_takes_the_place_its_name_sorts_to(tmp_path, monkeypatch):
    found = package_with(
        tmp_path,
        monkeypatch,
        "added_kpis",
        {"k24_last.py": added("Added last"), "k10_added.py": added("Added before the doors")},
    )

    doors = ORDER.index("Doors opened without your own word")
    after = [*ORDER[:doors], "Added before the doors", *ORDER[doors:], "Added last"]
    assert [kpi.name for kpi in found.KPIS] == after


def test_a_module_not_named_as_a_kpis_is_refused(tmp_path, monkeypatch):
    with pytest.raises(ImportError, match="last_one not named as"):
        package_with(tmp_path, monkeypatch, "stray_kpis", {"last_one.py": added("Stray")})


def test_the_page_shows_each_kpi_with_its_target_this_week_last_week_and_met_or_not(machine):
    _, rows, said = page(machine)

    assert list(rows) == [kpi.name for kpi in kpis.KPIS]
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
    assert rows["Change failure rate, push checks (DORA)"][5] == (
        "n/a n 0 no data: covers no project, since the store keeps no push check of main"
    )
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
        f"{at:%Y-%m-%d %H:%M} wait {number} https://example.test/pull/{number}: "
        f"{SECRET} [no-fixed]",
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


def test_the_jmerge_wait_is_each_weeks_median_of_jmerge_records_or_else_of_the_checks(machine):
    """`records` logs a 40-second wait held 30 seconds for its review for each merged pull
    request, alpha's 10 this week and beta's 11 last week. A merge with no record of jmerge's,
    alpha's 12, is counted from its last passed check to its merge, and a record, once there,
    takes its place."""
    merged = NOW + timedelta(hours=1)
    with (machine.state("alpha") / "ci-prs.jsonl").open("a") as listed:
        listed.write(
            json.dumps({"number": 12, "head": "h12", "created": iso(NOW), "merged": iso(merged)})
            + "\n"
        )
    machine.append("alpha", "merge.log", f"{NOW:%Y-%m-%d %H:%M} merged 12 alpha-two", home=True)
    ended = merged - timedelta(seconds=45)
    one = job(7, "h12", 12, "success", ended - timedelta(minutes=5))
    machine.append("alpha", "ci.jsonl", {**one, "event": "pull_request"})
    machine.append(
        "alpha",
        "merge-waits.jsonl",
        wait(20, NOW, 6),
        wait(21, NOW, 30, {"no-review": 20, "main-red": 4}),
        home=True,
    )
    machine.build()

    _, rows, _ = page(machine)

    waiting = rows["Waiting for jmerge, PR p50 minutes"]
    assert waiting[3] == "≤ 0.2 min"
    assert waiting[4] == "0.7 min n 1 missed"
    assert waiting[5] == "0.6 min n 4 missed"
    with machine.store() as store:
        held = store.execute(
            "SELECT code, sum(seconds) FROM jmerge_blockers WHERE week = '2026-10-25' "
            "GROUP BY code ORDER BY 2 DESC"
        ).fetchall()
    assert held == [("no-review", 50.0), ("main-red", 4.0)]

    machine.append("alpha", "merge-waits.jsonl", wait(12, merged, 3), home=True)
    machine.build()

    _, rows, _ = page(machine)

    assert rows["Waiting for jmerge, PR p50 minutes"][5] == "0.3 min n 4 missed"


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


def test_the_what_needs_me_asks_are_the_weeks_typed_messages_that_ask_it(machine):
    t3, home = T3(), "mcp:home-a"
    t3.thread(home, "alpha-id")
    t3.say("m-asks", home, NOW, text="what needs me?")
    t3.say("m-again", home, NOW + timedelta(hours=1), text="Does anything need me?")
    t3.say("m-tells", home, NOW + timedelta(hours=2), text="ship it")
    t3.say("m-why", home, NOW + timedelta(hours=3), text="why do these need me?")
    machine.build()

    _, rows, _ = page(machine)

    asks = rows["'What needs me' asks"]
    assert asks[4] == "0 n 0 met"
    assert asks[5] == "2 n 4 missed"
    assert "need me" not in (machine.root / "page" / "kpis.html").read_text()


def test_dollars_per_merged_row_is_an_estimate_from_the_dated_price_table(
    tmp_path, monkeypatch, t3_settings
):
    """The week's dollars per merged row, its calls at `jgauge.spend`'s prices, and the page says
    it is an estimate from the price table, with the table's date."""
    tokens = token_records.Machine(tmp_path, monkeypatch, t3_settings)
    tokens.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1")
    tokens.merged("row-a")
    counts = (1_000, 100_000, 2_000_000, 50_000)
    tokens.claude("s1", token_records.said(token_records.NOW, "m1", counts))
    tokens.run()

    out = tmp_path / "page" / "kpis.html"
    code, said = run("--week", "2026-10-28", "--out", str(out))
    assert code == 0, said
    cells = Cells()
    cells.feed(out.read_text())
    row = cells.rows["Dollars per merged row"]
    expected = spend.dollars("claude-opus-5-5", *counts)
    assert expected is not None
    assert row[1].startswith(
        f"an estimate at API list prices, from jgauge.spend's price table of {spend.PRICED_ON}:"
    )
    assert row[4] == "n/a n 0 no data"
    assert row[5] == f"${round(expected, 1):g} n 1 tracked"


def test_dollars_per_merged_row_names_each_model_the_price_table_does_not_price(
    tmp_path, monkeypatch, t3_settings
):
    """A Claude call of a model id `jgauge.spend.PRICES` has no key for adds no dollars, so the
    week's reading names each such model of its merged rows with its calls. A call of a row not
    merged is not named."""
    tokens = token_records.Machine(tmp_path, monkeypatch, t3_settings)
    tokens.thread("mcp:crew-a", "crew: row-a", "claudeAgent", "s1")
    tokens.thread("mcp:crew-b", "crew: row-b", "claudeAgent", "s2")
    tokens.merged("row-a")
    counts = (1_000, 100_000, 2_000_000, 50_000)
    at = token_records.NOW
    tokens.claude(
        "s1",
        token_records.said(at, "m1", counts),
        token_records.said(at, "m2", counts, model="claude-opus-5-5[1m]"),
        token_records.said(at, "m3", counts, model="claude-opus-5-5[1m]"),
        token_records.said(at, "m4", counts, model="claude-nova-1"),
    )
    tokens.claude("s2", token_records.said(at, "m5", counts, model="claude-quill-2", session="s2"))
    tokens.run()
    assert "claude-opus-5-5[1m]" not in spend.PRICES
    assert "claude-nova-1" not in spend.PRICES

    out = tmp_path / "page" / "kpis.html"
    code, said = run("--week", "2026-10-28", "--out", str(out))
    assert code == 0, said
    cells = Cells()
    cells.feed(out.read_text())
    row = cells.rows["Dollars per merged row"]
    expected = spend.dollars("claude-opus-5-5", *counts)
    assert expected is not None
    assert row[5] == (
        f"${round(expected, 1):g} n 1 tracked: no price in jgauge.spend's table for "
        "claude-nova-1 (1 call), claude-opus-5-5[1m] (2 calls)"
    )
    assert row[4] == "n/a n 0 no data"


def spell(at, minutes, slug="alpha-one", until=True):
    """A line of `stalls.jsonl` as `jbus.stall.spells` writes it: a spell opened, or ended."""
    since = at - timedelta(minutes=minutes)
    line = {"at": iso(at), "thread": "mcp:crew-a", "role": "crew", "slug": slug}
    line["since"] = iso(since)
    return line | ({"until": iso(at), "minutes": minutes, "became": "moving"} if until else {})


def test_stall_minutes_are_each_weeks_ended_spells_over_its_merged_rows_since_the_record_began(
    machine,
):
    machine.append(
        "alpha",
        "stalls.jsonl",
        spell(NOW - timedelta(minutes=30), 12, until=False),
        spell(NOW - timedelta(minutes=30), 12),
        spell(NOW + timedelta(minutes=50), 33),
        spell(NOW + timedelta(hours=2), 15, until=False),
    )
    machine.build()

    _, rows, _ = page(machine)

    stall = rows["Stall minutes per merged row"]
    assert stall[3] == "none yet"
    assert stall[5] == "45 min n 1 tracked: covers alpha"
    assert stall[4] == (
        "n/a n 0 no data: covers alpha; no stall record kept for 1 merged row, on 2026-10-21"
    )


def test_a_week_of_merged_rows_and_no_spell_has_no_stall_minute(machine):
    machine.append("alpha", "stalls.jsonl", spell(NOW - timedelta(days=1), 12, until=False))
    machine.build()

    _, rows, _ = page(machine)

    assert rows["Stall minutes per merged row"][5] == "0 min n 1 tracked: covers alpha"


def test_a_kpi_with_no_instrument_yet_says_so(machine):
    _, rows, _ = page(machine)

    lacking_one = next(kpi.name for kpi in kpis.KPIS if isinstance(kpi.source, kpis.Lacks))
    assert rows[lacking_one][4].startswith("no instrument yet: needs ")
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


def test_a_page_that_names_the_project_it_covers_names_no_other_and_jleak_finds_nothing(machine):
    machine.append("alpha", "ci.jsonl", job(1, "c1", 10, "success", NOW + timedelta(hours=1)))
    machine.build()

    out, _, _ = page(machine)
    text = out.read_text()

    assert "covers alpha" in text
    assert "beta" not in text
    assert "alpha-one" not in text
    assert str(machine.root) not in text
    assert SECRET not in text
    patterns = machine.root / "outbound.toml"
    patterns.write_text(
        f"[patterns]\nproject = '\\bbeta\\b'\nhome-path = '{machine.root}'\nsaid = '{SECRET}'\n"
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


def test_a_week_that_begins_before_the_row_records_shows_no_value_and_says_why(machine):
    _, rows, _ = page_of(machine, "2026-10-21")

    why = "n/a n 0 not covered: jbus's row records begin on 2026-10-14, after the week does"
    for name in (
        "Lead time, go to merge, median (DORA)",
        "Merges a week (DORA frequency)",
        "Change failure rate, push checks (DORA)",
        "Your typed messages per merged row",
    ):
        assert rows[name][4] == why, name
    assert rows["Lead time, go to merge, median (DORA)"][5] == "59 min n 1 missed"
    assert rows["Merges a week (DORA frequency)"][5] == "1 n 1 tracked"


def test_the_change_failure_rate_names_the_projects_it_covers_and_the_days_it_lacks(machine):
    machine.append("alpha", "ci.jsonl", job(1, "c1", 10, "success", NOW + timedelta(hours=1)))
    snapshots(
        machine,
        "alpha",
        [("alpha-one", 10, NOW + timedelta(hours=1)), ("alpha-two", 12, NOW - timedelta(days=2))],
    )
    machine.write("alpha", "queue.json", [{"slug": "alpha-one"}, {"slug": "alpha-two"}])
    machine.build()

    _, rows, _ = page(machine)

    assert rows["Change failure rate, push checks (DORA)"][5] == (
        "0% n 1 met: covers alpha; no push check of main kept for 1 merged row, on 2026-10-26"
    )


def test_s8_shows_a_labelled_weeks_wrong_closes_and_says_why_a_week_with_no_labels_has_none(
    machine,
):
    gates(machine, "alpha", [S, S, S, S, W, None])
    label(
        machine,
        "alpha",
        "2026-10-18",
        [
            ("alpha#1", "stood"),
            ("alpha#2", "stood"),
            ("alpha#3", "stood"),
            ("alpha#4", "corrected"),
            ("alpha#5", "other_done"),
            ("alpha#6", "open"),
        ],
    )
    machine.build()

    _, rows, _ = page(machine)

    s8 = rows["Gates closed by silence that were wrong (S8)"]
    assert s8[3] == "≤ 5%"
    assert s8[4] == "25% n 4 missed: your word 1 of 1"
    assert s8[5] == "n/a n 0 not covered: no scout's gate labels kept for the week"


def test_the_redo_rate_counts_the_rows_whose_7_days_end_in_the_week_a_later_row_redid(machine):
    machine.write(
        "beta",
        "queue.json",
        [
            {"slug": "beta-one"},
            {
                "slug": "beta-fix",
                "status": "queued",
                "approval": {
                    "basis": "rule",
                    "follows": "beta-one",
                    "ran_at": (NOW - timedelta(days=6)).isoformat(timespec="seconds"),
                },
            },
        ],
    )
    machine.build()

    _, rows, _ = page(machine)

    redo = rows["Redo rate"]
    assert redo[3] == "≤ 5%"
    assert redo[4] == (
        "n/a n 0 not covered: the parents named by follow-ups' goes begin on 2026-10-22, after "
        "the week does"
    )
    assert redo[5] == "100% n 1 missed: 0 merged rows not yet judged"


def test_the_redo_rate_says_how_many_rows_of_the_week_it_cannot_judge_yet(machine):
    merged = datetime.now(UTC) - timedelta(days=6, hours=12)
    records(machine, "alpha", merged, "alpha-new", 12)
    snapshots(machine, "alpha", [("alpha-new", 12, merged)])
    early = (merged - timedelta(days=20)).isoformat(timespec="seconds")
    planned = {"basis": "rule", "follows": "alpha-new", "ran_at": early}
    machine.write(
        "alpha", "queue.json", [{"slug": "alpha-new"}, {"slug": "u", "approval": planned}]
    )
    machine.build()

    _, rows, _ = page_of(machine, (merged + timedelta(days=7)).date().isoformat())

    with contextlib.closing(machine.store()) as store:
        waiting = store.execute(
            "SELECT count(*) FROM redo_rows WHERE NOT judged AND week = ?",
            (kpis.week_of((merged + timedelta(days=7)).date()).isoformat(),),
        ).fetchone()[0]
    assert waiting >= 1
    shown = f"{waiting} merged row{'s' * (waiting != 1)} not yet judged"
    assert rows["Redo rate"][5].endswith(shown)
