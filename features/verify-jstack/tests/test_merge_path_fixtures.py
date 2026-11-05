"""Controlled pull requests through jmerge's real merge path: a known-good one merges, and each
known-broken one holds, for the one fault it names and with the reason it must show.

Each fixture gets a new verify-jstack sandbox. Its branch `beta` is two real commits pushed to the
sandbox's origin, and the sandbox's GitHub, the stand-in `gh`, is told it may merge (`gh/merges`),
so a plain `jmerge` (no `--check`) runs its whole path: the judgement, the merge lock, the squash
through `gh pr merge`, the fetch and fast-forward of main, and the clean-up of the branch. The
stand-in is the only mock, where jstack already ends: GitHub.

GOOD is the pull request that merges. Every broken fixture is GOOD with one field replaced, so
the fault it names is the only thing that differs, and `test_each_broken_fixture_differs_from_the_
good_one_by_its_one_fault` keeps it so.

One command runs them all, in CI's `check` too (select_tests picks this file by its imports):
`uv run pytest -q features/verify-jstack/tests`. Add `-k merge_path -rP` to see each fixture's
printed line.
"""

import dataclasses
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from jmerge import ready
from test_verify_jstack import SCRIPTS, inside, launch

URL = "https://example.test/pull/7"
WATCHED = ("path", "check", "review", "checked_at", "main_edits")
OPEN_PULL = SCRIPTS / "open-pull.sh"


@pytest.fixture
def sandbox(tmp_path):
    """A new sandbox for each fixture, so no run leans on what an earlier one left."""
    ran = launch(tmp_path)
    assert ran.returncode == 0, ran.stderr
    env_sh = Path(ran.stdout.strip().removeprefix("ready: . "))
    yield env_sh
    subprocess.run([SCRIPTS / "cleanup.sh", env_sh.parent], capture_output=True)


@dataclasses.dataclass(frozen=True)
class Branch:
    """What a fixture's pull request is at: its first commit, its head, and main's tip."""

    first: str
    head: str
    tip: str


@dataclasses.dataclass(frozen=True)
class Fixture:
    """A pull request through the merge path. `fault` is the one thing that breaks it, empty for
    the good one, and `holds` the line `jmerge` must print for it."""

    fault: str
    holds: Callable[[Branch], str]
    path: str = "src/beta/a.py"
    """The one file its two commits change."""
    check: str = "SUCCESS"
    """The conclusion of the check named `check` at its head."""
    review: str = "clean"
    """`clean` at its head, `none`, or `finding`: one finding its Result never handles."""
    checked_at: str = "head"
    """The commit its crew's `Checked:` line names: `head`, or `first`, whose patch differs."""
    main_edits: bool = False
    """Main has its own commit to the line the pull request changes, so the two conflict."""


def waits(why: str) -> str:
    return f"wait 7 {URL}: {why}"


GOOD = Fixture(fault="", holds=lambda at: "")
BROKEN = {
    "red-check": dataclasses.replace(
        GOOD,
        fault="the check named check failed at its head",
        check="FAILURE",
        holds=lambda at: waits(ready.CHECK_FAILED.format(check="check")),
    ),
    "no-review": dataclasses.replace(
        GOOD,
        fault="its brief has no review",
        review="none",
        holds=lambda at: waits(ready.NO_REVIEW),
    ),
    "unhandled-finding": dataclasses.replace(
        GOOD,
        fault="its review has a finding the Result never handles",
        review="finding",
        holds=lambda at: waits(ready.NO_FIXED),
    ),
    "stale-checked": dataclasses.replace(
        GOOD,
        fault="its Checked: line is of its first commit, and its patch changed after it",
        checked_at="first",
        holds=lambda at: waits(ready.CHECKED_STALE.format(at=at.first[:12], head=at.head[:12])),
    ),
    "protected-path": dataclasses.replace(
        GOOD,
        fault="it changes secrets/a.key, a path only the user merges",
        path="secrets/a.key",
        holds=lambda at: (
            f"hold 7 {URL}: " + ready.TOUCHES.format(user="user", path="secrets/a.key")
        ),
    ),
    "conflicts-with-main": dataclasses.replace(
        GOOD,
        fault="main changed the same line after it branched, so it conflicts with its base",
        main_edits=True,
        holds=lambda at: waits(ready.CONFLICTS),
    ),
}


def run(env_sh: Path, command: str) -> str:
    ran = inside(env_sh, command)
    assert ran.returncode == 0, f"{command}: {ran.stderr}"
    return ran.stdout.strip()


def open_pull_request(env_sh: Path, fixture: Fixture) -> Branch:
    """Push the fixture's branch to the sandbox's origin, give its GitHub the pull request as
    GitHub would list it, and write the crew's brief for it. GitHub's `mergeable` is what git says
    of the head over main, not a field the fixture sets."""
    S = env_sh.parent
    path = fixture.path
    if fixture.main_edits:
        run(
            env_sh,
            f"mkdir -p {Path(path).parent} && echo 'a = 2' > {path} && git add -A && "
            "git commit -qm 'main edits it' && git push -q origin main",
        )
    start = run(env_sh, "git rev-list --max-parents=0 HEAD")
    commit = "git add -A && git commit -qm '{}' && git rev-parse HEAD"
    first = run(
        env_sh,
        f"git switch -q -c beta {start} && mkdir -p {Path(path).parent} && "
        f"echo 'a = 0' > {path} && " + commit.format("feat: beta, first"),
    )
    head = run(env_sh, f"echo 'a = 1' > {path} && " + commit.format("feat: beta, done"))
    run(env_sh, "git push -q origin beta && git switch -q main")
    tip = run(env_sh, "git rev-parse origin/main")
    merges = inside(
        env_sh, f'git -C "$VERIFY_JSTACK_SANDBOX/origin.git" merge-tree --write-tree {tip} {head}'
    )
    mergeable = "MERGEABLE" if merges.returncode == 0 else "CONFLICTING"
    run(env_sh, f'"{OPEN_PULL}" beta {path} {fixture.check} {head}')
    listed = S / "gh" / "open.json"
    listed.write_text(json.dumps([{**json.loads(listed.read_text())[0], "mergeable": mergeable}]))
    (S / "gh" / "merges").touch()

    checked = {"head": head, "first": first}[fixture.checked_at]
    review = {
        "clean": f"## Review\nVerdict: clean\nHead: {head}   Unchanged by the run: yes\n"
        "Findings:\nnone\n",
        "none": "",
        "finding": f"## Review\nVerdict: findings\nHead: {head}\nFindings:\n"
        "- warning src/beta/a.py:1 a made up one (bucket: Act on)\n",
    }[fixture.review]
    brief = (
        "# beta: a demo task\nWhere: `src/beta/`\nPull request: open one when done\n\n"
        f"## Result\nStatus: done\nBranch: beta   Pull request: {URL}\n"
        f"Checked: make check-fast BASE={tip} PART=guards exit 0 at {checked}\n\n{review}"
    )
    (S / "home" / ".local" / "state" / "home" / "demo" / "tasks" / "beta.md").write_text(brief)
    return Branch(first=first, head=head, tip=tip)


def github(env_sh: Path, name: str):
    return json.loads((env_sh.parent / "gh" / f"{name}.json").read_text())


def origin(env_sh: Path, ref: str) -> str:
    return inside(
        env_sh, f'git -C "$VERIFY_JSTACK_SANDBOX/origin.git" rev-parse -q --verify {ref}'
    ).stdout.strip()


def test_the_good_pull_request_merges_through_the_real_merge_path(sandbox):
    at = open_pull_request(sandbox, GOOD)
    said = run(sandbox, "jmerge")
    print(f"good: {said}")

    merged = origin(sandbox, "refs/heads/main")
    assert said == f'merged 7 beta {merged} "feat: beta", revert: gh pr revert {URL}'
    assert merged != at.tip
    assert run(
        sandbox, f'git -C "$VERIFY_JSTACK_SANDBOX/origin.git" rev-parse {merged}^ {merged}^{{tree}}'
    ).split() == [
        at.tip,
        run(sandbox, f"git rev-parse {at.head}^{{tree}}"),
    ]
    assert run(sandbox, "git rev-parse main") == merged
    assert origin(sandbox, "refs/heads/beta") == ""
    assert github(sandbox, "open") == []
    assert [one["number"] for one in github(sandbox, "merged")] == [7]
    assert f"pr merge 7 --squash --match-head-commit {at.head}" in run(
        sandbox, 'cat "$VERIFY_JSTACK_SANDBOX/gh/calls.log"'
    )


@pytest.mark.parametrize("name", list(BROKEN))
def test_each_broken_pull_request_holds_for_its_one_fault(sandbox, name):
    fixture = BROKEN[name]
    at = open_pull_request(sandbox, fixture)
    said = run(sandbox, "jmerge")
    print(f"{name} ({fixture.fault}): {said}")

    assert said == fixture.holds(at)
    assert origin(sandbox, "refs/heads/main") == at.tip
    assert origin(sandbox, "refs/heads/beta") == at.head
    assert [one["number"] for one in github(sandbox, "open")] == [7]
    assert github(sandbox, "merged") == []
    assert "pr merge" not in run(sandbox, 'cat "$VERIFY_JSTACK_SANDBOX/gh/calls.log"')


@pytest.mark.parametrize("name", list(BROKEN))
def test_each_broken_fixture_differs_from_the_good_one_by_its_one_fault(name):
    fixture = BROKEN[name]
    differs = [field for field in WATCHED if getattr(fixture, field) != getattr(GOOD, field)]
    assert len(differs) == 1, differs
    assert fixture.fault
    assert {field.name for field in dataclasses.fields(Fixture)} == {*WATCHED, "fault", "holds"}
