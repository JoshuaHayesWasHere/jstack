from __future__ import annotations

import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import jsettings
from jmerge import bus, judgement, mainjson, ready
from jmerge.bus import Migrations as Migrations
from jmerge.bus import Row
from jmerge.checks import NOT_RED
from jsettings import brief as brief_head
from jsettings import store

NO_PULL = "no pull request yet"


def migrations(checkout: Path) -> Migrations | None:
    found = bus.quiet_place(checkout)
    return None if found is None else found.migrations


def merge_order(rows: list[Row] | None, slugs: dict[int, str]) -> list[int]:
    table = {row["slug"]: row for row in rows or []}

    def before(slug: str) -> set[str]:
        found: set[str] = set()
        todo = list(table.get(slug, {}).get("merge_after", []))
        while todo:
            one = todo.pop()
            if one not in found:
                found.add(one)
                todo.extend(table.get(one, {}).get("merge_after", []))
        return found

    waits = {number: before(slug) for number, slug in slugs.items()}
    placed: list[int] = []
    left = sorted(slugs)
    while left:
        free = [one for one in left if not {slugs[n] for n in left if n != one} & waits[one]]
        first = free[0] if free else left[0]
        placed.append(first)
        left.remove(first)
    return placed


def _state(checkout: Path) -> Path | None | bool:
    try:
        found = bus.place(checkout)
    except jsettings.Refused:
        return False
    return None if found is None else found.state


def read(checkout: Path) -> list[Row] | None:
    state = _state(checkout)
    if state is False:
        return None
    if state is None:
        return []
    found = bus.found()
    return None if found is None else found.rows(state)


def stored(checkout: Path, slug: str) -> str | None:
    """The brief of `slug` as jbus stores it for the project of `checkout`, the text its go is
    judged against (`judgement.has_go`), or nothing."""
    state = _state(checkout)
    found = bus.found()
    return found.stored(state, slug) if isinstance(state, Path) and found else None


def main(checkout: Path) -> mainjson.Main:
    state = _state(checkout)
    return mainjson.read(state) if isinstance(state, Path) else mainjson.Main()


@dataclass(frozen=True)
class Ran:
    """What a pull request's own check proved at its head, as `jmerge.cli` reads it from its
    check runs' logs (`ran_in`): `over`, the red tip its head contains, or nothing; `every`,
    whether it ran the whole suite; `paths`, the test files and folders it ran otherwise; and
    `failed`, the tests it failed. A check that did not pass proves what its failed tests say
    and nothing of the rest, since a part of it may have stopped early: `failed` is read only
    from a browser run, which runs every browser test."""

    over: str = ""
    every: bool = False
    paths: frozenset[str] = frozenset()
    failed: frozenset[str] = frozenset()

    def covers(self, test: str) -> bool:
        """Whether the check ran `test`, a pytest id, and passed it."""
        path = test.split("::")[0]
        ran = self.every or any(
            path == one or path.startswith(f"{one.rstrip('/')}/") for one in self.paths
        )
        return ran and test not in self.failed


UNPROVED = Ran()
"""A check that proves nothing: no head over the red tip, no test run."""


def proves(red: str, failed: Sequence[str], ran: Ran) -> bool:
    """Whether a check proves the fix of the red tip `red`: its head contains that tip, and it
    ran each test that failed there and passed it. Where no failed test is known, nothing
    proves the fix."""
    return bool(red) and ran.over == red and bool(failed) and all(map(ran.covers, failed))


def red(main: mainjson.Main, slug: str, ran: Ran = UNPROVED) -> str:
    """The hold on a pull request into main while main is red: none for a fix, the pull request
    whose check proves it (`proves`, of the tests `main.json` names at the red tip), or the brief
    jbus filed for it (`mainjson.fix_of`)."""
    if not main.red or mainjson.fix_of(slug) or proves(main.red, main.failed, ran):
        return ""
    return ready.MAIN_RED.format(sha=main.red[: mainjson.SHA])


_STAMP = r"^(?:\S+Z )?"
_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PYTEST = re.compile(_STAMP + r"(?:\+ )?(?:uv run |python3? -m )?pytest(?: (.*))?$", re.M)
KEEPS = {
    "-n": True,
    "--numprocesses": True,
    "--dist": True,
    "--durations": True,
    "--junitxml": True,
    "--shard": True,
    "-q": False,
    "--quiet": False,
    "-v": False,
    "--verbose": False,
}
"""The options of pytest that leave the run whole, each with whether it takes a value: workers,
timings, reports, output, and `--shard`, whose parts are each read from their own job. Any
other option may leave out or stop tests (`--ignore`, `-k`, `--lf`, `--collect-only`, a plugin
of `-p`), so a command with one says nothing."""
CHECK = "not browser"
"""The marker of `make check`'s run, `-m "not browser"`: `jmerge.cli` reads the check's jobs with
it, for the tests main's failed check names."""
BROWSER = "browser"
"""The marker of `make check-browser`'s run, `-m browser`: `jmerge.cli` reads the browser run's
job with it, for the tests main's failed browser run names."""


def ran_in(log: str, mark: str) -> Ran | None:
    """What a job's log says it ran: the one pytest command it echoes, `make`'s echo of it or a
    shell's trace (`+ `). A path is a word of it that is no option or an option's value; with
    none, the whole suite ran. A log with no such command, or more than one, or one with an
    option that is not known to leave the run whole (`KEEPS`), says nothing. So does a marker
    other than `mark`, the one the caller reads the run for (`CHECK` or `BROWSER`), quoted or
    not as a shell's trace prints it: another may leave tests out, and the check's `not browser`
    runs none of the tests main's browser run failed, nor its `browser` any of the rest."""
    marked = re.compile(rf"""(?:^| )-m ?(?:'{mark}'|"{mark}"|{mark})(?= |$)""")
    found = _PYTEST.findall(_ESCAPE.sub("", log))
    if len(found) != 1:
        return None
    try:
        words = shlex.split(marked.sub("", found[0]))
    except ValueError:
        return None
    paths, value = [], False
    for word in words:
        if value:
            value = False
        elif not word.startswith("-"):
            paths.append(word)
        elif word.startswith("--") and "=" in word:
            if not KEEPS.get(word.split("=")[0]):
                return None
        elif word in KEEPS:
            value = KEEPS[word]
        elif not (word[:2] in KEEPS and KEEPS[word[:2]]):
            return None
    if value:
        return None
    return Ran(every=not paths, paths=frozenset(paths))


def base_red(base: str, runs: list[dict], slug: str, text: str = "") -> str:
    """The red hold of a pull request into an integration branch. It holds when a check of the
    branch's tip ended without passing on its latest run, as GitHub's check runs list them
    (`failed`). A cancelled run is no failed check, as on main (`jmerge.checks.NOT_RED`).

    It does not hold a fix of a red main, as `red` does not, nor the fix of this branch's red at
    its tip: the row jbus files for it (`integration_fix`, `jbus.sidered.integration_branches`),
    or a row whose brief `text` names that red (`fixes`). A fix of another red is held. `failed`,
    `latest`, `integration_fix` and `fixes` are at the end of this module.
    """
    red = failed(runs)
    sha = str(red[0].get("head_sha"))[: mainjson.SHA] if red else ""
    fix = mainjson.fix_of(slug) or slug == integration_fix(base, sha) or fixes(text) == (base, sha)
    if not red or fix:
        return ""
    return ready.BASE_RED.format(base=base, sha=sha)


def ordered(rows: list[Row] | None) -> set[str]:
    """The slugs of the rows that are not over and name a row they merge after: the only rows
    whose commits, carried by another pull request, can hold that one back."""
    return {
        row["slug"]
        for row in rows or []
        if row.get("status") not in judgement.FINAL and row.get("merge_after")
    }


def short(
    rows: list[Row] | None,
    slug: str,
    carries: Sequence[tuple[str, int, bool]] = (),
    *,
    brief: str | None,
) -> str:
    """Why the pull request of `slug` waits on the queue, or nothing. `brief` is the row's brief
    as jbus stores it (`stored`): a row waits on the user's go unless its go holds for that brief,
    as jbus's launch asks (`judgement.has_go`). `carries` holds the open pull requests that a merge
    of this one may land, each as its slug, its number and whether its head could be read: one whose
    commits this head contains and its base does not. This one waits on their rows' `merge_after`
    as on its own, and on one it could not read."""
    if rows is None:
        return ready.QUEUE_UNREADABLE
    table = {row["slug"]: row for row in rows}
    row = table.get(slug, {})
    if row.get("status") in judgement.FINAL:
        return ""
    if row.get("held"):
        return ready.ROW_HELD
    if row and not judgement.has_go(row, brief):
        return ready.NO_GO
    for other in row.get("merge_after", []):
        ahead = table.get(other)
        if ahead is not None and ahead.get("status") not in judgement.FINAL:
            return ready.MERGES_AFTER.format(slug=other, open=ahead.get("pr") or NO_PULL)
    for carried, number, read in carries:
        under = table.get(carried, {})
        if under.get("status") in judgement.FINAL:
            continue
        for other in under.get("merge_after", []):
            ahead = table.get(other)
            if other == slug or ahead is None or ahead.get("status") in judgement.FINAL:
                continue
            if not read:
                return ready.CARRIES_UNKNOWN.format(carried=carried, number=number)
            return ready.CARRIES_AFTER.format(
                carried=carried, number=number, slug=other, open=ahead.get("pr") or NO_PULL
            )
    return ""


INTEGRATION_FIX = "integration-red-"
"""The start of the slug of a fix row jbus files for a red integration branch
(`jbus.sidered.integration_branches`)."""
FIXES = "Fixes red:"
"""The head line of a brief whose row fixes a red integration branch, `Fixes red: <branch> at
<sha>`, with at least the first 12 characters of the red tip."""
_KEPT = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._-")


def integration_fix(branch: str, sha: str) -> str:
    """The slug of the fix row for the red of `branch` at `sha`, or with no `sha` the start that
    every fix row of the branch shares."""
    kept = "".join(one if one in _KEPT else " " for one in branch.lower())
    stem = "-".join(kept.split()).strip("-.") or "branch"
    return f"{INTEGRATION_FIX}{stem}-{sha[: mainjson.SHA]}"


def fixes(text: str) -> tuple[str, str] | None:
    """The branch and the red tip, to 12 characters, that the brief's `FIXES` line names in its
    head, or nothing."""
    for line in brief_head.head_lines(text):
        if line.startswith(FIXES):
            words = line.removeprefix(FIXES).split()
            if len(words) == 3 and words[1] == "at" and len(words[2]) >= mainjson.SHA:
                return words[0], words[2][: mainjson.SHA]
    return None


def latest(runs: list[dict]) -> list[dict]:
    """The latest run of each check, as GitHub's check runs of a commit list them."""
    found: dict[str, dict] = {}
    for one in sorted(runs, key=lambda run: str(run.get("started_at") or "")):
        found[str(one.get("name"))] = one
    return list(found.values())


def failed(runs: list[dict]) -> list[dict]:
    """The checks whose latest run ended without passing. A cancelled run is no failed check,
    as on main (`jmerge.checks.NOT_RED`)."""
    return [
        one
        for one in latest(runs)
        if one.get("status") == "completed" and one.get("conclusion") not in NOT_RED
    ]


BROWSER_FIX = "browser-red-"
"""The start of the slug of the fix row jbus files for main's red browser run
(`jbus.watch.BROWSER`)."""


def browser_red(
    head: str,
    slug: str,
    runs: list[dict],
    default: str,
    fixing: set[str],
    ran: Ran = UNPROVED,
    failed: Sequence[str] = (),
) -> str:
    """The hold on a pull request whose own browser run failed at `head`. The red is main's where
    main's last browser run failed too and its fix is open (`main_browser_red`, of `runs`, main's
    browser.yml runs as GitHub lists them, and `fixing`, from `browser_fixing`), and it waits as
    for a red main, unless it is the fix of that red. The fix is the pull request whose browser
    run proves it (`proves`, of `failed`, the tests main's run failed, and `ran`, what its own run
    ran and failed), or the row jbus files for it (`BROWSER_FIX`). Otherwise the red is the pull
    request's own, which jbus tells its crew (`jbus.expedite.TABLE`)."""
    red = "" if slug.startswith(BROWSER_FIX) else main_browser_red(runs, default, fixing)
    if red and not proves(red, failed, ran):
        return ready.MAIN_RED.format(sha=red[: mainjson.SHA])
    return ready.BROWSER_RED.format(head=head[: mainjson.SHA])


def main_browser_red(runs: list[dict], default: str, fixing: set[str]) -> str:
    """The commit of main's last browser run where it failed and its fix is open, or nothing
    (`main_browser_run`)."""
    last = main_browser_run(runs, default, fixing)
    return str(last.get("head_sha") or "") if last else ""


def main_browser_run(runs: list[dict], default: str, fixing: set[str]) -> dict | None:
    """Main's last browser run where it failed and its fix is open, or nothing.
    `runs` are the workflow's completed runs: a pull request's run, or a run on another branch
    than `default`, says nothing of main, and a cancelled or skipped one judged no code
    (`jmerge.checks.NOT_RED`). browser.yml runs on main only nightly, so its last run there stays
    red until the next one: once the fix of that run merged, or where jbus filed none (its id is
    not in `fixing`), that red is nobody's to wait on, and a pull request's own red is its own."""
    ran = [
        one
        for one in runs
        if one.get("event") != "pull_request"
        and one.get("head_branch") == default
        and one.get("status") == "completed"
        and one.get("conclusion") not in ("cancelled", "skipped")
    ]
    last = max(ran, key=lambda one: str(one.get("created_at") or ""), default=None)
    if last is None or last.get("conclusion") in NOT_RED or str(last.get("id")) not in fixing:
        return None
    return last


BROWSER_SEEN = "browser-runs.json"
"""The file in jbus's state of the project that maps each browser.yml run jbus has seen to the
slug of the fix row it filed for it, or to nothing (`jbus.watch.BROWSER.seen`)."""


def browser_fixing(checkout: Path, rows: list[Row] | None) -> set[str]:
    """The ids of main's red browser runs whose fix is open: the row jbus filed for the run
    (`BROWSER_SEEN`) is in `rows`, the queue, and is not over."""
    state = _state(checkout)
    seen = store.read_dict(state / BROWSER_SEEN) if isinstance(state, Path) else {}
    fixing = {row["slug"] for row in rows or [] if row.get("status") not in judgement.FINAL}
    return {str(run) for run, slug in seen.items() if slug and slug in fixing}
