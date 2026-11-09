"""What finished crews leave in /tmp never holds back a launch, and a launch /tmp does hold back
says so from its first pass.

A settled crew's whole Claude scratch folder goes with its worktrees (`jbus.cleanup.clear_scratch`).
A pass that `jgauge room` holds back for /tmp first removes the Claude scratch folders of crews
whose worktrees are gone and the copies of the base `proved.sh` left behind (`jbus.cleanup.sweep`),
then asks room again. Like `test_jbus_kitchen.py`, the tests run the real pass and the real
`jgauge room` against the fakes, here with a /tmp whose quota counts what the folders hold.
"""

import json
import os
import re
import subprocess

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
        "used=$(find \"$last\" -type f -printf '%s\\n' | awk '{s += $1} END {print s + 0}')\n"
        f"echo {QUOTA_KIB} $((used * {SCALE}))\n"
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
