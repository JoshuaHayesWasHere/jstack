"""This probe times, live, how long a pull request's check takes from ending on GitHub to its row's
line of `work.json`. Pytest does not collect it: run it by name, beside a running jbus.

    uv run python features/jbus/tests/checks_bound_probe.py --repo owner/name --pr 123 \
        --work ~/.local/state/jbus/<project>/work.json

jbus's leftover sweep (`jbus.strays`) stops an orphan, a process whose parent is a reaper as it is
after `setsid` or once the shell that started it is gone, when its working directory or a path
argument is under a task's worktree, or under /tmp or /var/tmp while a session of that worktree
started it. It keeps a process whose parent still runs, such as one in the user's own terminal.
So a thread that leaves the probe running starts it from the main checkout, with every path
argument and the output outside any worktree and /tmp:

    mkdir -p ~/.local/state/checks-bound-probe && cd <the main checkout> &&
        setsid -f uv run python features/jbus/tests/checks_bound_probe.py \
        --repo owner/name --pr 123 --work ~/.local/state/jbus/<project>/work.json \
        > ~/.local/state/checks-bound-probe/probe.log 2>&1

A scout works in the main checkout, and the sweep stops what a scout's own session left there, so a
scout leaves no probe running.

It writes nothing of jbus's, and reads the home's `required-checks` (`--required`). Every `POLL`
seconds it asks GitHub for the pull request, to follow its head, and for the check runs of that
head, each with the ETag it last saw, so a 304, which is every answer but the one after a change,
spends none of the API allowance. It asks
once for each workflow run it has not seen, for the workflow's name: about four counted calls a
head. It watches the directory of `work.json` with inotify and keeps the moment each write changed
the line whose `pr` is the pull request, with the line as it then was, and the moment that line
first had the pull request.

A round is one head whose required checks the probe saw going and then settled, where jmerge's
verdict is settled too (`round_end`): at the end of its first failed required job, or at the end
of its last required job. A job of a workflow no required check names, such as `browser`, does not
count. Its end is a `completed_at`, which GitHub gives to the second, and its delay is the first
change of the row's line after that end that names the head as ended (`ENDED`), the write of the
verdict on it. A write that names another head or none, such as a pass's at its start, is not the
round's end: on a draft only the merge tick writes it (sa-checks-bound-measure-8).
A round whose line did not name its head within `--wait` seconds counts as none. A push starts
the next round. A head whose checks had settled when the probe first saw them makes no round, and
neither does one whose checks ended before the row's line had the pull request: a probe started
then, or before the row was linked, records the next head's. `--rounds` is the count of rounds it
records. It prints each round as it ends and appends it as one JSON line to `--out`, then prints
the rounds, p50 and max in seconds.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import select
import statistics
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from jbus.restated import ENDED
from jmerge.checks import NOT_RED
from jmerge.ready import required_of

POLL = 0.5
OUT = Path("~/.local/state/checks-bound-probe/rounds.jsonl")
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


def round_end(
    runs: list[dict], workflow_of: dict[str, str], required: tuple[str, ...]
) -> tuple[float, str] | None:
    """When a head's round of checks ended, with `failed` or `passed`, or None while it goes.

    A required job is any job of a workflow that a required check names, shards included, found
    by the workflow run in its `html_url` (`workflow_of`). The round fails at the end of its first
    failed required job, and passes at the end of its last required job once GitHub lists a run
    of each required check: it lists `check` only after the shards it needs have ended. A job of
    any other workflow, such as `browser`, counts for neither."""
    mine = [one for one in runs if workflow_of.get(_run(one)) in required]
    failed = [
        one for one in mine if one["status"] == "completed" and one["conclusion"] not in NOT_RED
    ]
    if failed:
        return min(map(_ended, failed)), "failed"
    listed = {one["name"] for one in mine}
    if not set(required) <= listed or any(one["status"] != "completed" for one in mine):
        return None
    return max(map(_ended, mine)), "passed"


def _run(one: dict) -> str:
    found = _RUN_URL.search(one.get("html_url") or "")
    return found.group(1) if found else ""


def _ended(one: dict) -> float:
    return datetime.fromisoformat(one["completed_at"]).timestamp()


_RUN_URL = re.compile(r"/actions/runs/(\d+)/job/")


class Line:
    """The moments the row's line of `work.json` changed, each with the line as it then was, from
    inotify on its directory, and `since`, the first moment the probe saw a line of the pull
    request, None while it has seen none."""

    def __init__(self, work: Path, pr: int):
        self.work, self.pr, self.changed = work, pr, []
        self.last = self.read()
        self.since = time.time() if self.last else None
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
                self.changed.append((at, now or {}))
                if now and self.since is None:
                    self.since = at

    def named(self, head: str, ended: float) -> list[tuple[float, dict]]:
        """The changes since `ended` whose line names `head` as ended, with a verdict on it."""
        return [(at, now) for at, now in self.changed if at >= ended and now.get(ENDED) == head]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--wait", type=float, default=120)
    parser.add_argument(
        "--required",
        type=Path,
        help="the home's required-checks, by default ~/.local/state/home/<repo>/required-checks",
    )
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    home = Path("~/.local/state/home") / args.repo.split("/")[-1] / "required-checks"
    required = required_of((args.required or home).expanduser().read_text())
    out = args.out.expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"required: {', '.join(required)}; each round is appended to {out}", flush=True)
    line = Line(args.work.expanduser(), args.pr)
    workflow_of: dict[str, str] = {}
    delays: list[float | None] = []
    done: set[str] = set()
    going: set[str] = set()
    etags: dict[str, str] = {}
    sha = ""
    while len(delays) < args.rounds:
        time.sleep(POLL)
        _, etags["pull"], pull = gh(f"repos/{args.repo}/pulls/{args.pr}", etags.get("pull", ""))
        if isinstance(pull, dict):
            sha = pull["head"]["sha"]
        if sha and sha not in done:
            _, etags[sha], body = gh(
                f"repos/{args.repo}/commits/{sha}/check-runs", etags.get(sha, "")
            )
            runs = body.get("check_runs", []) if isinstance(body, dict) else None
            for run in {_run(one) for one in runs or []} - workflow_of.keys() - {""}:
                _, _, workflow = gh(f"repos/{args.repo}/actions/runs/{run}")
                if isinstance(workflow, dict):
                    workflow_of[run] = workflow["name"]
            end = round_end(runs or [], workflow_of, required)
            if runs and end is None:
                going.add(sha)
            elif end and (sha not in going or line.since is None or line.since > end[0]):
                done.add(sha)
            elif end:
                ended, verdict = end
                until = time.time() + args.wait
                while time.time() < until and not line.named(sha, ended):
                    time.sleep(0.05)
                after = [(at, now.get("value", "")) for at, now in line.named(sha, ended)]
                delay = after[0][0] - ended if after else None
                delays.append(delay)
                done.add(sha)
                said = f"{delay:.1f} s, the line says {after[0][1]}" if after else "none"
                print(
                    f"round {len(delays)}: head {sha[:7]}, checks {verdict} "
                    f"{datetime.fromtimestamp(ended):%H:%M:%S}: {said}",
                    flush=True,
                )
                kept = {
                    "repo": args.repo,
                    "pr": args.pr,
                    "head": sha,
                    "verdict": verdict,
                    "ended": datetime.fromtimestamp(ended, UTC).isoformat(),
                    "line_at": datetime.fromtimestamp(after[0][0], UTC).isoformat()
                    if after
                    else None,
                    "delay": round(delay, 3) if delay is not None else None,
                    "says": after[0][1] if after else None,
                }
                with out.open("a") as rounds:
                    rounds.write(json.dumps(kept) + "\n")
    timed = sorted(one for one in delays if one is not None)
    p50 = f"{statistics.median(timed):.1f} s" if timed else "none"
    print(
        f"{len(delays)} rounds, {len(delays) - len(timed)} none; "
        f"p50 {p50}, max {timed[-1] if timed else 0:.1f} s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
