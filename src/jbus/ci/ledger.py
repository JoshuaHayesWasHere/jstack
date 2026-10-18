"""What `jbus ci` keeps of a project's CI, in its state directory, as JSON lines.

`ci.jsonl` is one line per job, once: a job is kept when it has completed, and a job already
there is not added again, so a second run over the same days adds nothing. A line is
`run`, `job` and `attempt`, the job's `name`, `sha`, `branch`, `pr` (the pull request it ran
for, or None), `event`, `created`, `started`, `completed`, `conclusion`, the `runner` it
ran on and its `kind`, `hosted` or `local`, and `steps`, how many steps ran. A job that was
cancelled while it waited has a conclusion of `cancelled` and no runner or start: it is kept
and counted. A red local job also carries `tests`, the failing tests its log names, and
`signs`, the runner faults that log shows.

Each lever's telemetry is a field of the same line, `None` where the run did not give it:
`full` and `tree` (one suite per tree), `selection` (`all` or how many files) and `reason`
(the test map), `slowest_s` and `tail_s` (the slow tail), `cpu_pressure`, `cgroup_pressure`
and `workers` (the CPU), and `tmp_inode_pct`. A job writes these with `jbus ci --notice`; see
`jbus.ci.notice`.

`ci-prs.jsonl` is one line per pull request, rewritten each run: `number`, `branch`, `head`,
`created`, `merged`, `closed`, `merge_commit` and `pushes`, the times its branch was
force-pushed.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

JOBS, PULLS = "ci.jsonl", "ci-prs.jsonl"
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


def read(path: Path) -> list[dict[str, Any]]:
    """Every line of the file that is a JSON object, in order; none where it is not there."""
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
    """Append the rows whose job the file does not have yet, and say how many were added."""
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
