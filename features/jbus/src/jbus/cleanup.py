"""`jbus cleanup <brief>`: print the brief of the cleanup row that a `Review: after` review
needs.

The pull request of a brief whose `Review:` line says `after` merges on its check alone
(`jmerge.ready.after`). Its review's findings do not block the merge, and a crew fixes them
later, in a row of their own. The reviewer runs this command once it has written its section, and
pipes what it prints into `jbus queue add cleanup-<slug>`. That command queues the row
without approving it, so the row waits for the user's go like any other.

The command prints that row's brief, `cleanup-<slug>`, when the last round's verdict is
`findings`. The brief lists each finding that would have gone to the crew, with its
path:line, the pull request, and the merge commit GitHub gives for it. Where the pull request
has not merged yet, the brief gives the head the review saw instead. Where the review needs no row,
the command prints nothing and ends 1 with the reason on one line. That is when the brief
does not say `after` or `twice`, when the review is clean or has no verdict, or when the row
is already in the queue. A `queue add` on a row that is already there would withdraw its
approval.

A brief that says `twice` answers its first review in one fix round. The row's brief lists
the findings of its second review (`ready.second_review`): each one of severity `warning`
or `error`, whatever its bucket. The command drops the `info` findings and counts them.
Until the reviewer writes that second review, the command prints `FIRST`, because the first
review goes to the crew.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import jbus
from jbriefs import findings
from jbus import mirror, queue, verbs, watch
from jmerge import ready

PRIORITY = 50
NOT_AFTER = "no cleanup row: the brief does not say Review: after or twice"
FIRST = "first review: a Review: twice brief's first review goes to its crewmate, as step 4 named"
NO_WARNING = (
    "no cleanup row: its second review has no warning or error finding, {info} info dropped"
)
FILED = ("error", "warning")
UNREVIEWED = "no cleanup row: its last review has no verdict yet"
CLEAN = "no cleanup row: its last review is clean"
THERE = "no cleanup row: {slug} is already in the queue"
MERGED = "{url}, merged as {commit}"
OPEN = (
    "{url}, not merged when the review of {head} was written: its merge commit is "
    "`gh pr view {url} --json mergeCommit`"
)


def slug_of(slug: str) -> str:
    return f"cleanup-{slug}"


def filed(text: str) -> tuple[list[findings.Finding], int]:
    """Return the findings the brief's cleanup row lists, and the count of those it drops.
    For an `after` brief they are the findings its triage sends, with none dropped. For a
    `twice` brief they are its second review's findings of severity `warning` or `error`,
    with the count of its `info` ones."""
    said = ready.said_of(text)
    if said.mode == ready.AFTER:
        return (findings.triage(text).sent() if said.verdict == "findings" else []), 0
    heads = ready.second_review(text)
    second = [
        one
        for one in said.triage.findings
        if one.lead.head in heads and not one.superseded and one.bucket != findings.DISMISSED
    ]
    kept = [one for one in second if one.severity in FILED]
    return kept, len(second) - len(kept)


def brief(
    slug: str,
    text: str,
    merge: str,
    said: ready.Said,
    kept: tuple[list[findings.Finding], int],
) -> str:
    """Return the cleanup row's brief for the brief `text` of `slug`, or nothing where the
    row would list no finding. `said` is `ready.said_of(text)` and `kept` is `filed(text)`, which
    the caller reads once each. `merge` is the merge commit, or nothing while the pull request
    is open."""
    sent, dropped = kept
    if said.mode not in (ready.AFTER, ready.TWICE) or not sent:
        return ""
    url, _ = watch.named(mirror.last_result(text) or "")
    pull = (
        MERGED.format(url=url, commit=merge)
        if merge
        else OPEN.format(url=url, head=said.reviewed or "its head")
    )
    twice = said.mode == ready.TWICE
    listed = "\n".join(f"- {_shown(one, twice)}" for one in sent)
    places = sorted(dict.fromkeys(one.path for one in sent if one.path))
    if twice:
        head = (
            f"# {slug_of(slug)}: fix what the second review of {slug} found\n"
            f"Task: {slug} said `Review: twice`, so it merged once its second review was "
            f"written, and that review's warning and error findings come here; its {dropped} "
            f"info findings were dropped. Pull request: {pull}.\n"
        )
    else:
        head = (
            f"# {slug_of(slug)}: fix what the review of {slug} found after it merged\n"
            f"Task: {slug} said `Review: after`, so it merged on its check and its review's "
            f"findings come here. Pull request: {pull}.\n"
        )
    return head + (
        f"Done when:\n{listed}\n"
        "- Each finding above is fixed, or the Result says why it stands, citing a path:line.\n"
        "- The check command (`notes.md`) passes.\n"
        "Proves it: CI's `check` job on the pull request, and a test for each finding fixed "
        "where one can be written.\n"
        "Size: S\n"
        f"Where: {', '.join(f'`{one}`' for one in places) or 'the files the findings name'}\n"
        "Design: none, each finding names its own fix\n"
        "Pull request: open one when done\n"
        "Review: review\n"
        "Playbook: bug-fix\n"
    )


def _shown(one: findings.Finding, twice: bool) -> str:
    """Return one finding's line. A `twice` row's line includes the finding's severity,
    which is why the finding is in the row. An `after` row's line keeps its old form."""
    place = f"{one.path}:{one.line}" if one.line is not None else one.path
    severity = f"{one.severity} " if twice else ""
    risk = f" (risk: {one.risk})" if one.risk else ""
    return f"{one.id} {severity}{place}: {one.lead.what} ({one.bucket}){risk}"


def _merge_commit(url: str) -> str:
    """Return the merge commit GitHub gives for the pull request, or nothing where the pull
    request is open or GitHub gave no answer."""
    if not url:
        return ""
    try:
        asked = subprocess.run(
            ["gh", "pr", "view", url, "--json", "mergeCommit"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        said = json.loads(asked.stdout) if asked.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return ""
    return ((said or {}).get("mergeCommit") or {}).get("oid", "")


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("brief", help="the reviewed brief, <state>/tasks/<slug>.md")


def _run(args: argparse.Namespace, config: jbus.Config) -> int:
    path = Path(args.brief)
    try:
        text = path.read_text(errors="replace")
    except OSError as error:
        raise jbus.Refused(f"refused: no brief at {path} ({error.strerror})") from error
    slug = path.stem
    said = ready.said_of(text)
    if said.mode not in (ready.AFTER, ready.TWICE):
        print(NOT_AFTER)
        return 1
    if said.mode == ready.TWICE and not ready.second_review(text):
        print(FIRST)
        return 1
    kept = filed(text)
    why = ""
    if said.mode == ready.TWICE and not kept[0]:
        why = NO_WARNING.format(info=kept[1])
    elif said.verdict not in ("clean", "findings"):
        why = UNREVIEWED
    elif said.verdict == "clean":
        why = CLEAN
    else:
        state = config.state(verbs.project(config, args.project))
        if any(row["slug"] == slug_of(slug) for row in queue.load(state)):
            why = THERE.format(slug=slug_of(slug))
    if why:
        print(why)
        return 1
    url, _ = watch.named(mirror.last_result(text) or "")
    print(brief(slug, text, _merge_commit(url), said, kept), end="")
    return 0


VERBS = (
    verbs.Verb(
        "cleanup",
        "print the cleanup row a Review: after review or a Review: twice second review owes, "
        "or why none",
        _arguments,
        _run,
    ),
)
