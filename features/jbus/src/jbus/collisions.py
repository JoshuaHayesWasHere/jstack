"""Send the home the week's collision report: the files that pull requests kept conflicting in.

Josh's traffic fix, step 9 (2026-11-03), from the conflict-hotspots scout's recommendation 3:
`features/jmerge/scripts/force_pushes.py --files` names the kind of each conflict hunk, so that the
next list two rows keep adding to shows up in a weekly report and no scout has to find it.

Once a week, on the first pass on or after Monday in the user's zone, `weekly` runs that script in
the project's checkout over the 7 days before the pass, with `--json`, and sends the catch-all's
home, `uncategorized`, one message (`report`): the `TOP` files with the most `insert` and
`renumber` hunks, each with its pull requests, and a line naming each file of them that was not in
last week's top. A week with no such file is one line. A project whose checkout has no script
sends nothing.

`collisions.json` in the project's state keeps each report under the date of its week's Monday,
with its window, its top files and its message, as `day-warnings.json` keeps its days. A week with
a report there is done, and the latest week before it is the base of "new to the top". A run of the
script that fails, or a message the outbox holds or T3 Code does not take, records nothing, so the
next pass tries again.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from jbus import outbox, read_json, verbs, write_json
from jbus.t3 import T3Error
from jbus.wakes import catchall_of

if TYPE_CHECKING:
    from jbus.poll import Half

SCRIPT = "features/jmerge/scripts/force_pushes.py"
LEDGER = "collisions.json"
TEMPLATE = "collisions"
WEEK = timedelta(days=7)
TOP = 10
RANKED = ("insert", "renumber")
KINDS = ("insert", "renumber", "edit", "whole-file")

EVENTS = {"collisions": "quiet"}


def week_of(local: datetime) -> str:
    """The date of the Monday of the week `local`, a moment in the user's zone, falls in."""
    return (local.date() - timedelta(days=local.weekday())).isoformat()


def ranked(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The `TOP` files with the most `insert` and `renumber` hunks, most first, then the most pull
    requests, then by path. A file with neither kind is not ranked."""

    def score(one: dict[str, Any]) -> int:
        return sum(one["hunks"].get(kind, 0) for kind in RANKED)

    listed = [one for one in files if score(one)]
    return sorted(listed, key=lambda one: (-score(one), -len(one["pulls"]), one["path"]))[:TOP]


def report(
    project: str, week: str, since: datetime, until: datetime, said: dict, last: list[str] | None
) -> str:
    """The week's message. `said` is what the script printed, and `last` the paths of the last
    report's top files, or None where there is no report before this one."""
    files = said.get("files", [])
    top = ranked(files)
    span = f"{since:%Y-%m-%d} to {until:%Y-%m-%d}"
    head = f"collisions {project}, week of {week} ({span})"
    if not files:
        return f"{head}: no pull request conflicted with main."
    if not top:
        noun = "file" if len(files) == 1 else "files"
        return f"{head}: {len(files)} {noun} conflicted, none by an insert or renumber hunk."
    lines = [
        f"{head}: the top {len(top)} of {len(files)} files that conflicted, by insert and "
        "renumber hunks (`force_pushes.py --files`)."
    ]
    for at, one in enumerate(top, 1):
        hunks = ", ".join(
            f"{kind} {one['hunks'][kind]}" for kind in KINDS if one["hunks"].get(kind)
        )
        pulls = ", ".join(f"#{number}" for number in one["pulls"])
        lines.append(f"{at}. `{one['path']}`: {hunks}; {pulls}")
    if last is None:
        lines.append(f"New to the top {TOP}: no report before this one to compare with.")
    else:
        new = [f"`{one['path']}`" for one in top if one["path"] not in last]
        lines.append(f"New to the top {TOP}: {', '.join(new) or 'none'}.")
    return "\n".join(lines)


def weekly(half: Half) -> None:
    """Run the week's report where it is due, send it to the catch-all's home, and keep it."""
    run, client = half.run, half.client
    script = run.project.checkout / SCRIPT
    week = week_of(run.user.local(run.now))
    ledger: dict[str, Any] = read_json(run.state / LEDGER, {})
    if client is None or week in ledger or not script.is_file():
        return
    thread = catchall_of(run)
    if not thread:
        run.say(f"wait {run.project.name}: the week's collision report has no home to go to")
        return
    since, until = run.now - WEEK, run.now
    ran = run.run(
        sys.executable,
        str(script),
        str(run.state),
        "--since",
        f"{since:%Y-%m-%dT%H:%M:%SZ}",
        "--until",
        f"{until:%Y-%m-%dT%H:%M:%SZ}",
        "--files",
        "--json",
    )
    try:
        said = json.loads(ran.stdout) if not ran.returncode else None
    except ValueError:
        said = None
    if not isinstance(said, dict):
        tail = (ran.stderr or ran.stdout).strip().splitlines()[-1:] or ["it printed nothing"]
        run.say(f"wait {run.project.name}: {SCRIPT} did not run ({tail[0]}), retrying next pass")
        return
    before = [day for day in sorted(ledger) if day < week]
    last = ledger[before[-1]]["top"] if before else None
    text = report(run.project.name, week, since, until, said, last)
    key = f"{TEMPLATE}|{week}"
    try:
        went = outbox.send(
            run,
            client,
            thread=thread,
            row=TEMPLATE,
            key=key,
            text=text,
            template=TEMPLATE,
            needs="decide",
        )
    except T3Error as error:
        run.say(f"wait {run.project.name}: the week's collision report did not go ({error})")
        return
    if not went:
        return
    top = [one["path"] for one in ranked(said.get("files", []))]
    ledger[week] = {
        "since": f"{since:%Y-%m-%dT%H:%M:%SZ}",
        "until": f"{until:%Y-%m-%dT%H:%M:%SZ}",
        "top": top,
        "message": text,
    }
    write_json(run.state / LEDGER, ledger)
    line = text.splitlines()[0]
    run.box.send("", TEMPLATE, line, text)
    run.say(f"told {run.project.name}: {line}")


STEPS = (verbs.Step("close", 57, "collisions.weekly", weekly, ("client", "budget")),)
