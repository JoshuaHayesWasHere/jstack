"""`jbus ci --day` writes `reports/ci-day-<date>.md`: the CI health numbers and main-red for each of
the last 7 local days, with the n under each cell, and a before and after for each cicd row that
merged.

The tests run the real verb over a ledger cut from jstack's own, 2026-10-29 to 2026-11-04 ET
(`fixtures/ci/day`), and main's push runs of check.yml as `gh run list` gave them on 2026-11-04.
The definitions are in `docs/jbus/measure-the-ci.md`, "The day's report".
"""

import gzip
import json
import shlex
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import jbus
import jsettings
from jbus import verbs
from jbus.ci import collect, daily
from test_jbus_ci import fire, unit
from testing.paths import REPO as CHECKOUT

DAY = Path(__file__).parent / "fixtures" / "ci" / "day"
ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 5, 6, 45, tzinfo=ET)
"""The 06:45 run the timer makes on the morning after the cut."""
DATES = ["10-29", "10-30", "10-31", "11-01", "11-02", "11-03", "11-04"]
RUNS = json.loads((DAY / "main-runs.json").read_text())
GH = [
    "gh",
    "run",
    "list",
    "-R",
    "JoshuaHayesWasHere/jstack",
    "--workflow",
    "check.yml",
    "--branch",
    "main",
    "--event",
    "push",
    "--limit",
    "400",
    "--json",
    "conclusion,status,createdAt,updatedAt,headSha",
]


class Gh:
    """Stands in for `gh`: each call is kept, and `gh run list` answers with `runs`."""

    def __init__(self, runs=RUNS, code=0):
        self.runs, self.code, self.calls = runs, code, []

    def __call__(self, command):
        self.calls.append(list(command))
        said = "" if self.code else json.dumps(self.runs)
        return subprocess.CompletedProcess(command, self.code, said, "gh: HTTP 502")


class NoCollect:
    def __init__(self, *_, **__):
        raise AssertionError("--day collects nothing: the passes keep the ledger")


def brief(home, slug):
    return f"# {slug}: a row\nTask: x\nHome: {home}\n"


def merged(slug, at):
    return {"slug": slug, "from": "pr", "to": "merged", "at": at}


@pytest.fixture
def day(kitchen, monkeypatch):
    """The kitchen's project with the cut ledger in its state, the clock at 06:45 on 2026-11-05,
    `gh` answering main's runs, and `jbus ci --day` ready to run. `run` runs it and returns the
    exit code, what it printed and the report's text."""
    state = kitchen.state
    state.mkdir(parents=True, exist_ok=True)
    with gzip.open(DAY / "ci.jsonl.gz", "rt") as cut:
        (state / "ci.jsonl").write_text(cut.read())
    shutil.copy(DAY / "ci-prs.jsonl", state / "ci-prs.jsonl")
    (kitchen.home / "cicd").mkdir(parents=True)
    (kitchen.home / "cicd" / "home-id").write_text("mcp:launch:cicd\n")
    kitchen.git("remote", "set-url", "origin", "https://github.com/JoshuaHayesWasHere/jstack.git")
    monkeypatch.setattr(verbs, "clock", lambda: NOW.astimezone(UTC))
    monkeypatch.setattr(collect, "Cli", NoCollect)
    gh = Gh()
    monkeypatch.setattr(daily, "ask", gh)

    class Day:
        pass

    made = Day()
    made.kitchen, made.state, made.gh = kitchen, state, gh
    made.home = jbus.load().home(jbus.load().projects[0])
    made.path = made.home / "reports" / "ci-day-2026-11-05.md"

    def run(*more):
        code, said = kitchen.main("--project", "demo", "ci", "--day", *more)
        return code, said, made.path.read_text() if made.path.exists() else ""

    def rows(*given):
        briefs = state / "briefs"
        briefs.mkdir(exist_ok=True)
        lines = []
        for slug, home, at in given:
            (briefs / f"{slug}.md").write_text(brief(home, slug))
            lines.append(json.dumps(merged(slug, at)) + "\n")
        (state / "transitions.jsonl").write_text("".join(lines))

    made.run, made.rows = run, rows
    return made


def table(text, heading):
    """The rows of the first table under `heading`, each a list of its cells."""
    part = text.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]
    lines = [one for one in part.splitlines() if one.startswith("|")]
    return [[cell.strip() for cell in one.strip("|").split("|")] for one in lines]


def by_day(text):
    """The day table as {row name: {day: cell}}, with the n row under a number keyed
    `<name> n`."""
    head, _, *rest = table(text, "By day")
    days = [one.split()[0] for one in head[2:]]
    found, last = {}, ""
    for cells in rest:
        name = cells[0] or f"{last} n"
        last = cells[0] or last
        found[name] = dict(zip(days, cells[2:], strict=True))
    return found


def test_ci_day_writes_the_seven_local_days_before_the_run_each_cell_with_its_n(day):
    code, said, text = day.run()

    assert code == 0, said
    assert f"ci: day report {day.path}" in said
    found = by_day(text)
    assert list(found["red share"]) == DATES
    assert (found["red share"]["11-03"], found["red share n"]["11-03"]) == ("62%", "101 PRs")
    shard = (found["shard wait p90"]["11-03"], found["shard wait p90 n"]["11-03"])
    assert shard == ("555 s", "3162 jobs")
    macos = (found["macos wait p90"]["11-03"], found["macos wait p90 n"]["11-03"])
    assert macos == ("1029 s", "438 jobs")
    assert set(found) == {name for one in daily.MEASURES for name in (one.name, f"{one.name} n")}


def test_ci_day_gives_the_quiet_day_baseline_of_oct_30(day):
    """The brief's baseline for 10-30, from the scout's read of the ledger: 36 PRs, 25% red,
    shard and macos p90 3 s and 9 s, wall p50 9.3 min, 2.3 shas per PR and 0.4 h open to merge.
    One PR of the 36 had only a skipped `check`, which ran nothing, so the day counts 35 and
    9 of 35 is 26%."""
    found = by_day(day.run()[2])
    column = {name: cells["10-30"] for name, cells in found.items()}
    assert column["red share"] == "26%" and column["red share n"] == "35 PRs"
    assert column["shard wait p90"] == "3 s" and column["macos wait p90"] == "9 s"
    assert column["PR check wall p50"] == "9.3 min"
    assert column["head shas per merged PR"] == "2.3"
    assert column["open to merge p50"] == "0.4 h"


def test_ci_day_reads_no_data_for_a_day_under_20_prs_and_still_shows_its_n(day):
    found = by_day(day.run()[2])
    for when, n in (("10-31", "18 PRs"), ("11-01", "7 PRs")):
        assert found["red share"][when] == "no data"
        assert found["red share n"][when] == n
        assert found["shard wait p90"][when] == "no data"
    assert found["main-red"]["11-01"] != "no data"


def test_ci_day_marks_a_day_whose_shard_wait_p90_is_over_300_s_a_wave(day):
    head = table(day.run()[2], "By day")[0]
    assert head[2:] == [
        "10-29",
        "10-30",
        "10-31",
        "11-01",
        "11-02",
        "11-03 wave",
        "11-04",
    ]


def test_ci_day_counts_main_red_by_the_spell_method_split_at_local_midnight(day):
    """gap-revert-oldest-red's F1 read the same 400 runs and found 297 minutes on Nov 3-4."""
    found = by_day(day.run()[2])
    minutes = [float(found["main-red"][when].split()[0]) for when in ("11-03", "11-04")]
    assert round(sum(minutes)) == 297
    assert found["main-red n"]["11-03"].endswith(" runs")


def test_ci_day_makes_one_gh_run_list_call_collects_nothing_and_writes_only_its_report(day):
    before = {path for path in day.kitchen.root.rglob("*") if path.is_file()}

    code, said, _ = day.run()

    assert code == 0, said
    assert day.gh.calls == [GH]
    after = {path for path in day.kitchen.root.rglob("*") if path.is_file()}
    assert after - before == {day.path}
    assert day.kitchen.wakes.said == [] and not day.kitchen.events("alert")


def test_ci_day_reads_main_red_as_no_data_on_a_day_the_runs_do_not_reach_back_to(day):
    late = [one for one in RUNS if one["createdAt"] >= "2026-10-31T12:00:00Z"]
    day.gh.runs = late
    found = by_day(day.run()[2])
    assert [found["main-red"][when] for when in DATES[:3]] == ["no data"] * 3
    assert found["main-red"]["11-01"] != "no data"


def test_ci_day_writes_its_report_with_main_red_no_data_when_gh_does_not_answer(day):
    day.gh.code = 1
    code, said, text = day.run()
    assert code == 0, said
    assert "gh run list did not answer: gh: HTTP 502" in text
    assert set(by_day(text)["main-red"].values()) == {"no data"}
    assert by_day(text)["red share"]["11-03"] == "62%"


def test_ci_day_gives_a_before_and_after_for_each_cicd_row_that_merged(day):
    """`cicd-early` merged on 10-31: before it are 10-30 and 10-29, two busy days of three, and
    after it 11-02, 11-03 and 11-04, one a wave day. `cicd-near` merged two days later, so the
    two share their move. A row of another home is not listed."""
    day.rows(
        ("cicd-early", "cicd", "2026-10-31T16:00:00+00:00"),
        ("cicd-near", "cicd", "2026-11-02T16:00:00+00:00"),
        ("root-row", "root", "2026-11-02T17:00:00+00:00"),
    )

    rows = table(day.run()[2], "Before and after each cicd row that merged")

    names = [one[0] for one in rows[2:]]
    assert names == ["cicd-early", "cicd-near"]
    early = dict(zip(rows[0], rows[2], strict=True))
    assert early["merged"] == "10-31"
    assert early["before"] == "10-29, 10-30 (2 of 3)"
    assert early["after"] == "11-02, 11-03 wave, 11-04"
    assert early["notes"] == "shared with cicd-near; wave"
    assert early["red share"].startswith("no data")
    near = dict(zip(rows[0], rows[3], strict=True))
    assert near["after"] == "11-03 wave, 11-04 (2 of 3)"


def test_ci_day_keeps_a_rows_last_merge(day):
    day.rows(
        ("cicd-twice", "cicd", "2026-10-29T16:00:00+00:00"),
        ("cicd-twice", "cicd", "2026-11-02T16:00:00+00:00"),
    )
    rows = table(day.run()[2], "Before and after each cicd row that merged")
    assert [(one[0], one[1]) for one in rows[2:]] == [("cicd-twice", "11-02")]


@pytest.mark.parametrize(
    ("before", "after", "verdict"),
    [
        ((20.0, 30.0, 25.0), (40.0, 50.0, 45.0), "moved"),
        ((20.0, 30.0, 25.0), (29.0, 31.0, 30.0), "held"),
        ((20.0, 30.0, 25.0), (10.0, 12.0, 30.0), "moved"),
        ((20.0, 30.0), (40.0, 50.0, 45.0), "no data"),
        ((20.0, 30.0, 25.0), (40.0,), "no data"),
    ],
)
def test_ci_day_calls_a_move_only_when_the_after_median_is_outside_the_before_days(
    before, after, verdict
):
    assert daily.verdict(list(before), list(after)) == verdict


def test_ci_day_keeps_the_pull_requests_of_jmerges_line_out_of_the_counts(day):
    """A shadow pull request of jmerge's line (`jstack/line/`) tests a prefix of the line, not
    a crew's work: its red check is no red pull request."""
    with (day.state / "ci.jsonl").open("a") as jobs:
        for pr in (9001, 9002):
            jobs.write(
                json.dumps(
                    {
                        "run": pr,
                        "job": pr,
                        "attempt": 1,
                        "name": "check",
                        "sha": f"{pr:040d}",
                        "branch": f"jstack/line/{pr}",
                        "pr": pr,
                        "event": "pull_request",
                        "created": "2026-11-03T15:00:00+00:00",
                        "started": "2026-11-03T15:00:01+00:00",
                        "completed": "2026-11-03T15:05:00+00:00",
                        "conclusion": "failure",
                        "kind": "hosted",
                        "runner": "GitHub Actions 1",
                        "steps": 3,
                        "tests": [],
                        "signs": [],
                    }
                )
                + "\n"
            )
    found = by_day(day.run()[2])
    assert (found["red share"]["11-03"], found["red share n"]["11-03"]) == ("62%", "101 PRs")


def test_ci_day_gives_the_newest_day_as_lines_the_digest_reads(day):
    day.run()
    said = daily.latest(day.home, NOW.astimezone(UTC), jsettings.load())
    assert said["path"] == str(day.path)
    assert (said["date"], said["day"], said["stale"]) == ("2026-11-05", "2026-11-04", False)
    assert said["lines"][0].startswith("red share: ")
    assert len(said["lines"]) == len(daily.MEASURES)


def test_ci_day_with_report_is_refused(day):
    code, said, _ = day.run("--report")
    assert (code, said.strip()) == (2, "refused: --day writes the day's report alone, not --report")
    assert day.gh.calls == []


def test_ci_day_each_writes_the_report_of_each_project_that_asks(day):
    path = day.kitchen.config_dir / "config.toml"
    path.write_text(
        path.read_text().replace('state = "demo"\n', 'state = "demo"\nci_report = true\n')
    )
    command = shlex.split(unit("jbus-ci-day.service")["Service"]["ExecStart"])
    assert command[0].endswith("/.local/bin/jbus") and command[1:] == ["ci", "--day", "--each"]

    code, said = day.kitchen.main(*command[1:])

    assert code == 0, said
    assert day.path.exists() and day.gh.calls == [GH]


@pytest.mark.skipif(not shutil.which("systemd-analyze"), reason="no systemd-analyze")
def test_ci_day_timer_fires_every_day_at_06_45_in_the_machines_own_zone():
    new_york = fire("America/New_York", "jbus-ci-day.timer")
    assert [one.split()[1:3] for one in new_york] == [
        ["2026-10-18", "10:45:00"],
        ["2026-10-19", "10:45:00"],
        ["2026-10-20", "10:45:00"],
    ]
    timer = unit("jbus-ci-day.timer")
    assert timer["Timer"]["OnCalendar"] == "*-*-* 06:45:00"
    assert timer["Timer"]["Persistent"] == "true"


def test_ci_day_doc_names_each_number_and_its_target_as_a_proposal():
    """The doc is the one definition: every number the report gives is in it, with its proposed
    target, and no target is held."""
    doc = (CHECKOUT / "features/jbus/docs/jbus/measure-the-ci.md").read_text()
    part = doc.split("## The day's report", 1)[1]
    for one in daily.MEASURES:
        assert f"| {one.name} |" in part, one.name
        if one.proposal:
            assert f"| {one.name} | {one.proposal} (proposal) |" in part, one.name
    assert "never UTC" in part and "proposal" in part
