"""`jbus flow`: how work flowed in a window, over every project, measured from the records.

It reads the `events.jsonl` of every folder of jbus's state that has one (each project, and
any other jbus keeps state for), jbus's journal (`journalctl --user -u jbus`, or a file of its
lines with `--journal`), the jobs `jbus ci` kept in a project's `ci.jsonl`, and GitHub's runs,
jobs and merged pull requests of each configured project's repo, and prints for the window:

- each row's time from approved to merged, split into working and waiting (`measure.lead_times`),
  and with `--rows` every merged row's spans, each with the record that opened it;
- the classes of waiting ranked by hours lost, over every row with time in the window
  (`measure.pareto`), and what the hours behind a `depends` waited on at the head of the chain
  (`measure.behind`);
- how long main was red, and what that held up (`measure.main_red`);
- how long the machine had no room, why, and how long an account cap or a slot held a row
  (`measure.no_room`, `measure.caps`, `measure.slots`), and when jbus itself did not run;
- GitHub's queue and run time, cancels and reruns (`measure.ci`);
- how many events paged the owner (`measure.pages`);
- the share of the rows' time the records leave unexplained, and apart from it the share before
  any record of the row (`no record`), with when each source's records begin, since a window
  that starts before them is time no record covers.

`jbus flow nudges <since> <until>` counts the owner's nudges in the home threads instead, from
T3 Code's store (`jbus.flow.nudges`), and `jbus flow asks <since> <until>` his status asks in
every thread, per job and per day (`jbus.flow.asks`).

It writes nothing: no state, no lock, no file. It takes no lock, so it runs beside a pass. What it
prints is passed through `jbus.redact` with the config's secrets, so no webhook URL, key or token
is in it. `--no-github` skips GitHub. `--jobs` asks for each run's jobs, which give the queue time
and the run time of each job, at a call per run: it is refused where those calls would spend
more than half of what is left of GitHub's hourly budget, or take it to the floor that jbus and
the threads keep for merges (`records.affordable`, `jbus.budget`). Without it a
run's time is the run's own, from its start to its last update, and no queue time is known.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jbus
from jbus import digest, verbs
from jbus.ci import ledger
from jbus.flow import asks, measure, nudges, records

DEFAULT_DAYS = 7


def build(
    projects: list[records.Project],
    lines: list[records.Line],
    found_runs: list[records.Run],
    merges: dict[str, dict],
    repos: dict[str, str],
    since: datetime,
    until: datetime,
    jobs: dict[str, list[dict]] | None = None,
    spans: bool = False,
) -> dict[str, Any]:
    """Return the whole measure of the window as one dict. `merges` maps a repo to the times its
    pull requests merged, by number, `repos` maps a project to its repo, and `jobs` a project
    to the jobs its `ci.jsonl` kept. With `spans`, each merged row carries its spans."""
    by_project = {name: merges.get(repo, {}) for name, repo in repos.items()}
    found = measure.rows(projects, since, until, by_project)
    total = sum(one.hours() for one in found) or 1.0
    ranked = measure.pareto(found)
    unexplained = sum(one["hours"] for one in ranked if one["unexplained"])
    other = sum(one["hours"] for one in ranked if one["class"].startswith(("other:", "status ")))
    unrecorded = sum(one["hours"] for one in ranked if one["no_record"])
    starts = [one.first for one in projects if one.first]
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "coverage": {
            "events_from": min(starts).isoformat() if starts else None,
            "journal_from": lines[0].at.isoformat() if lines else None,
            "runs": len(found_runs),
            "projects": [one.name for one in projects],
            "events_from_by_project": {
                one.name: one.first.isoformat() if one.first else None for one in projects
            },
        },
        "rows": len(found),
        "row_hours": round(total, 1),
        "working_hours": round(sum(one.hours(True) for one in found), 1),
        "working": {
            what: round(sum(s.hours for one in found for s in one.spans if s.what == what), 1)
            for what in measure.WORKING
        },
        "waiting_hours": round(sum(one.hours(False) for one in found), 1),
        "unexplained_share": round((unexplained + other) / total, 3),
        "no_record_share": round(unrecorded / total, 3),
        "lead_times": measure.lead_times(found, spans),
        "pareto": ranked,
        "behind": measure.behind(found),
        "main_red": measure.main_red(found_runs, found, merges),
        "no_room": measure.no_room(lines, since, until),
        "caps": measure.caps(projects, lines, since, until),
        "slots": measure.slots(projects, since, until),
        "jbus": measure.jbus_down(lines, since, until),
        "ci": measure.ci(found_runs),
        "ci_ledger": measure.ledger_jobs(jobs or {}, since, until),
        "pages": measure.pages(projects, since, until),
    }


LOG = "events.jsonl"


def gather(config: jbus.Config, args: argparse.Namespace, since: datetime, until: datetime):
    """Read every source for the window. A source that cannot be read is left out and named."""
    missing: list[str] = []
    projects, repos, jobs = [], {}, {}
    configured = {config.state(one).name: one for one in config.projects}
    state = config.state_dir
    found = set()
    if state.is_dir():
        found = {one.name for one in state.iterdir() if (one / LOG).is_file()}
    for name in sorted(found | set(configured), key=str.lower):
        folder = state / name
        try:
            text = (folder / LOG).read_text(errors="replace")
        except OSError:
            missing.append(f"{name}: no {LOG}")
            text = ""
        projects.append(records.events(name, text.splitlines()))
        jobs[name] = ledger.read(folder / ledger.JOBS)
        project = configured.get(name)
        repo = records.repo_of(project.checkout) if project else None
        if repo:
            repos[name] = repo
        elif not args.no_github:
            missing.append(f"GitHub for {name}: no project of the config with a GitHub origin")
    said = None
    if args.journal is not None:
        try:
            said = args.journal.read_text(errors="replace")
        except OSError as error:
            why = f"refused: {args.journal} cannot be read: {error.strerror}"
            raise jbus.Refused(why) from None
    elif not args.no_journal:
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
    return projects, lines, found_runs, merges, repos, jobs, missing


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
        f"working, {said['waiting_hours']} h waiting, {said['unexplained_share']:.1%} "
        f"unexplained, {said['no_record_share']:.1%} before any record of the row (no record)",
        "working: " + ", ".join(f"{what} {hours} h" for what, hours in said["working"].items()),
        f"merged {lead['merged']}: approved to merged median {lead['median_hours']} h, "
        f"85th percentile {lead['p85_hours']} h; {lead['working_hours']} h working, "
        f"{lead['waiting_hours']} h waiting",
        "",
        "approved to merged, longest first (working / waiting hours, the longest wait):",
    ]
    every = "spans" in (lead["rows"][0] if lead["rows"] else {})
    for row in lead["rows"] if every else lead["rows"][:25]:
        out.append(
            f"  {row['project']}/{row['slug']}: {row['working_hours']} / "
            f"{row['waiting_hours']} h, most on {row['top_wait'] or '-'} "
            f"({row['top_wait_hours']} h)"
        )
        for span in row.get("spans", []):
            out.append(
                f"    {span['start']} {span['hours']:>6} h  {span['class']}  <- {span['source']}"
            )
    if not every and len(lead["rows"]) > 25:
        out.append(f"  ({len(lead['rows']) - 25} more, and each row's spans, with --rows)")
    out += ["", "waiting by class, hours lost (share, running share, rows, the longest row):"]
    for one in said["pareto"]:
        mark = " (unexplained)" if one["unexplained"] else ""
        mark = " (before any record)" if one["no_record"] else mark
        out.append(
            f"  {one['hours']:>7} h  {one['share']:>5.1%}  {one['cumulative']:>6.1%}  "
            f"{one['rows']:>3}  {one['class']}{mark}; most {one['worst_row']} "
            f"{one['worst_row_hours']} h"
        )
    chain = said["behind"]
    out += [
        "",
        f"ordering, what the head of each chain was doing: {chain['hours']} h, "
        f"{chain['chains']} spans behind a chain of two or more, the longest "
        f"{chain['longest_chain']} links",
    ]
    for one in chain["heads"]:
        out.append(f"  {one['hours']:>7} h  {one['share']:>5.1%}  {one['class']}")
    red = said["main_red"]
    out += ["", f"main red: held {red['rows_held']} rows for {red['row_hours_held']} row-hours"]
    for repo, one in red["repos"].items():
        out.append(
            f"  {repo} ({one['gate']}): red {one['red_hours']} h in {one['red_spans']} spans, "
            f"{one['merges_while_red']} merges while red; no job ran for "
            f"{one['no_job_hours']} h ({one['no_job_runs']} runs)"
        )
        for span in one["spans"]:
            out.append(
                f"    {span['start']} to {span['end']}: run {span['red_run']} to "
                f"{span['green_run'] or 'still red'}"
            )
        for flow, each in one["by_workflow"].items():
            if flow != one["gate"] and (each["red_spans"] or each["no_job_runs"]):
                still = ", still red" if each["still_red"] else ""
                out.append(
                    f"    other workflow {flow}: {each['runs']} runs, red {each['red_hours']} h "
                    f"in {each['red_spans']} spans{still}, no job ran in "
                    f"{each['no_job_runs']} runs ({each['no_job_hours']} h)"
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
        "GitHub runs (failure / cancelled / reruns; job queue total, median, 90th, with --jobs; "
        "run total):",
    ]
    for repo, one in said["ci"].items():
        out.append(
            f"  {repo}: {one['runs']} runs, {one['failure']} / {one['cancelled']} / "
            f"{one['reruns']}; queue {one['queue_hours']} h, {one['queue_median_s']} s, "
            f"{one['queue_p90_s']} s (self-hosted {one['queue_self_hosted_hours']} h); run "
            f"{one['run_hours']} h"
        )
    for name, one in said["ci_ledger"].items():
        out.append(f"  {name}, jobs `jbus ci` kept from {one['from']} to {one['to']}:")
        for kind, each in one.items():
            if isinstance(each, dict):
                out.append(
                    f"    {kind}: {each['jobs']} jobs, waited for a runner {each['queue_hours']} h"
                    f" (median {each['queue_median_s']} s, 90th {each['queue_p90_s']} s), "
                    f"{each['cancelled_waiting']} cancelled while waiting"
                )
    paged = said["pages"]
    kinds = ", ".join(f"{kind} {n}" for kind, n in paged["by_kind"].items()) or "none"
    out += ["", f"paged the owner: {paged['total']} ({kinds})"]
    return "\n".join(out)


def _flow(args: argparse.Namespace, config: jbus.Config) -> int:
    """Print the measure of the window. It writes nothing."""
    if args.measure == "nudges":
        return _nudges(args, config)
    if args.measure == "asks":
        return _asks(args, config)
    until = _time(args.until, config) or datetime.now(UTC)
    since = _time(args.since, config) or until - timedelta(days=DEFAULT_DAYS)
    if since >= until:
        raise jbus.Refused(f"refused: --since {args.since} is not before --until {until}")
    try:
        projects, lines, found_runs, merges, repos, jobs, missing = gather(
            config, args, since, until
        )
    except records.Unaffordable as error:
        raise jbus.Refused(str(error)) from None
    if args.project:
        projects = [one for one in projects if one.name == config.project(args.project).name]
    said = build(projects, lines, found_runs, merges, repos, since, until, jobs, args.rows)
    said |= {"missing": missing}
    said = jbus.redact(said, config.secrets())
    print(json.dumps(said, indent=2, sort_keys=True) if args.json else text(said))
    return 0


FLOW_ONLY = ("--since", "--until", "--rows", "--journal", "--no-github", "--jobs", "--no-journal")
"""The flags of `jbus flow` that `jbus flow nudges` and `jbus flow asks` have no use for,
refused before them."""


def _window(args: argparse.Namespace, config: jbus.Config) -> tuple[datetime, datetime]:
    """Return the window a count of T3 Code's store gives, refusing a flag of `jbus flow`'s."""
    given = [flag for flag in FLOW_ONLY if getattr(args, flag.lstrip("-").replace("-", "_"))]
    if given:
        raise jbus.Refused(
            f"refused: {', '.join(given)} is jbus flow's, not jbus flow {args.measure}'"
        )
    since, until = _time(args.start, config), _time(args.end, config)
    if since >= until:
        raise jbus.Refused(f"refused: {args.start} is not before {args.end}")
    return since, until


def _nudges(args: argparse.Namespace, config: jbus.Config) -> int:
    """Print each nudge of the window and the count. It writes nothing."""
    since, until = _window(args, config)
    said = nudges.messages(nudges.read(args.store, args.title), since, until)
    found = nudges.nudges(said)
    if args.json:
        rows = [
            {"at": one.at.isoformat(), "home": one.home, "thread": one.thread, "first": one.first}
            for one in found
        ]
        out = json.dumps({"messages": len(said), "nudges": len(found), "list": rows}, indent=2)
    else:
        out = nudges.text(said, found)
    print(jbus.redact(out, config.secrets()))
    return 0


def _asks(args: argparse.Namespace, config: jbus.Config) -> int:
    """Print each ask of the window, and the count per job and per day. It writes nothing."""
    since, until = _window(args, config)
    said = asks.messages(nudges.read(args.store, args.title), since, until)
    found = asks.asks(said)
    counted = asks.count(found, lambda at: config.user.local(at).date())
    if args.json:
        rows = [
            {
                "at": one.message.at.isoformat(),
                "jobs": list(one.jobs),
                "home": one.message.home,
                "thread": one.message.thread,
                "first": one.first,
            }
            for one in found
        ]
        out = json.dumps({"messages": len(said), **counted, "list": rows}, indent=2)
    else:
        out = asks.text(found, said, counted)
    print(jbus.redact(out, config.secrets()))
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
    parser.add_argument(
        "--until", help="to this time, the user's zone with none, as --since (default: now)"
    )
    parser.add_argument("--json", action="store_true", help="print the measure as JSON")
    parser.add_argument(
        "--rows", action="store_true", help="every merged row, each span with its record"
    )
    parser.add_argument(
        "--journal", type=Path, help="read jbus's journal lines from this file, not journalctl"
    )
    parser.add_argument("--no-github", action="store_true", help="ask GitHub nothing")
    parser.add_argument(
        "--jobs", action="store_true", help="ask each run's jobs for queue time: a call per run"
    )
    parser.add_argument("--no-journal", action="store_true", help="read no journal")
    measures = parser.add_subparsers(dest="measure")
    count = measures.add_parser(
        "nudges",
        help="the owner's nudges in the home threads, from T3 Code's store",
        description=nudges.DEFINITION,
    )
    count.add_argument("start", metavar="since", help="from this time, the user's zone with none")
    count.add_argument("end", metavar="until", help="to this time, as since")
    count.add_argument(
        "--title",
        default=nudges.TITLE,
        help="threads whose title is like this, as SQL's like (default: 'home: %%', every home)",
    )
    count.add_argument(
        "--store", type=Path, default=nudges.STORE, help="T3 Code's store, opened read-only"
    )
    count.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print the count and list as JSON, as jbus flow --json does before nudges",
    )
    count = measures.add_parser(
        "asks",
        help="the owner's status asks per job and per day, from T3 Code's store",
        description=asks.DEFINITION,
    )
    count.add_argument("start", metavar="since", help="from this time, the user's zone with none")
    count.add_argument("end", metavar="until", help="to this time, as since")
    count.add_argument(
        "--title",
        default=asks.TITLE,
        help="threads whose title is like this, as SQL's like (default: '%%', every thread)",
    )
    count.add_argument(
        "--store", type=Path, default=nudges.STORE, help="T3 Code's store, opened read-only"
    )
    count.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print the counts and list as JSON, as jbus flow --json does before asks",
    )


VERBS = (
    verbs.Verb(
        "flow",
        "how work flowed in a window: lead times, waits, main red, no room; writes nothing",
        _arguments,
        _flow,
        abbrev=False,
    ),
)
