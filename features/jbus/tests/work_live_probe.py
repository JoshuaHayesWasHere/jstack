"""This probe times how long a change to one row's input takes to reach that row's line of
`work.json`, watched with inotify. Pytest does not collect it on its own: run it by name.

    uv run pytest features/jbus/tests/work_live_probe.py -s

It runs the real jbus against the kitchen's fakes (`test_jbus_kitchen.py`), with no pass between
the change and the read. Each round makes one change of a kind and waits for the row's line to say
what the change means:

- `queue go` and `queue hold`: the user's go for a row, then `jbus queue hold`, which takes it
  back, a row's go as the queue has it.
- `reason`: a merge tick whose `jmerge` gives the pull request another reason, on another step.
- `checks`: a merge tick whose `jmerge` moves the pull request from the check step to review, as
  when its checks end.

The clock starts just before the writer runs: the CLI verb for `queue`, and the tick for the
other two, so a tick's own call to GitHub and its run of `jmerge` count. The 5 s between ticks
(`jbus-merge.timer`) does not. A round whose line does not change within `PROBE_WAIT` seconds
counts as none. `PROBE_ROWS` rows more stand in the queue beside the one timed, unapproved, as
a long-lived queue holds hundreds. `PROBE_ROUNDS` rounds of each kind run; the probe prints each
kind's rounds, p50, p99 and max in ms, and fails where any round is none or the p99 is
`PROBE_LIMIT_MS` or more.
"""

import ctypes
import json
import os
import select
import statistics
import struct
import threading
import time

import pytest

import jbus
from jbus import tick, work
from jmerge import ready
from test_jbus_kitchen import Kitchen
from test_jbus_queue import add, adds, batch, go

ROUNDS = int(os.environ.get("PROBE_ROUNDS", "50"))
WAIT = float(os.environ.get("PROBE_WAIT", "2"))
LIMIT = float(os.environ.get("PROBE_LIMIT_MS", "100"))
ROWS = int(os.environ.get("PROBE_ROWS", "0"))
PULL = "https://example.test/pull/9"
IN_CLOSE_WRITE, IN_MOVED_TO = 0x8, 0x80


class Watch:
    """An inotify watch on one directory that wakes on each write or rename into it."""

    def __init__(self, folder):
        self.libc = ctypes.CDLL("libc.so.6", use_errno=True)
        self.fd = self.libc.inotify_init1(os.O_NONBLOCK)
        assert self.fd >= 0, ctypes.get_errno()
        mask = IN_CLOSE_WRITE | IN_MOVED_TO
        assert self.libc.inotify_add_watch(self.fd, str(folder).encode(), mask) >= 0

    def names(self, until):
        """Yield the name of each file written into the folder, until the monotonic `until`."""
        while (left := until - time.perf_counter()) > 0:
            ready_fds, _, _ = select.select([self.fd], [], [], left)
            if not ready_fds:
                return
            data = os.read(self.fd, 65536)
            at = 0
            while at < len(data):
                _, _, _, size = struct.unpack_from("iIII", data, at)
                name = data[at + 16 : at + 16 + size].rstrip(b"\0").decode()
                at += 16 + size
                yield name

    def close(self):
        os.close(self.fd)


def value(kitchen):
    kept = json.loads((kitchen.state / work.NAME).read_text())
    return {one["key"]: one for one in kept["work"]}["alpha"]["value"]


def timed(kitchen, watch, change, wanted):
    """Run `change` and return the ms until `work.json` says `wanted` for the row, or None."""
    seen = []

    def waits():
        until = time.perf_counter() + WAIT
        for name in watch.names(until):
            if name == work.NAME and value(kitchen) == wanted:
                seen.append(time.perf_counter())
                return

    watcher = threading.Thread(target=waits)
    watcher.start()
    began = time.perf_counter()
    change()
    watcher.join()
    return (seen[0] - began) * 1000 if seen else None


def tick_says(kitchen, line, run_id):
    """Make the next tick find a run that ended, and its `jmerge` print `line`."""
    kitchen.set("jmerge.txt", f"{line}\n")
    kitchen.set("runs.json", {"workflow_runs": [{"id": run_id, "status": "completed"}]})


def summary(kind, took):
    done = [one for one in took if one is not None]
    nones = len(took) - len(done)
    if not done:
        return f"{kind}: {len(took)} rounds, none reached work.json within {WAIT:g} s"
    ranked = sorted(done)
    p99 = ranked[min(len(ranked) - 1, int(0.99 * len(ranked)))]
    return (
        f"{kind}: {len(took)} rounds, {nones} none, p50 {statistics.median(done):.1f} ms, "
        f"p99 {p99:.1f} ms, max {ranked[-1]:.1f} ms"
    )


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def test_a_change_of_each_kind_reaches_work_json(kitchen):
    if ROWS:
        text = batch(*(adds(f"row-{n}", "--priority 2") for n in range(ROWS)))
        code, said = kitchen.main("--project", "demo", "queue", "apply", stdin=text)
        assert code == 0, said
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    assert value(kitchen) == "unapproved"
    watch = Watch(kitchen.state)
    took = {"queue go": [], "queue hold": [], "reason": [], "checks": []}
    typed = ("--project", "demo", "queue", "hold", "alpha")
    for _ in range(ROUNDS):
        took["queue go"].append(timed(kitchen, watch, lambda: go(kitchen, "alpha"), "ready"))
        took["queue hold"].append(timed(kitchen, watch, lambda: kitchen.main(*typed), "unapproved"))
    go(kitchen, "alpha")
    kitchen.brief("alpha", f"\n## Result\nStatus: done\nBranch: alpha   Pull request: {PULL}\n")
    kitchen.t3.thread("alpha", "completed")
    kitchen.set("open.json", [kitchen.opened("alpha", 9, None)])
    kitchen.set("jmerge.txt", f"wait 9 {PULL}: {ready.NO_REVIEW}\n")
    kitchen.poll()
    assert value(kitchen) == "review"
    assert json.loads((kitchen.state / tick.PENDING).read_text()) == [9]
    config, run_id = jbus.load(), 0

    def ticks():
        assert tick.tick(config, lambda _: None) == 0

    def round_of(line, wanted):
        nonlocal run_id
        run_id += 1
        tick_says(kitchen, line, run_id)
        return timed(kitchen, watch, ticks, wanted)

    review = f"wait 9 {PULL}: {ready.NO_REVIEW}"
    rebase = f"wait 9 {PULL}: {ready.FRESH_CONFLICT}"
    check = f"wait 9 {PULL}: {ready.NOT_PASSED.format(check='check')}"
    for _ in range(ROUNDS):
        took["reason"].append(round_of(rebase, "rebase"))
        took["reason"].append(round_of(review, "review"))
    for _ in range(ROUNDS):
        took["checks"].append(round_of(check, "check"))
        took["checks"].append(round_of(review, "review"))
    watch.close()
    said = [summary(kind, one) for kind, one in took.items()]
    print("\n" + "\n".join(said))
    for one in took.values():
        done = sorted(x for x in one if x is not None)
        assert len(done) == len(one), said
        assert done[min(len(done) - 1, int(0.99 * len(done)))] < LIMIT, said
