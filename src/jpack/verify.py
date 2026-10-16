"""The check with no model that a pack's citations say what the notes claim.

For each citation it reads the subject repo at the cited commit: the commit is there, the
path is in it, the file has the cited lines, and the quote that follows the citation is on
them, with white space read as one space. Whoever wrote the notes, a scout or a crewmate,
this is the outside check on them: it can say no.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from jpack import Citation, citations, notes, said


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = ("git", "-c", "core.quotePath=false", "-C", str(repo), *args)
    return subprocess.run(command, capture_output=True, text=True, errors="replace")


def shallow(repo: Path) -> bool:
    return git(repo, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"


def fault(repo: Path, cited: Citation) -> str:
    """What is wrong with one citation, or nothing."""
    if git(repo, "cat-file", "-e", f"{cited.sha}^{{commit}}").returncode:
        more = ", and the checkout is shallow: fetch its history" if shallow(repo) else ""
        return f"{cited.note}: {cited}: no commit {cited.sha} in {repo}{more}"
    shown = git(repo, "show", f"{cited.sha}:{cited.path}")
    if shown.returncode:
        return f"{cited.note}: {cited}: no {cited.path} at {cited.sha}"
    lines = shown.stdout.splitlines()
    if cited.first < 1 or cited.last > len(lines) or cited.first > cited.last:
        return f"{cited.note}: {cited}: {cited.path} has {len(lines)} lines at {cited.sha}"
    there = said(" ".join(lines[cited.first - 1 : cited.last]))
    if cited.quote and said(cited.quote) not in there:
        return f'{cited.note}: {cited}: the line does not say "{cited.quote}"'
    return ""


def faults(pack: Path, repo: Path) -> list[str]:
    """One line per citation that does not hold, note by note."""
    found = []
    for name, text in notes(pack).items():
        for cited in citations(name, text):
            wrong = fault(repo, cited)
            if wrong:
                found.append(wrong)
    return found
