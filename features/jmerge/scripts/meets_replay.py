"""Replay the `Meets the brief:` rule over the homes' real task files, for the pull request of
brief-verdict-gate: how many rows whose last `Meets the brief:` line says `no` the rule
(`jbriefs.meets`) would have held, how many of those were later fixed or reverted, and how many
it would hold wrongly.

The rows are the week audit's (`week-audit-synth/synth.py` N9: a merged row of the base or audit
week whose last `Meets the brief:` line in its task file starts `no`), and every other row of
the home `--home` whose last such line starts `no`.

Those reviews were written in free text, before the typed line, so the replay reads each one's
first word, `yes` or `no`, and judges with the rule's own reading of the rounds
(`meets.last_round`): the last round, at the head and of the kind of the last section that ran.

- `held`: a section of the last round says `no`. The rule holds it.
- `stale`: the last line of the file says `no`, and the last round, at a later head or a scoped
  pass, says `yes`: an earlier round's `no` that the rule does not read.
- `unread`: a section of the last round has no `Meets the brief:` line, and none says `no`. The
  rule holds it too, as `meets-unread`, for want of a line, not for a `no`.
- `later fixed`: of the held, those that another brief of the same project names, by its slug or
  its pull request, in its head, where that brief's own pull request is a later one (a higher
  number): a follow-up row, or a fix of what it left.
- `reverted`: of the held, those whose pull request a merged pull request reverts, by its title
  in the audit's `prs.jsonl` or a commit subject of `--git`'s `origin/main`.
- `merged`: from the audit's `prs.jsonl`, and the home's `merge.log` (`merged <number> <slug>`).
- `wrongly`: of the held, those whose `no` lines are all about CI still running or a proof only
  the merge or the review gives, the case the brief writes as `waiting` or `after-merge`.

    uv run python features/jmerge/scripts/meets_replay.py \\
        --homes ~/.local/state/home --home jstack \\
        --data ~/.local/state/home/jstack/reports/week-audit/week-audit-data --git .
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from jbriefs import findings, meets
from jsettings.brief import head_lines

HELD, STALE, UNREAD, YES = "held", "stale", "unread", "yes"
WEEKS = ("base", "audit")
_WORD = re.compile(r"\s*(yes|no)\b", re.I)
WAITING = re.compile(
    r"still running|\bis running\b|(check|run|job)s? (is |are )?(queued|pending)|waits on CI"
    r"|not (yet )?shown at this head|no run on|after (the |it )?merge|once (it is )?merged"
    r"|post-merge|the review itself",
    re.I,
)
"""A `no` line about CI still running at review time or a proof only the merge gives."""
FAULT = re.compile(
    r"\bred\b|fail|timed out|finding|not met|does not hold|at risk|crossed|wrong|missing", re.I
)
"""Words of a `no` line that also names a fault, which no wait excuses."""


@dataclass(frozen=True)
class Row:
    project: str
    slug: str
    path: Path
    text: str
    url: str
    audit: bool = False


def last_line(text: str) -> str:
    said = [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.lstrip("-* ").startswith(meets.LABEL)
    ]
    return said[-1] if said else ""


def word_of(line: str) -> str:
    found = _WORD.match(line)
    return found[1].lower() if found else ""


def judged(text: str) -> tuple[str, list[str]]:
    """The rule's reading of the free-text rounds: `HELD`, `STALE`, `UNREAD` or `YES`, and the
    `no` lines of the last round."""
    last = meets.last_round(findings.triage(text))
    said = [meets.lines_of(text, one) for one in last]
    words = [word_of(lines[0].removeprefix(meets.LABEL)) if lines else "" for lines in said]
    nos = [lines[0] for lines, word in zip(said, words, strict=True) if word == "no"]
    if nos:
        return HELD, nos
    if not last or "" in words:
        return UNREAD, []
    return (STALE if word_of(last_line(text)) == "no" else YES), []


def url_of(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Branch:") and line.split()[-1].startswith("http"):
            return line.split()[-1]
    return ""


def number_of(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1] if "/pull/" in url else ""


def task_files(homes: Path) -> list[tuple[str, Path]]:
    found = []
    for path in sorted(homes.glob("*/tasks/*.md")) + sorted(homes.glob("*/*/tasks/*.md")):
        found.append((path.relative_to(homes).parts[0], path))
    return found


def rows_of(homes: Path, home: str, data: Path) -> list[Row]:
    audited = {}
    for line in (data / "rows.jsonl").read_text().splitlines():
        one = json.loads(line)
        merged = one.get("t_merged") or one.get("pr_merged_at")
        if one.get("week") in WEEKS and merged:
            audited[(one["project"], one["slug"])] = True
    rows = []
    for project, path in task_files(homes):
        text = path.read_text(errors="replace")
        if word_of(last_line(text)) != "no":
            continue
        audit = (project, path.stem) in audited
        if audit or project == home:
            rows.append(Row(project, path.stem, path, text, url_of(text), audit))
    return rows


def named_later(row: Row, briefs: list[tuple[str, Path, str, str]]) -> bool:
    number = number_of(row.url)
    if not number:
        return False
    marks = [re.compile(rf"(?<![\w-]){re.escape(row.slug)}(?![\w-])")]
    marks.append(re.compile(rf"#{number}\b|{re.escape(row.url)}"))
    for project, path, head, url in briefs:
        later = number_of(url)
        if project != row.project or path == row.path or repo_of(url) != repo_of(row.url):
            continue
        if not later or int(later) <= int(number):
            continue
        if any(one.search(head) for one in marks):
            return True
    return False


def repo_of(url: str) -> str:
    """The repo of a pull request's address, `https://github.com/<owner>/<repo>`: a number is a
    pull request of one repo, and a renamed repo's numbers start again."""
    return url.split("/pull/")[0]


def reverted(row: Row, prs: list[dict], subjects: dict[str, list[str]]) -> bool:
    number = number_of(row.url)
    if not number:
        return False
    own = next((one for one in prs if one.get("url") == row.url), None)
    title = (own or {}).get("title", "")
    repo = repo_of(row.url)
    said = [one.get("title") or "" for one in prs if repo_of(one.get("url") or "") == repo]
    said += subjects.get(repo, [])
    return any(
        "revert" in one.lower() and (re.search(rf"#{number}\b", one) or (title and title in one))
        for one in said
    )


def merged_numbers(homes: Path, home: str) -> set[str]:
    log = homes / home / "merge.log"
    lines = log.read_text(errors="replace").splitlines() if log.exists() else []
    return {line.split()[3] for line in lines if line.split()[2:3] == ["merged"]}


def wrongly(nos: list[str]) -> bool:
    """Whether every `no` line is about a wait alone (`WAITING`) and names no fault (`FAULT`). It
    reads free text, so it is a count to check by hand, not a verdict."""
    return bool(nos) and all(WAITING.search(one) and not FAULT.search(one) for one in nos)


def replay(homes: Path, home: str, data: Path, git: Path | None) -> dict[str, Counter[str]]:
    rows = rows_of(homes, home, data)
    prs = [json.loads(line) for line in (data / "prs.jsonl").read_text().splitlines()]
    merged = {one["url"] for one in prs if one.get("merged_at")}
    logged = merged_numbers(homes, home)
    subjects: dict[str, list[str]] = {}
    if git is not None:
        said = [
            subprocess.run(["git", "-C", str(git), *argv], capture_output=True, text=True).stdout
            for argv in (("remote", "get-url", "origin"), ("log", "--format=%s", "origin/main"))
        ]
        remote = (
            said[0].strip().removesuffix(".git").replace("git@github.com:", "https://github.com/")
        )
        subjects[remote] = said[1].splitlines()
    briefs = []
    for project, path in task_files(homes):
        text = path.read_text(errors="replace")
        briefs.append((project, path, "\n".join(head_lines(text)), url_of(text)))
    counts: dict[str, Counter[str]] = {}
    for row in rows:
        group = "audit" if row.audit else f"{home} other"
        tally = counts.setdefault(group, Counter())
        tally["rows"] += 1
        home_merged = row.project == home and number_of(row.url) in logged
        tally["merged"] += row.url in merged or row.audit or home_merged
        state, nos = judged(row.text)
        tally[state] += 1
        if state == HELD:
            tally["later fixed"] += named_later(row, briefs)
            tally["reverted"] += reverted(row, prs, subjects)
            tally["wrongly"] += wrongly(nos)
    return counts


ORDER = ("rows", "merged", HELD, "later fixed", "reverted", "wrongly", STALE, UNREAD, YES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--homes", type=Path, required=True, help="the directory of the homes")
    parser.add_argument("--home", required=True, help="the home whose other rows are replayed")
    parser.add_argument("--data", type=Path, required=True, help="the week audit's data folder")
    parser.add_argument("--git", type=Path, help="a checkout of the home's repo, for reverts")
    args = parser.parse_args(argv)
    counts = replay(args.homes.expanduser(), args.home, args.data.expanduser(), args.git)
    for group, tally in counts.items():
        print(f"{group}: " + ", ".join(f"{name} {tally[name]}" for name in ORDER))
    return 0


if __name__ == "__main__":
    sys.exit(main())
