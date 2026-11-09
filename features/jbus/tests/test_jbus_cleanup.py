"""What finished crews leave in /tmp never holds back a launch, and a launch /tmp does hold back
says so from its first pass.

A settled crew's whole Claude scratch folder goes with its worktrees (`jbus.cleanup.clear_scratch`).
A pass that `jgauge room` holds back for /tmp (`jbus.dispatch.Turns.take`) first removes the
Claude scratch folders of crews whose worktrees are gone and the copies of the base `proved.sh`
left behind (`jbus.cleanup.sweep`), then asks room again. Like `test_jbus_kitchen.py`, the tests
run the real pass and the real `jgauge room` against the fakes, here with a /tmp whose quota
counts what the folders hold.
"""

import json
import os
import re
import subprocess
import sys
import time

import pytest

from jbus import cleanup, verbs
from test_jbus_kitchen import RESULT, approved
from test_jbus_needs import AFTER

QUOTA_KIB = 1024 * 1024
"""The fake /tmp's quota, 1 GiB, as quotactl gives it."""
SCALE = 10_000
"""How many bytes of the quota each byte written counts for, so a test writes kilobytes."""


def mangled(path):
    return re.sub("[^A-Za-z0-9]", "-", str(path))


@pytest.fixture
def tmp(kitchen, monkeypatch):
    """A /tmp whose quota `jgauge room` reads as the bytes its files hold, times `SCALE`, with
    Claude Code's scratch folders in it and T3 Code's worktrees beside it. Return the /tmp."""
    kitchen.machine()
    where = kitchen.root / "machine" / "stub" / "tmp"
    stub = kitchen.root / "quota-stub"
    stub.mkdir()
    (stub / "python3").write_text(
        "#!/bin/sh\nfor arg; do last=$arg; done\n"
        'find "$last" -type f -exec cat {} + | wc -c'
        f" | awk '{{print {QUOTA_KIB}, $1 * {SCALE}}}'\n"
    )
    (stub / "python3").chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}:{os.environ['PATH']}")
    monkeypatch.setenv("QUOTA", str(where))
    monkeypatch.setenv("CLAUDE_CODE_TMPDIR", str(where))
    monkeypatch.setattr(cleanup, "WORKTREES", kitchen.root / "worktrees", raising=False)
    return where


def pad(tmp, kitchen, slug, size):
    """Fill the Claude scratch folder of the slug's T3 Code worktree with `size` bytes, as a
    session's scratchpad and task output, and return the folder."""
    tree = kitchen.root / "worktrees" / kitchen.checkout.name / slug
    folder = tmp / f"claude-{os.getuid()}" / mangled(tree)
    (folder / "session" / "scratchpad").mkdir(parents=True)
    (folder / "session" / "scratchpad" / "blob").write_bytes(b"x" * size)
    return folder


def base(tmp, name, size):
    """Leave a copy of the base, as a killed `proved.sh` leaves one, holding `size` bytes."""
    copy = tmp / name
    (copy / "src").mkdir(parents=True)
    (copy / "src" / "blob").write_bytes(b"x" * size)
    return copy


def test_a_settled_crew_leaves_no_claude_scratch_folder_but_a_crew_still_out_keeps_its_own(
    kitchen, tmp
):
    for slug in ("alpha", "beta"):
        tree = kitchen.root / "worktrees" / kitchen.checkout.name / slug
        kitchen.t3.thread(slug, "completed", worktreePath=str(tree))
    mine, theirs = pad(tmp, kitchen, "alpha", 10), pad(tmp, kitchen, "beta", 10)
    kitchen.git("worktree", "add", "-q", "--detach", str(mine / "session" / "scratchpad" / "base"))
    kitchen.brief("alpha", RESULT)
    kitchen.brief("beta", RESULT.replace("Status: done", "Status: paused"))
    kitchen.poll()
    assert not mine.exists()
    assert (theirs / "session" / "scratchpad" / "blob").exists()


def test_a_pass_over_a_tmp_full_of_finished_crews_scratch_frees_it_and_launches(kitchen, tmp):
    gone = [pad(tmp, kitchen, f"done-{n}", 30_000) for n in range(2)]
    gone.append(base(tmp, "base.Ab12Cd", 20_000))
    gone.append(base(tmp / f"claude-{os.getuid()}", "base.Ef34Gh", 5_000))
    (kitchen.root / "worktrees" / kitchen.checkout.name / "live").mkdir(parents=True)
    live = pad(tmp, kitchen, "live", 3_000)
    held = base(tmp, "base.Ij56Kl", 2_000)
    approved(kitchen, "alpha")
    with subprocess.Popen(["sleep", "60"], cwd=held / "src") as proving:
        try:
            said = kitchen.poll()
        finally:
            proving.kill()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha"], said
    assert [folder for folder in gone if folder.exists()] == []
    assert (live / "session" / "scratchpad" / "blob").exists()
    assert (held / "src" / "blob").exists()
    assert not any("no room" in line for line in said)


def test_a_row_that_still_waits_for_tmp_says_so_on_its_first_pass_and_on_jbus_needs(
    kitchen, tmp, monkeypatch
):
    (kitchen.root / "worktrees" / kitchen.checkout.name / "live").mkdir(parents=True)
    live = pad(tmp, kitchen, "live", 90_000)
    approved(kitchen, "alpha")
    kitchen.poll()
    assert kitchen.t3.launches == []
    assert live.exists()
    cause = f"waiting: {tmp} at 80% of its quota"
    rows = {row["slug"]: row for row in json.loads((kitchen.state / "queue.json").read_text())}
    assert rows["alpha"]["why"] == cause
    monkeypatch.setattr(verbs, "clock", lambda: AFTER)
    code, out = kitchen.main("needs")
    assert code == 0, out
    assert f"demo row alpha: {cause}" in out.splitlines()


@pytest.mark.parametrize("procfs", [True, False], ids=["proc", "no-proc"])
def test_a_base_copy_stays_while_a_proof_runs_in_its_folder(kitchen, tmp, monkeypatch, procfs):
    """A `proved.sh` between its head and base sides holds its copy with no process inside it, so
    every copy of the base in the folder it makes them in stays while it runs; with no /proc, as
    on macOS, `ps` says that one runs. The finished crew's folder still goes."""
    if not procfs:
        monkeypatch.setattr(cleanup, "ROOT", kitchen.root / "no-proc")
    gone = pad(tmp, kitchen, "done-1", 60_000)
    copy = base(tmp, "base.Mn78Op", 30_000)
    script = kitchen.root / "proof" / "proved.sh"
    script.parent.mkdir()
    script.write_text("sleep 60\n")
    env = {**os.environ, "TMPDIR": str(tmp)}
    approved(kitchen, "alpha")
    with subprocess.Popen(["bash", str(script)], env=env, cwd=kitchen.root) as proving:
        try:
            kitchen.poll()
        finally:
            proving.kill()
    assert (copy / "src" / "blob").exists()
    assert not gone.exists()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha"]


@pytest.mark.parametrize("procfs", [True, False], ids=["proc", "no-proc"])
def test_a_pass_that_knows_no_process_removes_nothing_and_waits(kitchen, tmp, monkeypatch, procfs):
    """Where no process can be read, from /proc or from `lsof` where there is none, no folder is
    known to be idle, so the sweep removes nothing and the row waits for /tmp."""
    empty = kitchen.root / "empty-proc"
    if procfs:
        empty.mkdir()
    else:
        stub = kitchen.root / "lsof-stub"
        stub.mkdir()
        (stub / "lsof").write_text("#!/bin/sh\nexit 0\n")
        (stub / "lsof").chmod(0o755)
        monkeypatch.setenv("PATH", f"{stub}:{os.environ['PATH']}")
    monkeypatch.setattr(cleanup, "ROOT", empty)
    gone = pad(tmp, kitchen, "done-1", 90_000)
    approved(kitchen, "alpha")
    kitchen.poll()
    assert gone.exists()
    assert kitchen.t3.launches == []


def session(tmp, kitchen, name, size, idle):
    """Leave a session folder in the Claude scratch folder of the main checkout, holding `size`
    bytes, whose entries were last written `idle` seconds ago, and return it."""
    folder = tmp / f"claude-{os.getuid()}" / mangled(kitchen.checkout) / name
    (folder / "scratchpad").mkdir(parents=True)
    (folder / "scratchpad" / "blob").write_bytes(b"x" * size)
    then = time.time() - idle
    for one in (folder / "scratchpad" / "blob", folder / "scratchpad", folder):
        os.utime(one, (then, then))
    return folder


def test_a_pass_waiting_on_tmp_clears_the_main_checkout_session_folders_that_ended(kitchen, tmp):
    """A home's, a scout's or the user's own session in the main checkout leaves its scratch folder
    when it ends. The sweep removes one nothing wrote in for `IDLE` and no process holds, beside a
    finished crew's, and keeps a live one and one written in lately."""
    old = cleanup.IDLE + 3_600
    ended = session(tmp, kitchen, "ended", 60_000, old)
    fresh = session(tmp, kitchen, "fresh", 5_000, 60)
    alive = session(tmp, kitchen, "alive", 5_000, old)
    finished = pad(tmp, kitchen, "done-1", 30_000)
    approved(kitchen, "alpha")
    with subprocess.Popen(["sleep", "60"], cwd=alive / "scratchpad") as working:
        try:
            said = kitchen.poll()
        finally:
            working.kill()
    assert not ended.exists()
    assert not finished.exists()
    assert (fresh / "scratchpad" / "blob").exists()
    assert (alive / "scratchpad" / "blob").exists()
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha"], said
    assert any(
        "1 folders finished crews left, 1 of sessions ended in a main checkout" in line
        for line in said
    ), said


@pytest.mark.parametrize("procfs", [True, False], ids=["proc", "no-proc"])
@pytest.mark.parametrize(
    "names", [["--resume={}"], ["--session-id", "{}"]], ids=["resume=id", "session-id id"]
)
def test_a_pass_waiting_on_tmp_keeps_the_folder_of_a_session_a_running_process_resumes(
    kitchen, tmp, monkeypatch, procfs, names
):
    """T3 Code runs a session in the main checkout with its cwd at the checkout and
    `--resume=<session id>`, so no path names its folder. The sweep keeps the folder of a session a
    process resumes, however long nothing wrote in it, and removes an ended one as old; with no
    /proc, as on macOS, `ps` gives the arguments."""
    if not procfs:
        monkeypatch.setattr(cleanup, "ROOT", kitchen.root / "no-proc")
    old = cleanup.IDLE + 3_600
    ended = session(tmp, kitchen, "ended", 100_000, old)
    resumed = session(tmp, kitchen, "resumed", 5_000, old)
    approved(kitchen, "alpha")
    given = [name.format(resumed.name) for name in names]
    command = [sys.executable, "-c", "import time; time.sleep(60)", *given]
    with subprocess.Popen(command, cwd=kitchen.root) as running:
        try:
            said = kitchen.poll()
        finally:
            running.kill()
    assert not ended.exists(), said
    assert (resumed / "scratchpad" / "blob").exists(), said
