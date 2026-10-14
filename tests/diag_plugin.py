import os
import subprocess
import sys
import tempfile
import time

import pytest


@pytest.fixture(autouse=True)
def _diag_browse(request, monkeypatch):
    if request.module.__name__ != "test_jbus_view_page":
        return
    t = request.module

    def browse(*arguments):
        command = [t.CHROMIUM, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom"]
        command += [*arguments]
        made = tempfile.TemporaryDirectory(prefix="jbus-view-", dir="/tmp")
        with made as short:
            env = {**os.environ, "TMPDIR": short}
            keys = {k: v for k, v in env.items() if k.startswith(("XDG", "HOME", "PATH"))}
            start = time.monotonic()
            try:
                ran = subprocess.run(command, env=env, capture_output=True, text=True, timeout=40)
                took = time.monotonic() - start
                sys.__stderr__.write(f"\nDIAG {request.node.name} rc={ran.returncode} {took:.1f}s\n")
                return ran
            except subprocess.TimeoutExpired as e:
                err = (e.stderr or b"").decode(errors="replace").splitlines()
                err = [line for line in err if "dbus" not in line]
                sys.__stderr__.write(f"\nDIAG TIMEOUT {request.node.name} env={keys}\n")
                sys.__stderr__.write("\n".join(err[-25:]) + "\n")
                sys.__stderr__.write(f"argv={command}\n")
                raise

    monkeypatch.setattr(t, "browse", browse)
