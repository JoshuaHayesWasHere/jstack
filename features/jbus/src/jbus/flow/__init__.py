"""`jbus flow`: how work flowed in a window, over every project, measured from the records.

It reads each project's `events.jsonl`, jbus's journal (`journalctl --user -u jbus`) and GitHub's
runs, jobs and merged pull requests of each project's repo, and prints for the window:

- each row's time from approved to merged, split into working and waiting (`measure.lead_times`);
- the classes of waiting ranked by hours lost, over every row with time in the window
  (`measure.pareto`);
- how long main was red, and what that held up (`measure.main_red`);
- how long the machine had no room, why, and how long an account cap or a slot held a row
  (`measure.no_room`, `measure.caps`, `measure.slots`), and when jbus itself did not run;
- GitHub's queue and run time, cancels and reruns (`measure.ci`);
- how many events paged the owner (`measure.pages`);
- the share of the rows' time the records leave unexplained, and when each source's records
  begin, since a window that starts before them is time no record covers.

It writes nothing: no state, no lock, no file. It takes no lock, so it runs beside a pass. What it
prints is passed through `jbus.redact` with the config's secrets, so no webhook URL, key or token
is in it. `--no-github` skips GitHub. `--jobs` asks for each run's jobs, which give the queue time
and the run time of each job, at a call per run: it is refused where those calls would spend
more than half of what is left of GitHub's hourly budget (`records.affordable`). Without it a
run's time is the run's own, from its start to its last update, and no queue time is known.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import jbus
from jbus import digest, verbs
from jbus.flow import measure, records

DEFAULT_DAYS = 7


def build(
    projects: list[records.Project],
    lines: list[records.Line],
    found_runs: list[records.Run],
    merges: dict[str, dict],
    repos: dict[str, str],
    since: datetime,
    until: datetime,
) -> dict[str, Any]:
    """Return the whole measure of the window as one dict. `merges` maps a repo to the times its
    pull requests merged, by number, and `repos` maps a project to its repo."""
    by_project = {name: merges.get(repo, {}) for name, repo in repos.items()}
    found = measure.rows(projects, since, until, by_project)
    total = sum(one.hours() for one in found) or 1.0
    ranked = measure.pareto(found)
    unexplained = sum(one["hours"] for one in ranked if one["unexplained"])
    other = sum(one["hours"] for one in ranked if one["class"].startswith(("other:", "status ")))
    starts = [one.first for one in projects if one.first]
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "coverage": {
            "events_from": min(starts).isoformat() if starts else None,
            "journal_from": lines[0].at.isoformat() if lines else None,
            "runs": len(found_runs),
            "projects": [one.name for one in projects],
        },
        "rows": len(found),
        "row_hours": round(total, 1),
        "working_hours": round(sum(one.hours(True) for one in found), 1),
        "waiting_hours": round(sum(one.hours(False) for one in found), 1),
        "unexplained_share": round((unexplained + other) / total, 3),
        "lead_times": measure.lead_times(found),
        "pareto": ranked,
        "main_red": measure.main_red(found_runs, found, merges),
        "no_room": measure.no_room(lines, since, until),
        "caps": measure.caps(projects, lines, since, until),
        "slots": measure.slots(projects, since, until),
        "jbus": measure.jbus_down(lines, since, until),
        "ci": measure.ci(found_runs),
        "pages": measure.pages(projects, since, until),
    }


def gather(config: jbus.Config, args: argparse.Namespace, since: datetime, until: datetime):
    """Read every source for the window. A source that cannot be read is left out and named."""
    missing: list[str] = []
    projects, repos = [], {}
    for project in config.projects:
        path = config.state(project) / "events.jsonl"
        try:
            text = path.read_text()
        except OSError:
            missing.append(f"{project.name}: no events.jsonl")
            text = ""
        projects.append(records.events(project.name, text.splitlines()))
        repo = records.repo_of(project.checkout)
        if repo:
            repos[project.name] = repo
    said = None
    if not args.no_journal:
        said = records.ask(
            [
                "journalctl",
                "--user",
                "-u",
                "jbus",
                "--since",
                _local(since),
                "--until",
                _local(until),
                "-o",
                "short-iso",
                "--no-pager",
            ]
        )
        if said is None:
            missing.append("the journal of jbus")
    lines = records.journal(said or "")
    found_runs: list[records.Run] = []
    merges: dict[str, dict] = {}
    for repo in [] if args.no_github else sorted(set(repos.values())):
        ran = records.github_runs(repo, since, until, args.jobs)
        merged = records.github_merges(repo, since)
        if ran is None or merged is None:
            missing.append(f"GitHub for {repo}")
        found_runs += ran or []
        merges[repo] = merged or {}
    return projects, lines, found_runs, merges, repos, missing


def _local(moment: datetime) -> str:
    return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def text(said: dict[str, Any]) -> str:
    """Return the measure as lines a person reads."""
    out = [f"flow {said['since']} to {said['until']}"]
    cover = said["coverage"]
    out.append(
        f"records: events from {cover['events_from']}, journal from {cover['journal_from']}, "
        f"{cover['runs']} GitHub runs, projects {', '.join(cover['projects'])}"
    )
    if said.get("missing"):
        out.append(f"not read: {'; '.join(said['missing'])}")
    lead = said["lead_times"]
    out += [
        "",
        f"rows {said['rows']}: {said['row_hours']} h in the window, {said['working_hours']} h "
        f"working, {said['waiting_hours']} h waiting, {said['unexplained_share']:.0%} unexplained",
        f"merged {lead['merged']}: approved to merged median {lead['median_hours']} h, "
        f"85th percentile {lead['p85_hours']} h; {lead['working_hours']} h working, "
        f"{lead['waiting_hours']} h waiting",
        "",
        "approved to merged, longest first (working / waiting hours, the longest wait):",
    ]
    for row in lead["rows"][:25]:
        out.append(
            f"  {row['project']}/{row['slug']}: {row['working_hours']} / "
            f"{row['waiting_hours']} h, {row['top_wait'] or '-'}"
        )
    out += ["", "waiting by class, hours lost (share, running share, rows):"]
    for one in said["pareto"]:
        mark = " (unexplained)" if one["unexplained"] else ""
        out.append(
            f"  {one['hours']:>7} h  {one['share']:>5.1%}  {one['cumulative']:>6.1%}  "
            f"{one['rows']:>3}  {one['class']}{mark}"
        )
    red = said["main_red"]
    out += ["", f"main red: held {red['rows_held']} rows for {red['row_hours_held']} row-hours"]
    for repo, one in red["repos"].items():
        out.append(
            f"  {repo} ({one['gate']}): red {one['red_hours']} h in {one['red_spans']} spans, "
            f"{one['merges_while_red']} merges while red"
        )
    room, cap, slot, bus = said["no_room"], said["caps"], said["slots"], said["jbus"]
    reasons = ", ".join(f"{why} {h} h" for why, h in room["by_reason"].items()) or "none"
    accounts = ", ".join(f"{name} {h} h" for name, h in cap["by_account"].items()) or "none"
    out += [
        "",
        f"no room: {room['hours']} h in {room['spans']} spans, {room['rows_held']} rows held "
        f"({reasons})",
        f"account caps: {cap['hours_any']} h with an account capped, {cap['rows_held']} rows "
        f"held ({accounts})",
        f"test slots: {slot['test_slot_waits']} waits, {slot['test_slot_hours']} h, longest "
        f"{slot['test_slot_longest_min']} min; review pool: {slot['review_pool_waits']} waits, "
        f"{slot['review_pool_hours']} h",
        f"jbus: {bus['passes']} passes from {bus['first_pass']}, {bus['failed_passes']} failed "
        f"({bus['failed_hours']} h), {bus['gaps_over_10_min']} gaps over 10 min "
        f"({bus['gap_hours']} h), GitHub unreachable {bus['github_unreachable_hours']} h, "
        f"{bus['webhook_failures']} webhook failures",
        "",
        "GitHub runs (failure / cancelled / reruns; job queue total, median, 90th; run total):",
    ]
    for repo, one in said["ci"].items():
        out.append(
            f"  {repo}: {one['runs']} runs, {one['failure']} / {one['cancelled']} / "
            f"{one['reruns']}; queue {one['queue_hours']} h, {one['queue_median_s']} s, "
            f"{one['queue_p90_s']} s (self-hosted {one['queue_self_hosted_hours']} h); run "
            f"{one['run_hours']} h"
        )
    paged = said["pages"]
    kinds = ", ".join(f"{kind} {n}" for kind, n in paged["by_kind"].items()) or "none"
    out += ["", f"paged the owner: {paged['total']} ({kinds})"]
    return "\n".join(out)


def _flow(args: argparse.Namespace, config: jbus.Config) -> int:
    """Print the measure of the window. It writes nothing."""
    until = _time(args.until, config) or datetime.now(UTC)
    since = _time(args.since, config) or until - timedelta(days=DEFAULT_DAYS)
    if since >= until:
        raise jbus.Refused(f"refused: --since {args.since} is not before --until {until}")
    try:
        projects, lines, found_runs, merges, repos, missing = gather(config, args, since, until)
    except records.Unaffordable as error:
        raise jbus.Refused(str(error)) from None
    if args.project:
        projects = [one for one in projects if one.name == config.project(args.project).name]
    said = build(projects, lines, found_runs, merges, repos, since, until) | {"missing": missing}
    said = jbus.redact(said, config.secrets())
    print(json.dumps(said, indent=2, sort_keys=True) if args.json else text(said))
    return 0


def _time(given: str | None, config: jbus.Config) -> datetime | None:
    try:
        return digest.since(given, config.user)
    except ValueError:
        raise jbus.Refused(f"refused: {given} is not a time, as 2026-10-14T00:00 is") from None


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--since", help=f"from this time, the user's zone with none (default: {DEFAULT_DAYS} days)"
    )
    parser.add_argument("--until", help="to this time (default: now)")
    parser.add_argument("--json", action="store_true", help="print the measure as JSON")
    parser.add_argument("--no-github", action="store_true", help="ask GitHub nothing")
    parser.add_argument(
        "--jobs", action="store_true", help="ask each run's jobs for queue time: a call per run"
    )
    parser.add_argument("--no-journal", action="store_true", help="read no journal")


VERBS = (
    verbs.Verb(
        "flow",
        "how work flowed in a window: lead times, waits, main red, no room; writes nothing",
        _arguments,
        _flow,
        abbrev=False,
    ),
)
