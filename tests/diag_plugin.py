import os
import pathlib
import subprocess
import sys
import time

import pytest

REAL = subprocess.run
KEEP = pathlib.Path("/tmp/chrome-diag")


def descendants(root):
    kids = {}
    for p in pathlib.Path("/proc").iterdir():
        if p.name.isdigit():
            try:
                ppid = int((p / "stat").read_text().rsplit(")", 1)[1].split()[1])
            except OSError:
                continue
            kids.setdefault(ppid, []).append(int(p.name))
    found, todo = [], [root]
    while todo:
        pid = todo.pop()
        found.append(pid)
        todo += kids.get(pid, [])
    return found


def snapshot(root):
    lines = []
    for pid in descendants(root):
        base = pathlib.Path(f"/proc/{pid}")
        try:
            cmd = (base / "cmdline").read_bytes().replace(b"\0", b" ").decode()[:160]
        except OSError:
            continue
        kind = [w for w in cmd.split() if w.startswith("--type=") or w.startswith("--utility-sub-type=")]
        lines.append(f"## pid {pid} {kind or cmd[:80]}")
        for task in sorted((base / "task").iterdir(), key=lambda p: int(p.name)):
            try:
                name = (task / "comm").read_text().strip()
                wchan = (task / "wchan").read_text().strip()
                state = (task / "stat").read_text().rsplit(")", 1)[1].split()[0]
            except OSError:
                continue
            lines.append(f"  tid {task.name} {name} {state} {wchan}")
        stacks = REAL(["sudo", "-n", "sh", "-c", f"for t in /proc/{pid}/task/*; do echo \"-- $t $(cat $t/comm)\"; cat $t/stack; done"], capture_output=True, text=True).stdout
        lines.append(stacks[:6000])
        try:
            fds = sorted(os.readlink(f) for f in (base / "fd").iterdir())
            lines.append("  fds: " + " | ".join(fds)[:1500])
        except OSError:
            pass
    return "\n".join(lines)


@pytest.fixture(autouse=True)
def _diag_run(request, monkeypatch):
    if request.module.__name__ != "test_jbus_view_page":
        return
    t = request.module
    name = request.node.name

    def run(command, **how):
        if not (isinstance(command, list) and t.CHROMIUM in command):
            return REAL(command, **how)
        at = command.index(t.CHROMIUM)
        command = command[: at + 1] + ["--enable-logging=stderr", "--v=1"] + command[at + 1 :]
        how.pop("timeout", None)
        how.pop("capture_output", None)
        start = time.monotonic()
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **how) as p:
            try:
                out, err = p.communicate(timeout=40)
            except subprocess.TimeoutExpired:
                KEEP.mkdir(exist_ok=True)
                (KEEP / f"{name}.proc").write_text(snapshot(p.pid))
                p.kill()
                out, err = p.communicate()
                (KEEP / f"{name}.err").write_text(err if isinstance(err, str) else err.decode())
                sys.__stderr__.write(f"\nDIAG HUNG {name}\n")
                return subprocess.CompletedProcess(command, t.STOPPED, out, err)
        sys.__stderr__.write(f"\nDIAG {name} {time.monotonic() - start:.1f}s\n")
        return subprocess.CompletedProcess(command, p.returncode, out, err)

    monkeypatch.setattr(subprocess, "run", run)
