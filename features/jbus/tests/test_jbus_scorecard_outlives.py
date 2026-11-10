"""The scorecard's build outlives the pass that starts it.

`jbus.service` is a oneshot unit, and systemd stops every process left in it when the pass ends,
a new session or not. A pass that systemd runs, which `INVOCATION_ID` tells, starts the build
with `systemd-run --user` as a transient unit of its own; a pass run by hand starts it in a
session of its own. A stub `systemd-run` on PATH logs what it was asked and starts the child, so
the page is written either way and the test reads it as its reader does.
"""

import json
import os
import re
import sys
from datetime import UTC, datetime

from jbus import telemetry
from test_jbus_scorecard_page import run, seed, waited
from test_jbus_telemetry import Machine

SYSTEMD_RUN = """\
#!{python}
import json, subprocess, sys
from pathlib import Path

stub = Path({stub!r})
with open(stub / "systemd-run.log", "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if (stub / "systemd-run-refuses").exists():
    print((stub / "systemd-run-refuses").read_text(), file=sys.stderr)
    sys.exit(1)
out = next(arg for arg in sys.argv if arg.startswith("--property=StandardOutput=truncate:"))
child = sys.argv[sys.argv.index("--") + 1 :]
with open(out.split("truncate:", 1)[1], "w") as log:
    subprocess.Popen(child, start_new_session=True, stdin=subprocess.DEVNULL, stdout=log)
"""


def stubbed(tmp_path, monkeypatch):
    machine = Machine(tmp_path, monkeypatch)
    stub = tmp_path / "bin"
    stub.mkdir()
    script = stub / "systemd-run"
    script.write_text(SYSTEMD_RUN.format(python=sys.executable, stub=str(stub)))
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ['PATH']}")
    now = datetime.now(UTC)
    seed(machine.state_dir / telemetry.FILE, now)
    return machine, stub, now


def asked(stub):
    log = stub / "systemd-run.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_a_pass_systemd_runs_starts_the_build_as_a_unit_of_its_own(tmp_path, monkeypatch):
    machine, stub, now = stubbed(tmp_path, monkeypatch)
    monkeypatch.setenv("INVOCATION_ID", "the-pass-unit")
    said = []
    run(now, said)
    page = machine.state_dir / telemetry.SCORECARD
    waited(page, lambda text: text.endswith("</html>\n"))
    (argv,) = asked(stub)
    assert argv[:3] == ["--user", "--quiet", "--collect"]
    (unit,) = [arg for arg in argv if arg.startswith("--unit=")]
    assert re.fullmatch(r"--unit=jbus-scorecard-[0-9a-f]{8}", unit)
    assert "--setenv=JBUS_STATE_DIR" in argv and "--setenv=INVOCATION_ID" not in argv
    assert argv[argv.index("--") + 1 :][-2:] == ["--out", str(page)]
    assert said == []


def test_a_refused_unit_is_one_line_on_the_pass(tmp_path, monkeypatch):
    _, stub, now = stubbed(tmp_path, monkeypatch)
    monkeypatch.setenv("INVOCATION_ID", "the-pass-unit")
    (stub / "systemd-run-refuses").write_text("Failed to start transient service unit: it exists")
    said = []
    run(now, said)
    assert said == ["scorecard: no page: Failed to start transient service unit: it exists"]


def test_a_pass_run_by_hand_starts_the_build_in_a_session_of_its_own(tmp_path, monkeypatch):
    machine, stub, now = stubbed(tmp_path, monkeypatch)
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    said = []
    run(now, said)
    waited(machine.state_dir / telemetry.SCORECARD, lambda text: text.endswith("</html>\n"))
    assert asked(stub) == []
    assert said == []
