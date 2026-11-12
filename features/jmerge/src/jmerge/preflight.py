"""The rule preflight: a pull request that adds or tightens a test runs it on each open pull
request's head merged with it before it merges.

#1702 merged at 01:16Z on 2026-11-12 with a new rule, and within the half hour #1711, #1712, #1713
and #1716 went red on it, each crew told to fix the same thing alone. So before `jmerge` merges a
pull request whose change adds or edits a test file (`RULE`, the repo's guard tests among them),
it runs those tests, with the command the state's `rule-preflight` file names (`RULES` set to
their paths), on the tree of its head merged with each other open pull request that a brief names.
One that fails there holds it (`ready.RULE_BREAKS`) until its head carries the fix (an exemption
or a changed rule), so every run passes, or its Result names each failing pull request on a
`Breaks:` line. It then merges with a note that names them (`lines.rule_breaks`), and jbus tells
each one's crew in the pass that reads it (`jbus.rulebreaks`).

The tests first run on the head alone: where they fail there, this machine does not run them as
CI did, the preflight proves nothing, and nothing is held. A failure on a merged tree is the other
pull request's own red, and holds nothing, where the tests it has fail at its head alone too.
A tree that conflicts, cannot be built or runs past `LIMIT_SECONDS` holds nothing: that pull
request's crew rebases once the rule lands, and the guards on the merged tree stand behind it.

A run's result depends on the two heads alone, so `rule-trees.json` keeps it until either moves,
and a run of the rule's head on an older head of the other counts until that head is run, so a
crew's push holds no rule. The runs of one `jmerge` run spend at most `RUN_SECONDS`, inside a
full test slot as the guards do (`treeguards.run_guards`); a pull request never run yet waits for
the next run (`ready.RULE_UNRUN`). A repo with no `rule-preflight` file runs none of this.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from jmerge import lines, ready, treeguards
from jsettings import store

NAME = "rule-preflight"
KEPT = "rule-trees.json"
TREE = "rule-tree"
RULE = re.compile(r"(^|/)test_[^/]*\.py$")
"""A test file: a change to one adds or tightens a rule, or a guard, of the repo's tests."""
NAMED = re.compile(r"^Breaks:(.*)$", re.MULTILINE)
LIMIT_SECONDS = 60
"""How long the tests may run on one tree: only the changed test files run."""
RUN_SECONDS = 90
"""The seconds of preflight runs one `jmerge` run spends before it starts no more. Apart from the
guards' `treeguards.RUN_SECONDS`, so a preflight never takes the guards' time; with one run at its
limit past it, the two stay inside the 17 minutes jbus gives `jmerge`."""
PASSES, FAILS, OWN = "passed", "failed", "its own"
CONFLICT, STOPPED, UNBUILT = "conflict", "stopped", "unbuilt"
AGAIN = frozenset({STOPPED, UNBUILT})
"""The results a loaded machine or a slot that would not start can give: each holds nothing, and
the next run with time left runs it again, so one such run does not leave a rule unrun."""


def rules_of(one: ready.PullRequest) -> tuple[str, ...]:
    """The test files the pull request adds or changes and keeps."""
    return tuple(sorted(p for p in one.files if RULE.search(p) and p not in one.removed))


def named(text: str) -> frozenset[int]:
    """The pull requests the brief's `Breaks:` lines name, by `#<number>`."""
    return frozenset(int(n) for line in NAMED.findall(text) for n in re.findall(r"#(\d+)", line))


@dataclass(frozen=True)
class Ran:
    """What one run of the rules on a tree said: `PASSES`, `FAILS`, or why it holds nothing, and
    the test that failed."""

    said: str
    test: str = ""


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


class Preflight:
    """The rule preflight of one `jmerge` run. `check` is True for `--check`, which runs the
    tests too, in a worktree of its own, so its `wait` line names the pull requests a rule
    breaks; both keep what they ran in `KEPT`."""

    def __init__(self, main: Path, state: Path, check: bool) -> None:
        self.main = main
        self.state = state
        self.path = state / KEPT
        self.tree = state / (TREE + ("-check" if check else ""))
        self.command = treeguards.command_of(state, NAME)
        self.spent = 0
        self.slotless = False
        self.records: dict | None = None

    def known(self) -> dict:
        if self.records is None:
            self.records = store.read_dict(self.path)
        return self.records

    def keep(self, number: int, record: dict) -> None:
        self.records = {**self.known(), str(number): record}
        store.write_json(self.path, self.records)

    def open_only(self, numbers: set[str] | dict[str, str]) -> None:
        """Drop the record of each pull request that is no longer open."""
        known = self.known()
        kept = {number: was for number, was in known.items() if number in numbers}
        if kept != known:
            self.records = kept
            store.write_json(self.path, kept)

    def of(
        self, one: ready.PullRequest, others: Sequence[ready.PullRequest], text: str
    ) -> tuple[str, str]:
        """Why the pull request waits on the rules it adds or tightens, or nothing, and the note
        of its merge where its brief names the pull requests they break. `others` are the open
        pull requests a brief names, with their heads in the main checkout."""
        rules = rules_of(one)
        if not self.command or not rules:
            return "", ""
        was = self.known().get(str(one.number))
        same = isinstance(was, dict) and (was.get("head"), was.get("rules")) == (
            one.head,
            list(rules),
        )
        record: dict = was if same and isinstance(was, dict) else {}
        record |= {"head": one.head, "rules": list(rules)}
        shown = " ".join(rules)
        rows = [other for other in others if self.apart(one, other)]
        if not rows:
            return "", ""
        again = record.get("alone") in AGAIN
        if "alone" not in record or again:
            alone = self.run(one.head, rules) if self.room() else None
            if alone is None and not again:
                return ready.RULE_UNRUN.format(tests=shown, ran=0, open=len(rows)), ""
            if alone is not None:
                record["alone"] = alone.said
                self.keep(one.number, record)
        if record["alone"] != PASSES:
            return "", ""
        on = record.get("on")
        if not isinstance(on, dict):
            on = record["on"] = {}
        def owed(row: ready.PullRequest) -> bool:
            seen = on.get(str(row.number))
            return isinstance(seen, dict) and seen.get("head") == row.head

        for other in sorted(rows, key=lambda row: (owed(row), row.number)):
            seen = on.get(str(other.number)) or {}
            if owed(other) and seen.get("said") not in AGAIN:
                continue
            if not self.room():
                break
            ran = self.pair(one, other, rules)
            if ran is None:
                break
            on[str(other.number)] = {"head": other.head, "said": ran.said, "test": ran.test}
            self.keep(one.number, record)
        failing = [row for row in rows if (on.get(str(row.number)) or {}).get("said") == FAILS]
        if failing and not {row.number for row in failing} <= named(text):
            breaks = ", ".join(
                f"#{row.number} ({on[str(row.number)].get('test') or treeguards.UNNAMED})"
                for row in failing
            )
            return ready.RULE_BREAKS.format(tests=shown, breaks=breaks), ""
        ran = sum(str(row.number) in on for row in rows)
        if ran < len(rows):
            return ready.RULE_UNRUN.format(tests=shown, ran=ran, open=len(rows)), ""
        if failing:
            return "", lines.rule_breaks(rules, [row.number for row in failing])
        return "", ""

    def apart(self, one: ready.PullRequest, other: ready.PullRequest) -> bool:
        """Whether `other` is a pull request of its own beside `one`: neither head holds the
        other's, as a stacked one does, whose own check already runs the rule."""
        if other.number == one.number:
            return False
        return all(
            _git(self.main, "merge-base", "--is-ancestor", a, b).returncode
            for a, b in ((other.head, one.head), (one.head, other.head))
        )

    def room(self) -> bool:
        return self.spent < RUN_SECONDS and not self.slotless

    def pair(
        self, one: ready.PullRequest, other: ready.PullRequest, rules: tuple[str, ...]
    ) -> Ran | None:
        """The rules run on `one`'s head merged with `other`'s, or None where no slot came free.
        A failure there is `OWN` where the rules `other` has fail at its head alone too."""
        merged = _git(self.main, "merge-tree", "--write-tree", one.head, other.head)
        tree = merged.stdout.split()[:1]
        if merged.returncode == 1 and tree:
            return Ran(CONFLICT)
        message = f"jmerge: #{one.number} merged with #{other.number} for its rules"
        made = (
            None
            if merged.returncode or not tree
            else _git(
                self.main,
                *treeguards.IDENTITY,
                "commit-tree",
                tree[0],
                "-p",
                one.head,
                "-p",
                other.head,
                "-m",
                message,
            )
        )
        if made is None or made.returncode:
            return Ran(UNBUILT)
        ran = self.run(made.stdout.strip(), rules)
        if ran is None or ran.said != FAILS:
            return ran
        theirs = tuple(rule for rule in rules if self.has(other.head, rule))
        if theirs:
            alone = self.run(other.head, theirs)
            if alone is None:
                return None
            if alone.said == FAILS:
                return Ran(OWN, ran.test)
        return ran

    def has(self, commit: str, path: str) -> bool:
        return not _git(self.main, "cat-file", "-e", f"{commit}:{path}").returncode

    def run(self, commit: str, rules: tuple[str, ...]) -> Ran | None:
        """Run the rules on `commit` in the worktree at `TREE`, or None where no full test slot
        came free in `treeguards.SLOT_SECONDS`. Each rule is one `commit` has."""
        self.clear()
        added = _git(self.main, "worktree", "add", "--detach", "-q", str(self.tree), commit)
        if added.returncode:
            return Ran(UNBUILT)
        try:
            ran = treeguards.run_guards(
                self.command, self.tree, {"RULES": " ".join(rules)}, LIMIT_SECONDS
            )
        finally:
            self.clear()
        if ran is None:
            self.slotless = True
            self.spent += treeguards.SLOT_SECONDS
            return None
        if isinstance(ran, str):
            return Ran(UNBUILT)
        self.spent += ran.waited + ran.seconds
        if ran.code is None:
            return Ran(STOPPED)
        return Ran(FAILS, treeguards.guard(ran.said)) if ran.code else Ran(PASSES)

    def clear(self) -> None:
        _git(self.main, "worktree", "remove", "--force", str(self.tree))
        shutil.rmtree(self.tree, ignore_errors=True)
        _git(self.main, "worktree", "prune")
