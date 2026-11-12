"""`jbus home status --home` under `## merged` shows each merge line a home has not read once,
also after a hand cuts merge.log. The home's mark is the one the home skill's merge step leaves in
`merge-seen`: the test runs that block as the skill gives it, then reads `jbus home status`."""

from __future__ import annotations

import os
import re
import subprocess
import textwrap

import pytest

from jbus import homestatus
from testing.paths import REPO

STEP = REPO / "features" / "home" / "skills" / "home" / "merging-a-pull-request-that-is-ready.md"
SCOPE = "beta"


def merged(n: int) -> str:
    return f'2026-10-12 13:4{n} merged {n} {SCOPE}-{n} abc{n} "feat {n}", revert: gh pr revert x{n}'


def the_merge_step() -> str:
    """The merge step's block, as the home skill gives it."""
    found = re.findall(r"^```sh\n(.*?)^```$", STEP.read_text(), re.M | re.S)
    (step,) = [text for text in found if "first}/merge-seen" in text]
    return textwrap.dedent(step)


class Repo:
    """A repo's state with one scoped home, whose briefs are those of every merge line."""

    def __init__(self, tmp_path, monkeypatch):
        self.state = tmp_path / "demo"
        self.home = self.state / SCOPE
        self.home.mkdir(parents=True)
        (self.home / "plan.md").write_text("# a plan\n")
        (self.home / "home-id").write_text("mcp:the-scoped-home\n")
        (self.home / "read-seen").write_text("")
        (self.state / "tasks").mkdir()
        for n in range(1, 6):
            (self.state / "tasks" / f"{SCOPE}-{n}.md").write_text(f"# {SCOPE}-{n}\nHome: {SCOPE}\n")
        self.log = self.state / "merge.log"
        self.log.write_text("")
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        (self.bin / "gh").write_text("#!/bin/sh\nexit 1\n")
        (self.bin / "gh").chmod(0o755)
        self.cwd = tmp_path
        monkeypatch.setattr(homestatus.paths, "repo_name", lambda: self.state.name)

    def merges(self, *ns: int) -> None:
        with self.log.open("a") as log:
            log.writelines(f"{merged(n)}\n" for n in ns)

    def cut(self, keep: int) -> None:
        """A hand cuts merge.log to its last `keep` lines."""
        lines = self.log.read_text().splitlines(keepends=True)
        self.log.write_text("".join(lines[len(lines) - keep :]))

    def merge_step(self) -> list[str]:
        """The home runs the skill's merge step, which moves its mark: the merge lines it showed."""
        top = f'H={self.state}\nM={self.home}\nwhose() {{ echo "$M"; }}\n'
        ran = subprocess.run(
            ["sh", "-c", top + the_merge_step()],
            capture_output=True,
            text=True,
            cwd=self.cwd,
            env={**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}"},
            check=True,
        )
        return [line for line in ran.stdout.splitlines() if line.startswith("merged ")]

    def status(self) -> list[str]:
        """The lines `jbus home status` prints under `## merged`."""
        said = homestatus.run(str(self.home), installed=False, only_gates=False)
        part = said[said.index("## merged") + 1 :]
        return [line for line in part[: part.index("## to read")] if " merged " in line]


@pytest.mark.parametrize(
    ("read", "new", "cut_to"),
    [((1, 2, 3), (4,), 2), ((1, 2), (4, 5), 2)],
    ids=["cut below the mark, keeping a line seen", "cut to the mark's length, all unseen"],
)
def test_a_merge_line_is_shown_once_after_a_hand_cuts_merge_log(
    tmp_path, monkeypatch, read, new, cut_to
):
    """The home's merge step read every line up to the last of `read`; jmerge appends `new`; a
    hand cuts merge.log to its last `cut_to` lines. `jbus home status` shows each new line the
    cut kept, once, and no line the home saw before; once the merge step has shown them, neither
    shows them again."""
    repo = Repo(tmp_path, monkeypatch)
    repo.merges(read[0])
    assert repo.merge_step() == []
    repo.merges(*read[1:])
    assert repo.merge_step() == [merged(n)[17:] for n in read[1:]]
    repo.merges(*new)
    repo.cut(cut_to)
    kept = [n for n in new if merged(n) in repo.log.read_text()]
    assert kept

    assert repo.status() == [merged(n) for n in kept]
    assert repo.merge_step() == [merged(n)[17:] for n in kept]
    assert repo.status() == []
    assert repo.merge_step() == []


def test_a_count_left_in_merge_seen_from_before_is_read_once_and_replaced_by_a_line(
    tmp_path, monkeypatch
):
    """A home whose merge step wrote merge-seen as a count, before it marked by a line, is shown
    the lines past that count once; the merge step then marks by the line it read."""
    repo = Repo(tmp_path, monkeypatch)
    repo.merges(1, 2)
    (repo.home / "merge-seen").write_text("1\n")

    assert repo.status() == [merged(2)]
    assert repo.merge_step() == [merged(2)[17:]]
    assert repo.status() == []
