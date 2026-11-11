"""A pull request whose required check failed, judged again over today's base.

A pull request's check runs on its merge with the base as the base was then, and a rerun runs on
that same merge. So a check that failed while the base was red stays red after the base is
fixed, and no push of the crew's is owed for it. `jmerge` judges such a pull request again once
its base has moved since the check started and is not red: `BaseMerge` asks GitHub to merge the
base into the branch, and GitHub's new check at the new head decides the rest by the normal path.
A green pull request whose base moved under it on a file it changes too merges on the guards on
its tree merged over today's base, where the repo names them (`cli.Repo.over_main`). Where they
failed or were stopped there, where the repo names none, and for a revert jbus opened, its check
ran over a base that is gone, so where its head merges cleanly over today's base, GitHub merges
the base into it too, one pull request at a time: the one at the head of the line of its base
(`BaseMerge.holders`), which every other one into that base whose base moved and that takes this
path, green, red or with a check that has no run, waits behind.

GitHub's endpoint merges the base into the branch and rewrites no history:
https://docs.github.com/en/rest/pulls/pulls#update-a-pull-request-branch. `expected_head_sha`
makes it refuse a branch that moved since `jmerge` judged it. A review stands across that merge
when the patch is unchanged, as across a rebase: its range-diff shows no content
(`rangediff.verdict`), which leaves out the merge commit.

A pull request whose last two check runs failed a same pytest id, which main's check at neither
run's base failed, is broken on its own, and a merge of the base would only fail it again
(#494, 2026-10-26: nine merges of main, each red on the same test). `Repeated` finds those ids
in the `FAILED <id>` lines of `gh run view <id> --log-failed`. Its answer is kept for the head,
the base tip and the check, "not repeated" as well, so no run log is read twice for one head and
tip: each run of `jmerge` read the logs of every red pull request again (2026-11-03).

Every call to GitHub here goes through `backoff`: after a refusal for the rate limit, none is made
until GitHub said it may be.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

from jmerge import backoff, ready
from jsettings import store

NAME = "base-merges.json"
SHA = 12
REFUSED = re.compile(r"\(HTTP (409|422)\)")
FAILED = re.compile(r"\sFAILED (\S+::\S+)")
RUNS = 20
ACCEPTED = "accepted"
HELD = timedelta(minutes=20)
"""How long a pull request keeps the head of the line with the head GitHub took the update of:
GitHub makes the new head within seconds, so one it did not make by then is not coming."""


class Line(NamedTuple):
    """The head of the line of `base`, held by a pull request: GitHub took a merge of the base
    into it, or the user gave it the head, whose `word` it keeps (`BaseMerge.accept`). A pull
    request that holds no line has none, so it has no word either. On its record in
    `base-merges.json` it is `line`, `base` and `accepted`."""

    base: str
    word: str = ""


class Move(StrEnum):
    """What a move of `BaseMerge` does to the pull request's line (`after`)."""

    STAY = "stay"
    TAKE = "take"
    ACCEPT = "accept"
    DROP = "drop"


MOVES: dict[str, frozenset[Move]] = {
    "of": frozenset({Move.TAKE, Move.DROP}),
    "keep": frozenset({Move.STAY}),
    "release": frozenset({Move.DROP}),
    "accept": frozenset({Move.ACCEPT}),
    "keep_stuck": frozenset({Move.STAY}),
    "restart": frozenset({Move.STAY}),
    "reopen": frozenset({Move.STAY, Move.DROP}),
    "open_only": frozenset({Move.STAY, Move.DROP}),
}
"""Each move of `BaseMerge` that keeps or drops a record, and what it may do to the line: `of`
takes it where GitHub took the merge and drops it where GitHub refused, a new head or tip
(`keep`) and a queued run (`keep_stuck`, `restart`) leave it as it was, `accept` gives it with
the user's word, and `release`, a reopen (`reopen`) and a pull request no longer open
(`open_only`, which drops the whole record) end it. A move of the head or the tip is never one
that ends it."""


def after(held: Line | None, move: Move, base: str = "", word: str = "") -> Line | None:
    """The line once `move` is made: taking the line of the base it holds keeps the word."""
    if move is Move.STAY:
        return held
    if move is Move.TAKE:
        return Line(base, held.word if held and held.base == base else "")
    if move is Move.ACCEPT:
        return Line(base, word)
    return None


def line_of(record: object) -> Line | None:
    """The line a record holds, or None: a word with no line holds none."""
    if not isinstance(record, dict) or record.get("line") is not True:
        return None
    base, word = record.get("base"), record.get(ACCEPTED)
    held = isinstance(base, str)
    return Line(str(base), word if isinstance(word, str) else "") if held else None


def _with(record: dict, line: Line | None, said: bool) -> dict:
    """The record with `line` as its line: `said` writes `line` off where it holds none."""
    rest = {key: value for key, value in record.items() if key not in ("line", ACCEPTED)}
    if line is None:
        return {**rest, "line": False} if said else rest
    return {**rest, "line": True, "base": line.base, **({ACCEPTED: line.word} if line.word else {})}


class BaseMerge:
    """The branch updates `jmerge` asked GitHub for, one record for a pull request, kept in
    `base-merges.json` in the project's state: the head, the base tip, and what GitHub said. A
    record of the same head and tip is said again and not asked again. A failure to ask, such as
    a `gh` that did not run, a 5xx, a 403 or 429 rate limit, keeps no record, so a later run asks
    again, after the wait a rate limit sets (`backoff`): only GitHub's answer about the branch, a
    merge or a 409 or 422 refusal, is kept. The record keeps too whether each failed check was
    `repeated`. A record goes once its pull request is no longer open (`open_only`). A run that
    asks nothing, `--check`, keeps what it learns for itself alone."""

    def __init__(self, main: Path, state: Path, about: list[str], run: bool) -> None:
        self.main = main
        self.path = state / NAME
        self.about = about
        self.run = run
        self.records: dict | None = None
        self.repeated = Repeated(main, about)

    def known(self) -> dict:
        if self.records is None:
            self.records = store.read_dict(self.path)
        return self.records

    def of(
        self,
        one: ready.PullRequest,
        tip: str,
        asked: str = ready.BASE_MERGE_ASKED,
        due: str = ready.BASE_MERGE_DUE,
        *,
        line: bool = False,
    ) -> str:
        """Why the pull request waits once its base's merge into it is asked of GitHub: `asked`
        once it is asked, and `due` in a run that asks nothing. With `line`, a merge GitHub took
        puts the pull request at the head of its base's line (`holders`), in a run that asks
        nothing for that run alone."""
        was = self.was(one, tip)
        if was is not None and isinstance(was.get("said"), str):
            return was["said"]
        values = {"base": one.base, "tip": tip[:SHA]}
        if not self.run:
            if line:
                self._keep(one, tip, {}, "of", Move.TAKE)
            return due.format(**values)
        why, answered = self.ask(one)
        said = ready.BASE_MERGE_REFUSED.format(**values, why=why) if why else asked.format(**values)
        if answered:
            self._keep(one, tip, {"said": said}, "of", Move.TAKE if line and not why else Move.DROP)
        return said

    def holders(self, listed: Collection[ready.PullRequest]) -> dict[str, int]:
        """The pull request at the head of the line of each base, of the open ones `listed`:
        the one GitHub last took a merge of that base into because the base moved after its
        check (`cli.Repo.over_main`), until `release`. GitHub merges the base into no other green
        pull request into that base while it holds the line, so each merge costs one rerun. A
        pull request into another base holds no line for it: a stack branch whose base moved
        does not hold up every pull request into main. One whose head is still the head GitHub
        took the update of, `HELD` after it took it, gives its line up: GitHub made no new head,
        and no check of one is coming to end its wait."""
        known, now, held = self.known(), datetime.now().astimezone(), {}
        for one in sorted(listed, key=lambda one: one.number):
            was = known.get(str(one.number))
            line = line_of(was)
            if not isinstance(was, dict) or line is None or line.base != one.base:
                continue
            if one.base in held:
                continue
            if was.get("head") == one.head and now - _at(was) >= HELD:
                self.release(one.number)
                continue
            held[one.base] = one.number
        return held

    def release(self, number: int) -> None:
        """Take the pull request from the head of the line. Its record stays, so the update GitHub
        was asked for is not asked again at the same head and tip, but the user's word that gave
        it the line (`accept`) goes with the line."""
        was = self.known().get(str(number))
        if isinstance(was, dict) and (was.get("line") or ACCEPTED in was):
            self._put(str(number), was, "release", Move.DROP)

    def accept(self, one: ready.PullRequest, word: str) -> None:
        """Give the pull request the head of its base's line on the user's word,
        `accepted by <user> at <when> on <message>`, kept on its record until it merges or gives
        the line up (`release`). Its merged line carries it (`cli.Repo.merge`)."""
        was = self.known().get(str(one.number))
        record = was if isinstance(was, dict) else {}
        self._put(str(one.number), record, "accept", Move.ACCEPT, base=one.base, word=word)

    def accepted(self, number: int) -> str:
        """The user's word that gave the pull request the head of its line, or nothing."""
        line = line_of(self.known().get(str(number)))
        return line.word if line else ""

    def _put(
        self, number: str, record: dict, by: str, move: Move, base: str = "", word: str = ""
    ) -> None:
        """Keep `record` for the pull request, with its line once `by` makes `move` (`MOVES`):
        the one writer of a record's line."""
        assert move in MOVES[by], f"{by} may not {move} the line"
        was = self.known().get(number)
        line = after(line_of(was), move, base, word)
        said = move is Move.DROP or (isinstance(was, dict) and "line" in was)
        self.records = {**self.known(), number: _with(record, line, said)}
        if self.run:
            store.write_json(self.path, self.records)

    def stuck(self, one: ready.PullRequest) -> dict:
        """What `jmerge` did about a run GitHub kept queued at the pull request's head
        (`cli.Repo.unstuck`): `since`, when GitHub had queued the run it restarts, `asked`, when
        it first tried, `closed` once the close took, `took` once the reopen took too, `reopen`
        while that reopen is owed, `unopened` once it asks it no more, `why` the last failure,
        and `gave_up` once it gave up the line. Nothing for another head."""
        return _stuck(self.known().get(str(one.number)), one.head)

    def keep_stuck(self, one: ready.PullRequest, **kept: object) -> None:
        """Keep `kept` in what `stuck` says of the pull request's head, over what it said. A
        value of None drops its key."""
        self._keep_stuck(str(one.number), {**self.stuck(one), "head": one.head, **kept})

    def _keep_stuck(
        self, number: str, stuck: dict, by: str = "keep_stuck", move: Move = Move.STAY
    ) -> None:
        was = self.known().get(number)
        kept = {key: value for key, value in stuck.items() if value is not None}
        self._put(number, {**(was if isinstance(was, dict) else {}), "stuck": kept}, by, move)

    def restart(self, one: ready.PullRequest, check: str, since: datetime) -> str:
        """Close and reopen the pull request, so GitHub starts a new run of each of its
        workflows in their concurrency groups, which cancels the queued one: GitHub refuses to
        rerun a run it has not ended, and a cancel can leave it queued (#1028, 2026-11-04). Each
        step is kept as it takes: the try before the close, with the reopen owed, `closed` once
        the close took, and `took` once the reopen did, so a run that stops between two steps
        leaves a record the next run goes on from (`reopen`). Only a restart that took is spent:
        a close that failed is tried again on the next run. Return nothing, or why the close or
        the reopen failed."""
        now = datetime.now(UTC).isoformat()
        asked = self.stuck(one).get("asked") or now
        self.keep_stuck(
            one, since=since.isoformat(), asked=asked, reopen=True, url=one.url, check=check
        )
        closed = self.gh("pr", "close", str(one.number))
        if closed.returncode:
            self.keep_stuck(one, reopen=None, why=_said(closed))
            return _said(closed)
        self.keep_stuck(one, closed=now)
        why = self.reopened(one.number)
        self.keep_stuck(one, **({"why": why} if why else {"reopen": None, "took": now}))
        return why

    def reopen(self, numbers: Collection[str]) -> None:
        """Settle each restart whose reopen is owed, for `numbers`, the open pull requests. One
        that is open again owes none: its restart took where its close had, and is not spent
        where the close is not known to have taken. One that is closed is reopened, until
        `ready.RESTART_MINUTES` from the restart's first try, and then `unopened`: `jmerge`
        asks it no more, and says so on each run until it is open again (`unopened`). A
        reopened one holds the line no more, for another took it while it was closed."""
        now = datetime.now(UTC)
        for number, was in list(self.known().items()):
            stuck = _stuck(was)
            if not (stuck.get("reopen") or stuck.get("unopened")):
                continue
            if number in numbers:
                took = stuck.get("took") or (now.isoformat() if stuck.get("closed") else None)
                kept = {**stuck, "reopen": None, "unopened": None, "took": took}
                self._keep_stuck(number, kept, "reopen")
            elif stuck.get("unopened"):
                continue
            elif late(stuck.get("asked"), now):
                kept = {**stuck, "reopen": None, "unopened": True}
                self._keep_stuck(number, kept, "reopen", Move.DROP)
            elif why := self.reopened(number):
                self._keep_stuck(number, {**stuck, "why": why}, "reopen")
            else:
                kept = {**stuck, "reopen": None, "took": now.isoformat()}
                self._keep_stuck(number, kept, "reopen", Move.DROP)

    def unopened(self, numbers: Collection[str]) -> list[tuple[str, dict]]:
        """The number and `stuck` record of each pull request not in `numbers`, the open ones,
        that a restart left closed: its reopen still owed, or `unopened`."""
        return [
            (number, stuck)
            for number, was in self.known().items()
            if number not in numbers
            and ((stuck := _stuck(was)).get("reopen") or stuck.get("unopened"))
        ]

    def reopened(self, number: int | str) -> str:
        """Reopen the pull request, and return nothing, or why it was not."""
        said = self.gh("pr", "reopen", str(number))
        return _said(said) if said.returncode else ""

    def gh(self, *args: str) -> subprocess.CompletedProcess[str]:
        return backoff.run(
            "gh",
            *args,
            cwd=self.main,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )

    def repeats(self, one: ready.PullRequest, tip: str, check: str) -> bool:
        """Whether the pull request failed a same test of its own in its last two runs of
        `check` (`Repeated`), so that its base is not merged into it. The answer is kept for the
        head, the base tip and the check, so GitHub's logs are read again only once the head or
        the tip moves. An answer GitHub left unsettled, a call it did not answer or a run of the
        base still going, is not kept."""
        was = self.was(one, tip) or {}
        kept = was.get("repeated")
        if isinstance(kept, dict) and isinstance(kept.get(check), list):
            return bool(kept[check])
        ids, settled = self.repeated.of(one, check)
        if settled:
            known = kept if isinstance(kept, dict) else {}
            self.keep(one, tip, repeated={**known, check: sorted(ids)})
        return bool(ids)

    def was(self, one: ready.PullRequest, tip: str) -> dict | None:
        was = self.known().get(str(one.number))
        if isinstance(was, dict) and (was.get("head"), was.get("tip")) == (one.head, tip):
            return was
        return None

    def keep(self, one: ready.PullRequest, tip: str, **kept: object) -> None:
        """Keep `kept` in the record of the head and tip, over what it held. The line, with the
        user's word that gave it, stays across a new head or tip (`MOVES`), and what was done
        about a run GitHub kept queued (`stuck`) across a new tip at the same head: a move of
        the base starts no run at the head, so its restart stays spent."""
        self._keep(one, tip, kept, "keep", Move.STAY)

    def _keep(self, one: ready.PullRequest, tip: str, kept: dict, by: str, move: Move) -> None:
        now = datetime.now().astimezone()
        was = self.was(one, tip) or {}
        if stuck := self.stuck(one):
            was = {**was, "stuck": stuck}
        record = {**was, "head": one.head, "tip": tip, **kept, "at": f"{now:%Y-%m-%dT%H:%M:%S%z}"}
        self._put(str(one.number), record, by, move, base=one.base if move is Move.TAKE else "")

    def open_only(self, numbers: Collection[str]) -> None:
        """Drop the record of each pull request whose number is not in `numbers`, the open ones:
        a merged or closed pull request is never judged again, and its record would only grow the
        file."""
        known = self.known()
        kept = {number: was for number, was in known.items() if number in numbers or _owed(was)}
        if kept != known:
            self.records = kept
            if self.run:
                store.write_json(self.path, kept)

    def ask(self, one: ready.PullRequest) -> tuple[str, bool]:
        """Ask GitHub to merge the base into the branch. Return nothing, or why it did not, and
        whether GitHub answered: `gh api` ends its error line with `(HTTP <status>)`. It asks
        with `--include`, so that a refusal for the rate limit waits as long as GitHub's
        `retry-after` says (`backoff`)."""
        path = f"repos/{{owner}}/{{repo}}/pulls/{one.number}/update-branch"
        ran = backoff.run(
            *("gh", "api", "-X", "PUT", path, "-f", f"expected_head_sha={one.head}", "--include"),
            cwd=self.main,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )
        if not ran.returncode:
            return "", True
        if backoff.is_wait(ran.stderr or ""):
            return ran.stderr.strip(), False
        try:
            message = json.loads(backoff.body(ran.stdout)).get("message")
        except (ValueError, AttributeError):
            message = None
        lines = (ran.stderr or ran.stdout).strip().splitlines()
        why = str(message or (lines[-1] if lines else f"gh exited {ran.returncode}"))
        return why, bool(REFUSED.search(ran.stderr))


def _owed(was: object) -> bool:
    """Whether a restart left the pull request closed (`BaseMerge.restart`): its reopen is
    owed, or `jmerge` asks it no more."""
    stuck = _stuck(was)
    return stuck.get("reopen") is True or stuck.get("unopened") is True


def _stuck(was: object, head: str = "") -> dict:
    """The `stuck` part of a record, of `head` where one is given, or nothing."""
    kept = was.get("stuck") if isinstance(was, dict) else None
    if not isinstance(kept, dict) or (head and kept.get("head") != head):
        return {}
    return kept


def late(at: object, now: datetime) -> bool:
    """Whether `ready.RESTART_MINUTES` have passed since `at`, a time a restart kept. A time
    `jmerge` cannot read, as in a record from before it kept one, is long past."""
    try:
        then = datetime.fromisoformat(str(at))
    except ValueError:
        return True
    return now - then >= timedelta(minutes=ready.RESTART_MINUTES)


def _said(ran: subprocess.CompletedProcess[str]) -> str:
    """The last line `gh` wrote of why it failed."""
    lines = (ran.stderr or ran.stdout or "").strip().splitlines()
    return lines[-1] if lines else f"gh exited {ran.returncode}"


def _at(record: dict) -> datetime:
    """When the record was kept, or long ago where it says no time `jmerge` reads."""
    try:
        return datetime.strptime(str(record.get("at")), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


class Repeated:
    """The pytest ids a pull request failed in each of its last two check runs, less those that
    main's check at either run's base failed: main's latest run of the check started by the time
    the pull request's run started. A run's ids are the `FAILED <id>` lines of its log. Where
    GitHub does not answer, or a run of main is not known, it finds none, and the base is merged
    as before. A run of `jmerge` reads each list of runs and each log once."""

    def __init__(self, main: Path, about: list[str]) -> None:
        self.main = main
        self.about = about
        self.listed: dict[tuple[str, str, str], list[dict] | None] = {}
        self.logs: dict[str, frozenset[str] | None] = {}

    def of(self, one: ready.PullRequest, check: str) -> tuple[frozenset[str], bool]:
        """The ids, of the runs of the workflow named `check`, and whether the answer is
        settled for the head and the base's tip: GitHub answered each call, and no run it
        reads from was still going."""
        listed = self.runs(one.branch, check, "pull_request")
        if listed is None:
            return frozenset(), False
        settled = all(run.get("status") == "completed" for run in listed)
        last = [run for run in listed if run.get("status") == "completed"][-2:]
        if len(last) < 2 or any(run.get("conclusion") != "failure" for run in last):
            return frozenset(), settled
        logs = [self.failing(run) for run in last]
        if any(log is None for log in logs):
            return frozenset(), False
        shared = (logs[0] or frozenset()) & (logs[1] or frozenset())
        if not shared:
            return frozenset(), settled
        base = self.runs(one.base, check, "push")
        if base is None:
            return frozenset(), False
        if any(run.get("status") != "completed" and run["at"] <= last[-1]["at"] for run in base):
            settled = False
        mains = [run for run in base if run.get("conclusion") in ("success", "failure")]
        for run in last:
            before = [main for main in mains if main["at"] <= run["at"]]
            if not before:
                return frozenset(), settled
            if before[-1].get("conclusion") == "failure":
                failed = self.failing(before[-1])
                if failed is None:
                    return frozenset(), False
                shared -= failed
        return shared, settled

    def runs(self, branch: str, check: str, event: str) -> list[dict] | None:
        """The runs of the check's workflow on the branch, oldest first, the ended ones with
        none cancelled and those still going, or None where GitHub gave no list."""
        key = (branch, check, event)
        if key not in self.listed:
            self.listed[key] = self.list(*key)
        return self.listed[key]

    def list(self, branch: str, check: str, event: str) -> list[dict] | None:
        said = self.gh(
            "run",
            "list",
            "--branch",
            branch,
            "--workflow",
            check,
            "--event",
            event,
            "--limit",
            str(RUNS),
            "--json",
            "databaseId,status,conclusion,createdAt",
        )
        try:
            listed = json.loads(said or "")
        except ValueError:
            return None
        if not isinstance(listed, list):
            return None
        kept = []
        for run in listed:
            if not isinstance(run, dict) or run.get("conclusion") == "cancelled":
                continue
            try:
                at = datetime.fromisoformat(str(run.get("createdAt")))
            except ValueError:
                continue
            kept.append({**run, "at": at})
        return sorted(kept, key=lambda run: run["at"])

    def failing(self, run: dict) -> frozenset[str] | None:
        """The pytest ids the run failed, or `None` where GitHub gave no log."""
        number = str(run.get("databaseId"))
        if number not in self.logs:
            log = self.gh("run", "view", number, "--log-failed")
            self.logs[number] = None if log is None else frozenset(FAILED.findall(log))
        return self.logs[number]

    def gh(self, *args: str) -> str | None:
        ran = backoff.run(
            "gh",
            *args,
            cwd=self.main,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )
        return None if ran.returncode else ran.stdout
