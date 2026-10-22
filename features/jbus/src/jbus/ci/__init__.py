"""`jbus ci`: count what a project's CI costs, keep the numbers, and compare them to nine targets.

`jbus ci` asks GitHub for the Actions jobs and pull requests of the last `--days` days
(`jbus.ci.collect`). It keeps each job once in `ci.jsonl` and each pull request in
`ci-prs.jsonl` of the project's state (`jbus.ci.ledger`). Then it prints the nine targets
(`jbus.ci.numbers`), each with how it counts. The `ci` panel of `jbus view` shows the
same ledger.

`--report` also writes `reports/ci-week-<date>.md` in the project's home over the last
`WEEK` days, and alerts the project once if the project missed a target (`jbus.ci.report`).
`jbus-ci.timer` runs `jbus ci --report` every Monday at 09:00 ET.

`--notice` is for a CI job: it prints the annotation that gives the collector the job's
telemetry (`jbus.ci.notice`), and needs no config.
"""

from __future__ import annotations

import argparse
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jbus
from jbus import verbs
from jbus.ci import collect, ledger, notice, numbers, report

DAYS = 14
WEEK = 7
REMOTE = "origin"


def repo_of(checkout: Path) -> str:
    """Return `<owner>/<name>` from the checkout's origin."""
    asked = subprocess.run(
        ["git", "-C", str(checkout), "remote", "get-url", REMOTE], capture_output=True, text=True
    )
    url = asked.stdout.strip().removesuffix(".git")
    if asked.returncode or "github.com" not in url:
        raise jbus.Refused(f"refused: {checkout} has no GitHub origin")
    return "/".join(url.replace(":", "/").split("/")[-2:])


def facts_of(state: Path, now: datetime) -> numbers.Facts:
    return numbers.Facts(
        ledger.read(state / ledger.JOBS),
        ledger.read(state / ledger.PULLS),
        ledger.read(state / "events.jsonl"),
        now,
    )


def lines(nine: list[numbers.Number]) -> list[str]:
    found = []
    for one in nine:
        verdict = "MISSED" if one.met is False else "met" if one.met else "no data"
        hosted = f"; hosted {one.hosted}" if one.hosted else ""
        found.append(f"{one.name}: {one.shown} (held to {one.target}) {verdict}{hosted}")
        found.append(f"  counted: {one.how} (n = {one.n})")
    return found


def run(args: argparse.Namespace, _: jbus.Config | None) -> int:
    if args.notice:
        try:
            print(notice.write(args.fields))
        except notice.Refused as error:
            print(f"refused: {error}")
            return 2
        return 0
    if args.fields:
        print("refused: field=value is for --notice")
        return 2
    config = jbus.load()
    project = verbs.project(config, args.project)
    state, now = config.state(project), datetime.now(UTC)
    try:
        counts = collect.collect(collect.Cli(), repo_of(project.checkout), state, now, args.days)
    except collect.Unavailable as error:
        print(f"ci: GitHub did not answer: {error}")
        return 1
    print(f"ci: {counts.runs} runs seen, {counts.jobs} jobs added, {counts.pulls} pull requests")
    facts = facts_of(state, now)
    start = now - timedelta(days=args.days)
    nine = numbers.compute(facts, start, now)
    print(f"ci: {project.name}, the last {args.days} days to {config.user.stamp(now)}")
    print("\n".join(lines(nine)))
    if not args.report:
        return 0
    week = now - timedelta(days=WEEK)
    this_week = numbers.compute(facts, week, now)
    zone = config.user.zone or UTC
    text = report.body(facts, this_week, week, now, zone, config.user)
    path = report.write(config.home(project), text, now, config.user)
    print(f"ci: report {path}")
    return report.escalate(config, project, this_week, path, now, print)


def _arguments(shown: argparse.ArgumentParser) -> None:
    shown.add_argument("--days", type=int, default=DAYS, help=f"days to collect and count ({DAYS})")
    shown.add_argument("--report", action="store_true", help="write the week's report and alert")
    shown.add_argument(
        "--notice",
        action="store_true",
        help="print the annotation that gives the collector a job's telemetry, and read no config",
    )
    shown.add_argument("fields", nargs="*", metavar="field=value", help="the fields of --notice")


VERBS = (
    verbs.Verb(
        "ci", "keep CI's job minutes and hold them to nine targets", _arguments, run, config=False
    ),
)
