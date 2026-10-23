"""The repos jstack works in, and the git hooks it links into each.

A feature declares its git hooks in `gitHooks`, which the generator lists in skills.json: jleak's
`pre-push` and `commit-msg`. The install links each one into every repo jstack works in:
- the main checkout it runs from, when it runs from one;
- the checkout of each project of jbus's config;
- each repo that `--repo` set up, which the machine keeps in a list (`Machine.repos`).

Each link points at the hook's script in the source: the checkout's, or the tree a release's
wheel installed. A release's script runs jleak on the release's own Python, so a repo's hooks
need no checkout. The worktrees of a repo run the hooks of its main checkout, so the one link
covers every branch.

A hook of jstack's own checkout is hard. A hook of any other repo is optional: a repo that has a
hook of its own keeps it, and its line says so for as long as it does not run jstack's.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import jbus
from jinstall.kinds import Found, Link, quoted
from jinstall.machine import Dropped, Machine


def checkouts(machine: Machine, config: Path) -> list[Path]:
    """Every repo jstack works in, by its main checkout, in this order: jstack's own checkout,
    each jbus project's, then each repo of the list. The function reads jbus's config at
    `config` and the list, and probes nothing. A config that jbus's loader refuses names no
    project, and its own line says why."""
    found = [machine.checkout] if machine.checkout is not None else []
    try:
        found += (
            [one.checkout for one in jbus.load(config.parent).projects] if config.is_file() else []
        )
    except Exception:
        pass
    found += machine.repos()
    return list(dict.fromkeys(Path(os.path.abspath(one)) for one in found))


def main_checkout(machine: Machine, path: Path) -> Path | None:
    """The main checkout of the git repo at `path`, or None when `path` is in no repo or the
    repo has no main checkout (a bare repo, or a submodule's)."""
    asked = machine.run(
        ["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"]
    )
    common = Path(asked.out.strip()) if asked.code == 0 else None
    return common.parent if common is not None and common.name == ".git" else None


@dataclass(frozen=True)
class GitHook:
    """A link from <repo>/.git/hooks/<name> to the script of that hook in the source.
    due: `.git` is a directory, and HOME is the account's own or holds the repo. A directory
      `.git` means a main checkout. When a sandbox or a test runs the install under another
      HOME, the run leaves a repo outside that HOME as it is.
    ok: the link points at the script, or the repo's own hook runs it (`chained`).
    old: a link to jleak's hook of this name in another source, such as an older checkout.
    foreign: any other hook, which is the repo's own: a file, or a link to anywhere else. Or
      core.hooksPath is set, so git runs the hook of that folder. The detail names the file and
      the line that would run jstack's hook from it. A put never writes over it.
    drop: unlink the path only when it points at the script. An own hook that runs the
      script is kept, and the line says so."""

    repo: Path
    name: str
    script: str

    def path(self) -> Path:
        return self.repo / ".git" / "hooks" / self.name

    def _target(self, machine: Machine) -> Path:
        return machine.source / self.script

    def _ask(self, machine: Machine) -> str:
        return f'to run jstack\'s as well, add sh {quoted(self._target(machine))} "$@" to it'

    def _runs_it(self, machine: Machine, own: Path) -> bool:
        try:
            return str(self._target(machine)) in own.read_text()
        except (OSError, UnicodeDecodeError):
            return False

    def _elsewhere(self, machine: Machine) -> Path | None:
        """The hook git runs when core.hooksPath sends it to another folder."""
        asked = machine.run(["git", "-C", str(self.repo), "config", "--get", "core.hooksPath"])
        folder = asked.out.strip() if asked.code == 0 else ""
        return self.repo / os.path.expanduser(folder) / self.name if folder else None

    def probe(self, machine: Machine) -> Found:
        own = self._elsewhere(machine)
        if own is not None:
            if self._runs_it(machine, own):
                return Found.ok("chained from the repo's own hook")
            why = f"core.hooksPath is set, so git runs {own}, which the install does not write over"
            return Found.foreign(f"{why}: {self._ask(machine)}")
        path, target = self.path(), self._target(machine)
        if path.is_symlink():
            to = os.readlink(path)
            if to == str(target):
                return Found.ok()
            if to.endswith(f"/{self.script}"):
                return Found.old(to)
        elif not path.exists():
            return Found.missing()
        if self._runs_it(machine, path):
            return Found.ok("chained from the repo's own hook")
        why = "a hook of the repo's own, which the install does not write over"
        return Found.foreign(f"{why}: {self._ask(machine)}")

    def due(self, machine: Machine) -> bool:
        ours = machine.home == machine.account or self.repo.is_relative_to(machine.home)
        return ours and (self.repo / ".git").is_dir()

    def put(self, machine: Machine) -> None:
        Link(self.path(), self._target(machine)).put(machine)

    def drop(self, machine: Machine) -> Dropped:
        path = self.path()
        if not path.is_symlink() and path.is_file() and self._runs_it(machine, path):
            why = f"yours, it runs {self._target(machine)}: take that line out"
            return Dropped(kept=(f"hook {path} {self.name} -> {why}",))
        return Link(path, self._target(machine)).drop(machine)
