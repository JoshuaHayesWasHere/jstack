"""jgauge's `load.tsv`, a row of the machine's load each 15 s (`jgauge.sample`), read where
jgauge writes it, `jgauge.sample.log_path`: a log of text lines under a header, whose key is of
the line as text. The header and any line whose time is not a number are rows with no `at`."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo

from jbus.telemetry.records import Source
from jbus.telemetry.values import STAMP, Row, _columns
from jgauge import sample


def _float(field: str | None) -> float | None:
    try:
        return float(field) if field else None
    except ValueError:
        return None


def row(line: str, zone: tzinfo | None) -> Row:
    """A row of `load.tsv`, `<unix time> <cores> <load1> ...` by tabs: its time, its cores and its
    1-minute load, each None where the field is empty or not a number."""
    fields = dict(zip(sample.COLUMNS, line.split("\t"), strict=False))
    when, cores = _float(fields.get("time")), _float(fields.get("cores"))
    return {
        "at": datetime.fromtimestamp(when, UTC).strftime(STAMP) if when else None,
        "cores": int(cores) if cores else None,
        "load1": _float(fields.get("load1")),
    }


SOURCE = Source(
    "load_samples",
    "load.tsv",
    "log",
    _columns("at", "cores", "load1"),
    row,
    where="machine",
    text=True,
    located=sample.log_path,
)
