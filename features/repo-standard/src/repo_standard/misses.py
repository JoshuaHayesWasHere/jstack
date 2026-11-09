"""The ledger of the tests main's runs failed, and the net that keeps them in every selection.

A pull request's check runs the tests its change selects, and main runs the whole suite after each
merge, so a test the selection missed fails on main. The shared check keeps what it learns there:

- Each part of the tests writes the ids that failed (`REPO_STANDARD_FAILED`, which each adapter's
  test command fills, `repo_standard.adapters`). On a push to the default branch a red part runs
  its failed ids once more and writes those that failed again.
- The `passed` job of that run records one `Row` per failed id (`record`) to the artifact
  `miss-ledger-<run id>`, kept `KEPT` days, and to the job's summary. A row holds the id, the merged
  pull request, whether `make select BASE=HEAD^1` on the main commit selects it, and its class
  (`kind`): `flaky` where it passed when run again, `miss` where the selection did not reach it,
  `race` where it did but no pull request's passed check left the marker
  `checked-tree-<HEAD^1 tree>-<HEAD tree>`, so the pull request checked other trees than the ones
  that merged, and `env` where it did and one did, so the same tests passed on the same trees.
- A pull request's `plan` job adds to its selection each id that a ledger of main's runs of the
  last `DAYS` days names in a row that is not `flaky`, that no later green run of main passed, and
  whose path still exists (`failing`). Runs are ordered by id, as GitHub numbers them as it makes
  them, so a green run of an older commit that ends after a red one passes nothing of it. A green
  run of main, on a push or the nightly schedule, ran the whole suite or found its tree already
  passed, so it passed every test.

`misses` gives a person the rate: rows of class `miss` per merged pull request, one push run of
main to a merge, in the window, and the rows. Everything here runs in the runner's python3 before
any setup and reads GitHub through `gh api`, with the standard library alone.
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal, get_args

from repo_standard.config import Refused, Stack
from repo_standard.stacks import ALL, WHOLE, owner

Kind = Literal["flaky", "miss", "race", "env"]
KINDS: tuple[str, ...] = get_args(Kind)
LEDGER = "miss-ledger-"
FILE = "ledger.jsonl"
KEPT = 90
DAYS = 30
CHECKED = "checked-tree-"
PAGES = 10
"""GitHub lists 1,000 runs at most for a filtered query: 10 pages of 100."""
PER_PAGE = 100
GREEN = "success"
RED = "failure"
MAIN_EVENTS = ("push", "schedule")
PULL = re.compile(r"\(#(\d+)\)\s*$|^Merge pull request #(\d+)")

Ask = Callable[[str], Any]


@dataclass(frozen=True)
class Row:
    """One test a run of main failed: its id, the pull request the commit merged, whether the
    commit's own selection selects it, its class, and the commit."""

    id: str
    pr: str
    selected: bool
    kind: Kind
    commit: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise Refused(f"a ledger row of class {self.kind!r}, not one of {', '.join(KINDS)}")

    def line(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def read(cls, line: str) -> Row:
        try:
            data = json.loads(line)
            return cls(
                id=str(data["id"]),
                pr=str(data["pr"]),
                selected=bool(data["selected"]),
                kind=data["kind"],
                commit=str(data["commit"]),
            )
        except (ValueError, KeyError, TypeError) as error:
            raise Refused(f"a ledger row that cannot be read: {line!r}") from error


@dataclass(frozen=True)
class Run:
    """A run of the check on main, as GitHub lists it."""

    id: int
    event: str
    conclusion: str
    commit: str


def kind(passed_again: bool, selected: bool, marker: bool) -> Kind:
    """The class of a test main failed, from what the run and the commit say, in this order."""
    if passed_again:
        return "flaky"
    if not selected:
        return "miss"
    return "env" if marker else "race"


def chosen(one: str, selection: Iterable[str], stacks: dict[str, Stack]) -> bool:
    """Whether a selection, as `make select` prints it, runs the test `one`."""
    found = set(selection)
    if ALL in found or one in found:
        return True
    name = owner(path_of(one), stacks)
    return name is not None and f"{WHOLE}{name}" in found


def path_of(one: str) -> str:
    """The path of an id: a browser id `<spec> > <title>` is its spec's."""
    return one.split(" > ", 1)[0]


def record(
    failed: dict[str, bool],
    selection: list[str],
    marker: bool,
    pr: str,
    commit: str,
    stacks: dict[str, Stack],
) -> list[Row]:
    """A row for each failed id, given whether it passed when run again."""
    return [
        Row(
            id=one,
            pr=pr,
            selected=(picked := chosen(one, selection, stacks)),
            kind=kind(again, picked, marker),
            commit=commit,
        )
        for one, again in sorted(failed.items())
    ]


def failing(runs: list[Run], ledgers: dict[int, list[Row]]) -> list[str]:
    """The ids a red run's ledger names in a row that is not flaky and that no later green run
    passed, sorted. Runs are ordered by id."""
    last: dict[str, int] = {}
    for run in sorted(runs, key=lambda one: one.id):
        if run.conclusion == RED:
            last |= {row.id: run.id for row in ledgers.get(run.id, []) if row.kind != "flaky"}
    passed = max((run.id for run in runs if run.conclusion == GREEN), default=0)
    return sorted(one for one, at in last.items() if at > passed)


def failed_ids(folder: Path) -> dict[str, bool]:
    """Each id a part wrote to `failed.txt` under the folder, and whether it passed when run
    again: a part that ran its ids again wrote those that failed again to `again.txt` beside it."""
    found: dict[str, bool] = {}
    for written in sorted(folder.glob("**/failed.txt")):
        ids = lines(written)
        again = written.with_name("again.txt")
        still = set(lines(again)) if again.is_file() else set(ids)
        for one in ids:
            found[one] = found.get(one, True) and one not in still
    return found


def lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))


def table(rows: list[Row]) -> str:
    """The rows as a Markdown table, for a job's summary."""
    head = "| id | pull request | selected | class |\n|---|---|---|---|\n"
    body = "".join(
        f"| `{row.id}` | {row.pr or 'none'} | {'yes' if row.selected else 'no'} | {row.kind} |\n"
        for row in rows
    )
    return head + body


# GitHub, through `gh api`.


def gh(path: str, raw: bool = False) -> Any:
    done = subprocess.run(["gh", "api", path], capture_output=True, timeout=60)
    if done.returncode:
        said = done.stderr.decode(errors="replace").strip() or f"gh exited {done.returncode}"
        raise RuntimeError(said.splitlines()[0])
    return done.stdout if raw else json.loads(done.stdout)


def repository(env: dict[str, str]) -> str:
    if env.get("GITHUB_REPOSITORY"):
        return env["GITHUB_REPOSITORY"]
    done = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
    )
    if done.returncode or not done.stdout.strip():
        raise RuntimeError("no GITHUB_REPOSITORY, and gh repo view names no repo")
    return done.stdout.strip()


def workflow(env: dict[str, str]) -> str:
    """The file of the caller's workflow, which GitHub lists runs by: the run's own, else
    check.yml, the caller every repo starts from."""
    ref = env.get("GITHUB_WORKFLOW_REF", "").split("@", 1)[0]
    return ref.rsplit("/", 1)[-1] if ref.endswith((".yml", ".yaml")) else "check.yml"


class GitHub:
    """The calls the ledger makes, for one repo."""

    def __init__(self, repo: str, call: Callable[..., Any] = gh) -> None:
        self.repo, self.call = repo, call

    def ask(self, path: str, raw: bool = False) -> Any:
        return self.call(f"repos/{self.repo}/{path}".rstrip("/"), raw)

    def runs(self, file: str, since: date) -> list[Run]:
        """The completed runs of the workflow on main, pushed or scheduled, made since the day."""
        branch = self.ask("")["default_branch"]
        found: list[Run] = []
        for page in range(1, PAGES + 1):
            listed = self.ask(
                f"actions/workflows/{file}/runs?branch={branch}&status=completed"
                f"&created=%3E%3D{since.isoformat()}&per_page={PER_PAGE}&page={page}"
            )["workflow_runs"]
            found += [
                Run(int(one["id"]), one["event"], one.get("conclusion") or "", one["head_sha"])
                for one in listed
                if one.get("event") in MAIN_EVENTS
            ]
            if len(listed) < PER_PAGE:
                break
        return found

    def ledger(self, run: int) -> list[Row]:
        """The rows of the run's ledger, or none where it left no ledger or it expired."""
        listed = self.ask(f"actions/runs/{run}/artifacts?name={LEDGER}{run}")["artifacts"]
        for artifact in listed:
            if artifact.get("expired") or artifact.get("name") != f"{LEDGER}{run}":
                continue
            zipped = self.ask(f"actions/artifacts/{artifact['id']}/zip", raw=True)
            text = zipfile.ZipFile(io.BytesIO(zipped)).read(FILE).decode()
            return [Row.read(line) for line in text.splitlines() if line.strip()]
        return []

    def ledgers(self, runs: list[Run]) -> dict[int, list[Row]]:
        """The ledger of each red push run: only a push to main records one."""
        red = [run.id for run in runs if run.conclusion == RED and run.event == "push"]
        return {run: self.ledger(run) for run in red}

    def marker(self, base: str, tree: str) -> bool:
        """Whether a passed check of a pull request left the marker of the two trees."""
        listed = self.ask(f"actions/artifacts?name={CHECKED}{base}-{tree}&per_page={PER_PAGE}")
        return any(not one.get("expired") for one in listed["artifacts"])

    def pull(self, commit: str, subject: str) -> str:
        """The pull request the commit merged, `#<n>`, or nothing."""
        try:
            pulls = self.ask(f"commits/{commit}/pulls")
            merged = [one for one in pulls if one.get("merged_at")]
            if merged:
                return f"#{merged[0]['number']}"
        except RuntimeError:
            pass
        found = PULL.search(subject)
        return f"#{found[1] or found[2]}" if found else ""


def since(days: int, today: date | None = None) -> date:
    return (today or date.today()) - timedelta(days=days)


def rate(runs: list[Run], ledgers: dict[int, list[Row]]) -> tuple[int, int]:
    """The rows of class miss, and the merged pull requests: one push run of main each."""
    misses = sum(row.kind == "miss" for rows in ledgers.values() for row in rows)
    return misses, sum(run.event == "push" for run in runs)


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return done.stdout.strip()


def write(out: Path, rows: list[Row]) -> None:
    """The ledger file, written whole and renamed into place, so a run again replaces it."""
    out.mkdir(parents=True, exist_ok=True)
    temp = out / f".{FILE}"
    temp.write_text("".join(f"{row.line()}\n" for row in rows), encoding="utf-8")
    temp.replace(out / FILE)


def record_here(
    folder: Path, out: Path, github: GitHub, stacks: dict[str, Stack], warn: Callable[[str], None]
) -> list[Row]:
    """The rows of this checkout's commit of main, from the parts' failed ids under `folder`,
    written to `out`."""
    failed = failed_ids(folder)
    commit, subject = git("rev-parse", "HEAD"), git("log", "-1", "--format=%s")
    done = subprocess.run(
        ["make", "-s", "--no-print-directory", "select", "BASE=HEAD^1"],
        capture_output=True,
        text=True,
    )
    selection = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    if done.returncode:
        warn(f"make select BASE=HEAD^1 failed ({done.stderr.strip()}), so no row is a miss")
        selection = [ALL]
    try:
        marker = github.marker(git("rev-parse", "HEAD^1^{tree}"), git("rev-parse", "HEAD^{tree}"))
    except RuntimeError as error:
        warn(f"could not ask for the checked-tree marker ({error}), so no row is a race")
        marker = True
    rows = record(failed, selection, marker, github.pull(commit, subject), commit, stacks)
    write(out, rows)
    return rows


def failing_here(github: GitHub, file: str, days: int) -> list[str]:
    """The ids that join a selection, whose path still exists in this checkout."""
    runs = github.runs(file, since(days))
    return [one for one in failing(runs, github.ledgers(runs)) if Path(path_of(one)).exists()]


def report(github: GitHub, file: str, days: int) -> list[str]:
    """The lines `repo-standard misses` prints: the rate, then each row with its run."""
    runs = github.runs(file, since(days))
    ledgers = github.ledgers(runs)
    misses, merged = rate(runs, ledgers)
    share = f" ({100 * misses / merged:.1f}%)" if merged else ""
    head = (
        f"miss rate: {misses} misses in {merged} merged pull requests{share},"
        f" from the runs of {file} on main in the last {days} days"
    )
    rows = [
        f"{run}\t{row.commit[:12]}\t{row.pr or '-'}\t{row.kind}\t"
        f"{'selected' if row.selected else 'not selected'}\t{row.id}"
        for run, found in sorted(ledgers.items())
        for row in found
    ]
    return [head, *rows]
