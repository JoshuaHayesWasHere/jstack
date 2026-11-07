"""This probe times, live, how long a pull request's check takes from ending on GitHub to its row's
line of `work.json`. Pytest does not collect it: run it by name, beside a running jbus.

    uv run python features/jbus/tests/checks_bound_probe.py --repo owner/name --pr 123 \
        --work ~/.local/state/jbus/<project>/work.json

It reads and writes nothing of jbus's. Every `POLL` seconds it asks GitHub for the check runs of
the pull request's head with the ETag it last saw, so a 304, which is every answer but the one
after a change, spends none of the API allowance. It watches the directory of `work.json` with
inotify and keeps the moment each write changed the line whose `pr` is the pull request.

A round is one head whose check runs the probe saw going and then all ended: its end is the
latest `completed_at`, which GitHub gives to the second, and its delay is the first change of the
row's line after that end.
A round whose line did not change within `--wait` seconds counts as none. A push starts the next
round. It prints each round as it ends, then the rounds, p50 and max in seconds.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import select
import statistics
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

POLL = 0.5
IN_CLOSE_WRITE, IN_MOVED_TO = 0x8, 0x80


def gh(path: str, etag: str = "") -> tuple[str, str, object]:
    """Ask GitHub for `path` with `etag`: the status, the new ETag and the body, None on a 304."""
    asked = subprocess.run(
        ["gh", "api", path, "-i", *(["-H", f"If-None-Match: {etag}"] if etag else [])],
        capture_output=True,
        text=True,
    )
    head, _, body = asked.stdout.replace("\r", "").partition("\n\n")
    lines = head.splitlines() or [""]
    status = (lines[0].split()[1:2] or [""])[0]
    tags = [one.split(":", 1)[1].strip() for one in lines if one.lower().startswith("etag:")]
    return status, tags[0] if tags else etag, json.loads(body) if status == "200" else None


class Line:
    """The moments the row's line of `work.json` changed, from inotify on its directory."""

    def __init__(self, work: Path, pr: int):
        self.work, self.pr, self.changed = work, pr, []
        self.last = self.read()
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        self.fd = libc.inotify_init1(os.O_NONBLOCK)
        assert (
            libc.inotify_add_watch(self.fd, str(work.parent).encode(), IN_CLOSE_WRITE | IN_MOVED_TO)
            >= 0
        )
        threading.Thread(target=self.follow, daemon=True).start()

    def read(self) -> dict | None:
        try:
            lines = json.loads(self.work.read_text())["work"]
        except (OSError, ValueError, KeyError):
            return None
        mine = [one for one in lines if str(one.get("pr", "")) == f"#{self.pr}"]
        return mine[0] if mine else None

    def follow(self) -> None:
        while True:
            select.select([self.fd], [], [])
            at = time.time()
            os.read(self.fd, 65536)
            now = self.read()
            if now != self.last:
                self.last = now
                self.changed.append((at, (now or {}).get("value", "")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--wait", type=float, default=120)
    args = parser.parse_args()
    line = Line(args.work.expanduser(), args.pr)
    delays: list[float | None] = []
    done: set[str] = set()
    going: set[str] = set()
    etags: dict[str, str] = {}
    while len(delays) < args.rounds:
        _, _, pull = gh(f"repos/{args.repo}/pulls/{args.pr}")
        sha = pull["head"]["sha"] if isinstance(pull, dict) else ""
        while sha and sha not in done:
            status, etags[sha], body = gh(
                f"repos/{args.repo}/commits/{sha}/check-runs", etags.get(sha, "")
            )
            runs = body.get("check_runs", []) if isinstance(body, dict) else None
            if runs and any(one["status"] != "completed" for one in runs):
                going.add(sha)
            elif runs and sha in going:
                ended = max(datetime.fromisoformat(one["completed_at"]).timestamp() for one in runs)
                until = time.time() + args.wait
                while time.time() < until and not [at for at, _ in line.changed if at >= ended]:
                    time.sleep(0.05)
                after = [(at, value) for at, value in line.changed if at >= ended]
                delay = after[0][0] - ended if after else None
                delays.append(delay)
                done.add(sha)
                said = f"{delay:.1f} s, the line says {after[0][1]}" if after else "none"
                print(
                    f"round {len(delays)}: head {sha[:7]}, checks ended "
                    f"{datetime.fromtimestamp(ended):%H:%M:%S}: {said}",
                    flush=True,
                )
                break
            time.sleep(POLL)
        time.sleep(POLL)
    timed = sorted(one for one in delays if one is not None)
    p50 = f"{statistics.median(timed):.1f} s" if timed else "none"
    print(
        f"{len(delays)} rounds, {len(delays) - len(timed)} none; "
        f"p50 {p50}, max {timed[-1] if timed else 0:.1f} s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
