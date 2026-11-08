"""`plan(check, event, selection) -> Plan`: what the shared check workflow's jobs run.

The workflow `.github/workflows/repo-standard-check.yml` asks this once, in its `plan` job, and
hands the answer to its other jobs as outputs. The answer holds whether the run tests anything,
the parts the tests run in, and what each part runs.

A run tests nothing only on a nightly schedule that the config's `check.nightly` leaves off. A
pull request's selection is what `make select` printed: the test ids its change reaches, one a
line, or the word `all`. Every other run, and a pull request whose selection the workflow did not
make, tests the whole suite, and a selection of no id runs `none` in each part. The ids are dealt
out to the parts in turn, in the order `make select` printed them, to no more parts than there
are ids. Where the selection is `all`, every part runs `all`, and the workflow runs
`make test SHARD=<part>/<parts>` in each.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from repo_standard.config import Check, Refused

ALL = "all"
NONE = "none"


@dataclass(frozen=True)
class Plan:
    run: bool
    selection: str
    parts: tuple[str, ...]

    def outputs(self) -> dict[str, str]:
        """The plan as the `key=value` outputs a step of GitHub Actions gives."""
        return {
            "run": "true" if self.run else "false",
            "selection": self.selection,
            "shards": json.dumps(list(range(1, len(self.parts) + 1))),
            "parts": json.dumps({str(at): part for at, part in enumerate(self.parts, 1)}),
        }


def selected(text: str) -> tuple[str, ...]:
    """The ids `make select` printed, or `(ALL,)` where it printed `all` on any line."""
    ids = tuple(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))
    spaced = [one for one in ids if len(one.split()) > 1]
    if spaced:
        raise Refused(f"make select printed an id with a space, unfit for TESTS: {spaced[0]}")
    return (ALL,) if ALL in ids else ids


def plan(check: Check, event: str, selection: tuple[str, ...] | None) -> Plan:
    """The run's plan for the config's `check` part, the event, and a pull request's selection."""
    run = event != "schedule" or check.nightly
    if selection is None or selection == (ALL,):
        return Plan(run, ALL, (ALL,) * check.shards)
    if not selection:
        return Plan(run, NONE, (NONE,) * check.shards)
    parts = min(check.shards, len(selection))
    return Plan(run, "some", tuple(" ".join(selection[at::parts]) for at in range(parts)))
