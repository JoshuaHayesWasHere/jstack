"""The digest: what waits and what moved, over every project, as one dict and with no model.

`build` is the one builder. `jbus digest --json` prints what it gives, and a server can
give the same dict at an address. It reads what the passes left and asks nobody: no
`jmerge`, no GitHub, no T3 Code, and it takes no lock and writes no file. The dict is:

- `at`, when it was built, and `since`, the time the merges are counted from;
- `projects`, by name, each with:
  - `rows`: the rows of the queue that are not over (`queue.over`), each with the columns in
    `COLUMNS`, or None where `queue.json` does not parse. A row that merged or is done and
    leaves nothing is over, and one that merged with work left for after the merge is not;
  - `merged`: `{"slug", "pr", "at"}` for each row that turned `merged` at or after `since`,
    oldest first, from `transitions.jsonl`: `pr` is as a row has it, `#<n>`, or nothing;
  - `done`: the same for each row that turned `done`, which has no pull request;
  - `pulls`: `{"number", "slug", "url", "waits"}` for each of those rows that has a pull
    request and is not merged: `waits` is the last line `jmerge` logged for it, as
    `<wait or hold>: <why>`, from `merge.log.last`, and nothing where it logged none;
  - `by_rule`: `{"slug", "rule", "follows", "at"}` for each row of the queue, an open one or
    not, that a home approved by a standing rule at or after `since`, oldest first. The user
    did not speak of such a row: its length is the count he is told, `follows` the row he
    did approve, and `at` when the approval was run, as the row has it, to the minute: a
    `since` is taken back to its minute, so a row is listed twice at worst and never missed;
  - `waiting`: the list of what waits on the user, as the last pass left it (`waiting`);
  - `sweep`: what the last look at a sweep found;
- `status`: what `jbus status` prints;
- `token_expires`: when the sign-in to T3 Code runs out, by the stored token, or, for a
  builder that has no token file to read, as the last pass wrote it in the status file.

A pull request is named two ways, as the records it comes from name it: a row's `pr` and a
merge's are the string `#<n>`, and a `number`, of `pulls` or of a hold, is the integer. A
gate's `number` is a string: the number of a question jbus holds, or whatever the heading of
a gate in `gates.md` says.

No webhook URL, key or token is in it: `redact` takes each out of every string.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import jsettings
from jbus import (
    Config,
    Project,
    Refused,
    alert,
    merge,
    project,
    queue,
    read_json,
    record,
    redact,
    t3,
    verbs,
    waiting,
)
from jbus.wake import Box

DAY = timedelta(days=1)
COLUMNS = (
    "slug",
    "priority",
    "depends",
    "approved",
    "status",
    "thread",
    "pr",
    "checks",
    "updated",
    "why",
    "since",
)


def since(given: str | None, user: jsettings.Settings) -> datetime | None:
    """A `since` as it is typed or put in an address: a time as ISO 8601 writes it, a day
    alone included, or None for none. One with no zone is a time of the user's zone, and one
    that is not a time is a `ValueError`."""
    return user.local(datetime.fromisoformat(given)) if given else None


def status(config: Config) -> dict[str, Any]:
    """What `jbus status` prints: the status file, the streaks and the homes not on the bus
    as they are now, and the record of the pass."""
    return read_json(config.status_path, {}) | {
        "streaks": alert.streaks(config.state_dir),
        "homes_off_bus": project.missing(config),
        "pass": record.read(config),
    }


def _turned(
    config: Config, project: Project, start: datetime, word: str, pulls: dict[str, str]
) -> list:
    """Each change of a row to `word` at or after `since`. A line that is not one is left out."""
    try:
        lines = queue.transitions_path(config.state(project)).read_text().splitlines()
    except OSError:
        return []
    found = []
    for line in lines:
        try:
            move = json.loads(line)
            late = config.user.local(datetime.fromisoformat(move["at"])) >= start
            slug, to = move["slug"], move["to"]
        except (ValueError, KeyError, TypeError):
            continue
        if to == word and late:
            found.append({"slug": slug, "pr": pulls.get(slug, ""), "at": move["at"]})
    return found


def _pulls(config: Config, project: Project, rows: list[queue.Row]) -> list[dict[str, Any]]:
    """What each row's pull request waits on, by the last line `jmerge` logged for it."""
    last = read_json(config.home(project) / "merge.log.last", {})
    last = last if isinstance(last, dict) else {}
    found = []
    for row in rows:
        number = str(row.get("pr") or "").removeprefix("#")
        if not number.isdigit():
            continue
        logged = merge.parse(str(last.get(number, "")))
        logged = logged if logged and logged.reason else None
        found.append(
            {
                "number": int(number),
                "slug": row["slug"],
                "url": logged.name if logged else "",
                "waits": f"{logged.word}: {logged.reason}" if logged else "",
            }
        )
    return found


def _by_rule(config: Config, table: list[queue.Row], start: datetime) -> list[dict[str, str]]:
    """Each row approved by a standing rule at or after `start`. One whose record holds no
    time jbus stamped is left out.

    A record's time is to the minute, so `start` is taken back to its minute: a row approved
    in the minute a digest was built is in the next one too, and in none is it missed."""
    start = start.replace(second=0, microsecond=0)
    found = []
    for row in table:
        made = queue.record(row)
        if not made or made.basis != queue.RULE:
            continue
        try:
            ran = config.user.local(datetime.fromisoformat(made.ran_at[:16]))
        except ValueError:
            continue
        if ran >= start:
            one = {"slug": row["slug"], "rule": made.ref, "follows": made.follows}
            found.append((ran, one | {"at": made.ran_at}))
    return [one for _, one in sorted(found, key=lambda pair: (pair[0], pair[1]["slug"]))]


def _project(config: Config, project: Project, start: datetime) -> dict[str, Any]:
    state = config.state(project)
    try:
        table: list[queue.Row] | None = sorted(queue.load(state), key=queue.order)
    except queue.Unparsable:
        table = None
    rows = [row for row in table or [] if not queue.over(row)]
    pulls = {row["slug"]: str(row.get("pr") or "") for row in table or []}
    return {
        "rows": None
        if table is None
        else [{column: row.get(column, "") for column in COLUMNS} for row in rows],
        "merged": _turned(config, project, start, "merged", pulls),
        "done": [
            {"slug": one["slug"], "at": one["at"]}
            for one in _turned(config, project, start, "done", pulls)
        ],
        "pulls": _pulls(config, project, [row for row in rows if row.get("status") != "merged"]),
        "by_rule": _by_rule(config, table or [], start),
        "waiting": waiting.read(state) or [],
        "sweep": Box(state, project).marks().get("sweep", ""),
    }


def build(
    config: Config, since: datetime | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """The digest. `since` is the time the merges are counted from: a day before with none."""
    now = config.user.local(now or datetime.now(UTC))
    since = config.user.local(since or now - DAY)
    expires = t3.expiry(config.token_path)
    told = status(config)
    said = {
        "at": now.astimezone(UTC).isoformat(timespec="seconds"),
        "since": since.astimezone(UTC).isoformat(timespec="seconds"),
        "projects": {project.name: _project(config, project, since) for project in config.projects},
        "status": told,
        "token_expires": config.user.stamp(expires) if expires else told.get("token_expires"),
    }
    return redact(said, config.secrets())


def _status(_: argparse.Namespace, config: Config) -> int:
    """Print the status file, with the streaks and the homes not on the bus as they are now
    and the record of the pass.

    The file's own streaks are a copy from the last pass that ended, and `jbus alarm` counts
    after it. The record is there from the start of a pass, so a first pass that never ended
    is printed too.
    """
    if not config.status_path.is_file() and not config.pass_path.is_file():
        raise Refused(f"refused: no status at {config.status_path}: no pass has run")
    print(json.dumps(status(config), indent=2, sort_keys=True))
    return 0


def _start(given: str | None, config: Config) -> datetime | None:
    """`--since`, as `since` reads it. One that is not a time is refused."""
    try:
        return since(given, config.user)
    except ValueError:
        why = f"refused: --since {given} is not a time, as 2026-10-12T15:00 is"
        raise Refused(why) from None


def _digest(args: argparse.Namespace, config: Config) -> int:
    """Print the digest of every project, as JSON. It writes nothing, and asks nobody."""
    if not args.json:
        raise Refused("refused: jbus digest prints JSON and nothing else: jbus digest --json")
    print(json.dumps(build(config, _start(args.since, config)), indent=2, sort_keys=True))
    return 0


def _events(args: argparse.Namespace, config: Config) -> int:
    """Print the project's event log, one JSON object a line, oldest first. It writes nothing.

    `--since` is a time as ISO 8601 writes it, a day alone included: one with no zone is in the
    user's zone.
    """
    start = _start(args.since, config)
    project = verbs.project(config, args.project)
    for one in Box(config.state(project), project).log():
        if args.slug is not None and one["slug"] != args.slug:
            continue
        if start is not None and datetime.fromisoformat(one["at"]) < start:
            continue
        print(json.dumps(one, sort_keys=True))
    return 0


def _log(log: argparse.ArgumentParser) -> None:
    log.add_argument("--slug", help="only the events of this slug")
    log.add_argument(
        "--since", help="only the events sent at or after this time, the user's zone with none"
    )


def _whole(whole: argparse.ArgumentParser) -> None:
    whole.add_argument("--json", action="store_true", help="as JSON, the one form there is")
    whole.add_argument("--since", help="count the merges from this time, the user's zone with none")


VERBS = (
    verbs.Verb(
        "status", "what the last pass left: the status file and pass.json", verbs.nothing, _status
    ),
    verbs.Verb("events", "every event jbus sent, JSON lines", _log, _events, abbrev=False),
    verbs.Verb(
        "digest",
        "what waits and what moved, over every project",
        _whole,
        _digest,
        abbrev=False,
    ),
)
