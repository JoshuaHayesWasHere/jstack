"""`jbus flow`: how the work flowed in a window, measured from the records, and what held it.

It reads, and writes nothing:

- each project's `events.jsonl` under jbus's state, every folder there that has one: the
  queue's table over time gives each row's time from approved to merged, split into working
  and waiting, with the reason of each wait (`jbus.flow.rows`);
- jbus's journal, `journalctl --user -u jbus`: when the machine had no room or no account
  to launch on, and why, and when no pass ran (`jbus.flow.machine`);
- GitHub's Actions runs of each project's repo, through `gh api`: queue time, run time,
  cancels, reruns, and when main was red (`jbus.flow.runs`);
- the jobs `jbus ci` kept in a project's `ci.jsonl`, where there are any: how long each job
  waited for a runner, which a run's own times do not show.

It prints the window's numbers (`jbus.flow.report`): each merged row's lead time, the value
stream, the wait reasons ranked by the row-hours they cost, main red and what it held up, the
machine's lack of room, CI, and the share of time the records do not explain. `--json` prints
the same numbers as JSON. A project's repo is its checkout's origin in the config. Where no
config loads, or a project is not in it, GitHub is not asked, and the output says so.

Times given with no zone are the machine's own. The output holds no webhook URL or key: the
config's secrets are taken out of it.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import jbus
from jbus import verbs
from jbus.ci import ledger, repo_of
from jbus.flow import machine, report, rows, runs

DAYS = 7
LOG = "events.jsonl"


def moment(text: str) -> datetime:
    """Return a time typed as an ISO date or date and time, in the machine's zone if it has none."""
    try:
        given = datetime.fromisoformat(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not a date or time: {text}") from error
    return given if given.tzinfo else given.astimezone()


def arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--since", type=moment, help=f"start of the window (default {DAYS} days ago)"
    )
    parser.add_argument("--until", type=moment, help="end of the window (default now)")
    parser.add_argument("--json", action="store_true", help="print the numbers as JSON")
    parser.add_argument("--rows", action="store_true", help="list every merged row, not the top")
    parser.add_argument("--offline", action="store_true", help="ask GitHub nothing")
    parser.add_argument("--journal", type=Path, help="read journal lines from this file")


def loaded() -> jbus.Config | None:
    """Return the config, or None where none loads: the flow reads the state all the same."""
    try:
        return jbus.load()
    except Exception:
        return None


def state_dir(config: jbus.Config | None) -> Path:
    if config is not None:
        return config.state_dir
    return Path(os.environ.get("JBUS_STATE_DIR") or Path.home() / ".local" / "state" / "jbus")


def gather(
    config: jbus.Config | None,
    named: str | None,
    since: datetime,
    until: datetime,
    lines: list[str],
    ask: runs.Ask | None,
) -> report.Records:
    """Read every record of the window. With no `ask`, GitHub is not asked."""
    found = report.Records(since, until)
    state = state_dir(config)
    folders = sorted(
        (one for one in state.iterdir() if (one / LOG).is_file()) if state.is_dir() else [],
        key=lambda one: one.name.lower(),
    )
    if named is not None:
        folders = [one for one in folders if one.name == named]
    for folder in folders:
        events = list(rows.read(folder / LOG))
        found.tables[folder.name] = rows.walk(folder.name, events, until)
        found.first[folder.name] = min(filter(None, map(rows.at, events)), default=None)
        found.jobs[folder.name] = ledger.read(folder / ledger.JOBS)
        if ask is None:
            found.unasked[folder.name] = "--offline"
            continue
        project = next(
            (one for one in (config.projects if config else ()) if one.state == folder.name), None
        )
        if project is None:
            found.unasked[folder.name] = "no project of the config keeps its state here"
            continue
        try:
            repo = repo_of(project.checkout)
            branch = str(ask(f"repos/{repo}").get("default_branch") or "main")
            kept = runs.fetch(ask, repo, since, until)
        except (jbus.Refused, runs.Unavailable, AttributeError) as error:
            found.unasked[folder.name] = str(error)
            continue
        found.actions[folder.name] = runs.count(repo, kept, branch, until)
    found.journal = machine.machine(lines, since, until)
    return found


def run(args: argparse.Namespace, _: jbus.Config | None) -> int:
    config = loaded()
    until = args.until or datetime.now().astimezone()
    since = args.since or until - timedelta(days=DAYS)
    if since >= until:
        print("refused: --since is not before --until")
        return 2
    if args.journal is not None:
        try:
            lines = args.journal.read_text(errors="replace").splitlines()
        except OSError as error:
            print(f"refused: the journal file cannot be read: {error.strerror}")
            return 2
    else:
        lines = machine.journal(since, until)
    ask = None if args.offline else runs.gh
    numbers = report.measure(gather(config, args.project, since, until, lines, ask))
    said = json.dumps(numbers, indent=2) + "\n" if args.json else report.text(numbers, args.rows)
    if config is not None:
        said = jbus.redact(said, config.secrets())
    print(said, end="")
    return 0


VERBS = (
    verbs.Verb(
        "flow",
        "measure how the work flowed in a window, and what held it (reads only)",
        arguments,
        run,
        config=False,
    ),
)
