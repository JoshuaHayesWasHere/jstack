"""`jbus cleanup <brief>`: print the brief of the cleanup row that a `Review: after` review
needs.

The pull request of a brief whose `Review:` line says `after` merges on its check alone
(`jmerge.ready.after`). Its review's findings do not block the merge, and a crew fixes them
later, in a row of their own. The reviewer runs this command once it has written its section, and
pipes what it prints into `jbus queue add cleanup-<slug>`. That command approves the row by the
home's follow-up rule where the reviewed row had the user's go (`queue.FOLLOW_UP`), and otherwise
the row waits for the user's go like any other.

The command prints that row's brief, `cleanup-<slug>`, when the last round's verdict is `findings`.
The brief lists each finding that would have gone to the crew, with its path:line, the pull request,
and the pull request's merge commit as GitHub gives it. Where the pull request has not merged yet,
the brief gives the head the review saw instead, says it has not merged, and says the row launches
after it merges. A finding with no repo path, `-` or none, stays out of the brief's `Where:`.
Where the review needs no row, the command prints nothing but the reason, on one line, and exits
with status 1. That is when the brief does not say `after` or `twice`, when the review is clean or
has no verdict, or when the row is already in the queue. A `queue add` on a row that is already
there would withdraw its approval.

For a brief that says `twice`, the crew answers the first review in one fix round. The row's brief
lists the findings of the second review (`ready.second_review`): each one of severity `warning` or
`error`, whatever its bucket. The command drops the `info` findings and counts them. Until the
reviewer writes that second review, the command prints `FIRST`, because the first review goes to the
crew.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import jbus
from jbriefs import findings, home
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
    For an `after` brief, they are the findings that the brief's triage sends, and the
    function drops none. For a `twice` brief, they are the second review's findings of
    severity `warning` or `error`, and the count is that of its `info` findings."""
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
    is open. The row has the `Home:` line of `text`, so its Result goes to the home of
    the work."""
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
    places = sorted(dict.fromkeys(one.path for one in sent if one.path not in ("", "-")))
    waits = " Its pull request is open and has not merged, so this row launches after it merges."
    if twice:
        why = (
            "so it merged once its second review was written, and that review's"
            if merge
            else "and its second review's"
        )
        head = (
            f"# {slug_of(slug)}: fix what the second review of {slug} found\n"
            f"Task: {slug} said `Review: twice`, {why} warning and error findings "
            f"come here; its {dropped} info findings were dropped.{'' if merge else waits} "
            f"Pull request: {pull}.\n"
        )
    else:
        why = "so it merged on its check and its" if merge else "and its"
        head = (
            f"# {slug_of(slug)}: fix what the review of {slug} found"
            f"{' after it merged' if merge else ''}\n"
            f"Task: {slug} said `Review: after`, {why} review's findings come here."
            f"{'' if merge else waits} Pull request: {pull}.\n"
        )
    named = home.named(text)
    return head + (
        f"Done when:\n{listed}\n"
        "- Each finding above is fixed, or the Result says why it stands, citing a path:line.\n"
        "- The check command (`notes.md`) passes.\n"
        "Proves it: CI's `check` job on the pull request, and a test for each finding fixed "
        "where one can be written.\n"
        "Size: S\n"
        f"Where: {', '.join(f'`{one}`' for one in places) or 'the files the findings name'}\n"
        "Design: none, each finding names its own fix\n"
        f"Decisions: none, jbus files this follow-up of {slug}'s review, and its findings "
        "are the task\n"
        "Pull request: open one when done\n"
        "Review: review\n"
        "Playbook: bug-fix\n"
        f"Builds on: {slug}: the code of its pull request, which the findings are in\n"
        + (f"Home: {named}\n" if named else "")
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
