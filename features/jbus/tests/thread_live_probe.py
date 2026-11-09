"""This probe times how long a thread's turn starting or ending in T3 Code takes to reach its
row's line of `work.json`, watched with inotify. Pytest does not collect it on its own: run it by
name.

    uv run pytest features/jbus/tests/thread_live_probe.py -s

It runs the real jbus against the kitchen's fakes (`test_jbus_kitchen.py`), with no pass between
the event and the read, and with `jbus follow` (`jbus.follow`) running where this tree has it.
T3 Code's store is a `statev2.sqlite` of the probe's own, with the table the follower reads,
which the probe writes as T3 Code does: one event a round, in its own transaction.
`PROBE_NOISE` events a second of other kinds go into it besides, from a thread of their own, as
a busy T3 Code writes turn items many times a second. None go in by default: a quiet store is
the worst case, since each write that wakes the follower is then the one it waits for. Each round
makes one event, and waits for the row's line to say it:

- `turn start`: `run.updated` with status `running`, which the line says as the thread `moving`.
- `turn end`: `run.updated` with status `completed`, which the line says as the thread `completed`.

The row's Result is written, so it is `done` either way, as a row is whose crew is still at work
on its pull request. The clock starts just before the event is written. A round whose line does
not change within `PROBE_WAIT` seconds counts as none: in a tree with no follower each round is
none, since the line waits for the next pass (`jbus.timer`, 10 s after the last pass ended, and
the pass's write of `work.json` some 30 s into it). `PROBE_ROWS` rows more stand in the queue
beside the one timed,
unapproved. `PROBE_ROUNDS` rounds of each kind run; the probe prints each kind's rounds, p50, p99
and max in ms, and fails where any round is none or the p99 is `PROBE_LIMIT_MS` or more.
"""

import ctypes
import json
import os
import select
import sqlite3
import statistics
import struct
import threading
import time
from datetime import timedelta

import pytest

import jbus
from jbus import queue, work
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add, adds, batch

try:
    from jbus import follow
except ImportError:
    follow = None

ROUNDS = int(os.environ.get("PROBE_ROUNDS", "50"))
WAIT = float(os.environ.get("PROBE_WAIT", "2"))
LIMIT = float(os.environ.get("PROBE_LIMIT_MS", "1000"))
ROWS = int(os.environ.get("PROBE_ROWS", "0"))
NOISE = float(os.environ.get("PROBE_NOISE", "0"))
IN_CLOSE_WRITE, IN_MOVED_TO = 0x8, 0x80
TABLE = (
    "create table if not exists orchestration_events (sequence integer primary key"
    " autoincrement, aggregate_kind text not null, stream_id text not null, event_type text not"
    " null, occurred_at text not null, payload_json text not null)"
)


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


class Store:
    """T3 Code's store as the probe writes it: one connection, as T3 Code's server holds one."""

    def __init__(self, where):
        where.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(where, isolation_level=None, check_same_thread=False)
        self.db.execute("pragma journal_mode = wal")
        self.db.execute(TABLE)
        self.lock = threading.Lock()
        self.minute = 0

    def emit(self, thread, kind, status=None):
        self.minute += 1
        at = (NOW + timedelta(minutes=10 + self.minute)).isoformat(timespec="milliseconds")
        payload = json.dumps({"threadId": thread, **({"status": status} if status else {})})
        with self.lock:
            self.db.execute(
                "insert into orchestration_events (aggregate_kind, stream_id, event_type,"
                " occurred_at, payload_json) values ('thread', ?, ?, ?, ?)",
                (thread, kind, at.replace("+00:00", "Z"), payload),
            )

    def noise(self, stop):
        """Write `NOISE` turn items a second until `stop` is set."""
        while NOISE and not stop.wait(1 / NOISE):
            self.emit("mcp:another-thread", "turn-item.updated")


def thread_facet(kitchen):
    kept = json.loads((kitchen.state / work.NAME).read_text())
    return {one["key"]: one for one in kept["work"]}["alpha"]["facts"]["thread"]


def timed(kitchen, watch, change, wanted):
    """Run `change` and return the ms until `work.json` says `wanted` for the row's thread."""
    seen = []

    def waits():
        until = time.perf_counter() + WAIT
        for name in watch.names(until):
            if name == work.NAME and thread_facet(kitchen) == wanted:
                seen.append(time.perf_counter())
                return

    watcher = threading.Thread(target=waits)
    watcher.start()
    began = time.perf_counter()
    change()
    watcher.join()
    return (seen[0] - began) * 1000 if seen else None


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
    monkeypatch.setattr(queue, "clock", lambda: NOW)
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path / "t3"))
    yield made
    made.close()


def test_a_turn_starting_and_ending_reaches_work_json(kitchen, tmp_path):
    if ROWS:
        text = batch(*(adds(f"row-{n}", "--priority 2") for n in range(ROWS)))
        code, said = kitchen.main("--project", "demo", "queue", "apply", stdin=text)
        assert code == 0, said
    add(kitchen, "alpha")
    kitchen.poll()
    (thread,) = kitchen.t3.threads
    kitchen.brief("alpha", "\n## Result\nStatus: done\nBranch: alpha   Pull request: none\n")
    thread.update(status="completed")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert thread_facet(kitchen) == "completed"
    store = Store(tmp_path / "t3" / "userdata" / "statev2.sqlite")
    stop, said = threading.Event(), []
    threads = [threading.Thread(target=store.noise, args=(stop,), daemon=True)]
    if follow is not None:
        args = (jbus.load(), said.append, stop, tmp_path / "t3" / "userdata" / "statev2.sqlite")
        threads.append(threading.Thread(target=follow.follow, args=args, daemon=True))
    for one in threads:
        one.start()
    time.sleep(0.2)
    watch = Watch(kitchen.state)
    took = {"turn start": [], "turn end": []}
    tid = thread["threadId"]
    for _ in range(ROUNDS):
        start = timed(kitchen, watch, lambda: store.emit(tid, "run.updated", "running"), "moving")
        took["turn start"].append(start)
        end = timed(
            kitchen, watch, lambda: store.emit(tid, "run.updated", "completed"), "completed"
        )
        took["turn end"].append(end)
    stop.set()
    for one in threads:
        one.join(WAIT)
    watch.close()
    lines = [
        f"follower: {'jbus follow' if follow else 'none in this tree'}, noise {NOISE:g}/s",
        *(summary(kind, one) for kind, one in took.items()),
    ]
    print("\n" + "\n".join(lines))
    for one in took.values():
        done = sorted(x for x in one if x is not None)
        assert len(done) == len(one), lines
        assert done[min(len(done) - 1, int(0.99 * len(done)))] < LIMIT, lines
