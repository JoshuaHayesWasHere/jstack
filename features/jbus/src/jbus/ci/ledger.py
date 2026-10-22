"""Keep what `jbus ci` records of a project's CI, in its state directory, as JSON lines.

`ci.jsonl` has one line per job, written once. `jbus ci` keeps a job once it has completed,
and never adds a job that is already there, so a second run over the same days adds nothing.
A line has `run`, `job` and `attempt`, and the job's `name`, `sha`, `branch`, `pr` (the pull
request it ran for, or None), `event`, `created`, `started`, `completed` and `conclusion`.
It also has the `runner` the job ran on, its `kind`, `hosted` or `local`, and `steps`, how
many steps ran. A job cancelled while it waited has a conclusion of `cancelled` and no
runner or start, and the ledger keeps and counts it. A red local job also has `tests`, the
failing tests its log names, and `signs`, the runner faults that log shows.

Each lever's telemetry is a field of the same line, `None` where the run did not give it:
`full` and `tree` (one suite per tree), `selection` (`all` or how many files) and `reason`
(the test map), `slowest_s` and `tail_s` (the slow tail), `cpu_pressure`, `cgroup_pressure`
and `workers` (the CPU), and `tmp_inode_pct`. A job writes these with `jbus ci --notice`; see
`jbus.ci.notice`.

`ci-prs.jsonl` has one line per pull request, and each run rewrites it: `number`, `branch`,
`head`, `created`, `merged`, `closed`, `merge_commit` and `pushes`, the times someone
force-pushed its branch.
"""

from __future__ import annotations

import fcntl
import json
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

JOBS, PULLS, LOCK = "ci.jsonl", "ci-prs.jsonl", "ci.lock"
TELEMETRY = (
    "full",
    "tree",
    "selection",
    "reason",
    "slowest_s",
    "tail_s",
    "cpu_pressure",
    "cgroup_pressure",
    "workers",
    "tmp_inode_pct",
)


@contextmanager
def locked(state: Path) -> Iterator[None]:
    """Hold the state directory's collection lock, so a second `jbus ci` waits for the first
    and then finds its jobs kept, instead of racing it to the same files."""
    state.mkdir(parents=True, exist_ok=True)
    with (state / LOCK).open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def read(path: Path) -> list[dict[str, Any]]:
    """Return every line of the file that is a JSON object, in order, or none where the file
    is not there."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        try:
            one = json.loads(line)
        except ValueError:
            continue
        if isinstance(one, dict):
            rows.append(one)
    return rows


def add(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """Append the rows whose job the file does not have yet, and return how many it added."""
    seen = {one.get("job") for one in read(path)}
    new = []
    for row in rows:
        if row["job"] not in seen:
            seen.add(row["job"])
            new.append(row)
    if new:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write("".join(json.dumps(one, sort_keys=True) + "\n" for one in new))
    return len(new)


def rewrite(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("".join(json.dumps(one, sort_keys=True) + "\n" for one in rows))
    temporary.replace(path)
