"""`plan(config, event, selection, root) -> Plan`: what the shared check workflow's jobs run.

The workflow `.github/workflows/repo-standard-check.yml` asks this once, in its `plan` job, and
hands the answer to its other jobs as outputs. The answer holds whether the run tests anything,
the parts the tests run in, what each part runs, and what the browser job runs.

A run tests nothing only on a nightly schedule that the config's `check.nightly` leaves off. A
pull request's selection is what `make select` printed: the test ids its change reaches, one a
line, or the word `all`. Every other run, and a pull request whose selection the workflow did not
make, tests the whole suite, and a selection of no id runs `none` in each part. The ids are dealt
out to the parts in turn, in the order `make select` printed them, to no more parts than there
are ids (`repo_standard.stacks.deal`). Where the selection is `all`, every part is dealt `all`,
and the workflow runs `make test SHARD=<part>/<parts>` in each, which runs that part's share of
the ids the stack lists, dealt by the same rule: the whole suite is split across the parts and
not run in each.

The browser ids go to the browser job and not to the parts: an id with a title,
`<spec> > <title>`, and a `*.spec.*` file under the `testDir` of the Playwright config of a stack
whose config sets `e2e:`, as the repo's own `scripts/node_browser.py` reads it (`Runner`), or under
its e2e root where the repo has no such script. A `*.spec.*` file elsewhere, such as a unit spec
Vitest's `include` names, goes to the parts. An id `stack:<name>` of such a stack goes to both, as
that stack's whole suite. The browser job runs
`all` wherever the parts do, `some` given browser ids, and `none` given none or where no stack
sets `e2e:`, and it runs in the Playwright image of the version the e2e roots' lockfiles pin.
"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

from repo_standard.config import Config, Refused, Stack
from repo_standard.rules import Repo, node_browser
from repo_standard.stacks import TITLE, WHOLE, deal, within
from repo_standard.tree import tracked

ALL = "all"
NONE = "none"
SOME = "some"
SPEC = re.compile(r"\.spec\.[cm]?[jt]sx?$")
PACKAGES = ("node_modules/@playwright/test", "node_modules/playwright")


@dataclass(frozen=True)
class Plan:
    run: bool
    selection: str
    parts: tuple[str, ...]
    browser: str = NONE
    browser_ids: tuple[str, ...] = ()
    playwright: str = ""

    def outputs(self) -> dict[str, str]:
        """The plan as the `key=value` outputs a step of GitHub Actions gives."""
        return {
            "run": "true" if self.run else "false",
            "selection": self.selection,
            "shards": json.dumps(list(range(1, len(self.parts) + 1))),
            "parts": json.dumps({str(at): part for at, part in enumerate(self.parts, 1)}),
            "browser": self.browser,
            "browser-ids": json.dumps(list(self.browser_ids)),
            "playwright": self.playwright,
        }


def selected(text: str) -> tuple[str, ...]:
    """The ids `make select` printed, or `(ALL,)` where it printed `all` on any line."""
    ids = tuple(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))
    return (ALL,) if ALL in ids else ids


def browsers(config: Config) -> dict[str, Stack]:
    return {name: one for name, one in config.stacks.items() if one.e2e is not None}


def test_dirs(config: Config, root: Path) -> tuple[str, ...]:
    """The folders whose `*.spec.*` files are browser tests: each e2e stack's `testDir`, as the
    repo's own `scripts/node_browser.py` reads it, or its e2e root where the repo has none."""
    roots = {
        posixpath.normpath(one.e2e.root): one.e2e.script
        for one in browsers(config).values()
        if one.e2e is not None
    }
    module = node_browser(root) if roots else None
    if module is None:
        return tuple(roots)
    repo = Repo(root, config, tracked(root))
    return tuple(
        module.Runner(at, script, set(repo.paths), repo.read).test_dir
        for at, script in roots.items()
    )


def split(
    ids: tuple[str, ...], config: Config, dirs: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The ids the parts run, and the ids the browser job runs, given the browser tests' folders."""
    mine = browsers(config)
    tests, browser = [], []
    for one in ids:
        if one.startswith(WHOLE):
            tests.append(one)
            if one[len(WHOLE) :] in mine:
                browser.append(one)
            continue
        spec = posixpath.normpath(one.split(TITLE)[0])
        if TITLE in one or (SPEC.search(spec) and any(within(spec, at) for at in dirs)):
            browser.append(one)
        else:
            tests.append(one)
    spaced = [one for one in tests if len(one.split()) > 1]
    if spaced:
        raise Refused(f"make select printed an id with a space, unfit for TESTS: {spaced[0]}")
    return tuple(tests), tuple(browser)


def playwright(config: Config, root: Path) -> str:
    """The version of Playwright the e2e roots' lockfiles pin, the same in each, or nothing
    where no stack sets `e2e:`."""
    found = {}
    for name, one in browsers(config).items():
        assert one.e2e is not None
        lock = root / one.e2e.root / "package-lock.json"
        try:
            packages = json.loads(lock.read_text(encoding="utf-8")).get("packages") or {}
        except (OSError, ValueError, AttributeError):
            packages = {}
        version = next(
            (
                packages[key]["version"]
                for key in PACKAGES
                if isinstance(packages.get(key), dict) and packages[key].get("version")
            ),
            None,
        )
        if version is None:
            raise Refused(f"stack {name}: {lock.relative_to(root)} pins no @playwright/test")
        found[name] = version
    if len(set(found.values())) > 1:
        pins = ", ".join(f"{name} {version}" for name, version in found.items())
        raise Refused(f"the e2e roots pin Playwright at more than one version: {pins}")
    return next(iter(found.values()), "")


def plan(config: Config, event: str, selection: tuple[str, ...] | None, root: Path) -> Plan:
    """The run's plan for the config, the event, and a pull request's selection."""
    check = config.check
    run = event != "schedule" or check.nightly
    version = playwright(config, root)
    whole = NONE if not browsers(config) else ALL
    if selection is None or selection == (ALL,):
        return Plan(run, ALL, (ALL,) * check.shards, whole, (), version)
    tests, browser = split(selection, config, test_dirs(config, root))
    ran = (SOME if browser else NONE, browser, version)
    if not tests:
        return Plan(run, NONE, (NONE,) * check.shards, *ran)
    parts = min(check.shards, len(tests))
    dealt = tuple(" ".join(deal(tests, at, parts)) for at in range(1, parts + 1))
    return Plan(run, SOME, dealt, *ran)
