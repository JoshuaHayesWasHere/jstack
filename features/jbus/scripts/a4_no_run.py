"""Replay alarm A4 with the no-run filter over a jbus events log, and print each time it fires.

A4 fires once when `jmerge`'s last word on a pull request has been a wait on a required check for
45 minutes. `jmerge` logs a wait only when it changes, so the word holds from its line until the
next. The no-run filter keeps a wait only where GitHub has no run of that check at the head the
pull request had then: a line `<check> has no run at <head12>` says so itself, and an older line
`<check> has not passed` is asked of GitHub. The head of the time is found from the head before
the first force push after it, or the head of today where none came after, walked back along
first parents to the last commit committed by then. A check with no run is what `clock.held`
wakes the home for, and a check that ran and is slow is the merge runner's.

    uv run python features/jbus/scripts/a4_no_run.py 2026-10-26 2026-10-27 \
        ~/.local/state/jbus/jstack/events.jsonl JoshuaHayesWasHere/jstack

The method is the one of scout day-audit-1026-3's `a4.py`, with the filter.
"""

from __future__ import annotations

import functools
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta

MINUTES = 45
WAIT = re.compile(r"(\S+) has (?:not passed|no run at ([0-9a-f]{12}))$")


def gh(path: str) -> list | dict:
    ran = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", path], capture_output=True, text=True, check=True
    )
    pages = json.loads(ran.stdout)
    if all(isinstance(page, list) for page in pages):
        return [one for page in pages for one in page]
    return pages


PUSHES = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      headRefOid
      timelineItems(itemTypes: [HEAD_REF_FORCE_PUSHED_EVENT], first: 100) {
        nodes { ... on HeadRefForcePushedEvent { createdAt beforeCommit { oid } } }
      }
    }
  }
}
"""


@functools.cache
def pushes(repo: str, number: str) -> tuple[str, tuple[tuple[datetime, str], ...]]:
    """The pull request's head today, and each force push with the head it replaced."""
    owner, name = repo.split("/")
    ran = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={PUSHES}", "-f", f"owner={owner}"]
        + ["-f", f"name={name}", "-F", f"number={number}"],
        capture_output=True,
        text=True,
        check=True,
    )
    pull = json.loads(ran.stdout)["data"]["repository"]["pullRequest"]
    nodes = pull["timelineItems"]["nodes"]
    replaced = [(at(one["createdAt"]), one["beforeCommit"]["oid"]) for one in nodes if one]
    return pull["headRefOid"], tuple(sorted(replaced))


@functools.cache
def commit(repo: str, sha: str) -> tuple[datetime, str]:
    """When the commit was committed, and its first parent."""
    found = gh(f"repos/{repo}/commits/{sha}")
    one = found[0] if isinstance(found, list) else found
    parents = one.get("parents") or [{}]
    return at(one["commit"]["committer"]["date"]), parents[0].get("sha", "")


def head_at(repo: str, number: str, since: datetime) -> str:
    """The head the pull request had at `since`."""
    head, replaced = pushes(repo, number)
    sha = next((before for when, before in replaced if when > since), head)
    while sha:
        when, parent = commit(repo, sha)
        if when <= since:
            return sha
        sha = parent
    return ""


@functools.cache
def started(repo: str, sha: str, check: str) -> tuple[datetime, ...]:
    pages = gh(f"repos/{repo}/commits/{sha}/check-runs?check_name={check}&per_page=100")
    runs = [run for page in pages for run in page["check_runs"]]
    return tuple(at(run["started_at"]) for run in runs if run.get("started_at"))


def at(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def no_run(repo: str, number: str, why: str, since: datetime, fire: datetime) -> bool:
    """Whether the wait `why` is on a required check with no run at the head of the time."""
    found = WAIT.search(why)
    if found is None:
        return False
    if found[2]:
        return True
    head = head_at(repo, number, since)
    return bool(head) and not any(when <= fire for when in started(repo, head, found[1]))


def main(argv: list[str]) -> int:
    first, last, events, repo = argv
    state: dict[str, tuple[str, datetime]] = {}
    fired: set[tuple[str, datetime]] = set()
    for raw in open(events):
        event = json.loads(raw)
        if not event.get("event") or not (first <= event["at"] < last):
            continue
        now = at(event["at"])
        for number, (why, since) in state.items():
            fire = since + timedelta(minutes=MINUTES)
            if (number, since) in fired or now < fire or not no_run(repo, number, why, since, fire):
                continue
            fired.add((number, since))
            print(f"FIRES {fire:%H:%M}Z #{number} {why}, since {since:%H:%M}Z")
        if event["event"] != "jmerge":
            continue
        words = event["line"].split()
        if words[0] in ("wait", "merged") and len(words) > 1 and words[1].isdigit():
            why = event["line"].split(": ", 1)[1] if words[0] == "wait" else "merged"
            if state.get(words[1], ("",))[0] != why:
                state[words[1]] = (why, now)
    print("total", len(fired))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
