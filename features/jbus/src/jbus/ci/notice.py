"""`jbus ci --notice`: how a CI job gives its telemetry to the collector.

A job cannot give the collector a file, and the API cannot read the job's summary. So the
job prints its telemetry as a workflow command on its own output: an annotation titled
`jstack-ci` whose message is a JSON object of the fields of `jbus.ci.ledger.TELEMETRY`. The
collector reads it back from the job's check run (`jbus.ci.collect.notice`). A lever that
adds a field writes it with this command, the one way, and the field must be in the ledger
before the lever can write it:

    jbus ci --notice full=true tree=$(git rev-parse HEAD^{tree}) workers=4
    jbus ci --notice cpu_pressure="$(head -n 1 /proc/pressure/cpu)"

A value `true` or `false` is a boolean, a whole number or a decimal is a number, and
anything else is text. The command refuses a name that is not a field of the ledger, so a
typo does not leave a silent gap in the series. Where the run has `GITHUB_STEP_SUMMARY`, the
command also writes the fields there as a table, for whoever reads the run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from jbus.ci import ledger
from jbus.ci.collect import TITLE


class Refused(Exception):
    """The command got a pair that is not `field=value`, or a field the ledger does not
    have."""


def value(text: str) -> bool | int | float | str:
    if text in ("true", "false"):
        return text == "true"
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            continue
    return text


def parse(pairs: list[str]) -> dict[str, bool | int | float | str]:
    given: dict[str, bool | int | float | str] = {}
    for pair in pairs:
        name, said, text = pair.partition("=")
        if not said:
            raise Refused(f"{pair!r} is not field=value")
        if name not in ledger.TELEMETRY:
            raise Refused(f"{name} is not a field of ci.jsonl: {', '.join(ledger.TELEMETRY)}")
        given[name] = value(text)
    return given


def command(given: dict[str, bool | int | float | str]) -> str:
    """Return the workflow command that annotates the job with the fields."""
    message = json.dumps(given, sort_keys=True, separators=(",", ":"))
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::notice title={TITLE}::{escaped}"


def write(pairs: list[str], summary: Path | None = None) -> str:
    """Return the command for the fields, and write their table in the job's summary where
    there is one."""
    given = parse(pairs)
    where = summary or (
        Path(os.environ["GITHUB_STEP_SUMMARY"]) if "GITHUB_STEP_SUMMARY" in os.environ else None
    )
    if where:
        table = "".join(f"| {k} | {v} |\n" for k, v in sorted(given.items()))
        with where.open("a") as handle:
            handle.write(f"### {TITLE}\n\n| field | value |\n| --- | --- |\n{table}\n")
    return command(given)
