import os
import subprocess
import sys
import time

import pytest

REAL = subprocess.run


@pytest.fixture(autouse=True)
def _diag_run(request, monkeypatch):
    if request.module.__name__ != "test_jbus_view_page":
        return
    t = request.module
    name = request.node.name

    def run(command, **how):
        if not (isinstance(command, list) and command and command[0] == t.CHROMIUM):
            return REAL(command, **how)
        how["timeout"] = 40
        extra = os.environ.get("DIAG_FLAGS", "").split()
        if os.environ.get("DIAG_VERBOSE"):
            extra += ["--enable-logging=stderr", "--v=1"]
        command = [command[0], *extra, *command[1:]]
        start = time.monotonic()
        lock = f"lockdir={t.LOCK.parent.is_dir()} lock={t.LOCK.exists()}"
        try:
            ran = REAL(command, **how)
            took = time.monotonic() - start
            sys.__stderr__.write(f"\nDIAG {name} rc={ran.returncode} {took:.1f}s {lock}\n")
            return ran
        except subprocess.TimeoutExpired as e:
            tree = REAL(["ps", "-eo", "pid,ppid,stat,etime,args", "--forest"], capture_output=True, text=True).stdout
            err = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
            err = [line for line in err.splitlines() if "dbus" not in line]
            out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            import pathlib
            keep = pathlib.Path("/tmp/chrome-diag")
            keep.mkdir(exist_ok=True)
            (keep / f"{name}.err").write_text(err and "\n".join(err) or "")
            (keep / f"{name}.ps").write_text(tree)
            sys.__stderr__.write(f"\nDIAG TIMEOUT {name} {lock} stdout={len(out)}\n")
            sys.__stderr__.write("\n".join(err[-40:]) + "\n")
            sys.__stderr__.write("\n".join(l[:200] for l in tree.splitlines() if "chrom" in l or "pytest" in l) + "\n")
            raise

    monkeypatch.setattr(subprocess, "run", run)
