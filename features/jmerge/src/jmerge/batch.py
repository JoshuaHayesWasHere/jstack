"""The batch: the pull requests main moved past, proven together by CI's check of one tree.

Where the state has a `merge-batch` file (`SWITCH`), a pull request into the default branch that
is ready by every rule but "main moved" and the guards on its merged tree is a member
(`cli.Repo.over_main`). `jmerge` builds main's tip with each member merged in, in merge order,
force-pushes that commit to its own branch `BRANCH`, under one standing draft pull request, and
keeps the tip, the tree, the commit and the members in `KEPT`. CI's check of that pull request
runs on GitHub's merge of its head over main, whose tree is the batch's, since the head holds the
tip, and leaves the artifact of the two trees (`green.checked`). On it, with the tip unmoved,
`jmerge` squash-merges each member at its own head, in order, with no guards run
(`cli.Repo.merge_batch`). A batch whose check failed, passed with no artifact, or ran past
`PENDING_MINUTES`, sends each member down the single path of today at that head (`failed`).

The batch pull request is jmerge's own: it is never judged as a row's, and never merged.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from jmerge import bus, ready
from jsettings import store

BRANCH = "jmerge/batch"
KEPT = "batch.json"
SWITCH = "merge-batch"
MOST = 12
"""The most members a batch takes: the scout's cap, above which a failed batch costs too many
members a round of their own (scouts/po-batched-merge-scout.md)."""
PENDING_MINUTES = 30
"""How long a batch's check may go without an end before the batch counts as failed: above the
p90 of 387 s of the pull request check, so a run GitHub left queued or never started does not
hold its members for ever."""
SHA = 12
_IDENTITY = ("-c", "user.name=jmerge", "-c", "user.email=jmerge@localhost")

IN_BATCH = ready.Reason(
    "check",
    "it is in jmerge's batch over {base} at {tip}, whose check decides its merge",
    ready.MERGING.code,
)
"""The wait of a member of a batch whose check runs. Its code is `merging`, jmerge's own merge at
work, which no crew can fix: jbus sorts the codes of `ready` alone."""
AFTER = ready.Reason(
    "check",
    "jmerge's batch over {base} at {tip} is checked and merges first: a merge before it would "
    "undo that check",
    ready.MERGING.code,
)
"""The wait of a pull request that would merge while a batch is checked: a member that joined
after it was built, one the batch had no room for, and one that would merge alone."""
STOPPED = ready.Reason(
    "check",
    "jmerge's batch over {base} at {tip} stopped at #{number}, which did not merge: the next "
    "batch takes it",
    ready.MERGING.code,
)
UNMADE = "batch: not made over {base} at {tip} ({why}), so its members go alone"
"""The line of a batch that could not be built, pushed or opened: each member goes the single
path of today in the same run. It is about no pull request, so jbus reads nothing of it."""
PASSED = "CI's check passed jmerge's batch over {base} at {tip} in {run}, so no guards ran"
TITLE = "jmerge: batch over {base}"
BODY = (
    "jmerge's batch: {base}'s tip with each ready pull request main moved past merged in, for "
    "CI's check of that tree. jmerge force-pushes it and never merges it: each member merges "
    "on its own once the check passed (features/jmerge/docs/jmerge.md#batches)."
)

NONE = "none"
PENDING = "pending"
PROVEN = "proven"
FAILED = "failed"


@dataclass(frozen=True)
class Member:
    number: int
    head: str


@dataclass(frozen=True)
class Batch:
    """A batch as `KEPT` keeps it: the tip it was built over, its tree, the commit pushed to
    `BRANCH`, its members in merge order, and when it was pushed."""

    tip: str
    tree: str
    commit: str
    members: tuple[Member, ...]
    at: str

    def holds(self, one: ready.PullRequest) -> bool:
        return Member(one.number, one.head) in self.members


@dataclass
class Record:
    """`KEPT`: the batch out, if any, and the heads of the members of a batch that failed, which
    go the single path at those heads."""

    path: Path
    batch: Batch | None = None
    failed: dict[str, str] = field(default_factory=dict)

    @classmethod
    def read(cls, state: Path) -> Record:
        path = state / KEPT
        kept = store.read_dict(path)
        failed = kept.get("failed")
        failed = {str(k): str(v) for k, v in failed.items()} if isinstance(failed, dict) else {}
        try:
            made = Batch(
                str(kept["tip"]),
                str(kept["tree"]),
                str(kept["commit"]),
                tuple(Member(int(m["number"]), str(m["head"])) for m in kept["members"]),
                str(kept.get("at") or ""),
            )
        except (KeyError, TypeError, ValueError):
            made = None
        return cls(path, made, failed)

    def write(self) -> None:
        kept: dict = {}
        if self.batch is not None:
            made = self.batch
            kept = {
                "tip": made.tip,
                "tree": made.tree,
                "commit": made.commit,
                "members": [{"number": m.number, "head": m.head} for m in made.members],
                "at": made.at,
            }
        store.write_json(self.path, {**kept, "failed": self.failed})


def state_of(
    batch: Batch | None,
    pull: ready.PullRequest | None,
    tip: str,
    run: str | None,
    now: datetime,
) -> str:
    """Where the batch stands: none out, or one stale (the tip moved, or its pull request is not
    open at its commit); proven, where `run` is the run that left the artifact of the tip's tree
    and its tree; failed, where its check failed, passed with no artifact, or ran past
    `PENDING_MINUTES`; and pending otherwise."""
    if batch is None or tip != batch.tip or pull is None or pull.head != batch.commit:
        return NONE
    if run:
        return PROVEN
    if pull.failed or not pull.waiting or late(batch.at, now):
        return FAILED
    return PENDING


def late(at: str, now: datetime) -> bool:
    try:
        pushed = datetime.fromisoformat(at)
    except ValueError:
        return True
    return now - pushed > timedelta(minutes=PENDING_MINUTES)


def _git(main: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=main, capture_output=True, text=True)


def _said(ran: subprocess.CompletedProcess[str]) -> str:
    lines = (ran.stderr or ran.stdout).strip().splitlines()
    return lines[-1] if lines else f"git exited {ran.returncode}"


@dataclass(frozen=True)
class Built:
    tree: str
    commit: str
    members: tuple[Member, ...]


def build(main: Path, base: str, tip: str, heads: list[Member]) -> Built | str | None:
    """Merge each head over `tip` in turn with `git merge-tree`, as GitHub's squashes will land
    them: each step a commit of one parent over the last, so each head merges from its own fork
    point, as its squash does. A head that conflicts with those before it is left out, and
    `MOST` heads at most go in. The batch is one commit of the last tree, whose one parent is the
    tip. Return it, why it could not be built, or None where no head went in."""
    at, tree, members = tip, "", []
    for one in heads:
        if len(members) == MOST:
            break
        merged = _git(main, "merge-tree", "--write-tree", at, one.head)
        found = merged.stdout.split()[:1]
        if merged.returncode == 1 and found:
            continue
        if merged.returncode or not found:
            return f"#{one.number} could not be merged in ({_said(merged)})"
        step = _git(main, *_IDENTITY, "commit-tree", found[0], "-p", at, "-m", f"#{one.number}")
        if step.returncode:
            return _said(step)
        at, tree = step.stdout.strip(), found[0]
        members.append(one)
    if not members:
        return None
    numbers = " ".join(f"#{one.number}" for one in members)
    message = f"jmerge: batch of {numbers} over {base} at {tip[:SHA]}"
    made = _git(main, *_IDENTITY, "commit-tree", tree, "-p", tip, "-m", message)
    if made.returncode:
        return _said(made)
    return Built(tree, made.stdout.strip(), tuple(members))


def push(main: Path, commit: str) -> str:
    """Force-push `commit` to `BRANCH`, jmerge's own branch, and say why where it failed."""
    ran = _git(main, "push", "-q", "--force", "origin", f"{commit}:refs/heads/{BRANCH}")
    return _said(ran) if ran.returncode else ""


Judged = tuple[ready.PullRequest, str, str, ready.Judged]
"""A member as this run judged it: the pull request, its slug, its note and its judgement."""


@dataclass
class Batching:
    """One run's batching: the record, where the batch it holds stands (`state_of`), the run that
    proved it, the batch pull request GitHub lists, and the members this run judged, in merge
    order, each with its slug and its note."""

    record: Record
    state: str
    run: str
    pull: ready.PullRequest | None
    members: list[Judged] = field(default_factory=list)
    migration: int | None = None
    """The member that adds a migration, which a batch holds one of at most."""

    def migrating(self, one: ready.PullRequest, settings: bus.Migrations | None) -> int:
        """The member ahead that adds a migration, where `one` adds one too, or 0. A second
        migration waits for the first to merge, so the two land in their order and a clash of
        their numbers shows to the second's own check, as when they merge alone."""
        if settings is None or not ready.migrations(one, settings.directory):
            return 0
        if self.migration in (None, one.number):
            self.migration = one.number
            return 0
        return self.migration

    def takes(self, one: ready.PullRequest, default: str, revert: bool) -> bool:
        """Whether `one`, ready but for main moving under its check, is a member: a pull request
        into the default branch that is no revert, whose path is its own, first in line, and that
        was no member of a failed batch at this head."""
        failed = self.record.failed.get(str(one.number)) == one.head
        return not revert and bool(default) and one.base == default and not failed

    @property
    def first(self) -> bool:
        """Whether a batch is out, so that a pull request that would merge alone waits for it:
        its merge would move the tip the batch's check ran over."""
        return self.state in (PENDING, PROVEN)
