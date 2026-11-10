from __future__ import annotations

import argparse
import functools
import itertools
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, NamedTuple

import jsettings
from jbriefs import home as home_rule
from jbriefs import meets, parse, proved
from jmerge import (
    backoff,
    bus,
    checks,
    claims,
    judgement,
    lines,
    lock,
    mainjson,
    proof,
    rangediff,
    ready,
    rejudge,
    remake,
    rows,
    sweep,
    trailers,
    treeguards,
    waits,
)
from jmerge import reverts as reverting
from jmerge import stacked as stacks
from jmerge.asked import why as asked_why
from jmerge.joblog import failed_in
from jsettings import paths, proc, store

LIST = (
    "number,url,title,headRefName,headRefOid,baseRefName,mergeable,statusCheckRollup,"
    "files,changedFiles,isDraft"
)
LIMIT = 100
"""The most open pull requests `gh pr list` is asked for, the cap jbus's own lists use. Left
unsaid, `gh` gives 30."""
DECIDING = (1, 2, 4, 8, 15, 30)
"""The pauses, in seconds, after which an accept asks GitHub again while it has not decided
whether the accepted pull request merges, 60 s in all; past them the accept judges what GitHub
said last. GitHub works that out in the background after an ask, a while after the base moved.
An accept that waited for the run lock behind jbus's merge run, whose merges moved main, read
`ready.UNDECIDED` on its one ask and merged nothing: #1504 did on three runs on 2026-11-09."""
PACKAGE = Path(__file__).parent
PROTECTED = PACKAGE / "protected.txt"
REQUIRED_CHECKS = "required-checks"
JUDGED_AGAIN_AT_MOST = 2
TIMEOUT_SECONDS = 120
FETCH_TRIES = 3
FETCH_PAUSE_SECONDS = 0.5
LOCKED = "cannot lock ref"


def _run(cwd: Path, *command: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    limit = float(os.environ.get("JMERGE_TIMEOUT") or TIMEOUT_SECONDS)
    done = backoff.run(*command, cwd=cwd, timeout=limit, stdin=stdin)
    if isinstance(done, proc.TimedOut):
        said = f"timed out after {limit:g} s: {shlex.join(command)}"
        return subprocess.CompletedProcess(command, 124, "", said)
    return done


def _why(cwd: Path, asked: subprocess.CompletedProcess[str], said: str = "") -> str:
    """Why `gh` gave no answer, asking `gh api rate_limit` in `cwd` for a rate-limit refusal."""
    return asked_why(asked, functools.partial(_run, cwd), said)


def _text(cwd: Path, *command: str) -> str | None:
    ran = subprocess.run(command, cwd=cwd, capture_output=True)
    return None if ran.returncode else ran.stdout.decode(errors="replace")


def _line_after(text: str, line: str) -> str:
    """`line` as it goes at the end of `text`, on a line of its own."""
    return ("" if not text or text.endswith("\n") else "\n") + line + "\n"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _first_word(text: str) -> str:
    return "".join(text.split()[:1])


def patterns(path: Path) -> tuple[str, ...]:
    try:
        return ready.patterns_of(path.read_text(encoding="utf-8"))
    except OSError:
        raise SystemExit(f"jmerge: {path} cannot be read") from None
    except ValueError as pattern:
        raise SystemExit(
            f"jmerge: {path} has a pattern that cannot be read, so nothing is merged: {pattern}"
        ) from None


QUEUE_WAITS = frozenset({ready.ROW_HELD.code, ready.MERGES_AFTER.code})
"""The codes of the queue's waits that GitHub's passing state does not replace
(`Repo.row_first`)."""
QUEUE_OUTRANKS = frozenset(
    one.code for one in (ready.UNDECIDED, ready.CHECK_FAILED, ready.NOT_PASSED, ready.LIVE_RUN)
)
"""The codes of GitHub's waits that a queue wait of `QUEUE_WAITS` comes before."""


class Homes(NamedTuple):
    known: dict[str, str]
    running: dict[str, str]


class Judgement(NamedTuple):
    slug: str
    verb: str
    why: str
    note: str
    judged: ready.Judged | None


class Repo:
    def __init__(
        self,
        main: Path,
        state: Path,
        home: str | None,
        every: bool,
        protected: tuple[str, ...] = (),
        asks: bool = False,
        *,
        user: jsettings.Settings,
    ) -> None:
        self.user = user
        self.main = main
        self.state = state
        self.every = every
        self.protected = protected
        self.accepted: tuple[int, str] | None = None
        self.lifts: list[str] = []
        self.word = ""
        self.fetched = False
        self.through: int | None = None
        self.order: list[int] = []
        self.line: dict[str, int] = {}
        self.rebasing: set[int] = set()
        self.numbers_on: dict[str, set[int]] = {}
        self.required = ready.required_of(_read(state / REQUIRED_CHECKS))
        self.trunk = ""
        self.reds: dict[str, list[dict]] = {}
        self.proofs: dict[tuple[int, str, str, str], rows.Ran] = {}
        self.logs: dict[str, str | None] = {}
        self.open: list[ready.PullRequest] = []
        self.heads: dict[int, bool] = {}
        self.words: dict[tuple[meets.Waiver, str], bool] = {}
        origin = _run(main, "git", "remote", "get-url", "origin")
        self.about = [] if origin.returncode else ["--repo", origin.stdout.strip()]
        self.base_merge = rejudge.BaseMerge(main, state, self.about, asks)
        self.guards = treeguards.Guards(
            main, state, asks, lambda path: self.api(f"repos/{{owner}}/{{repo}}/{path}")
        )
        self.spells = waits.Spells(state, asks)
        self.began: dict[int, datetime] = {}
        self.listed, self.was = home_rule.ids(state)
        self.mine = home or self.listed

    @functools.cached_property
    def queue(self) -> list[dict] | None:
        return rows.read(self.main)

    def stored(self, slug: str) -> str | None:
        return rows.stored(self.main, slug)

    def heard(self, text: str, slug: str) -> frozenset[meets.Waiver]:
        """The brief's `Waived:` lines whose word jbus checked as the user's own, or the bot's,
        of this row, waiving the line each names (`rows.heard`), each asked once a run."""
        for one in meets.waivers(text):
            if (one, slug) not in self.words:
                self.words[(one, slug)] = not rows.heard(self.main, one, slug)
        return frozenset(one for one in meets.waivers(text) if self.words[(one, slug)])

    @functools.cached_property
    def reverts(self) -> dict[str, reverting.Revert]:
        return rows.reverts(self.main)

    @functools.cached_property
    def main_state(self) -> mainjson.Main:
        return rows.main(self.main)

    @functools.cached_property
    def bases(self) -> tuple[str, ...]:
        return rows.bases(self.main)

    @functools.cached_property
    def migrations(self) -> bus.Migrations | None:
        return rows.migrations(self.main)

    def numbers(self, base: str) -> set[int] | None:
        if base not in self.numbers_on and self.migrations:
            where = f"origin/{base}"
            listed = None
            if not _run(self.main, "git", "fetch", "-q", "origin", base).returncode:
                tree = f"{self.migrations.directory}/"
                listed = _run(self.main, "git", "ls-tree", "-z", "--name-only", where, "--", tree)
            if listed is None or listed.returncode:
                return None
            names = (Path(path).name for path in listed.stdout.split("\0") if path)
            self.numbers_on[base] = {int(d) for n in names if (d := ready.migration_number(n))}
        return self.numbers_on.get(base)

    def line_up(self, listed: list[ready.PullRequest], default: str) -> list[ready.PullRequest]:
        """The open pull requests in merge order: each revert jbus opened for a red main
        (`jmerge.reverts`) first, then the rest by number, those that add migrations in the
        queue's declared order among the places they hold. A revert branches from main's tip, so
        by number it would come last, and wait a turn behind every pull request main moved past
        on a red main (#862 holds none of them)."""
        listed = sorted(listed, key=lambda one: one.number)
        first = [one for one in listed if self.is_revert(one)]
        rest = [one for one in listed if not self.is_revert(one)]
        return first + self.migrations_in_order(rest)

    def is_revert(self, one: ready.PullRequest) -> bool:
        """Whether `jmerge.reverts` names the pull request as a revert jbus opened."""
        return any(revert.pull == one.url for revert in self.reverts.values())

    def migrations_in_order(self, listed: list[ready.PullRequest]) -> list[ready.PullRequest]:
        settings = self.migrations
        mine = {
            one.number: one
            for one in listed
            if settings and ready.migrations(one, settings.directory)
        }
        if not settings or not mine:
            return listed
        slugs = {}
        for number, one in mine.items():
            brief = ready.brief_of(one.url, self.state / "tasks")
            slugs[number] = brief.stem if brief else ""
        self.order = rows.merge_order(self.queue, slugs)
        places = iter(mine[number] for number in self.order)
        return [next(places) if one.number in mine else one for one in listed]

    def short_on_migrations(self, one: ready.PullRequest, default: str) -> str:
        settings = self.migrations
        names = ready.migrations(one, settings.directory) if settings else ()
        if not settings or not names:
            return ""
        taken = self.numbers(default)
        if taken is None:
            return f"{default} could not be fetched to see its migration numbers"
        short = ready.short_on_migration(names, taken, default) if settings.numbered else ""
        if short or one.number not in self.order:
            return short
        for ahead in self.order[: self.order.index(one.number)]:
            if ahead in self.rebasing:
                return ready.MIGRATION_REBASING.format(number=ahead)
        if self.through not in (None, one.number):
            return ready.MIGRATION_MERGING.format(number=self.through)
        return ""

    def has(self, one: ready.PullRequest) -> bool:
        """GitHub keeps each pull request's head as `refs/pull/<number>/head`, also one from a
        fork, so `jmerge` fetches a head the main checkout does not have from that ref:
        https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/checking-out-pull-requests-locally
        """
        if one.number not in self.heads:
            commit = f"{one.head}^{{commit}}"
            if _run(self.main, "git", "cat-file", "-e", commit).returncode:
                _run(self.main, "git", "fetch", "-q", "origin", f"refs/pull/{one.number}/head")
            self.heads[one.number] = not _run(self.main, "git", "cat-file", "-e", commit).returncode
        return self.heads[one.number]

    def on_stack(self, one: ready.PullRequest, default: str, stacked: stacks.Stacked | None) -> str:
        """Why a link jbus stacked waits, or nothing. It waits while its line names its base's
        branch, whatever base GitHub gives it now: GitHub bases it on the default branch by
        itself when the base's branch is deleted on its merge, and its head still holds the
        base's commits then. Once jbus wrote the commit that merged its base and the branch it
        merged into, it waits until it is based on that branch and its head holds that commit:
        its crew rebased its own commits onto it.

        CI checks it while it is stacked, beside its base's own check, as it checks every open
        pull request, so its move onto the default branch adds no round in series where the move
        checks the same trees (`reuse`)."""
        if stacked is None:
            return ""
        onto = stacked.branch if stacked.at else default
        if not stacked.at or one.base != onto:
            return ready.STACKED_ON.format(branch=stacked.branch, slug=stacked.slug, default=onto)
        if not self.has(one) or self.outside(stacked.at, one.head):
            return ready.STACKED_UNMOVED.format(
                slug=stacked.slug, sha=stacked.at[:12], default=onto
            )
        return ""

    def outside(self, commit: str, of: str) -> bool:
        """Whether `of` lacks `commit`. A ref that cannot be read lacks it too, which keeps a
        pull request waiting rather than merging what it may carry."""
        return bool(_run(self.main, "git", "merge-base", "--is-ancestor", commit, of).returncode)

    @functools.cached_property
    def ordered(self) -> dict[int, str]:
        """The open pull requests whose rows merge after another row, by number, with their
        slugs. Only these can hold back a pull request that carries them (`rows.short`)."""
        slugs = rows.ordered(self.queue)
        found = {}
        for one in self.open:
            brief = ready.brief_of(one.url, self.state / "tasks")
            if brief is not None and brief.stem in slugs:
                found[one.number] = brief.stem
        return found

    def carries(self, one: ready.PullRequest) -> list[tuple[str, int, bool]]:
        """The open pull requests in `ordered` whose commits a merge of `one` would land: those
        whose head `one`'s head contains and its base does not. Each comes with whether both
        heads could be read, and one that could not is kept, since it may be carried."""
        found = []
        for other in self.open:
            slug = self.ordered.get(other.number)
            if slug is None or other.number == one.number:
                continue
            if not (self.has(other) and self.has(one)):
                found.append((slug, other.number, False))
            elif not self.outside(other.head, one.head) and self.outside(
                other.head, f"origin/{one.base}"
            ):
                found.append((slug, other.number, True))
        return found

    def others(self, text: str) -> bool:
        """Whether the brief is another home's, to a home that asks with `--home`. A home sees
        its own pull requests alone, and merges none: only a run that names no home, jbus's,
        merges, and it judges every home's brief as its own (`every`). The `home-thread` file
        plays no part: a home that asks never merges, whatever the file holds, since jbus is
        the only merger."""
        return claims.home_of(text, self.homes.known) != self.asking

    @functools.cached_property
    def asking(self) -> str:
        """The home that asks with `--home`. The root home owns no row, but until the catch-all's
        home (`uncategorized`) runs, the root asks for it, as `jbriefs.home.thread_of` sends the
        catch-all's messages to the root's thread."""
        catchall_runs = claims.UNCATEGORIZED in self.homes.running.values()
        root = claims.ROOT if catchall_runs else claims.UNCATEGORIZED
        if self.mine == self.listed:
            return root
        if self.mine in self.homes.running:
            return self.homes.running[self.mine]
        root_runs, handed_off = bool(self.listed), self.mine in self.homes.known
        if root_runs or handed_off:
            return claims.NOBODY
        return root

    @functools.cached_property
    def homes(self) -> Homes:
        named, running = {}, {}
        for scope, now, was in home_rule.scopes(self.state):
            named.update(dict.fromkeys(filter(None, [scope.name, now, was]), scope.name))
            if now:
                running[now] = scope.name
        named.update(dict.fromkeys(filter(None, [self.listed, self.was]), claims.UNCATEGORIZED))
        named[claims.ROOT] = claims.UNCATEGORIZED
        if self.listed:
            running[self.listed] = claims.ROOT
        return Homes(known=named, running=running)

    def claimed(self) -> int:
        asked = _run(
            self.main,
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "1000",
            "--json",
            "number,url",
            *self.about,
        )
        try:
            open_pulls = {str(one["url"]): int(one["number"]) for one in json.loads(asked.stdout)}
        except (ValueError, KeyError, TypeError, AttributeError):
            open_pulls = None
        if asked.returncode or open_pulls is None:
            print(f"wait: could not ask GitHub{_why(self.main, asked)}", flush=True)
            return 1
        homes = self.homes.known
        for brief in sorted((self.state / "tasks").glob("*.md")):
            claim = claims.of_brief(brief.stem, _read(brief), open_pulls, homes)
            if claim:
                print(claim.line(), flush=True)
        return 0

    def scoped(self, slug: str) -> int:
        text = _read(self.state / "tasks" / f"{slug}.md")
        if not text:
            print(f"jmerge: no brief {slug} in {self.state / 'tasks'}", file=sys.stderr)
            return 1
        if not parse.where(text):
            print(
                f"jmerge: {slug}'s Where: line names no path, so its width cannot be checked",
                file=sys.stderr,
            )
            return 1
        branch, pull = claims.branch_of(slug, text)
        stacked = stacks.of(text)
        changed = self.changed(branch, stacked.branch if stacked else "")
        if changed is None and pull:
            asked = _run(
                self.main, "gh", "pr", "view", pull, "--json", "files", "--jq", ".files[].path"
            )
            changed = None if asked.returncode else sorted(asked.stdout.splitlines())
        if changed is None:
            print(
                f"jmerge: no branch {branch} here or on origin, and no pull request to ask",
                file=sys.stderr,
            )
            return 1
        for line in claims.scope(text, changed):
            print(line, flush=True)
        return 0

    def changed(self, branch: str, base: str) -> list[str] | None:
        if not base:
            tip = _run(
                self.main, "git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"
            )
            base = tip.stdout.strip().removeprefix("origin/")
        heads = (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}")
        starts = (f"refs/remotes/origin/{base}", f"refs/heads/{base}") if base else ()
        for head, start in itertools.product(heads, starts):
            fork = _run(self.main, "git", "merge-base", start, head)
            if fork.returncode:
                continue
            diff = _run(
                self.main,
                *("git", "-c", "core.quotePath=false", "diff", "--no-renames", "--name-only"),
                fork.stdout.strip(),
                head,
            )
            return None if diff.returncode else sorted(diff.stdout.splitlines())
        return None

    def default(self) -> tuple[str, str]:
        asked = _run(
            self.main,
            "gh",
            "repo",
            "view",
            *self.about[1:],
            "--json",
            "defaultBranchRef",
            "--jq",
            ".defaultBranchRef.name",
        )
        if asked.returncode:
            return "", _why(self.main, asked)
        branch = asked.stdout.strip()
        return branch, "" if branch else _why(self.main, asked, "it named no default branch")

    def based_on(self, branch: str) -> str:
        """When a pull request merges and its branch is deleted, GitHub retargets every open pull
        request whose base was that branch. So deleting the branch would change a stack's
        order:
        https://github.blog/changelog/2020-05-19-pull-request-retargeting/
        """
        asked = _run(
            self.main,
            "gh",
            "pr",
            "list",
            "--base",
            branch,
            "--state",
            "open",
            "--limit",
            str(LIMIT),
            "--json",
            "number",
            *self.about,
        )
        try:
            numbers = sorted(int(one["number"]) for one in json.loads(asked.stdout))
        except (ValueError, KeyError, TypeError):
            numbers = None
        if asked.returncode or numbers is None:
            why = _why(self.main, asked)
            return f"could not ask GitHub whether a pull request is based on it{why}"
        if not numbers:
            return ""
        several = "s" if len(numbers) > 1 else ""
        verb = "are" if several else "is"
        return f"the open pull request{several} {' '.join(map(str, numbers))} {verb} based on it"

    def files_of(self, number: int, jq: str) -> subprocess.CompletedProcess[str]:
        """What `jq` picks from each file of GitHub's files endpoint for pull request `number`,
        paged through: https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files"""
        return backoff.run(
            "gh",
            "api",
            "--paginate",
            f"repos/{{owner}}/{{repo}}/pulls/{number}/files",
            "--jq",
            jq,
            cwd=self.main,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )

    def in_full(self, one: ready.PullRequest) -> ready.PullRequest:
        """`gh pr list` lists at most 100 of a pull request's files, and the files endpoint
        pages through up to 3000:
        https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files
        Where it cannot be read, `one` keeps the files it has, and `ready.needs_the_user`
        holds it for the user with the counts."""
        if len(one.files) >= one.changed:
            return one
        asked = self.files_of(one.number, ".[] | {filename, status}")
        try:
            every = [] if asked.returncode else list(map(json.loads, asked.stdout.splitlines()))
            return ready.listed_in_full(one, every)
        except (ValueError, KeyError, TypeError, AttributeError):
            return one

    def left(self, one: ready.PullRequest) -> tuple[str, ...] | None:
        """`gh pr list` lists a rename under its new path alone, and only the files endpoint
        gives the file's old path, as `previous_filename`:
        https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files
        """
        if not one.renamed:
            return ()
        asked = self.files_of(one.number, ".[] | .previous_filename // empty")
        return None if asked.returncode else tuple(asked.stdout.splitlines())

    def moved(self, default: str, since: datetime) -> tuple[str, tuple[str, ...]] | None:
        if _run(self.main, "git", "fetch", "-q", "origin").returncode:
            return None
        tip = _run(self.main, "git", "rev-parse", "-q", "--verify", f"origin/{default}^{{commit}}")
        log = _run(
            self.main,
            "git",
            "-c",
            "core.quotePath=false",
            "log",
            "--first-parent",
            f"--since={since.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ}",
            "--name-status",
            "-M",
            "--format=",
            f"origin/{default}",
            "--",
        )
        if tip.returncode or log.returncode:
            return None
        paths = [path for line in log.stdout.splitlines() for path in line.split("\t")[1:]]
        return tip.stdout.strip(), tuple(dict.fromkeys(paths))

    def range_diff(
        self, reviewed: str, head: str, default: str, stacked: stacks.Stacked | None = None
    ) -> rangediff.Verdict:
        if not self.fetched:
            self.fetched = True
            _run(self.main, "git", "fetch", "-q", "origin")
        since = self.own_fork(default, reviewed, head, stacked) if stacked else None
        return rangediff.verdict(self.main, reviewed, head, default, since or "")

    def prose(self, one: ready.PullRequest) -> Callable[[str], bool]:
        """Whether a `.py` file of the pull request changes in its docstrings and comments alone
        (`proved.prose_in`), from the merge-base of its base on origin to its head, which a fetch
        of origin brings once a pass."""

        @functools.cache
        def asked() -> Callable[[str], bool]:
            if not self.fetched:
                self.fetched = True
                _run(self.main, "git", "fetch", "-q", "origin")
            return proved.prose_in(str(self.main), f"origin/{one.base}", one.head)

        return lambda path: asked()(path)

    def as_fixed(self, slug: str, text: str, one: ready.PullRequest) -> str:
        """The brief's text as `jmerge` judges it: with the `Fixed:` line a crew did not write
        (`ready.unwritten_fixed`), where git gives the commit it names, the newest of the head
        and the heads kept before a rebase that holds the fix (`kept_fix`). The line is read and
        never written to the brief."""
        unwritten = ready.unwritten_fixed(text, one.head)
        if unwritten is None:
            return text
        commit = (
            "" if unwritten.reason else self.kept_fix(slug, one.base, unwritten.reviewed, one.head)
        )
        if not (unwritten.reason or commit):
            return text
        word = f"none needed, {unwritten.reason}" if unwritten.reason else commit
        return text + _line_after(text, f"Fixed: {word}")

    def kept_fix(self, slug: str, base: str, reviewed: str, *first: str) -> str:
        """The newest of `first`, then of the heads the crew kept under
        `refs/jstack/pre-rebase/<slug>/` before each rebase, that holds a fix pushed after
        `reviewed`: one with `reviewed` in its history that leaves `base` where `reviewed` does,
        so no rebase moved it since. Empty where git names none, or where that head is
        `reviewed` itself, so nothing was pushed before the rebase."""
        if not self.fetched:
            self.fetched = True
            _run(self.main, "git", "fetch", "-q", "origin")
        fork = _run(self.main, "git", "merge-base", f"origin/{base}", reviewed)
        refs = ("git", "for-each-ref", "--sort=-committerdate", "--format=%(objectname)")
        kept = _run(self.main, *refs, f"refs/jstack/pre-rebase/{slug}/")
        if fork.returncode or kept.returncode:
            return ""
        for commit in (*first, *kept.stdout.split()):
            holds = _run(self.main, "git", "merge-base", "--is-ancestor", reviewed, commit)
            if holds.returncode:
                continue
            moved = _run(self.main, "git", "merge-base", f"origin/{base}", commit)
            if moved.returncode or moved.stdout != fork.stdout:
                continue
            return "" if commit == reviewed else commit
        return ""

    def before_rebase(self, slug: str, base: str, reviewed: str, fixed: str) -> str:
        """The commit `jmerge` compares from for `fixed`, a `Fixed:` commit after `reviewed`.
        Where a rebase made it, so it leaves `base` elsewhere than `reviewed` does, that is the
        head the crew kept before the rebase (`kept_fix`), else `reviewed`, as for a `Fixed:`
        line read from git. It is `fixed` itself where no rebase came between, and where git
        cannot name the fork of either commit."""
        forks = [
            _run(self.main, "git", "merge-base", f"origin/{base}", commit)
            for commit in (reviewed, fixed)
        ]
        if any(fork.returncode for fork in forks) or forks[0].stdout == forks[1].stdout:
            return fixed
        return self.kept_fix(slug, base, reviewed) or reviewed

    def rebase_since_review(self, base: str, covered: str, head: str) -> ready.Rebase | None:
        forks = []
        for commit in (covered, head):
            fork = _run(self.main, "git", "merge-base", f"origin/{base}", commit)
            if fork.returncode:
                return None
            forks.append(fork.stdout.strip())
        if forks[0] == forks[1]:
            return None
        names = ("git", "-c", "core.quotePath=false", "diff", "--no-renames", "--name-only")
        patches = [
            _text(self.main, *names, fork, commit)
            for fork, commit in zip(forks, (covered, head), strict=True)
        ]
        texts = [patch for patch in patches if patch is not None]
        if len(texts) != len(patches):
            return None
        files = sorted({file for patch in texts for file in patch.splitlines()})
        return ready.Rebase(tuple(files), covered, head)

    def left_main_elsewhere(self, base: str, under: str, head: str) -> bool:
        for _ in range(2):
            forks = [
                _run(self.main, "git", "merge-base", f"origin/{base}", commit)
                for commit in (under, head)
            ]
            if not any(fork.returncode for fork in forks):
                return forks[0].stdout != forks[1].stdout
            if self.fetched:
                break
            self.fetched = True
            _run(self.main, "git", "fetch", "-q", "origin")
        return True

    def dropped(
        self, base: str, rebase: ready.Rebase, head: str
    ) -> tuple[ready.Drop, ...] | ready.NoPatch:
        forks = []
        for commit in (rebase.before, rebase.head, head):
            fork = _run(self.main, "git", "merge-base", f"origin/{base}", commit)
            if fork.returncode:
                return ready.NoPatch(commit)
            forks.append(fork.stdout.strip())
        old, new, _ = forks
        if old == new:
            return ()
        diff = ("git", "-c", "core.quotePath=false", "diff", "--no-ext-diff", "--no-renames", "-U0")
        patches = [
            _text(self.main, *diff, "--name-only", fork, commit)
            for fork, commit in ((old, rebase.before), (new, rebase.head))
        ]
        if None in patches:
            return ready.NoPatch(rebase.before)
        lost = []
        for file in sorted({file for patch in patches if patch for file in patch.splitlines()}):
            main = _text(self.main, *diff, old, new, "--", file)
            own = _text(self.main, *diff, old, rebase.before, "--", file)
            if main is None or own is None:
                return ready.NoPatch(rebase.before)
            counts = [
                ready.dropped(main, own, _text(self.main, "git", "show", f"{at}:{file}") or "")
                for at in dict.fromkeys((rebase.head, head))
            ]
            theirs, ours = (min(count) for count in zip(*counts, strict=True))
            if theirs or ours:
                lost.append(ready.Drop(file, theirs, ours))
        return tuple(lost)

    def over_main(
        self, one: ready.PullRequest, left: tuple[str, ...] | None
    ) -> tuple[str, ready.Judged]:
        """Why the head waits over today's base, or nothing, and what it was judged over: the
        base's tip, and whether its files overlap the base's changes. Where the base changed no
        path since the check started, the check ran over today's base. Where it did, a head that
        conflicts with the tip with `git merge-tree` waits for a rebase. A clean one merges on
        its existing check, with no update of its branch and no rerun, and `Repo.merge` runs the
        fast guards on its tree merged over the tip first (`treeguards`), where the repo names
        them. That holds for one whose files, and the old paths of its renames (`left`), share
        none of the base's changed paths (Josh's rule of 2026-11-02, #847, back on 2026-11-04
        with GitHub's strict rule off), where the guards catch a clash two pull requests make
        with no shared file, as #923 and #935 made with two new `v007_` files. A repo with no
        guards merges such a one on its existing check alike (Josh, 2026-11-05: "we don't need
        every pr to be up to date"). It holds too for one that overlaps, in a repo that names
        guards (Josh's vision of 2026-11-06, item F: "merge as soon as green, not stopping to
        rebase if not needed or to catch up with main"), with main's own run and jbus's reverts
        behind it. Such a one whose guards failed or were stopped at its head over the tip, one
        in a repo with no guards, and a revert jbus opened, whose path is its own, have GitHub
        merge the base into the branch (`in_turn`), and the check at the new head decides."""
        if one.started is None:
            return "", ready.Judged()
        moved = self.moved(one.base, one.started)
        if moved is None:
            why = f"{one.base} could not be fetched to see what changed after its check"
            return why, ready.Judged()
        tip, paths = moved
        if not paths:
            return "", ready.Judged(tip)
        merged = _run(self.main, "git", "merge-tree", "--write-tree", tip, one.head)
        if merged.returncode == 1:
            return ready.FRESH_CONFLICT, ready.Judged()
        if merged.returncode:
            return ready.UNMERGED.format(why=lines.said(merged)), ready.Judged()
        if left is not None and not {*one.files, *left} & set(paths):
            return "", ready.Judged(tip)
        if not self.guards.command or self.is_revert(one) or self.guards.kept(one, tip):
            return self.base_moved(one, tip), ready.Judged()
        return "", ready.Judged(tip, overlaps=True)

    def base_moved(self, one: ready.PullRequest, tip: str) -> str:
        """Why a green pull request waits for GitHub's merge of its base at `tip` into its
        branch, in its turn (`in_turn`)."""
        return self.in_turn(one, tip, ready.BASE_MOVED_ASKED, ready.BASE_MOVED_DUE)

    def in_turn(self, one: ready.PullRequest, tip: str, asked: str, due: str) -> str:
        """Why the pull request waits for GitHub's merge of the base at `tip` into its branch:
        `asked` or `due` once it is its turn, and in line behind the pull request at the head of
        its base's line (`self.line`) until then. Green, red and unrun alike take their place in
        one line for each base, in merge order, so each merge costs one CI round: #1009's probe,
        with one green pull request in line and two red ones, asked GitHub to update all three
        each time main moved. A revert jbus opened (`is_revert`) takes its base's line from a
        pull request that is not one, which then waits behind it with its record kept
        (`rejudge.BaseMerge.release`): on a red main the revert is the merge that turns it green."""
        ahead = self.line.get(one.base, one.number)
        holder = next((other for other in self.open if other.number == ahead), None)
        if holder and holder is not one and self.is_revert(one) and not self.is_revert(holder):
            self.base_merge.release(holder.number)
            del self.line[one.base]
            ahead = one.number
        if ahead != one.number:
            return ready.IN_LINE.format(number=ahead, base=one.base)
        said = self.base_merge.of(one, tip, asked, due, line=True)
        self.line |= self.base_merge.holders([one])
        return said

    def again(self, one: ready.PullRequest, red: str) -> str:
        """Why a pull request whose required checks failed waits, judged over today's base. Its
        check is its own fault, `red`, unless the base moved since the check started. Then GitHub
        merges the base into it, and its check at the updated head decides, unless the last two
        runs of a check that failed, whichever required check it is, failed a same test of its
        own (`rejudge.Repeated`): a merge would fail it again. Nor is a red main merged in while
        jbus's `main.json` names it red: its head would be red again, a CI round spent for nothing,
        so the check waits as its own until main is green. The merge waits its turn in the line
        green pull requests take (`in_turn`)."""
        moved = None if one.started is None else self.moved(one.base, one.started)
        if (
            moved is None
            or not moved[1]
            or (one.base == self.trunk and bool(self.main_state.red))
            or any(self.base_merge.repeats(one, moved[0], check) for check in one.failed)
        ):
            return red
        return self.in_turn(one, moved[0], ready.BASE_MERGE_ASKED, ready.BASE_MERGE_DUE)

    def proven_at(self, one: ready.PullRequest, text: str) -> str:
        """The head whose review proved the safety fact that holds at `one`'s head: that head's
        own, else the last review's where the range-diff from its head to this one is clean, as
        over a rebase, a push for a failed check or a merge of the base. A fix for the findings
        changes the content, so no proof carries over it. The rule is the same in every review
        mode."""
        last = ready.said_of(text).reviewed
        if proof.fact(text, one.head) or not last or proof.fact(text, last) is None:
            return one.head
        verdict = self.range_diff(last, one.head, one.base, stacks.of(text))
        return last if verdict.clean else one.head

    def waits(self, one: ready.PullRequest, default: str) -> Judgement:
        found = self.judge(one, default)
        if self.line.get(one.base) == one.number and in_line(one, found):
            found = self.unstuck(one, found)
        elif self.base_merge.stuck(one).get("gave_up") and one.queued:
            found = found._replace(why=self.gave_up(one))
        if self.line.get(one.base) == one.number and not in_line(one, found):
            self.base_merge.release(one.number)
            del self.line[one.base]
        rebasing = found.verb == "wait" and not one.draft and ready.being_rebased(found.why)
        if one.number in self.order and rebasing:
            self.rebasing.add(one.number)
        else:
            self.rebasing.discard(one.number)
        return found

    def unstuck(self, one: ready.PullRequest, found: Judgement) -> Judgement:
        """The judgement of the pull request at the head of the line, once a required run GitHub
        queued there and started none of is restarted, or the line is given up for it. A run
        queued for `ready.QUEUED_MINUTES` gets one restart (`rejudge.BaseMerge.restart`), spent
        only once its close and reopen took: one that failed is tried again on each run for
        `ready.RESTART_MINUTES`, and then the line goes to the next. Once it took, GitHub has
        `ready.RESTART_MINUTES` to list a newer run. Where it then lists none, or the newer one
        is queued for `ready.QUEUED_MINUTES` too, the pull request gives the head of the line to
        the next, as on a failed check, and waits saying so while its run stays queued. A run
        that started is never restarted, however long it runs. Each step reads what GitHub
        lists and what the record of the head keeps, so a run of `jmerge` again finds nothing
        left to do."""
        if not one.queued or not self.base_merge.run:
            return found
        check, since = min(one.queued, key=lambda queued: queued[1])
        now = datetime.now(UTC)
        minutes = int((now - since).total_seconds() // 60)
        stuck = self.base_merge.stuck(one)
        restarted = self.restarted_by(one, since)
        if minutes < ready.QUEUED_MINUTES and not restarted:
            return found
        values = {"check": check, "head": one.head[:12], "minutes": minutes}
        if restarted is None and not rejudge.late(stuck.get("asked") or now.isoformat(), now):
            why = self.base_merge.restart(one, check, since)
            if self.base_merge.stuck(one).get("reopen"):
                return found._replace(why=ready.QUEUED_UNOPENED.format(**values, why=why))
            if why:
                return found._replace(why=ready.QUEUED_UNCLOSED.format(**values, why=why))
            return found._replace(why=ready.QUEUED_RESTARTED.format(**values))
        if restarted and not rejudge.late(stuck.get("took"), now):
            return found._replace(why=ready.QUEUED_RESTARTED.format(**values))
        self.base_merge.keep_stuck(one, gave_up=True)
        return found._replace(why=self.gave_up(one))

    def restarted_by(self, one: ready.PullRequest, since: datetime) -> bool | None:
        """None while no restart of the head took, True where the run queued `since` is the one
        GitHub queued before the restart, or one from before it, and False for a newer run."""
        stuck = self.base_merge.stuck(one)
        kept = stuck.get("since")
        if not isinstance(stuck.get("took"), str) or not isinstance(kept, str):
            return None
        return since <= datetime.fromisoformat(kept)

    def gave_up(self, one: ready.PullRequest) -> ready.Reason:
        """Why the pull request gave up the line for its queued run: its restart took and the
        run is queued still, or its restart never took."""
        check = min(one.queued, key=lambda queued: queued[1])[0]
        stuck = self.base_merge.stuck(one)
        if stuck.get("took"):
            return ready.QUEUED_GAVE_UP.format(
                check=check, head=one.head[:12], minutes=ready.QUEUED_MINUTES
            )
        return ready.QUEUED_UNRESTARTED.format(
            check=check,
            head=one.head[:12],
            minutes=ready.RESTART_MINUTES,
            why=stuck.get("why") or "not known",
        )

    def unopened(self, listed: list[ready.PullRequest]) -> list[str]:
        """A `wait` line for each pull request a restart left closed, which GitHub lists among
        the open ones no more: its reopen is owed, and `jmerge` asks it again on the next run,
        or it asks it no more (`rejudge.BaseMerge.reopen`). The second is a wait no runner is at
        work on, which jbus raises to the home (`jbus.clock.held`)."""
        said = []
        for number, stuck in self.base_merge.unopened({str(one.number) for one in listed}):
            values = {
                "check": stuck.get("check") or "check",
                "head": str(stuck.get("head") or "")[:12],
                "why": stuck.get("why") or "not known",
            }
            if stuck.get("unopened"):
                why = ready.QUEUED_UNREOPENED.format(**values, minutes=ready.RESTART_MINUTES)
            else:
                at = datetime.fromisoformat(str(stuck["since"]))
                minutes = int((datetime.now(UTC) - at).total_seconds() // 60)
                why = ready.QUEUED_UNOPENED.format(**values, minutes=minutes)
            said.append(lines.waits("wait", int(number), str(stuck.get("url") or ""), why))
        return said

    def judge(self, one: ready.PullRequest, default: str) -> Judgement:
        """The judgement of the pull request. Where all that holds it is a required check that
        failed, or one with no run at its head, it is judged again as if that check had passed,
        and a judgement that gets as far as today's base judges it over that base: `again` for a
        check that failed, and for a check with no run GitHub's merge of a base that moved since
        its check started, which brings the head the workflows the base has. One that falls short
        of anything else says that, and not the check: #529 waited ten hours on "macos has not
        passed" while it was short of a scoped review that nobody was asked for."""
        found = self.judged(one, default)
        held = ready.red_only(one) or ready.unrun_only(one)
        if not held or found.why != ready.short_on_github(one):
            return found
        return self.judged(replace(one, waiting=(), unrun=()), default, found.why)

    def judged(self, one: ready.PullRequest, default: str, red: str = "") -> Judgement:
        brief = ready.brief_of(one.url, self.state / "tasks")
        if brief is None and not one.draft and self.accepted == (one.number, one.head):
            return self.unbriefed(one, default, red)
        if brief is None:
            why = ready.HAND_DRAFT if one.draft else ready.NO_BRIEF
            return Judgement("", "wait", why, "", None)
        text = self.as_fixed(brief.stem, _read(brief), one)
        if self.others(text) and not self.every:
            return Judgement(brief.stem, "wait", ready.OTHER_HOME, "", None)
        self.trunk = default
        self.lifts = []
        lifted = self.lifted(one)
        stacked = stacks.of(text)
        short = self.lift(ready.held(one, default, stacked, self.bases), lifted)
        short = short or self.on_stack(one, default, stacked)
        reverted = not short and self.reverted(brief.stem, one)
        if not short and not reverted:
            heard = self.heard(text, brief.stem)

            def carries(at: str) -> bool:
                return self.range_diff(at, one.head, one.base, stacked).clean

            prose = self.prose(one)
            proven = ready.proves(text, one, carries, prose)
            short = self.lift(ready.short_of(text, one.head, heard, proven), lifted)
            short = short or self.lift(ready.short_on_proved(text, one, carries, prose), lifted)
            short = short or ready.short_on_checked(text, one.head, carries)
        rebase: ready.Rebase | None = None
        unreviewed = ready.said_of(text).mode == ready.NONE
        covered = None if reverted or unreviewed else ready.to_range_diff(text, one.head)
        under = ready.under_fix(text, one.head)
        lost: tuple[ready.Drop, ...] = ()
        if not short and covered:
            if _run(self.main, "git", "fetch", "-q", "origin").returncode:
                short = f"{one.base} could not be fetched to see what its rebase kept"
            else:
                if under:
                    covered = self.before_rebase(brief.stem, one.base, under, covered)
                rebase = self.rebase_since_review(one.base, covered, one.head)
            found = () if short or rebase is None else self.dropped(one.base, rebase, one.head)
            if isinstance(found, ready.NoPatch):
                short = ready.cannot_check(found.commit)
            else:
                lost = found
        if rebase is None and covered is None:
            lost = ready.answered(text, one.head)
        short = short or ready.short_on_github(one)
        short = self.row_first(brief.stem, short)
        note = ""
        silent = ready.unexplained(lost, text, one.head)
        if (
            under
            and covered is None
            and not short
            and self.left_main_elsewhere(one.base, under, one.head)
        ):
            covered = self.kept_fix(brief.stem, one.base, under) or under
        reviewed = None if short or silent else covered
        verdict: rangediff.Verdict | None = None
        if reviewed == "":
            short = ready.NO_HEAD
        elif reviewed:
            verdict = self.range_diff(reviewed, one.head, one.base, stacked)
            short = ready.short_on_content(verdict)
            note = ready.rebase_note(verdict)
        if short:
            return Judgement(brief.stem, judgement.verb(short), short, note, None)
        short = (
            rows.short(self.queue, brief.stem, brief=self.stored(brief.stem))
            or rows.short(self.queue, brief.stem, self.carries(one), brief=self.stored(brief.stem))
            or self.red(one, default, brief.stem)
            or self.short_on_migrations(one, one.base)
        )
        if short:
            return Judgement(brief.stem, judgement.verb(short), short, note, None)
        left = self.left(one)
        command = verdict.command if verdict else "nothing"
        kind, why = ready.drops(lost, text, one.head, user=self.user, command=command)
        if not kind:
            kind, why = ready.declines(text, user=self.user)
        if kind == judgement.HOLD and not self.lift(why, lifted):
            kind = ""
        if kind:
            return Judgement(brief.stem, kind, why, note, None)
        hold = self.lift(ready.needs_the_user(one, self.protected, left, user=self.user), lifted)
        if hold:
            return Judgement(brief.stem, "hold", hold, note, None)
        if red and re.fullmatch(ready.NO_RUN.pattern, red):
            moved = None if one.started is None else self.moved(one.base, one.started)
            if moved is not None and moved[1]:
                red = self.in_turn(one, moved[0], ready.BASE_MOVED_ASKED, ready.BASE_MOVED_DUE)
            return Judgement(brief.stem, "wait", red, note, None)
        if red:
            return Judgement(brief.stem, "wait", self.again(one, red), note, None)
        if one.draft:
            return Judgement(brief.stem, "wait", ready.HAND_DRAFT, note, None)
        short, judged = self.over_main(one, left)
        short = short or self.guards.kept(one, judged.tip)
        if short:
            return Judgement(brief.stem, "wait", short, note, None)
        note = f"{note}, {ready.KEPT}" if note else ""
        if (self.state / "merge-off").exists():
            return Judgement(
                brief.stem, judgement.verb(ready.MERGE_OFF), ready.MERGE_OFF, note, None
            )
        if one.number in self.order:
            self.through = one.number
        return Judgement(brief.stem, "", "", note, judged)

    def row_first(self, slug: str, short: str) -> str:
        """`short`, unless it is one of GitHub's waits that come and go (`QUEUE_OUTRANKS`) and the
        queue row of `slug` is held or merges after a row not merged yet. That wait stands as long
        as the row does, while GitHub's state moves under it: its mergeability is undecided each
        time main moves, and a check fails or runs again. Said in the row's place, it drew a `wait`
        line on each change, and #1335 went from `row-held` to `undecided` and back all night. A
        check with no run at the head, and a conflict where `ready.short_on_github` names one (no
        required check waits), are work for the crew, and keep their place."""
        if not isinstance(short, ready.Reason) or short.code not in QUEUE_OUTRANKS:
            return short
        queued = rows.short(self.queue, slug, brief=self.stored(slug))
        return queued if ready.code_of(queued) in QUEUE_WAITS else short

    def unbriefed(self, one: ready.PullRequest, default: str, red: str) -> Judgement:
        """The judgement of a pull request no brief names, which the user's own message accepts
        (`accept`), by every rule that needs no brief: its base is one jmerge merges into, its
        required checks passed at its head, a protected path is a hold the accept lifts, and a
        door the user's word opens, it merges over today's base in its turn, as `judged` has it,
        and `merge-off` holds it. With no brief, no review, Result or queue row is there to judge,
        and its slug is empty."""
        self.trunk = default
        self.lifts = []
        short = ready.held(one, default, None, self.bases) or ready.short_on_github(one)
        if short:
            return Judgement("", judgement.verb(short), short, "", None)
        left = self.left(one)
        needs = ready.needs_the_user(one, self.protected, left, user=self.user)
        if short := self.lift(needs, self.lifted(one)) or red:
            return Judgement("", judgement.verb(short), short, "", None)
        short, judged = self.over_main(one, left)
        short = (
            short or self.guards.kept(one, judged.tip) or self.short_on_migrations(one, one.base)
        )
        if short:
            return Judgement("", "wait", short, "", None)
        if (self.state / "merge-off").exists():
            return Judgement("", judgement.verb(ready.MERGE_OFF), ready.MERGE_OFF, "", None)
        return Judgement("", "", "", "", judged)

    def red(self, one: ready.PullRequest, default: str, slug: str) -> str:
        """The hold on a pull request into main for its own browser run (`browser_red`). A red
        main holds no pull request: a pull request red at its own head is held by its own checks,
        and jbus reverts the one clear culprit of a red main (`jmerge.reverts`). A pull request
        into another merge base has no browser hold either, since main's browser runs say nothing
        of that branch."""
        if one.base != default:
            return ""
        return browser_red(self, one, default, slug)

    def reverted(self, slug: str, one: ready.PullRequest) -> bool:
        """Whether the pull request is a revert jbus opened for a red main (`jmerge.reverts`), at
        the head jbus opened it at or one whose range-diff from that head is clean, as after a
        merge of main into it. Such a pull request needs no review."""
        revert = reverting.of_branch(self.reverts, slug)
        if revert is None or one.url != revert.pull:
            return False
        return one.head == revert.head or self.range_diff(revert.head, one.head, one.base).clean

    def proved_browser(self, one: ready.PullRequest, red: str) -> rows.Ran:
        """What the pull request's own browser run proved of main's red browser run at `red`:
        what it ran and the tests it failed, which it names in full, at a head that has `red`."""
        key = (one.number, one.head, red, ready.BROWSER)
        if key not in self.proofs:
            self.proofs[key] = rows.UNPROVED
            rollup = self.reds.get(ROLLUP.format(number=one.number), [])
            run = ready.latest(rollup, ready.BROWSER)
            job = jobs(run, ("FAILURE",))
            log = self.job_log(job[0]) if len(job) == 1 else None
            found = rows.ran_in(log or "", rows.BROWSER)
            if found is not None and self.has(one) and not self.outside(red, one.head):
                failed = failed_in(log or "")
                if failed.count == len(failed.tests):
                    self.proofs[key] = rows.Ran(
                        red, found.every, found.paths, frozenset(failed.tests)
                    )
        return self.proofs[key]

    def run_failed(self, run: object) -> tuple[str, ...]:
        """The tests a run failed, as its failed jobs' logs name them (`mainjson.failures`), or
        none where GitHub did not list its jobs or give a log."""
        said = self.api(f"repos/{{owner}}/{{repo}}/actions/runs/{run}/jobs?per_page=100")
        listed = said.get("jobs") if isinstance(said, dict) else None
        named = []
        for job in listed if isinstance(listed, list) else []:
            if not isinstance(job, dict) or job.get("conclusion") in checks.NOT_RED:
                continue
            log = self.job_log(str(job.get("id")))
            if log is None:
                return ()
            found = failed_in(log)
            named.append((str(job.get("name") or ""), found.tests, found.count))
        return tuple(mainjson.failures(named))

    def api(self, path: str) -> object:
        """GitHub's answer to `gh api <path>`, or None."""
        asked = backoff.run(
            "gh",
            "api",
            path,
            cwd=self.main,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )
        try:
            return None if asked.returncode else json.loads(asked.stdout)
        except ValueError:
            return None

    def job_log(self, job: str) -> str | None:
        """A job's log, as GitHub gives it, once a run, or None. gh gives a log that holds escape
        sequences only when asked to, as `jbus.watch.job_log` does."""
        if job not in self.logs:
            asked = backoff.run(
                "gh",
                "api",
                f"repos/{{owner}}/{{repo}}/actions/jobs/{job}/logs",
                "--allow-escape-sequences",
                cwd=self.main,
                env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
            )
            self.logs[job] = None if asked.returncode else asked.stdout
        return self.logs[job]

    def own_fork(
        self, base: str, before: str, head: str, stacked: stacks.Stacked | None
    ) -> str | None:
        """Where the link's own commits start in its head `before` a rebase onto `head`: its
        fork from `base`, or None when git cannot say. A link jbus moved once its base merged is
        the exception: its old head forks from the base's branch before the base's commits,
        which a squash merge leaves out of that branch's history, so its own commits are as many
        of its last ones as `head` has above its fork."""
        if stacked is None or not stacked.at:
            fork = _run(self.main, "git", "merge-base", f"origin/{base}", before)
            return None if fork.returncode else fork.stdout.strip()
        fork = _run(self.main, "git", "merge-base", f"origin/{base}", head)
        if fork.returncode:
            return None
        span = f"{fork.stdout.strip()}..{head}"
        count = _run(self.main, "git", "rev-list", "--count", "--first-parent", span)
        if count.returncode:
            return None
        own = _run(self.main, "git", "rev-parse", "--verify", f"{before}~{count.stdout.strip()}")
        return None if own.returncode else own.stdout.strip()

    def holds(self) -> dict[str, str]:
        return store.read_dict(self.state / "holds.json")

    def lined_up(self, listed: list[ready.PullRequest]) -> None:
        """Find the open pull request at the head of each base's line (`over_main`)."""
        self.line = self.base_merge.holders(listed)

    def open_only(self, listed: list[ready.PullRequest]) -> None:
        """Keep only the holds of pull requests still open: a merge or a close drops one, and the
        pull request's record in `base-merges.json` too."""
        heads = {str(one.number): one.head for one in listed}
        self.base_merge.reopen(heads)
        self.base_merge.open_only(heads)
        self.guards.open_only(heads)
        self.spells.open_only({one.number for one in listed})
        self.holds_are({number: head for number, head in self.holds().items() if number in heads})

    def lifted(self, one: ready.PullRequest) -> frozenset[str]:
        """The codes of the holds the user's accept lifts for `one` at its head: every code in
        the run of the accept, and none otherwise."""
        return ready.codes() if self.accepted == (one.number, one.head) else frozenset()

    def lift(self, why: str, lifted: frozenset[str]) -> str:
        """`why`, or nothing where `--accept` lifts it (`judgement.accepted`) and the accept
        lifted its code."""
        if judgement.accepted(why) and ready.code_of(why) in lifted:
            self.lifts.append(why)
            return ""
        return why

    def timed(self, line: str) -> None:
        """Keep the wait of the open pull request a line is about (`waits.Spells`): a `wait` or
        `hold` is a sighting of it held by the line's code, and a `merged` line ends its wait at
        the second its merge began."""
        said = lines.one(line)
        one = next((one for one in self.open if said and one.number == said.number), None)
        if said is None or one is None:
            return
        now = datetime.now(UTC)
        began = self.began.pop(one.number, now)
        if said.word == "merged":
            self.spells.merged(one, began)
        elif said.word in ("wait", "hold"):
            coded = lines.one(lines.logged(line))
            self.spells.saw(one, (coded.code if coded else "") or ready.UNKNOWN, now)

    def hold(self, one: ready.PullRequest) -> None:
        self.holds_are({**self.holds(), str(one.number): one.head})

    def holds_are(self, holds: dict[str, str]) -> None:
        if holds != self.holds() and self.state.is_dir():
            store.write_json(self.state / "holds.json", holds)

    def accept(
        self,
        one: ready.PullRequest,
        default: str,
        by: str | None,
        when: str | None,
        say: Callable[[str], None],
        check: bool,
        acting: bus.Acting | None = None,
        message: str | None = None,
    ) -> int:
        """Lift the hold of `one` and merge it, the user's hand-merge. A wait the accept lifts
        (`judgement.WAIVED`) is lifted as a hold is, at the head GitHub gives now, since no run
        keeps a record of it; one it does not is refused with why (`judgement.UNLIFTED`). One
        that waits only on its turn in line takes the head of the line instead (`take_line`). A
        draft is not merged: the accept says what it waits on (`HAND_DRAFT`) and marks nothing
        ready. The `merged` line names the word it was accepted on. A pull request no brief names
        merges on the user's own message alone (`--message`), judged by every rule that needs no
        brief (`unbriefed`), and its `merged` line names it `#<number>` for its slug, as jbus
        names a line with no slug. With `acting`,
        the accept is an act of the bus's (`jmerge.bus`): a door the party may not open parks a
        gate and merges nothing. `check` says what it would do, and is no act."""
        about = f"{one.number} {one.url}"
        first = self.waits(one, default)
        if first.verb == "wait" and ready.code_of(first.why) == ready.IN_LINE.code:
            return self.take_line(one, default, first.slug, (by, when, message), say, check, acting)
        waived = first.verb == "wait" and judgement.accepted(first.why)
        unbriefed = first.verb == "wait" and ready.code_of(first.why) == ready.NO_BRIEF.code
        heard = unbriefed and (bool(acting and message) or (check and not by))
        if first.verb != "hold" and not waived and not heard:
            state = f"it waits: {first.why}" if first.verb else "jmerge merges it by itself"
            unlifted = judgement.UNLIFTED.get(ready.code_of(first.why)) if first.verb else None
            say(f"refused {about}: it is not held, {state}" + (f": {unlifted}" if unlifted else ""))
            return 1
        was = self.holds().get(str(one.number), "")
        if not waived and not heard and was != one.head:
            held = f"was at {was[:12]}" if was else "is not on record, run jmerge first"
            say(f"refused {about}: its hold {held}, and its head is {one.head[:12]}")
            return 1
        text = "" if heard else _read(self.state / "tasks" / f"{first.slug}.md")
        at = self.proven_at(one, text)
        proven = None if heard else proof.fact(text, at)
        unreviewed = ready.said_of(text).mode == ready.NONE
        if proven is None and not unreviewed and not heard:
            say(f"refused {about}: {proof.short(text, at)}")
            return 1
        safe = "no review proof, its brief says Review: none"
        if heard:
            safe = (
                "no review proof, no brief names it, so it merges on the user's own message alone"
            )
        if proven:
            safe = f"safe because {proven[0]} (proven at {at[:12]})"
        self.accepted = (one.number, one.head)
        found = self.waits(one, default)
        if found.judged is None:
            say(lines.waits(found.verb, one.number, one.url, found.why))
            return 1
        why = " and ".join(self.lifts) or first.why
        slug = found.slug or f"#{one.number}"
        if check:
            notes = [f"accepted: {why}", safe]
            say(lines.ready(one.number, one.head, one.branch, slug, notes))
            return 0
        ran: list[str] = []

        word = f"accepted by {by} at {when}" + (f" on {message}" if message else "")

        def does() -> str:
            ran.append(one.head)
            say(f"accepted {about}: {why}, lifted at {one.head[:12]} by {by} at {when}, {safe}")
            self.word = word
            said = self.merge(one, slug, found.note, found.judged)
            say(said)
            if not said.startswith("merged "):
                raise jsettings.Refused(said)
            return said

        if acting is None:
            try:
                does()
            except jsettings.Refused:
                return 1
            return 0
        touched = bool(ready.protected_path(one, self.protected, self.left(one) or ()))
        outcome, line = bus.found().accept(
            acting, one.number, found.slug, one.head, text, touched, does
        )
        if outcome == "done":
            return 0
        if not ran:
            say(line)
        return 1

    def take_line(
        self,
        one: ready.PullRequest,
        default: str,
        slug: str,
        word: tuple[str | None, str | None, str | None],
        say: Callable[[str], None],
        check: bool,
        acting: bus.Acting | None,
    ) -> int:
        """Give `one`, which waits only on its turn in its base's line (`in_turn`), the head of
        that line on the user's own message: GitHub is asked to merge the base into it now, and
        a later run merges it once its check passes at that head, as the head of the line merges.
        The accept lifts no wait: a check from before the base moved still merges nothing. The
        pull request at the head before it keeps the update GitHub made it and goes back in line
        (`rejudge.BaseMerge.release`). The word stays on its record, and its merged line carries
        it. Where GitHub does not take the update, the line stays as it was. `word` is who
        accepts, when, and the message it was said in."""
        by, when, message = word
        about = f"{one.number} {one.url}"
        ahead = self.line.get(one.base)
        if not message:
            say(f"refused {about}: it waits in line, and only --message gives it the head")
            return 1
        if check:
            say(f"accepted {about}: it would take the head of the line of {one.base} from #{ahead}")
            return 0
        accepted = f"accepted by {by} at {when} on {message}"

        def does() -> str:
            self.line[one.base] = one.number
            self.base_merge.accept(one.number, accepted)
            found = self.waits(one, default)
            if self.line.get(one.base) != one.number:
                self.base_merge.release(one.number)
                if ahead is not None:
                    self.line[one.base] = ahead
                raise jsettings.Refused(lines.waits(found.verb, one.number, one.url, found.why))
            if ahead is not None:
                self.base_merge.release(ahead)
            took = f"accepted {about}: it takes the head of the line of {one.base} from #{ahead}"
            say(f"{took}, {accepted}")
            say(lines.waits(found.verb, one.number, one.url, found.why))
            return took

        assert acting is not None, "main refuses --message where jbus has no project"
        text = _read(self.state / "tasks" / f"{slug}.md")
        touched = bool(ready.protected_path(one, self.protected, self.left(one) or ()))
        outcome, line = bus.found().accept(acting, one.number, slug, one.head, text, touched, does)
        if outcome == "done":
            return 0
        say(line)
        return 1

    def clear_up(self, branch: str, head: str) -> str:
        tree = at = ""
        listed = _run(self.main, "git", "worktree", "list", "--porcelain").stdout
        for line in listed.splitlines():
            if line.startswith("worktree "):
                at = line.removeprefix("worktree ")
            elif line == f"branch refs/heads/{branch}":
                tree = at
        local = _run(self.main, "git", "rev-parse", "-q", "--verify", f"refs/heads/{branch}")
        if local.stdout.strip() != head:
            return f"{branch} is not at the merged head"
        if tree and _run(self.main, "git", "-C", tree, "status", "--porcelain").stdout.strip():
            return f"{tree} has uncommitted work"
        if tree:
            ran = _run(self.main, "git", "worktree", "remove", tree)
            if ran.returncode:
                why = lines.said(ran)
                return f"{tree} could not be removed, and both branches are left ({why})"
        ran = _run(self.main, "git", "branch", "-q", "-D", branch)
        if ran.returncode:
            why = lines.said(ran)
            return f"the local and remote branch {branch}, the worktree is removed ({why})"
        gone = f"the remote branch {branch}, the worktree and the local branch are removed"
        based = self.based_on(branch)
        if based:
            return f"{gone} ({based})"
        ref = f"refs/heads/{branch}"
        ran = _run(
            self.main, "git", "push", "-q", f"--force-with-lease={ref}:{head}", "origin", f":{ref}"
        )
        if not ran.returncode:
            return ""
        stale = "(stale info)" in ran.stderr
        why = "it is not at the merged head on the origin" if stale else lines.said(ran)
        return f"{gone} ({why})"

    def messages(self, one: ready.PullRequest) -> list[str] | None:
        """The message of each commit on the branch and not on its base, oldest first, as
        GitHub's default squash body lists them, and None when git cannot read them."""
        base = f"refs/remotes/origin/{one.base}"
        fetched = _run(
            self.main, "git", "fetch", "-q", "origin", one.head, f"+refs/heads/{one.base}:{base}"
        )
        if fetched.returncode:
            return None
        ran = _run(self.main, "git", "log", "--reverse", "--format=%B%x00", one.head, "--not", base)
        if ran.returncode:
            return None
        return [message.strip() for message in ran.stdout.split("\0") if message.strip()]

    def merge(
        self,
        one: ready.PullRequest,
        slug: str,
        rebase: str = "",
        judged: ready.Judged | None = None,
    ) -> str:
        judged = judged or ready.Judged()
        from jmerge.lock import MergeLock

        lock = MergeLock(self.state)
        try:
            return self.merge_holding(lock, one, slug, rebase, judged)
        finally:
            lock.give()

    def fetch_trunk(self) -> subprocess.CompletedProcess[str]:
        """Fetch the default branch into the main checkout after a merge. Another process (a jbus
        pass, a tick, a crew or a home) can fetch `origin/<trunk>` in the same checkout at the same
        moment, and git then refuses this fetch's ref update with "cannot lock ref". That race
        clears by itself, so the fetch is tried again, up to FETCH_TRIES in all, a short pause
        apart. Any other failure is returned at once."""
        fetched = _run(self.main, "git", "fetch", "-q", "origin", self.trunk)
        for _ in range(FETCH_TRIES - 1):
            if not fetched.returncode or LOCKED not in fetched.stderr:
                break
            time.sleep(FETCH_PAUSE_SECONDS)
            fetched = _run(self.main, "git", "fetch", "-q", "origin", self.trunk)
        return fetched

    def merge_holding(
        self, lock, one: ready.PullRequest, slug: str, rebase: str, judged: ready.Judged
    ) -> str:
        """Merge `one` while this run holds the repo's merge lock, from the read of its base's
        tip to the merge. A tip that moved since it was judged gives the lock back while the pull
        request is judged again, so a wait on GitHub holds up no other run."""
        number = str(one.number)
        again = 0
        while lock.take():
            if not judged.tip:
                break
            at = _run(self.main, "git", "ls-remote", "origin", f"refs/heads/{one.base}")
            if not at.returncode and _first_word(at.stdout) == judged.tip:
                break
            lock.give()
            if again == JUDGED_AGAIN_AT_MOST:
                moved = ready.MAIN_MOVED.format(base=one.base)
                return lines.waits("wait", number, one.url, moved)
            again += 1
            self.numbers_on.clear()
            again_judged = self.waits(one, self.trunk or one.base)
            if again_judged.judged is None:
                return lines.waits(again_judged.verb, number, one.url, again_judged.why)
            rebase, judged = again_judged.note, again_judged.judged
        else:
            return lines.waits("wait", number, one.url, ready.MERGING)
        messages = self.messages(one)
        if messages is None:
            return lines.waits("wait", number, one.url, ready.NO_MESSAGES)
        tip = judged.tip or _run(self.main, "git", "rev-parse", f"origin/{one.base}").stdout.strip()
        guarded, passed = self.guards.of(one, tip)
        if guarded and judged.overlaps and self.guards.kept(one, tip):
            guarded = self.base_moved(one, tip)
        if guarded:
            return lines.waits("wait", number, one.url, guarded)
        body = "\n\n".join(f"* {trailers.strip(message)}" for message in messages)
        self.began[one.number] = datetime.now(UTC)
        ran = _run(
            self.main,
            "gh",
            "pr",
            "merge",
            number,
            "--squash",
            "--match-head-commit",
            one.head,
            "--subject",
            f"{one.title} (#{number})",
            "--body-file",
            "-",
            *self.about,
            stdin=trailers.strip(body) + "\n",
        )
        if ran.returncode:
            return lines.waits("wait", number, one.url, f"{ready.MERGE_FAILED}: {lines.said(ran)}")
        if self.line.get(one.base) == one.number:
            del self.line[one.base]
        word = self.word or self.base_merge.accepted(one.number)
        notes = [note for note in (rebase, passed, word) if note]
        asked = _run(
            self.main,
            "gh",
            "pr",
            "view",
            number,
            "--json",
            "mergeCommit",
            "--jq",
            ".mergeCommit.oid",
            *self.about,
        )
        commit = asked.stdout.strip()
        if asked.returncode or not commit:
            commit = one.head
            notes.append("that commit is its head, GitHub did not give the merge commit")
        before = _run(self.main, "git", "rev-parse", "HEAD").stdout.strip()
        pulled = self.fetch_trunk()
        if not pulled.returncode:
            pulled = _run(self.main, *("git", "merge"), "-q", "--ff-only", f"origin/{self.trunk}")
        self.numbers_on.clear()
        if pulled.returncode:
            notes.append(lines.not_pulled(lines.said(pulled)))
        else:
            from jmerge.follow import follow

            notes += follow(_run, self.main, before)
        kept = self.clear_up(one.branch, one.head)
        if kept:
            notes.append(f"kept: {kept}")
        return lines.merged(number, slug, commit, one.title, notes, one.url)


PROC = Path("/proc")


def _cwds_from_proc() -> dict[int, str] | None:
    try:
        listed = [PROC / name for name in os.listdir(PROC) if name.isdigit()]
    except OSError:
        return None
    if PROC / str(os.getpid()) not in listed:
        return None
    cwds = {}
    for entry in listed:
        try:
            cwds[int(entry.name)] = os.readlink(entry / "cwd")
        except OSError:
            continue
    return cwds


def _cwds_from_lsof() -> dict[int, str] | None:
    """The working directory of each of the user's processes on a Mac, which has no /proc. lsof's
    `-F n` prints a `p<pid>` line for each process and an `n<path>` line for its cwd."""
    command = ["lsof", "-w", "-a", "-d", "cwd", "-u", str(os.getuid()), "-F", "n"]
    try:
        said = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if said.returncode:
        return None
    cwds, pid = {}, 0
    for line in said.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n") and pid:
            cwds[pid] = line[1:]
    return cwds if os.getpid() in cwds else None


def _running(tree: str) -> int | None:
    """The lowest pid of a process whose working directory is in the tree, 0 for none, and None
    when no list of every process could be read. A Mac reads lsof, unless a caller set PROC."""
    on_a_mac = sys.platform == "darwin" and Path("/proc") == PROC
    cwds = _cwds_from_lsof() if on_a_mac else _cwds_from_proc()
    if cwds is None:
        return None
    inside = os.path.realpath(tree)
    found = [pid for pid, at in cwds.items() if at == inside or at.startswith(f"{inside}/")]
    return min(found, default=0)


class Sweep:
    def __init__(self, repo: Repo) -> None:
        self.repo = repo
        self.main = repo.main
        self.state = repo.state
        self.trees = Path.home() / ".t3" / "worktrees" / repo.main.name
        self.default = self.tip = ""
        self.remote: dict[str, str] = {}
        self.markers: dict[str, str] = {}
        self.local: dict[str, str] = {}
        self.worktrees: list[tuple[str, str]] = []

    def read(self) -> bool:
        asked = _run(
            self.main,
            "git",
            "ls-remote",
            "--symref",
            "origin",
            "HEAD",
            "refs/heads/*",
            f"{sweep.MARKERS}*",
        )
        for line in asked.stdout.splitlines():
            first, _, name = line.partition("\t")
            if first.startswith("ref: refs/heads/") and name == "HEAD":
                self.default = first.removeprefix("ref: refs/heads/")
            elif name.startswith("refs/heads/"):
                self.remote[name.removeprefix("refs/heads/")] = first
            elif name.startswith(sweep.MARKERS):
                self.markers[name] = first
        self.tip = self.remote.get(self.default, "")
        if asked.returncode or not self.tip:
            return False
        if _run(self.main, "git", "fetch", "-q", "origin").returncode:
            return False
        self.local = self._heads(self.main)
        at = on = ""
        listed = _run(self.main, "git", "worktree", "list", "--porcelain").stdout
        for line in [*listed.splitlines(), ""]:
            if line.startswith("worktree "):
                at, on = line.removeprefix("worktree "), ""
            elif line.startswith("branch refs/heads/"):
                on = line.removeprefix("branch refs/heads/")
            elif not line and at:
                self.worktrees.append((at, on))
                at = ""
        return True

    def _heads(self, repo: Path) -> dict[str, str]:
        listed = _run(
            repo, "git", "for-each-ref", "--format=%(objectname) %(refname)", "refs/heads"
        )
        heads = (line.split(" ", 1) for line in listed.stdout.splitlines())
        return {name.removeprefix("refs/heads/"): commit for commit, name in heads}

    def records(self) -> dict[str, list[sweep.Record]]:
        named: dict[str, list[sweep.Record]] = {}
        for directory, read in (("tasks", sweep.of_brief), ("scouts", sweep.of_request)):
            for path in sorted((self.state / directory).glob("*.md")):
                record = read(path.stem, _read(path))
                named.setdefault(record.branch, []).append(record)
        return named

    def left(self, branch: str) -> dict[str, str]:
        there = {
            sweep.WORKTREE: next((at for at, on in self.worktrees if on == branch), ""),
            sweep.LOCAL: self.local.get(branch, ""),
            sweep.REMOTE: self.remote.get(branch, ""),
        }
        return {what: at for what, at in there.items() if at}

    def _within(self, commit: str, of: str) -> bool:
        ran = _run(self.main, "git", "merge-base", "--is-ancestor", commit, of)
        return ran.returncode == 0

    def _safe(self, commit: str, head: str, pull: str) -> bool:
        """GitHub keeps a pull request's head as `refs/pull/<number>/head` after its branch is
        deleted. So when the main checkout no longer has a merged head, `jmerge` fetches it
        from that ref:
        https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/checking-out-pull-requests-locally
        """
        if commit == head or self._within(commit, self.tip):
            return True
        if not head:
            return False
        if _run(self.main, "git", "cat-file", "-e", f"{head}^{{commit}}").returncode:
            number = pull.rstrip("/").rsplit("/", 1)[-1]
            _run(self.main, "git", "fetch", "-q", "origin", f"refs/pull/{number}/head")
        return self._within(commit, head)

    def found(self, record: sweep.Record, left: dict[str, str]) -> sweep.Found:
        state: Literal["MERGED", "OPEN", "CLOSED", ""] = ""
        head = silent = ""
        if record.pull and not record.short:
            asked = _run(
                self.main, "gh", "pr", "view", record.pull, "--json", "state,headRefOid,baseRefName"
            )
            try:
                said = json.loads(asked.stdout)
                told = "" if asked.returncode else str(said["state"])
                state = told if told in ("MERGED", "OPEN", "CLOSED") else ""
                if state == "MERGED" and said["baseRefName"] in (self.default, *self.repo.bases):
                    head = str(said["headRefOid"])
            except (ValueError, KeyError, TypeError):
                state = ""
            if not state:
                silent = _why(self.main, asked)
        tree = left.get(sweep.WORKTREE, "")
        status = _run(self.main, "git", "-C", tree, "status", "--porcelain") if tree else None
        refs = (sweep.LOCAL, sweep.REMOTE)
        found = sweep.Found(
            default=self.default,
            pull=state,
            silent=silent,
            merged=bool(head),
            tree=tree,
            trees="" if not tree or self.trees in Path(tree).parents else str(self.trees),
            dirty=bool(status and Path(tree).exists() and (status.returncode or status.stdout)),
            stray=tuple(
                ref for ref in refs if ref in left and not self._safe(left[ref], head, record.pull)
            ),
            pid=_running(tree) if tree else 0,
        )
        if sweep.REMOTE in left and not sweep.kept(record, found):
            found = replace(found, based=self.repo.based_on(record.branch))
        return found

    def remove(self, branch: str, left: dict[str, str]) -> tuple[list[str], str, str]:
        ref = f"refs/heads/{branch}"
        tree = left.get(sweep.WORKTREE, "")
        steps = {
            sweep.WORKTREE: ["worktree", "remove", tree],
            sweep.LOCAL: ["update-ref", "-d", ref, left.get(sweep.LOCAL, "")],
            sweep.REMOTE: [
                "push",
                "-q",
                f"--force-with-lease={ref}:{left.get(sweep.REMOTE, '')}",
                "origin",
                f":{ref}",
            ],
        }
        gone: list[str] = []
        for what in left:
            ran = _run(self.main, "git", *steps[what])
            if ran.returncode:
                return gone, what, lines.said(ran)
            gone.append(what)
            if what == sweep.LOCAL:
                _run(self.main, "git", "config", "--remove-section", f"branch.{branch}")
        return gone, "", ""

    def marked(self, ref: str, commit: str) -> int | None:
        asked = "git", "show", "-s", "--format=%ct", f"{commit}^{{commit}}"
        made = _run(self.main, *asked)
        if made.returncode:
            _run(self.main, "git", "fetch", "-q", "origin", ref)
            made = _run(self.main, *asked)
        return int(made.stdout) if not made.returncode and made.stdout.strip().isdigit() else None

    def markers_past(self, say: Callable[[str], None], check: bool) -> list[tuple[str, str]]:
        kept: list[tuple[str, str]] = []
        for ref, commit in sorted(self.markers.items()):
            kind, _, tree = ref.removeprefix(sweep.MARKERS).rpartition("/")
            label = f"green-tree/{kind}{'/' if kind else ''}{tree[:12]}"
            made = self.marked(ref, commit)
            if made is None:
                kept.append((label, "the commit its marker is at could not be read"))
                continue
            days = sweep.past(made, time.time())
            if not days:
                continue
            what = f"{label} no-thread: the marker of a tree that passed {days} days ago"
            if check:
                say(f"removable {what}")
                continue
            lease = f"--force-with-lease={ref}:{commit}"
            ran = _run(self.main, "git", "push", "-q", lease, "origin", f":{ref}")
            if ran.returncode:
                kept.append((label, f"its marker could not be removed ({lines.said(ran)})"))
            else:
                say(f"removed {what}")
        return kept

    def run(self, say: Callable[[str], None], check: bool) -> int:
        if not self.read():
            say("wait: could not read origin")
            return 1
        named = self.records()
        kept: list[tuple[str, str]] = []
        for branch in sorted(named):
            left = self.left(branch)
            if not left:
                continue
            first, *more = named[branch]
            if more:
                why = f"{first.source} and {more[0].source} both name it"
            elif branch == self.default:
                why = "it is the default branch"
            elif branch in self.repo.bases:
                why = "it is a merge base of the project"
            else:
                why = sweep.kept(first, self.found(first, left))
            if why:
                kept.append((branch, why))
                continue
            thread = first.thread or "no-thread"
            if check:
                say(f"removable {branch} {thread}: {', '.join(left)}")
                continue
            gone, stopped, said = self.remove(branch, left)
            if not gone:
                kept.append((branch, f"{stopped} could not be removed ({said})"))
            else:
                tail = f", kept: {stopped} ({said})" if stopped else ""
                say(f"removed {branch} {thread}: {', '.join(gone)}{tail}")
        kept += self.markers_past(say, check)
        for at, on in self.worktrees[1:]:
            if self.trees in Path(at).parents and on not in named:
                on = f"its branch {on}" if on else "it, and it is on no branch"
                kept.append((Path(at).name, f"no brief or request names {on}"))
        for label, why in sorted(kept):
            say(f"kept {label}: {why}")
        return 0


def _job(repo: str, job: str) -> dict:
    """A job as GitHub gives it, or an empty dict where GitHub gives none."""
    given = _run(Path.cwd(), "gh", "api", f"repos/{repo}/actions/jobs/{job}")
    try:
        found = json.loads(given.stdout) if not given.returncode else {}
    except ValueError:
        return {}
    return found if isinstance(found, dict) else {}


def said_of_checks(pull: str) -> str:
    pr = [pull] if pull else []
    try:
        fields = "headRefOid,statusCheckRollup"
        asked = _run(Path.cwd(), "gh", "pr", "view", *pr, "--json", fields)
        view = json.loads(asked.stdout) if not asked.returncode else {}
        rollup, head = view["statusCheckRollup"] or [], view["headRefOid"] or ""
        never = checks.never_started(rollup, _job)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return "wait: could not ask GitHub"
    return checks.SAID[checks.checks(rollup, never)].format(head=head)


def homes_state(main_checkout: Path) -> Path:
    """The repo's state in the homes' state, the directory named for its main checkout. The homes'
    state is `JBUS_HOME_DIR`, as jbus reads it, or `~/.local/state/home`."""
    return paths.homes_dir() / main_checkout.name


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        prog="jmerge",
        description="Merge this repo's pull requests that are reviewed, fixed and green, pull "
        "the main checkout, and remove each one's worktree and branches. Prints one line per "
        "open pull request. A pull request based on a branch other than the default branch "
        "is never merged, unless its project names that branch as a merge base (jbus project "
        "bases --add): one into a merge base merges on the default branch's rules, and a red main "
        "does not hold it. "
        "A draft is never merged or marked ready, with any flag. "
        "A green check stands for its own head: one whose head no longer merges over a main "
        "that changed one of its paths after its check started waits for a rebase, and one "
        "that still merges cleanly merges on that check. One whose rebase dropped "
        "a line waits for its crew to say why and for the scoped review to uphold it, and is "
        "printed as hold when it does not. "
        "One that changes a protected path (features/jmerge/src/jmerge/protected.txt) is "
        "never merged and is printed as hold. A merge-off file in the repo's state merges "
        "nothing. "
        "A run that may merge or remove holds the repo's run lock for the whole run, so one "
        "runs at a time: it waits for another to end, or with --if-free does nothing. "
        "With --sweep it merges nothing: it "
        "removes the worktree and the branches of each finished thread whose "
        "work is all merged or pushed, and prints what it removed and what it kept. With "
        "--claims it changes nothing: it prints one line per brief that still holds files, "
        "with its state, its home and its Where line. With --accept it lifts the hold of one "
        "pull request, at the head the hold was said at, when a review proved its one safety "
        "fact at that head, and merges it as any other. With --checks it changes nothing: it "
        "prints the state of one pull request's checks in a line. With --range-diff it "
        "changes nothing: it prints whether a rebase changed the content of a branch.",
    )
    top.add_argument(
        "--check",
        action="store_true",
        help="print what is ready and what waits, or with --sweep what is removable; "
        "merge and remove nothing",
    )
    instead = top.add_mutually_exclusive_group()
    instead.add_argument(
        "--sweep",
        action="store_true",
        help="remove what finished threads left, in place of merging",
    )
    instead.add_argument(
        "--claims",
        action="store_true",
        help="print the files claimed by each brief that is not launched, out, or has an "
        "open pull request, across this repo's homes; merge, remove and log nothing",
    )
    instead.add_argument(
        "--scope",
        metavar="SLUG",
        help="print each file the brief's branch changes that its Where: line does not cover, "
        "as 'outside: <path>'; nothing is printed when all are inside; merge, remove and log "
        "nothing",
    )
    instead.add_argument(
        "--checks",
        metavar="PR",
        nargs="?",
        const="",
        help="print the state of a pull request's checks in one line, each check by its latest "
        "run: passed, failed, wait or unrun, then why; the pull request is a number, an address "
        "or a branch, by default the current branch's; merge, remove and log nothing",
    )
    instead.add_argument(
        "--range-diff",
        metavar="BEFORE..HEAD",
        help="print 'clean: <why>' when the branch at HEAD has the content it had at BEFORE, "
        "by the range-diff over origin/<--base> that jmerge carries a review over with, else "
        "'changed: <why>'; run it in the checkout that has both; merge, remove and log nothing",
    )
    instead.add_argument(
        "--remake",
        action="store_true",
        help="while a rebase is stopped, name the files to resolve by hand, or make each "
        "generated file again over the base's version, by the command the generated key of "
        "the repo's [[project]] in jbus's config gives it (uv.lock by uv lock where none "
        "does); merge, remove and log nothing",
    )
    instead.add_argument(
        "--accept",
        metavar="NUMBER",
        help="lift the hold of this pull request at its current head and merge it: the "
        "user's hand-merge, on --message or on --by and --at, taken as an act of jbus's; with "
        "--check alone, say what it would do",
    )
    top.add_argument(
        "--base",
        metavar="BRANCH",
        default="main",
        help="with --range-diff: the branch both heads sit on (default: main)",
    )
    top.add_argument(
        "--by", metavar="WHO", help="with --accept: who accepts it, the user jstack's config names"
    )
    top.add_argument(
        "--at", metavar="WHEN", help='with --accept: when it was said, "YYYY-MM-DD HH:MM ZONE"'
    )
    top.add_argument(
        "--message",
        metavar="THREAD/MESSAGE",
        help="with --accept: the user's own message in T3 Code, which jbus reads, in place of "
        "--by and --at",
    )
    top.add_argument(
        "--as",
        dest="as_",
        choices=("home", "user"),
        default="home",
        help="with --accept: the party that accepts, a home (default) or the user, who acts on "
        "a --message alone",
    )
    top.add_argument(
        "--if-free",
        action="store_true",
        help="do nothing and exit 75 when another run of jmerge is under way, in place of "
        "waiting for it to end (jbus's merge tick)",
    )
    top.add_argument(
        "--home",
        metavar="ID",
        help="the home that is asking: say what jmerge would do of its own pull requests, as "
        "--check does, and merge nothing, since jbus alone merges",
    )
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.checks is not None:
        print(said_of_checks(args.checks))
        return 0
    if args.range_diff:
        before, _, head = args.range_diff.partition("..")
        found = rangediff.verdict(Path.cwd(), before, head, args.base)
        print(f"{'clean' if found.clean else 'changed'}: {found.why}, by {found.command}")
        return 0
    if args.remake:
        print("\n".join(remake.remake()))
        return 0
    try:
        user = jsettings.load()
    except jsettings.Invalid as error:
        raise SystemExit(f"jmerge: {error}") from None
    if args.accept is None and (args.by or args.at or args.message):
        raise SystemExit("jmerge: --by, --at and --message go with --accept")
    if args.message and (args.by or args.at):
        raise SystemExit("jmerge: --accept takes --message, or --by and --at, and not both")
    if args.accept is not None and not args.accept.isdigit():
        raise SystemExit(f"jmerge: --accept takes a pull request's number, not {args.accept}")
    if args.home:
        args.check = True
    typed = bool(args.by or args.at)
    said = args.accept is not None and not (args.check and not typed and not args.message)
    if said and not args.message and args.by != user.user:
        raise SystemExit(f"jmerge: only {user.user} accepts a hold, not {args.by or 'nobody'}")
    if said and not args.message and not user.takes(args.at or ""):
        raise SystemExit(f'jmerge: --at is "{user.form(args.at or "")}"')
    main_checkout = paths.main_checkout(Path.cwd())
    if main_checkout is None:
        raise SystemExit("jmerge: not in a git repository")
    if not shutil.which("gh"):
        raise SystemExit("jmerge: gh is not installed")
    state = homes_state(main_checkout)
    backoff.watch(state, keeps=not (args.check or args.claims or args.scope))
    if args.check or args.claims or args.scope or not state.is_dir():
        return _merging(args, user, main_checkout, state, said, typed)
    if args.accept is not None:
        first: list[str] = []
        if _merging(args, user, main_checkout, state, said, typed, first.append):
            print("\n".join(first), flush=True)
            return 1
    with lock.running(state, wait=not args.if_free) as free:
        if not free:
            print(lock.BUSY_LINE.format(path=state / lock.RUN), flush=True)
            return lock.BUSY
        return _merging(args, user, main_checkout, state, said, typed)


def _merging(
    args: argparse.Namespace,
    user: jsettings.Settings,
    main_checkout: Path,
    state: Path,
    said: bool,
    typed: bool,
    look: Callable[[str], None] | None = None,
) -> int:
    """The run itself, once `main` holds the run lock where the run may write. With `look`, the
    first look of an accept, which takes no lock: the run of its check, with the party that
    accepts read as the accept reads it, saying each line to `look`. An accept that would not
    merge ends there, saying why. One that waited for the lock first sat behind jbus's merge
    run for minutes, whose merges moved main, and then read that GitHub had not decided whether
    it merges: #1492 said that four times on 2026-11-09 while its check said the scoped review
    it was short of."""
    check = args.check or look is not None
    if args.claims:
        return Repo(main_checkout, state, args.home, not args.home, user=user).claimed()
    if args.scope:
        return Repo(main_checkout, state, args.home, not args.home, user=user).scoped(args.scope)

    repo = Repo(
        main_checkout,
        state,
        args.home,
        not args.home,
        patterns(PROTECTED),
        not check,
        user=user,
    )

    now = datetime.now().astimezone()

    def say(line: str) -> None:
        if look is not None:
            look(line)
            return
        print(line, flush=True)
        said = lines.one(line)
        if not check and state.is_dir():
            repo.timed(line)
            waits = str(said.number) if said and said.word in ("wait", "hold") else ""
            if not said and backoff.is_wait(line.removeprefix("wait: ")):
                waits = "github"
            kept = lines.logged(line)
            last: dict = {}
            if waits:
                last = store.read_dict(state / "merge.log.last")
                if last.get(waits) == kept:
                    return
                last[waits] = kept
            with (state / "merge.log").open("a", encoding="utf-8") as log:
                log.write(f"{now:%Y-%m-%d %H:%M} {kept}\n")
            if waits:
                store.write_json(state / "merge.log.last", last)

    if waiting := backoff.gate.held():
        say(f"wait: {waiting}")
        return 1

    if args.sweep:
        return Sweep(repo).run(say, check)

    def ask() -> tuple[subprocess.CompletedProcess[str], list[ready.PullRequest] | None]:
        asked = _run(
            main_checkout,
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            str(LIMIT),
            "--json",
            LIST,
            *repo.about,
        )
        try:
            return asked, [with_browser(repo, one) for one in json.loads(asked.stdout)]
        except (ValueError, KeyError, TypeError, AttributeError):
            return asked, None

    asked, listed = ask()
    if args.accept is not None and not args.check:
        for pause in DECIDING:
            if not undecided(listed, int(args.accept)):
                break
            time.sleep(pause)
            asked, listed = ask()
    default, silent = repo.default() if listed else ("", "")
    if asked.returncode or listed is None:
        silent = _why(main_checkout, asked)
    if silent or listed is None:
        say(f"wait: could not ask GitHub{silent}")
        return 1
    listed = [repo.in_full(one) for one in listed]
    repo.open = listed
    full = len(listed) >= LIMIT
    if full:
        say(
            f"listed: GitHub gave {LIMIT} open pull requests, the most jmerge asks for, so it"
            " judges those alone and keeps the records of every one"
        )
    if not check and not full:
        repo.open_only(listed)
    repo.lined_up(listed)

    if args.accept is not None:
        found = next((one for one in listed if one.number == int(args.accept)), None)
        if found is None:
            say(f"refused {args.accept}: no open pull request has that number")
            return 1
        acting = None
        if said and not args.check:
            try:
                acting = bus.found().acting(main_checkout, args.message, args.at, args.as_, user)
            except jsettings.Refused as error:
                say(f"refused {args.accept}: {str(error).removeprefix('refused: ')}")
                return 1
            if acting is None and args.message:
                say(f"refused {args.accept}: --message is read by jbus, which has no project here")
                return 1
        by, at = args.by, args.at
        if acting is not None and args.message:
            by, at = user.user, acting.said_at
        return repo.accept(found, default, by, at, say, check, acting, args.message)

    for one in repo.line_up(listed, default):
        found = repo.waits(one, default)
        if found.verb == "hold" and not check:
            repo.hold(one)
        if found.judged is None:
            say(lines.waits(found.verb, one.number, one.url, found.why))
        elif check:
            notes = [found.note]
            say(lines.ready(one.number, one.head, one.branch, found.slug, notes))
        else:
            say(repo.merge(one, found.slug, found.note, found.judged))
    for line in repo.unopened(listed):
        say(line)
    return 0


MAIN_BROWSER = "{default} browser.yml"
"""The key of `Repo.reds` that keeps main's browser runs, which no branch name can be."""
ROLLUP = "#{number} rollup"
"""The key of `Repo.reds` that keeps a pull request's checks as GitHub lists them."""


IN_LINE = frozenset(
    reason.code
    for reason in (
        ready.OTHER_HOME,
        ready.MERGE_OFF,
        ready.MERGING,
        ready.MAIN_MOVED,
        ready.UNDECIDED,
        ready.NOT_PASSED,
        ready.NO_RUN,
        ready.LIVE_RUN,
        ready.MIGRATION_MERGING,
        ready.BASE_MOVED_ASKED,
        ready.BASE_MOVED_DUE,
        ready.QUEUED_RESTARTED,
        ready.QUEUED_UNOPENED,
        ready.QUEUED_UNCLOSED,
    )
)
"""The waits that keep a pull request at the head of its base's line (`Repo.over_main`): those
on jmerge, GitHub and its check, which end in its merge by themselves. Any other wait, or a
failed check, gives the line to the next pull request: one that waits on its crew or the user
would hold every other one its base moved past for as long."""


UPDATING_RED = frozenset((ready.BASE_MERGE_ASKED.code, ready.BASE_MERGE_DUE.code))
"""The waits of a pull request whose failed check is what its turn at the head of the line is
for: GitHub's merge of the base into it, asked or due (`Repo.again`)."""


def in_line(one: ready.PullRequest, found: Judgement) -> bool:
    """Whether the pull request at the head of the line keeps it after this judgement. A failed
    check gives it up, unless the base's merge into it, its turn, is for that check."""
    if one.failed:
        return ready.code_of(found.why) in UPDATING_RED
    return found.judged is not None or ready.code_of(found.why) in IN_LINE


def undecided(listed: list[ready.PullRequest] | None, number: int) -> bool:
    """Whether GitHub listed pull request `number` with no answer yet to whether it merges."""
    found = next((one for one in listed or () if one.number == number), None)
    return found is not None and found.mergeable not in ("MERGEABLE", "CONFLICTING")


def with_browser(repo: Repo, listed: dict) -> ready.PullRequest:
    """The pull request GitHub `listed`, with its checks kept for `browser_red`."""
    repo.reds[ROLLUP.format(number=listed["number"])] = listed.get("statusCheckRollup") or []
    return ready.pull_request(listed, repo.required)


def browser_red(repo: Repo, one: ready.PullRequest, default: str, slug: str) -> str:
    """The wait on a pull request into main for its own browser run: one still going waits as any
    pending run, and one that failed holds it (`rows.browser_red`). It asks GitHub for main's
    browser runs once a run, and only for a pull request whose browser run failed. When GitHub
    gives no answer, main is not known to be red, and the red is the pull request's own."""
    state = ready.browser(repo.reds.get(ROLLUP.format(number=one.number), []))
    if state == ready.BROWSER_PENDING:
        return ready.NOT_PASSED.format(check=ready.BROWSER)
    if state != ready.BROWSER_FAILED:
        return ""
    key = MAIN_BROWSER.format(default=default)
    if key not in repo.reds:
        asked = backoff.run(
            "gh",
            "api",
            "repos/{owner}/{repo}/actions/workflows/browser.yml/runs"
            f"?branch={default}&status=completed&per_page=20",
            cwd=repo.main,
            env={**os.environ, **({"GH_REPO": repo.about[1]} if repo.about else {})},
        )
        try:
            runs = [] if asked.returncode else json.loads(asked.stdout)["workflow_runs"]
        except (ValueError, KeyError, TypeError):
            runs = []
        listed = runs if isinstance(runs, list) else []
        repo.reds[key] = [run for run in listed if isinstance(run, dict)]
    fixing = rows.browser_fixing(repo.main, repo.queue)
    run = rows.main_browser_run(repo.reds[key], default, fixing)
    ran, failed = rows.UNPROVED, ()
    if run is not None and not slug.startswith(rows.BROWSER_FIX):
        failed = repo.run_failed(run.get("id"))
        if failed:
            ran = repo.proved_browser(one, str(run.get("head_sha") or ""))
    return rows.browser_red(one.head, slug, repo.reds[key], default, fixing, ran, failed)


_JOB = re.compile(r"/job/(\d+)")
PASSED = ("SUCCESS", "NEUTRAL", "SKIPPED")


def passed(rollup: list[dict]) -> bool:
    """Whether every check of the head has run and passed, the latest run of each, so every
    part of a check that runs in parts passed."""
    names = {one.get("name") or one.get("context") for one in rollup}
    latest = [run for name in names for run in ready.latest(rollup, name)]
    return bool(latest) and all(
        one.get("conclusion") in PASSED or one.get("state") == "SUCCESS" for one in latest
    )


def jobs(rollup: list[dict], ended: tuple[str, ...] = PASSED) -> list[str]:
    """The ids of the jobs of the checks in `rollup` that ended so, from their links."""
    return [
        found[1]
        for one in rollup
        if one.get("conclusion") in ended and (found := _JOB.search(one.get("detailsUrl") or ""))
    ]
