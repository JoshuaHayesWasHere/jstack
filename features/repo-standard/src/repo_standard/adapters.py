"""`COMMANDS`: what each adapter runs for a stack of a repo with `stacks:`, given the stack's roots.

Each command is an argv run from the repo's root by `repo_standard.stacks`. An adapter's scripts
sit in the repo's `scripts/`, copied from `features/repo-standard/adapters/<name>/scripts/`, and
take `--roots`, so each places only the paths under its stack's roots.

- go runs `scripts/go.py` once over all the stack's roots, each a folder of whole Go modules.
- python-uv takes each root as a uv project of its own, whose `pyproject.toml` and `uv.lock` sit
  in the root and whose dev group holds pytest and ruff. pytest runs with the root as its rootdir
  and the root's `pyproject.toml` as its config, so the repo's own config never reaches it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

Argv = list[str]


@dataclass(frozen=True)
class Commands:
    lint: Callable[[tuple[str, ...]], list[Argv]]
    test: Callable[[tuple[str, ...], list[str]], list[Argv]]
    select: Callable[[tuple[str, ...], str], Argv]
    scripts: tuple[str, ...]


def _roots(roots: tuple[str, ...]) -> Argv:
    return [arg for root in roots for arg in ("--roots", root)]


def _go(verb: str, roots: tuple[str, ...], rest: list[str]) -> Argv:
    return ["python3", "scripts/go.py", verb, *_roots(roots), *rest]


def _uv(root: str, *command: str) -> Argv:
    return ["uv", "run", "--locked", "--project", root, *command]


def _within(path: str, root: str) -> bool:
    return root == "." or path == root or path.startswith(f"{root}/")


def _pytest(roots: tuple[str, ...], ids: list[str]) -> list[Argv]:
    runs = []
    for root in roots:
        mine = [one for one in ids if _within(one, root)] if ids else [root]
        if mine:
            config = f"{root}/pyproject.toml"
            runs.append(_uv(root, "pytest", f"--rootdir={root}", "-c", config, *mine))
    return runs


COMMANDS: dict[str, Commands] = {
    "go": Commands(
        lint=lambda roots: [_go("lint", roots, [])],
        test=lambda roots, ids: [_go("test", roots, ids)],
        select=lambda roots, base: _go("select", roots, [base]),
        scripts=("scripts/go.py",),
    ),
    "python-uv": Commands(
        lint=lambda roots: [
            command
            for root in roots
            for command in (
                _uv(root, "ruff", "check", root),
                _uv(root, "ruff", "format", "--check", root),
            )
        ],
        test=_pytest,
        select=lambda roots, base: ["python3", "scripts/select.py", *_roots(roots), base],
        scripts=("scripts/select.py",),
    ),
}
