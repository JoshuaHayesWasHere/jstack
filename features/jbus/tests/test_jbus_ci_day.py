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
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import jbus
import jsettings
from jbus import verbs
from jbus.ci import collect, daily, ruleset
from jgauge import spend
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


KEPT = CHECKOUT / ruleset.KEPT
RULESET = ["gh", "api", "repos/JoshuaHayesWasHere/jstack/rulesets/25665226"]


class Gh:
    """Stands in for `gh`: each call is kept, `gh run list` answers with `runs` and `gh api` with
    `ruleset`, the live ruleset, by default the checked-in body."""

    def __init__(self, runs=RUNS, code=0):
        self.runs, self.code, self.calls = runs, code, []
        self.ruleset = json.loads(KEPT.read_text())

    def __call__(self, command):
        self.calls.append(list(command))
        given = self.ruleset if command[1] == "api" else self.runs
        said = "" if self.code else json.dumps(given)
        return subprocess.CompletedProcess(command, self.code, said, "gh: HTTP 502")


class NoCollect:
    def __init__(self, *_, **__):
        raise AssertionError("--day collects nothing: the passes keep the ledger")


STORE = """
CREATE TABLE orchestration_v2_projection_threads (
    thread_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL);
CREATE TABLE orchestration_v2_projection_runs (
    run_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, requested_at TEXT NOT NULL,
    completed_at TEXT, payload_json TEXT NOT NULL);
CREATE TABLE orchestration_v2_projection_run_attempts (attempt_id TEXT PRIMARY KEY, run_id TEXT);
CREATE TABLE orchestration_v2_projection_provider_turns (
    provider_turn_id TEXT PRIMARY KEY, run_attempt_id TEXT, payload_json TEXT NOT NULL);
"""


class Store:
    """Stands in for T3 Code's store: `run` adds a run of a thread, by its title and project."""

    def __init__(self, path):
        self.path, self.runs = path, 0
        with sqlite3.connect(path) as db:
            db.executescript(STORE)

    def run(self, title, start, done, given, output, project):
        self.runs += 1
        run, thread = f"run{self.runs}", f"thread:{project}:{title}"
        usage = {"inputTokens": given, "outputTokens": output}
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT OR IGNORE INTO orchestration_v2_projection_threads VALUES (?, ?, ?)",
                (thread, project, title),
            )
            db.execute(
                "INSERT INTO orchestration_v2_projection_runs VALUES (?, ?, ?, ?, ?)",
                (run, thread, start, done, json.dumps({"startedAt": start})),
            )
            db.execute(
                "INSERT INTO orchestration_v2_projection_run_attempts VALUES (?, ?)", (run, run)
            )
            db.execute(
                "INSERT INTO orchestration_v2_projection_provider_turns VALUES (?, ?, ?)",
                (run, run, json.dumps({"turnTokenUsage": usage})),
            )


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
    monkeypatch.setattr(spend, "STORE", kitchen.root / "t3" / "statev2.sqlite")

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

    def store():
        spend.STORE.parent.mkdir(parents=True, exist_ok=True)
        return Store(spend.STORE)

    def task(slug, *branches):
        tasks = made.home / "tasks"
        tasks.mkdir(parents=True, exist_ok=True)
        lines = [f"Branch: {slug}   Pull request: {one}" for one in branches]
        (tasks / f"{slug}.md").write_text("\n".join([f"# {slug}: a row", *lines, ""]))

    made.run, made.rows, made.store, made.task = run, rows, store, task
    made.project = jbus.load().projects[0].project_id
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


@pytest.fixture
def guarded(day):
    """The day's run in a checkout that keeps main's ruleset body, with the home's
    `required-checks` naming check, borders and macos, as jstack's does."""
    (day.kitchen.checkout / ruleset.KEPT).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(KEPT, day.kitchen.checkout / ruleset.KEPT)
    (day.home / "required-checks").write_text("check\nborders\nmacos\n")
    return day


def told(day):
    """What a pass tells the home about the ruleset."""
    day.kitchen.poll(NOW.astimezone(UTC))
    return [line for line in day.kitchen.wakes.said if "ruleset" in line]


def lacking_macos(body):
    body = json.loads(json.dumps(body))
    for rule in body["rules"]:
        if rule["type"] == "required_status_checks":
            checks = rule["parameters"]["required_status_checks"]
            checks[:] = [one for one in checks if one["context"] != "macos"]
    return body


def test_ci_day_ruleset_that_matches_tells_nobody_after_one_read(guarded):
    code, said, _ = guarded.run()

    assert code == 0, said
    assert guarded.gh.calls == [GH, RULESET]
    assert "ruleset 25665226 on JoshuaHayesWasHere/jstack matches" in said
    assert told(guarded) == []


def test_ci_day_ruleset_that_lacks_macos_tells_the_home_its_drift(guarded):
    guarded.gh.ruleset = lacking_macos(guarded.gh.ruleset)

    code, said, _ = guarded.run()

    assert code == 0, said
    (line,) = told(guarded)
    assert "ruleset 25665226" in line and "drifted" in line
    assert "required_status_checks" in line and "lacks macos of required-checks" in line


def test_ci_day_ruleset_requiring_a_check_required_checks_does_not_name_is_drift(guarded):
    (guarded.home / "required-checks").write_text("check\nborders\n")

    guarded.run()

    (line,) = told(guarded)
    assert "requires macos, which required-checks does not name" in line
    assert "rules differ" not in line


@pytest.mark.parametrize(
    ("code", "answer", "why"),
    [(1, None, "gh: HTTP 502"), (0, {"message": "Not Found"}, "gh gave no rules")],
)
def test_ci_day_ruleset_gh_does_not_give_is_said_and_tells_nobody(guarded, code, answer, why):
    guarded.gh.code, guarded.gh.ruleset = code, answer

    ran, said, _ = guarded.run()

    assert ran == 0, said
    assert f"ruleset 25665226 not read: {why}" in said
    assert told(guarded) == []


def test_ci_day_ruleset_of_a_checkout_with_no_github_origin_is_said_and_never_asked(guarded):
    guarded.kitchen.git("remote", "set-url", "origin", "/elsewhere/demo.git")

    _, said, _ = guarded.run()

    assert "ruleset 25665226 not read: the checkout has no GitHub origin" in said
    assert guarded.gh.calls == []
    assert told(guarded) == []


def test_ci_day_ruleset_with_no_required_checks_file_is_held_to_jmerges_check_alone(guarded):
    (guarded.home / "required-checks").unlink()

    guarded.run()

    (line,) = told(guarded)
    assert "requires borders, macos, which required-checks does not name" in line


PULL = "https://github.com/JoshuaHayesWasHere/jstack/pull/{}"


def reviews(day):
    """Five review launches on 11-04 and one on 11-02, of the fixture's pull requests:

    - #1038 (`check` green at its newest head at 18:57:49Z): its first review at 18:40Z, two
      runs of 5 and 2 minutes, before the green, and its scoped pass at 19:00Z, 5 minutes;
    - #1041 (green at 19:09:28Z): one review at 19:10Z, 4 minutes;
    - #1043 (green at 19:31:46Z): one review at 19:35Z, 2 minutes;
    - a review of a slug whose brief names no pull request, and one of another T3 project;
    - on 11-02, a review of a slug whose brief names #99999, which the ledger does not hold, and
      one of a slug with no brief.
    """
    store = day.store()
    us, them = day.project, "another-project"
    review = "review: cicd-pstack-pins, 1"
    store.run(review, "2026-11-04T18:40:00Z", "2026-11-04T18:45:00Z", 600_000, 6_000, us)
    store.run(review, "2026-11-04T18:50:00Z", "2026-11-04T18:52:00Z", 400_000, 4_000, us)
    scoped = "review: cicd-pstack-pins, scoped"
    store.run(scoped, "2026-11-04T19:00:00Z", "2026-11-04T19:05:00Z", 500_000, 5_000, us)
    pair = "review: cicd-macos-pair-reuse, 1"
    store.run(pair, "2026-11-04T19:10:00Z", "2026-11-04T19:14:00Z", 300_000, 3_000, us)
    health = "review: cicd-ci-health-numbers, 1"
    store.run(health, "2026-11-04T19:35:00Z", "2026-11-04T19:37:00Z", 200_000, 2_000, us)
    store.run("review: no-pull, 1", "2026-11-04T20:00:00Z", "2026-11-04T20:09:00Z", 9, 9, us)
    store.run(pair, "2026-11-04T19:10:00Z", "2026-11-04T19:59:00Z", 9_000_000, 90_000, them)
    gone = "review: gone-pull, 1"
    store.run(gone, "2026-11-02T15:00:00Z", "2026-11-02T15:03:00Z", 2_000_000, 1_000, us)
    unbriefed = "review: no-brief, 1"
    store.run(unbriefed, "2026-11-02T16:00:00Z", "2026-11-02T16:01:00Z", 9, 9, us)
    day.task("cicd-pstack-pins", PULL.format(1038), "none")
    day.task("cicd-macos-pair-reuse", PULL.format(1041))
    day.task("cicd-ci-health-numbers", PULL.format(1043))
    day.task("no-pull", "none")
    day.task("gone-pull", PULL.format(99999))


def test_ci_day_gives_the_review_steps_launches_tokens_and_active_wall_per_pull_request(day):
    """Per pull request, a day sums its launches: #1038's two are 1.5M input, 15k output and
    12 minutes of runs, the 3 minutes between its first review's two turns not among them. The
    p50 of the three pull requests is 300k, 3k and 4 min. The launch of a slug with no pull
    request is a launch and no pull request's, and another project's is not counted."""
    reviews(day)
    found = by_day(day.run()[2])
    column = {name: cells["11-04"] for name, cells in found.items()}
    assert (column["review launches"], column["review launches n"]) == ("5", "3 PRs")
    tokens = (column["review input tokens per PR p50"], column["review output tokens per PR p50"])
    assert tokens == ("300k", "3k")
    assert column["review input tokens per PR p50 n"] == "3 PRs"
    wall = (column["review active wall per PR p50"], column["review active wall per PR p50 n"])
    assert wall == ("4 min", "3 PRs")
    assert (found["review launches"]["11-03"], found["review launches n"]["11-03"]) == (
        "0",
        "0 PRs",
    )
    assert found["review active wall per PR p50"]["11-03"] == "no data"


def test_ci_day_counts_the_review_launches_before_check_passed_at_the_newest_head(day):
    """Of the 4 launches on 11-04 joined to a pull request, only #1038's first came before
    `check` was green at its newest head. On 11-02 the one launch's pull request has no `check`
    in the ledger, so it is not counted either way, and a launch of a slug with no brief is a
    launch alone."""
    reviews(day)
    found = by_day(day.run()[2])
    before = "review launches before check"
    assert (found[before]["11-04"], found[f"{before} n"]["11-04"]) == ("1", "4 launches")
    assert (found["review launches"]["11-02"], found["review launches n"]["11-02"]) == (
        "2",
        "1 PRs",
    )
    assert found["review input tokens per PR p50"]["11-02"] == "2M"
    assert (found[before]["11-02"], found[f"{before} n"]["11-02"]) == ("no data", "0 launches")


def test_ci_day_reads_the_review_numbers_as_no_data_when_t3_codes_store_is_not_there(day):
    code, said, text = day.run()
    assert code == 0, said
    assert f"T3 Code's store was not read: {spend.STORE} is not T3 Code's store" in text
    assert set(by_day(text)["review launches"].values()) == {"no data"}
    assert by_day(text)["red share"]["11-03"] == "62%"


def test_ci_day_reads_the_review_numbers_as_no_data_when_t3_codes_store_cannot_be_read(day):
    spend.STORE.parent.mkdir(parents=True, exist_ok=True)
    spend.STORE.write_text("not a database")
    code, said, text = day.run()
    assert code == 0, said
    assert f"T3 Code's store was not read: {spend.STORE} cannot be read: " in text
    assert set(by_day(text)["review launches"].values()) == {"no data"}
