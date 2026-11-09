"""`COMMANDS`: what each adapter runs for a stack of a repo with `stacks:`, given the stack's roots.

Each command is an argv run from the repo's root by `repo_standard.stacks`. An adapter's scripts
sit in the repo's `scripts/`, copied from `features/repo-standard/adapters/<name>/scripts/`, and
take `--roots`, so each places only the paths under its stack's roots. Each lists the stack's whole
suite as ids, sorted, which `repo_standard.stacks` deals out to the parts of a sharded run.

Each test command, and node-vite's e2e command, given `REPO_STANDARD_FAILED=<file>` in its
environment, appends to the file the id of each test that failed, one a line, in the form its
select and list print, read from its test runner's own report: the shared check names them, reruns
them on main and keeps them in a ledger (`repo_standard.misses`). A run that fails and names no
test appends every id it ran, so a failed run always names what to run again.

- go runs `scripts/go.py` once over all the stack's roots, each a folder of whole Go modules. It
  reads the failed packages from `go test -json`.
- python-uv takes each root as a uv project of its own, whose `pyproject.toml` and `uv.lock` sit
  in the root and whose dev group holds pytest and ruff. `scripts/select.py --test` runs pytest
  with the root as its rootdir and the root's `pyproject.toml` as its config, so the repo's own
  config never reaches it, and reads the failed files from pytest's `lastfailed` cache.
- node-vite takes each root as an npm package of its own and runs the package's own scripts:
  `npm run check` for the lint and `npm test` for the tests, each in the root, as `npm --prefix`
  runs them. Given ids, `scripts/node.py test` runs `npm test -- <files>` in each root, each a
  path from the root, and a root the ids miss runs nothing; it reads the failed files from
  Vitest's JSON reporter. The selection, `scripts/node.py`, reads the import graph of
  `scripts/node_graph.py`, and for a stack with `e2e:` the browser tests of
  `scripts/node_browser.py`, which reads a table spec with `scripts/node_table.py`. `make e2e`
  runs `scripts/node.py e2e` on the stack's e2e root and script, given a file of browser ids or
  none for every browser test.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repo_standard.config import E2E

Argv = list[str]


@dataclass(frozen=True)
class Commands:
    """An adapter's commands: `select` takes the stack's roots, the base and its `e2e:` part, and
    `e2e`, for an adapter that runs browser tests, the part and a file of ids, or None for all."""

    lint: Callable[[tuple[str, ...]], list[Argv]]
    test: Callable[[tuple[str, ...], list[str]], list[Argv]]
    select: Callable[[tuple[str, ...], str, E2E | None], Argv]
    list: Callable[[tuple[str, ...]], Argv]
    scripts: tuple[str, ...]
    e2e: Callable[[E2E, str | None], Argv] | None = None


def _roots(roots: tuple[str, ...]) -> Argv:
    return [arg for root in roots for arg in ("--roots", root)]


def _go(verb: str, roots: tuple[str, ...], rest: list[str]) -> Argv:
    return ["python3", "scripts/go.py", verb, *_roots(roots), *rest]


def _uv(root: str, *command: str) -> Argv:
    return ["uv", "run", "--locked", "--project", root, *command]


COMMANDS: dict[str, Commands] = {
    "go": Commands(
        lint=lambda roots: [_go("lint", roots, [])],
        test=lambda roots, ids: [_go("test", roots, ids)],
        select=lambda roots, base, e2e: _go("select", roots, [base]),
        list=lambda roots: _go("list", roots, []),
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
        test=lambda roots, ids: [["python3", "scripts/select.py", *_roots(roots), "--test", *ids]],
        select=lambda roots, base, e2e: ["python3", "scripts/select.py", *_roots(roots), base],
        list=lambda roots: ["python3", "scripts/select.py", *_roots(roots), "--list"],
        scripts=("scripts/select.py",),
    ),
    "node-vite": Commands(
        lint=lambda roots: [["npm", "--prefix", root, "run", "check"] for root in roots],
        test=lambda roots, ids: [["python3", "scripts/node.py", "test", *_roots(roots), *ids]],
        select=lambda roots, base, e2e: [
            "python3",
            "scripts/node.py",
            "select",
            *_roots(roots),
            *(["--e2e", e2e.json()] if e2e else []),
            base,
        ],
        list=lambda roots: ["python3", "scripts/node.py", "list", *_roots(roots)],
        scripts=(
            "scripts/node.py",
            "scripts/node_graph.py",
            "scripts/node_browser.py",
            "scripts/node_table.py",
        ),
        e2e=lambda e2e, listed: [
            "python3",
            "scripts/node.py",
            "e2e",
            "--root",
            e2e.root,
            "--script",
            e2e.script,
            *(["--list", listed] if listed else []),
        ],
    ),
}
