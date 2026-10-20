import os
import time
from pathlib import Path

import pytest

from jgauge import cli, sample

REPO = Path(__file__).parent.parent
DAY = 86400
HEADER = (
    "time\tcores\tload1\tload5\tload15"
    "\tcpu_some_avg10\tcpu_some_avg60\tcpu_full_avg10\tcpu_full_avg60"
    "\tmemory_some_avg10\tmemory_some_avg60\tmemory_full_avg10\tmemory_full_avg60"
    "\tio_some_avg10\tio_some_avg60\tio_full_avg10\tio_full_avg60"
)


def pressure(some, full):
    return (
        f"some avg10={some[0]} avg60={some[1]} avg300=0.00 total=1\n"
        f"full avg10={full[0]} avg60={full[1]} avg300=0.00 total=2\n"
    )


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A /proc made of files, and a log the sampler is pointed at, both under tmp_path."""
    proc = tmp_path / "proc"
    (proc / "pressure").mkdir(parents=True)
    (proc / "loadavg").write_text("11.54 8.96 7.51 11/2475 114345\n")
    (proc / "pressure" / "cpu").write_text(pressure(("5.00", "5.72"), ("0.00", "0.10")))
    (proc / "pressure" / "memory").write_text(pressure(("0.01", "0.02"), ("0.03", "0.04")))
    (proc / "pressure" / "io").write_text(pressure(("1.50", "2.25"), ("0.75", "1.25")))
    log = tmp_path / "state" / "jgauge" / "load.tsv"
    monkeypatch.setenv("PROC", str(proc))
    monkeypatch.setenv("JGAUGE_LOAD_LOG", str(log))
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield proc, log
    monkeypatch.undo()
    time.tzset()


def rows(log):
    return [line.split("\t") for line in log.read_text().splitlines()[1:]]


def test_a_sample_appends_one_row_under_a_header_of_the_columns(machine):
    proc, log = machine
    before = int(time.time())
    assert cli.main(["sample"]) == 0
    assert cli.main(["sample"]) == 0

    lines = log.read_text().splitlines()
    assert lines[0] == HEADER
    assert len(lines) == 3
    row = lines[1].split("\t")
    assert before <= int(row[0]) <= int(time.time())
    assert row[1:] == [
        str(len(os.sched_getaffinity(0))),
        *("11.54", "8.96", "7.51"),
        *("5.00", "5.72", "0.00", "0.10"),
        *("0.01", "0.02", "0.03", "0.04"),
        *("1.50", "2.25", "0.75", "1.25"),
    ]


def test_a_missing_pressure_file_writes_empty_fields_and_not_a_crash(machine):
    proc, log = machine
    (proc / "pressure" / "io").unlink()
    (proc / "pressure" / "cpu").write_text("some avg10=3.00 avg60=4.00 avg300=0.00 total=1\n")
    assert cli.main(["sample"]) == 0
    (row,) = rows(log)
    assert row[5:9] == ["3.00", "4.00", "", ""]
    assert row[9:13] == ["0.01", "0.02", "0.03", "0.04"]
    assert row[13:] == ["", "", "", ""]


def test_a_machine_with_no_pressure_and_no_loadavg_still_writes_a_row(machine):
    proc, log = machine
    for name in ("cpu", "memory", "io"):
        (proc / "pressure" / name).unlink()
    (proc / "pressure").rmdir()
    (proc / "loadavg").unlink()
    assert cli.main(["sample"]) == 0
    (row,) = rows(log)
    assert len(row) == 17 and row[2:] == [""] * 15


def test_rows_older_than_30_days_are_dropped_by_the_sampler(machine):
    _, log = machine
    now = int(time.time())
    log.parent.mkdir(parents=True)
    kept = [now - 2 * DAY, now - DAY]
    old = [now - 31 * DAY, now - 30 * DAY - 60]
    log.write_text(HEADER + "\n" + "".join(f"{at}\t24" + "\t" * 15 + "\n" for at in old + kept))
    assert cli.main(["sample"]) == 0
    times = [int(row[0]) for row in rows(log)]
    assert times[:2] == kept and len(times) == 3
    assert min(times) >= now - 30 * DAY


def test_a_log_with_other_columns_is_not_appended_to(machine, capsys):
    _, log = machine
    log.parent.mkdir(parents=True)
    log.write_text("time\tload\n1\t2\n")
    with pytest.raises(SystemExit, match="other columns"):
        cli.main(["sample"])
    assert log.read_text() == "time\tload\n1\t2\n"


def fixture(log, at):
    """Six rows on 24 cores, where room's line is a 1-minute load of 48 (200% of 24): over the
    line with CPU pressure low, at the line under 10 (both counted), over the line with CPU
    pressure high, just under the line, CPU pressure not read, and quiet."""
    log.parent.mkdir(parents=True, exist_ok=True)
    loads = [
        ("49.00", "5.00"),
        ("48.00", "9.99"),
        ("49.00", "12.00"),
        ("47.99", "1.00"),
        ("60.00", ""),
        ("3.00", "0.50"),
    ]
    body = "".join(
        f"{at + 15 * n}\t24\t{load}\t1\t1\t0\t{cpu}\t0\t0" + "\t0" * 8 + "\n"
        for n, (load, cpu) in enumerate(loads)
    )
    log.write_text(HEADER + "\n" + body)


def test_the_report_counts_rows_over_rooms_line_while_cpu_pressure_was_low(machine, capsys):
    _, log = machine
    fixture(log, 1_760_918_400)
    assert cli.main(["sample", "--report"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "rows: 6, from 2025-10-20 00:00:00 to 2025-10-20 00:01:15 (0:01:15);"
        " a row every 15 s would give 6",
        "read: 5 rows have the 1-minute load and CPU pressure (some avg60), and 1 of the 6 do not",
        "load at or over room's line, 200% of the cores: 3 of 5 rows (60.0%)",
        "and CPU pressure under 10: 2 of 5 rows (40.0%), 2 of the 3 over the line (66.7%)",
    ]


def test_the_report_takes_a_pressure_line_and_a_start(machine, capsys):
    _, log = machine
    fixture(log, 1_760_918_400)
    assert cli.main(["sample", "--report", "--pressure", "11", "--since", "1760918415"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("rows: 5, from 2025-10-20 00:00:15 ")
    assert out[3] == (
        "and CPU pressure under 11: 1 of 4 rows (25.0%), 1 of the 2 over the line (50.0%)"
    )
    assert cli.main(["sample", "--report", "--since", "2025-10-20 00:01"]) == 0
    assert capsys.readouterr().out.splitlines()[0].startswith("rows: 2, ")


def test_a_report_on_no_rows_says_so(machine, capsys):
    _, log = machine
    assert cli.main(["sample", "--report"]) == 0
    assert capsys.readouterr().out == f"rows: 0 in {log}\n"


def test_a_start_that_is_not_a_time_is_refused(machine, capsys):
    with pytest.raises(SystemExit):
        cli.main(["sample", "--report", "--since", "last week"])
    assert "is not a time" in capsys.readouterr().err


def test_the_load_line_is_the_one_room_reads(machine):
    room = (REPO / "src" / "jgauge" / "room.sh").read_text()
    assert "  LOAD=200\n" in room and sample.load_line() == 200
