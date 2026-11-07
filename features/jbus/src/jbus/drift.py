"""Drift (S4): the user's standing words, each with a probe that says whether jstack still keeps it.

A standing word is something the user said once that holds from then on. `PROBES` is the registry,
one `Probe` for each word that still holds, with the id of the message it was said in and when.
Each probe reads the code or the files the word is about, never a person's account of them, and
counts the breaches it finds: 0 is `held`, more is `broken`. A probe that raises is `unrun`, and
counts as broken, since a word nobody could check is not known to hold.

- `D1`, the later reviews' warnings (the user, 2026-11-01, 6494a676, built as #836): a warning a
  review after the first finds is kept for the day's follow-up row. `jbriefs.findings.triage`
  routes the warning of a fixed brief's later review `KEPT`, and the pass has the step that keeps
  it, `daywarnings.keep`.
- `D2`, no standing-rule files (2026-11-02, 819ce35a98): `jbus.rules.found` finds no
  `standing.md` with text and no auto-memory file, for any project. It replaces the word of
  2026-10-26, at most three rules in memory, which the telemetry-plane scout retired.
- `D3`, no Mermaid in ketchup (2026-10-23, 49113c9d95): the ketchup skill's file, as
  `skills.json` names it in the tree jbus runs from, says nothing of Mermaid, in any case.
- `D4`, no entries in a home's notes (2026-10-28, 3d97639078): no home of a project, nor any of
  its scopes, has a dated line in its notes file (`jbus.notes.FILE`), as `jbus.notes` reads
  one. Every dated line counts, not only those since the word, since `jbus.notes` asks for each
  to move out.
- `D6`, jbus merges with jmerge (2026-10-19, 3f5a838c64): each pull request that merged in the
  `WINDOW` before the run, into the project's default branch or one of its `merge_bases`, has
  jmerge's `merged` line in the home's `merge.log`. It reads every merge `merged.json` keeps,
  which is each one GitHub lists, queue row or not, so a dependabot pull request or one with no
  brief counts. A line is the merge's only where it names its number and its commit: jmerge
  writes the merge commit, or the head where GitHub gave none, so a line of the same number from
  another repo or another era does not hide a merge. A pull request merged by hand has none, and
  GitHub names the same account for both, so a merge by the user counts here as well as one by
  a crew. Each breach is named, with its project, number, base, merge time and head.

D5, jmerge keeping integration bases, was retired by the user's word of 2026-11-02 (780f8c01).

`run` runs every probe and appends one line for each to `drift.jsonl` in jbus's state, all
under one `at`: the probe, its word's message id, its status, the breaches it found, the commit
of the tree it read and, for an unrun probe, the name of what it raised and no more. A probe
that names its breaches (`D6`) writes them too, under `breaches`. The
telemetry store keeps the lines (`jbus.telemetry.records`), and the KPI is the probes not held
in each week's last run (`weekly_drift`). The pass's chore runs the probes at most once a day
of the user's, and says which words are not held, with the breaches each one names.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import jbus
from jbriefs import findings, skills
from jbriefs import home as homes
from jbus import history, notes, rules, verbs

FILE = "drift.jsonl"
WINDOW = timedelta(days=7)
"""How far back `D6` reads merges: a week, so the week's last run reads the whole week."""
Status = Literal["held", "broken", "unrun"]
_MERGED = re.compile(r"^\S+ \S+ merged #?(\d+) \S+ ([0-9a-f]{40})\b")
_HEAD, _FIX = "a" * 40, "b" * 40
LATER_WARNING = f"""# drift-d1: a task
Review: review

## Review
By: reviewer model high #1
Verdict: findings
Head: {_HEAD}
Findings:
- warning a.py:3 the loop reads the list twice (bucket: Act on)

## Review
By: reviewer model high #1
Verdict: findings
Scope: range-diff x..{_HEAD} x..{_FIX}
Head: {_FIX}
Findings:
- warning c.py:7 a test asserts what the code computed (bucket: Act on)
"""
"""A brief whose first review is fixed and whose scoped pass of the fix finds one warning."""


def _steps() -> set[str]:
    """The names of the pass's steps, of every slot."""
    return {step.name for found in verbs.ranked(jbus.__path__).values() for step in found}


@dataclass(frozen=True)
class Ground:
    """What a probe reads: the config, the run's time, the source tree jbus runs from, and the
    code the `D1` probe runs, which a test can give in place of jbus's own."""

    config: jbus.Config
    now: datetime
    root: Path
    triage: Callable[[str], findings.Triage] = findings.triage
    steps: Callable[[], set[str]] = field(default=_steps)


Breach = dict[str, str | int]
"""A breach a probe names: for `D6`, a merge's project, number, base, merge time and head."""


@dataclass(frozen=True)
class Probe:
    """A standing word: its name, the id of the message it was said in, when, what it says, and
    the check that counts its breaches, or names each one."""

    name: str
    word: str
    said: str
    says: str
    check: Callable[[Ground], int | list[Breach]]


def _later_warnings(ground: Ground) -> int:
    said = ground.triage(LATER_WARNING)
    later = [
        one
        for one in said.findings
        if one.severity == "warning" and said.sections[one.lead.section].later
    ]
    if not later:
        raise LookupError("the fixed brief has no later review's warning")
    wrong = sum(one.route != findings.KEPT for one in later)
    return wrong + ("daywarnings.keep" not in ground.steps())


def _rule_files(ground: Ground) -> int:
    return sum(len(rules.found(ground.config, one)) for one in ground.config.projects)


def _mermaid(ground: Ground) -> int:
    text = skills.where("skill", "ketchup", ground.root).read_text()
    return sum("mermaid" in line.lower() for line in text.splitlines())


def _notes(ground: Ground) -> int:
    count = 0
    for project in ground.config.projects:
        home = ground.config.home(project)
        for directory in [home, *(scope for scope, _, _ in homes.scopes(home))]:
            path = directory / notes.FILE
            if path.is_file():
                count += len(notes.dated(path.read_text(errors="replace")))
    return count


def _default_branch(checkout: Path) -> str:
    """The branch `origin/HEAD` names in the checkout, or `main` where git names none."""
    try:
        done = subprocess.run(
            [
                "git",
                "-C",
                str(checkout),
                "symbolic-ref",
                "-q",
                "--short",
                "refs/remotes/origin/HEAD",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "main"
    return done.stdout.strip().removeprefix("origin/") or "main"


def _merged_by_hand(ground: Ground) -> list[Breach]:
    since = ground.now - WINDOW
    found: list[Breach] = []
    for project in ground.config.projects:
        state, home = ground.config.state(project), ground.config.home(project)
        merged = state / "merged.json"
        if not merged.is_file():
            continue
        bases = {_default_branch(project.checkout), *project.merge_bases}
        log = home / "merge.log"
        lines = log.read_text(errors="replace").splitlines() if log.is_file() else []
        by_jmerge = {(int(hit[1]), hit[2]) for line in lines if (hit := _MERGED.match(line))}
        pulls = {
            pull.get("number"): pull
            for pull in json.loads(merged.read_text()).values()
            if isinstance(pull, dict)
        }
        for number, pull in sorted(pulls.items(), key=lambda one: str(one[0])):
            at, base = pull.get("mergedAt"), pull.get("baseRefName")
            if not isinstance(at, str):
                continue
            when = datetime.fromisoformat(at.replace("Z", "+00:00"))
            if not since <= when <= ground.now or base not in bases:
                continue
            head = str(pull.get("headRefOid") or "")
            commits = {head, str((pull.get("mergeCommit") or {}).get("oid") or "")} - {""}
            if not any((number, commit) in by_jmerge for commit in commits):
                found.append(
                    {
                        "project": project.name,
                        "number": number,
                        "base": base,
                        "mergedAt": at,
                        "head": head,
                    }
                )
    return found


PROBES: tuple[Probe, ...] = (
    Probe(
        "D1",
        "6494a676",
        "2026-11-01",
        "a later review's warning collects in one follow-up row a day",
        _later_warnings,
    ),
    Probe(
        "D2",
        "819ce35a98",
        "2026-11-02",
        "no standing rule in a standing.md or an auto-memory file",
        _rule_files,
    ),
    Probe("D3", "49113c9d95", "2026-10-23", "no Mermaid in ketchup", _mermaid),
    Probe("D4", "3d97639078", "2026-10-28", "homes add no entries to their notes file", _notes),
    Probe(
        "D6",
        "3f5a838c64",
        "2026-10-19",
        "jbus merges with jmerge: each merge in the last week has jmerge's line",
        _merged_by_hand,
    ),
)


@dataclass(frozen=True)
class Finding:
    """A probe's result in one run: its status, the breaches it found, and for an unrun probe the
    name of what it raised."""

    probe: Probe
    status: Status
    found: int | None
    error: str | None = None
    breaches: tuple[Breach, ...] | None = None


def probe(one: Probe, ground: Ground) -> Finding:
    """Run one probe: held where it finds no breach, unrun where it raises."""
    try:
        checked = one.check(ground)
    except Exception as raised:
        return Finding(one, "unrun", None, type(raised).__name__)
    if isinstance(checked, list):
        return Finding(one, "broken" if checked else "held", len(checked), None, tuple(checked))
    return Finding(one, "broken" if checked else "held", checked)


def _sha(root: Path) -> str | None:
    """The commit the tree is at, or None where it is not a checkout git can read."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


def run(ground: Ground, probes: Iterable[Probe] = PROBES) -> list[Finding]:
    """Run every probe and append one line for each to `drift.jsonl`, all under one `at`."""
    found = [probe(one, ground) for one in probes]
    at = ground.now.astimezone(UTC).isoformat(timespec="seconds")
    sha = _sha(ground.root)
    lines = [
        {
            "at": at,
            "probe": one.probe.name,
            "word": one.probe.word,
            "status": one.status,
            "found": one.found,
            "sha": sha,
            "error": one.error,
        }
        | ({} if one.breaches is None else {"breaches": list(one.breaches)})
        for one in found
    ]
    path = ground.config.state_dir / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as handle:
        handle.write("".join(json.dumps(line, sort_keys=True) + "\n" for line in lines))
    return found


def ran_today(config: jbus.Config, now: datetime) -> bool:
    """Whether `drift.jsonl` holds a run of the user's day of `now`."""
    held = history.held(config.state_dir / FILE, lambda one: one.get("at"), history.TAIL)
    stamps = [one for one in held if isinstance(one, str)]
    if not stamps:
        return False
    last = datetime.fromisoformat(max(stamps))
    return config.user.local(last).date() == config.user.local(now).date()


def _ground(config: jbus.Config, now: datetime) -> Ground:
    return Ground(config, now, skills.root())


def _named(one: Finding) -> str:
    """A probe not held, with the breaches it names: `D6 (jstack #1035, jstack #1036)`."""
    if not one.breaches:
        return one.probe.name
    named = ", ".join(f"{breach['project']} #{breach['number']}" for breach in one.breaches)
    return f"{one.probe.name} ({named})"


def _chore(config: jbus.Config, _, now: datetime, say: Callable[[str], None]) -> None:
    if not ran_today(config, now):
        found = run(_ground(config, now))
        broken = [_named(one) for one in found if one.status != "held"]
        if broken:
            say(
                f"drift: {len(broken)} of {len(found)} standing words not held: {', '.join(broken)}"
            )


CHORES = (verbs.Chore(34, "the probes of the standing words, once a day", _chore),)
