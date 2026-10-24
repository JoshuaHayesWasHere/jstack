import json
import os
import sys
import time
from pathlib import Path

import pytest

from jbus import passes
from jgauge import cli, sample
from testing.paths import REPO

DAY = 86400
HEADER = (
    "time\tcores\tload1\tload5\tload15"
    "\tcpu_some_avg10\tcpu_some_avg60\tcpu_full_avg10\tcpu_full_avg60"
    "\tmemory_some_avg10\tmemory_some_avg60\tmemory_full_avg10\tmemory_full_avg60"
    "\tio_some_avg10\tio_some_avg60\tio_full_avg10\tio_full_avg60"
)
HEADER_WITH_TMP = HEADER + "\ttmp_files\ttmp_used"


def pressure(some, full):
    return (
        f"some avg10={some[0]} avg60={some[1]} avg300=0.00 total=1\n"
        f"full avg10={full[0]} avg60={full[1]} avg300=0.00 total=2\n"
    )


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A /proc made of files, and a log that the test points the sampler at, both under tmp_path."""
    proc = tmp_path / "proc"
    (proc / "pressure").mkdir(parents=True)
    (proc / "loadavg").write_text("11.54 8.96 7.51 11/2475 114345\n")
    (proc / "pressure" / "cpu").write_text(pressure(("5.00", "5.72"), ("0.00", "0.10")))
    (proc / "pressure" / "memory").write_text(pressure(("0.01", "0.02"), ("0.03", "0.04")))
    (proc / "pressure" / "io").write_text(pressure(("1.50", "2.25"), ("0.75", "1.25")))
    log = tmp_path / "state" / "jgauge" / "load.tsv"
    monkeypatch.setenv("PROC", str(proc))
    monkeypatch.setenv("JGAUGE_LOAD_LOG", str(log))
    monkeypatch.setenv("JBUS_STATE_DIR", str(tmp_path / "jbus"))
    monkeypatch.setenv("TMPFS", str(tmp_path))
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
    assert lines[0] == HEADER_WITH_TMP
    assert len(lines) == 3
    row = lines[1].split("\t")
    assert before <= int(row[0]) <= int(time.time())
    files = os.statvfs(machine[0].parent)
    if files.f_files:
        assert int(row[17]) == files.f_files and 0 < int(row[18]) <= files.f_files
    else:
        assert row[17:] == ["", ""]
    assert row[1:17] == [
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
    assert row[13:17] == ["", "", "", ""]


def test_a_machine_with_no_pressure_and_no_loadavg_still_writes_a_row(machine):
    proc, log = machine
    for name in ("cpu", "memory", "io"):
        (proc / "pressure" / name).unlink()
    (proc / "pressure").rmdir()
    (proc / "loadavg").unlink()
    assert cli.main(["sample"]) == 0
    (row,) = rows(log)
    assert len(row) == 19 and row[2:17] == [""] * 15


DARWIN = Path(__file__).parent / "fixtures" / "darwin"


@pytest.fixture
def mac(machine, monkeypatch, tmp_path):
    """The machine above as a Mac: `sys.platform` is darwin and `sysctl` prints the output in
    fixtures/darwin. The /proc of the machine fixture is still there, so a value read from it
    would show."""
    shown = tmp_path / "darwin"
    shown.mkdir()
    (shown / "sysctl.txt").write_text((DARWIN / "sysctl.txt").read_text())
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("DARWIN", str(shown))
    monkeypatch.setenv("PATH", f"{DARWIN / 'bin'}:{os.environ['PATH']}")
    return shown, machine[1]


def test_a_sample_on_a_mac_has_its_load_and_cores_and_no_pressure(mac):
    """macOS has no pressure (PSI) lines: their fields are empty, as on a kernel without them."""
    _, log = mac
    assert cli.main(["sample"]) == 0
    (row,) = rows(log)
    assert row[1:5] == ["12", "1.62", "1.88", "2.03"]
    assert row[5:17] == [""] * 12


def test_a_sample_on_a_mac_whose_sysctl_says_nothing_still_writes_a_row(mac):
    shown, log = mac
    (shown / "sysctl.txt").write_text("")
    assert cli.main(["sample"]) == 0
    (row,) = rows(log)
    assert len(row) == 19 and row[1:17] == [""] * 16


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
    """Six rows on 24 cores, where room's line is a 1-minute load of 48 (200% of 24). One row is
    over the line with CPU pressure low, and one is at the line with CPU pressure under 10: the
    report counts both. One is over the line with CPU pressure high, and one is just under the
    line. One has no CPU pressure reading, and the last has a low load."""
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
    assert capsys.readouterr().out.splitlines()[:4] == [
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


def test_each_of_rooms_lines_is_read_from_room_sh(machine):
    room = (REPO / "features" / "jgauge" / "src" / "jgauge" / "room.sh").read_text()
    for name in sample.ROOM_LINES:
        line = sample.room_line(name)
        assert f"  {name}={line}\n" in room or f"  {name}=${{HEADROOM:-{line}}}\n" in room


def test_a_log_from_before_the_tmp_columns_gets_them_once_and_keeps_its_rows(machine):
    _, log = machine
    log.parent.mkdir(parents=True)
    old = f"{int(time.time()) - 60}\t24" + "\t1" * 15
    log.write_text(HEADER + "\n" + old + "\n")
    assert cli.main(["sample"]) == 0
    lines = log.read_text().splitlines()
    assert lines[:2] == [HEADER_WITH_TMP, old + "\t\t"]
    assert len(lines) == 3 and len(lines[2].split("\t")) == 19


def test_the_report_gives_the_peaks_against_rooms_lines_and_the_jbus_stalls(machine, capsys):
    proc, log = machine
    at = 1_760_918_400
    log.parent.mkdir(parents=True)
    rows = [
        (at, "30.00", "12.00", "0.50", "1048576", "300000"),
        (at + 15, "50.40", "44.00", "11.00", "1048576", "900000"),
        (at + 30, "20.00", "3.00", "0.00", "", ""),
        (at + 45, "99.00", "99.00", "99.00", "1048576", "1000000"),
    ]
    body = "".join(
        f"{t}\t24\t{load}\t1\t1\t0\t{cpu}\t0\t0\t0\t{memory}\t0\t0" + "\t0" * 4 + f"\t{n}\t{u}\n"
        for t, load, cpu, memory, n, u in rows
    )
    log.write_text(HEADER_WITH_TMP + "\n" + body)
    events = proc.parent / "jbus" / "one" / "events.jsonl"
    events.parent.mkdir(parents=True)
    moment = "2025-10-20T00:00:20+00:00"
    events.write_text(
        "\n".join(
            [
                f'{{"at": "{moment}", "event": "stall", "line": "stall a: left"}}',
                f'{{"at": "{moment}", "event": "slot-wake", "line": "slot-wake: woke b, a full'
                ' slot is free for `make check`, after 7 min"}',
                f'{{"at": "{moment}", "event": "slot-wake", "line": "slot-wake: woke c, a short'
                ' slot is free for `pytest`, after 2 min"}',
                f'{{"at": "{moment}", "event": "slot-wake", "line": "slot-wake: woke d, a short'
                ' slot is free for `pytest`"}',
                json.dumps(
                    {
                        "at": moment,
                        "event": passes.CONDITION,
                        "line": f"{passes.CONDITION} e: no room for 10 passes: x",
                    }
                ),
                '{"at": "2025-10-20T00:01:20+00:00", "event": "stall", "line": "after the span"}',
                "not a record",
            ]
        )
    )
    assert cli.main(["sample", "--report", "--until", str(at + 45)]) == 0
    assert capsys.readouterr().out.splitlines()[4:] == [
        "CPU pressure (some avg60): at most 44; at or over room's line of 40: 1 of 3 rows (33.3%)",
        "memory pressure (some avg60): at most 11; at or over room's line of 10:"
        " 1 of 3 rows (33.3%)",
        "1-minute load: at most 50.4, 210% of 24 cores",
        "/tmp files: at most 900000 of 1048576 (85.8%); over room's line of 85%: 1 of 2 rows",
        "jbus events in 1 projects: 1 stalls, 3 threads woken from a wait for a test slot (of the"
        " 2 that say how long, 1 waited over 5 min, the longest 7 min), 1 rows gated for no room",
    ]


def test_a_span_with_no_rows_still_counts_the_jbus_stalls(machine, capsys):
    assert cli.main(["sample", "--report", "--since", "2025-10-20", "--until", "2025-10-21"]) == 0
    assert capsys.readouterr().out.splitlines()[1].startswith("jbus events: none read, ")
