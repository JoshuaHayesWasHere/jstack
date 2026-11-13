"""`jbus run-wait`: a crew waits on a GitHub Actions run it started, and jbus wakes it once the
run has ended.

A crew that proves a change on a run it dispatched (the macOS nightly, a browser run) would end
its turn on a run of most of an hour, and nothing in T3 Code wakes it when the run ends. Its row
went stale, or its Result said "run in progress" and the row stayed not done until the root
noticed. So the crew registers the wait, `jbus run-wait <run id> --thread <its thread id>`, and
ends its turn:

- The verb asks GitHub for the run once, in the project's checkout. A run GitHub does not know is
  refused, so no wait is kept that no run can end. A run that has ended already registers
  nothing: the verb prints its conclusion, and the crew reads it at once. Any other run is kept
  in `run-waiters.json` (`jbus.runwaiters`), with its workflow's name and its page.
- While the wait is kept, the thread's turn ended on a wait that jbus owns
  (`watch.owned_waits`): its row is never stale or left, the `Stop` hook lets the turn end, and
  the row's `why` names the run (`watch.status`).
- Each pass, `wake` asks GitHub once for each run its project's threads wait on, with one
  `gh api` read, and no more. A run that has ended wakes its thread with one message in mode
  queue that names the run and its conclusion, keyed by the wait, so a retry is the same message.
  The wait leaves the file once T3 Code took the message, or its thread is gone, settled or
  ended (`slotwait.dead`). A run GitHub did not answer for is asked again on the next pass.
"""

from __future__ import annotations

import argparse
import functools
import json
import subprocess
from collections.abc import Callable
from typing import Any

import jbus
from jbus import END_TURN, outbox, runwaiters, slotwait, verbs
from jbus.passes import Pass
from jbus.runwaiters import RunWait
from jbus.t3 import GONE, Client, T3Error, T3Refused
from jsettings import proc

EVENTS = {"run-wake": "quiet"}
FIELDS = "{status, conclusion, name, html_url}"
TIMEOUT = 30
ENDED = (
    "jbus: GitHub run {run} ({name}), which this thread waits on, has ended: {conclusion}. {url}"
    " Read what it found and go on with the task from there. " + END_TURN
)


def ask(run: str, call: Callable[..., subprocess.CompletedProcess[str]]) -> dict[str, Any] | str:
    """GitHub's word on the run `run`, with one `gh api` read that `call` runs in the project's
    checkout: its status, its conclusion, its workflow's name and its page. A string says why
    there is none."""
    path = f"repos/{{owner}}/{{repo}}/actions/runs/{run}"
    try:
        said = call("gh", "api", path, "--jq", FIELDS, timeout=TIMEOUT)
    except OSError as error:
        return str(error)
    if said.returncode != 0:
        return (said.stderr or said.stdout).strip() or f"gh ended {said.returncode}"
    try:
        found = json.loads(said.stdout)
    except ValueError:
        return f"gh gave no run: {said.stdout.strip()[:80]}"
    return found if isinstance(found, dict) else f"gh gave no run: {said.stdout.strip()[:80]}"


def wake(run: Pass, client: Client) -> None:
    """Wake each thread whose run of this project has ended, once, and drop the waits that are
    over: woken, or with a thread that cannot be woken."""
    at = runwaiters.where()
    mine = [one for one in runwaiters.read(at) if one.project == run.project.name]
    over: set[str] = set()
    for one in mine:
        if slotwait.dead(run, client, one):
            over.add(one.id)
            continue
        found = ask(one.run, run.run)
        if isinstance(found, str):
            run.say(f"wait {one.thread}: GitHub run {one.run} could not be read ({found})")
            continue
        if found.get("status") == "completed" and tell(run, client, one, found):
            over.add(one.id)
    if over:
        runwaiters.forget(at, over)


def tell(run: Pass, client: Client, one: RunWait, found: dict[str, Any]) -> bool:
    """Send the thread the end of its run, and say whether the wait is over: T3 Code took the
    message, or said the thread is gone."""
    conclusion = str(found.get("conclusion") or "no conclusion")
    name = str(found.get("name") or one.name)
    text = ENDED.format(run=one.run, name=name, conclusion=conclusion, url=one.url)
    try:
        went = outbox.send(
            run,
            client,
            thread=one.thread,
            row=one.thread,
            key=f"run-wake|{one.thread}|{one.id}",
            text=text,
            template="run-wake",
            needs="act",
        )
    except T3Refused as error:
        if GONE.search(str(error)):
            run.say(f"wait {one.thread}: its run wait is dropped, its thread is gone ({error})")
            return True
        run.say(f"wait {one.thread}: it could not be told run {one.run} ended ({error})")
        return False
    except T3Error as error:
        run.say(f"wait {one.thread}: it could not be told run {one.run} ended ({error})")
        return False
    if not went:
        return False
    line = (
        f"run-wake: woke {one.thread}, GitHub run {one.run} ({name}) ended {conclusion},"
        f" after {slotwait.waited(one, run.now)} min"
    )
    run.find("", "run-wake", line, key=one.id)
    run.say(line)
    return True


def _register(args: argparse.Namespace, config: jbus.Config) -> int:
    project = verbs.here(config, args.project)
    found = ask(args.run, functools.partial(proc.run, cwd=project.checkout))
    if isinstance(found, str):
        raise jbus.Refused(f"refused: GitHub gives no run {args.run} for {project.name}: {found}")
    name, url = str(found.get("name") or "a workflow"), str(found.get("html_url") or "")
    if found.get("status") == "completed":
        conclusion = found.get("conclusion") or "no conclusion"
        print(
            f"ended: run {args.run} ({name}) has ended already, {conclusion}: {url}. Nothing is"
            " registered: read it now."
        )
        return 0
    wait = runwaiters.register(
        runwaiters.where(), args.thread, project.name, args.run, name, url, verbs.clock()
    )
    print(
        f"waiting: run {args.run} ({name}) is {found.get('status') or 'not ended'}, and jbus"
        f" wakes {wait.thread} once when it ends: end your turn now."
    )
    return 0


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("run", help="the id of the GitHub Actions run to wait on")
    parser.add_argument("--thread", required=True, help="the id of the thread to wake")


VERBS = (
    verbs.Verb(
        "run-wait",
        "wait on a GitHub Actions run: jbus wakes the thread once it ends",
        _arguments,
        _register,
    ),
)

STEPS = (
    verbs.Step(
        "tellers",
        45,
        "runwait.wake",
        lambda half: wake(half.run, half.client),
        ("client", "world", "budget"),
    ),
)
