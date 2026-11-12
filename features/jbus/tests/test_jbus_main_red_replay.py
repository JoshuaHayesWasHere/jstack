"""jstack's red spells of main from 2026-11-10 and 11, replayed through the real `mainmoved.tell`
and read by the real `flakerow.flakes`, each with the verdict the scout
enhancement-effects-2026-11-11 found from how the spell ended.

Spell 41 (#1584) and spell 43 (#1620) were real faults that a fix ended: #1591 changed the failed
test's file, and #1628 the `fake-gh` script its tests drive. Each had a second red tip,
8b6c51f76 and 54d9f0055, judged after pull requests checked over the red main had failed its
tests on their own branches, which `reverts.flaky` reads as a flake: the ledger called both
`flake`. Spells 44 (#1638) and 45 (#1651) went green on merges that touched neither the failed
test nor its feature's code, #1640 and #1649: flakes, which the ledger called `change`.

The replay keeps each spell's first red, its second where it had one, and the merge that ended
it; the commits are jstack's own."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jbus import flakerow, mainmoved
from jmerge import mainjson
from test_jbus_telemetry import NOW, iso, machine
from test_jbus_telemetry_spells import flaked

__all__ = ["machine"]

SPELLS_41 = (
    "features/jbus/tests/test_jbus_telemetry_spells.py::"
    "test_tell_writes_why_main_went_red_once_and_the_store_reads_it_as_the_spells_cause"
)
BLOCKERS = "features/verify-jstack/tests/test_home_clears_blockers.py::"
SPELL_43 = (
    f"{BLOCKERS}test_a_red_check_gets_a_fix_row_with_no_event",
    f"{BLOCKERS}test_a_fix_whose_own_check_failed_is_not_at_work_"
    "and_the_next_try_then_the_cap_follow",
)
SPELL_44 = (
    "features/jmerge/tests/test_jmerge_treeguards.py::"
    "test_guards_stopped_at_their_time_end_quietly_where_a_stopped_group_answers_eperm"
)
SPELL_45 = (
    "features/repo-guards/tests/test_linux_only_marked.py::"
    "test_every_test_that_reaches_a_linux_only_facility_is_marked_linux_only"
)
STATECHART = "features/skill-library/skills/statechart/scripts/statechart/cli.py"


@dataclass(frozen=True)
class Tip:
    """A commit on main: its pull request, its check, the tests it failed, the files it changed,
    and whether pull requests checked over it failed its tests on two branches of their own."""

    sha: str
    pr: int
    check: str
    failed: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    shared: bool = False


GREEN = Tip("0" * 40, 1583, "green")
MAIN = [
    Tip("fb91d403c21725c490d89f0c098fdebaed1a762d", 1584, "failed", (SPELLS_41,)),
    Tip("8b6c51f76598f4278ed44696da6b64763d565c97", 1587, "failed", (SPELLS_41,), shared=True),
    Tip(
        "f7e35d1867d741a5d4c520eab00eacbf93718edd",
        1591,
        "green",
        files=("features/jbus/src/jbus/mainmoved.py", SPELLS_41.split("::")[0]),
    ),
    Tip("ac7090388f62dba8eff0d6667a2739850fe9229e", 1620, "failed", SPELL_43),
    Tip(
        "54d9f00557427b520a293fd2373e39e9130f7a28",
        1625,
        "failed",
        SPELL_43,
        ("features/jbus/docs/jbus/the-telemetry-store.md",),
        shared=True,
    ),
    Tip(
        "76e46d4c07ce86282fa242e0fff0929ab1ad16a6",
        1628,
        "green",
        files=("features/verify-jstack/project-skill/scripts/fake-gh",),
    ),
    Tip("072ff1679aff9764b7d4494ab798cb701a9224a7", 1638, "failed", (SPELL_44,)),
    Tip(
        "3573df26cc9c3f0a10727c92a8e313c53b966f60",
        1640,
        "green",
        files=(STATECHART, "features/skill-library/tests/test_statechart_png_scale.py"),
    ),
    Tip("d6d1e7754833f0ebf021d69538e6b2334885e125", 1651, "failed", (SPELL_45,)),
    Tip(
        "184b917ef6b69c11a189e8620ab1a2a83d52de19",
        1649,
        "green",
        files=(
            STATECHART,
            "features/jbus/spec/MainRed-statechart/summary.json",
            "features/repo-guards/tests/test_statechart_current.py",
        ),
    ),
]
CHAIN = [GREEN, *MAIN]


@dataclass
class Asked:
    stdout: str
    returncode: int = 0


@dataclass
class GitHub:
    """A pass as `tell` reads it, with main at `main`, over GitHub's answers for `CHAIN`."""

    state: Path
    main: str
    now: Any = NOW
    answers: dict[str, Any] = field(default_factory=dict)
    world: Any = None

    def tip(self) -> str:
        return self.main

    def run(self, *command: str) -> Asked:
        asked = self.answer(*command)
        if "-i" in command and asked.returncode == 0:
            return Asked("HTTP/2.0 200 OK\r\n\r\n" + asked.stdout)
        return asked

    def answer(self, *command: str) -> Asked:
        path = command[2] if command[:2] == ("gh", "api") else ""
        place = {tip.sha: n for n, tip in enumerate(CHAIN)}
        if "/commits?sha=" in path:
            at = place[path.split("sha=")[1].split("&")[0]]
            return Asked(
                json.dumps(
                    [
                        {
                            "sha": tip.sha,
                            "parents": [{"sha": CHAIN[n - 1].sha}] if n else [],
                            "commit": {"message": f"fix: a change (#{tip.pr})"},
                        }
                        for n, tip in reversed(list(enumerate(CHAIN[: at + 1])))
                    ]
                )
            )
        if "/actions/runs?head_sha=" in path:
            runs = [{"event": "push", "head_branch": "main", "check_suite_id": 1}]
            return Asked(json.dumps({"workflow_runs": runs}))
        if path.endswith("/check-runs"):
            n = place[path.split("/commits/")[1].split("/")[0]]
            run = {"id": 100 + n, "name": "check 1 of 8", "status": "completed"}
            return Asked(
                json.dumps(
                    {"check_runs": [{**run, "conclusion": "failure", "check_suite": {"id": 1}}]}
                )
            )
        if path.endswith("/logs"):
            failed = CHAIN[int(path.split("/")[-2]) - 100].failed
            return Asked(
                "".join(f"FAILED {test} - assert 1 == 2\n" for test in failed)
                + f"===== {len(failed)} failed, 9 passed in 1.0s =====\n"
                "make: *** [Makefile:85: test] Error 1\n"
            )
        if "/actions/jobs/" in path:
            return Asked(json.dumps({"steps": [{"name": "make test", "conclusion": "failure"}]}))
        if (at := path.rpartition("/commits/")[2]) in place:
            files = [{"filename": name} for name in CHAIN[place[at]].files]
            return Asked(json.dumps({"sha": at, "files": files}))
        if command[:2] == ("git", "symbolic-ref"):
            return Asked("origin/main\n")
        return Asked("", 1)


def test_the_nov_10_11_spells_get_the_verdicts_their_ends_tell(machine, monkeypatch):
    """A red that fails only its open spell's tests is that spell, a real fault, though the
    pull requests over it make `reverts.flaky` read its tests as flakes; a spell ends in a fix
    where a merge changed the failed test's file or its feature's own code; and the flakes
    `flakerow` counts are the spells that went green with no fix."""
    state = machine.state("alpha")
    record = mainjson.record(main=GREEN.sha, at=iso(NOW), check="green", broken="", green=GREEN.sha)
    (state / mainjson.NAME).write_text(json.dumps(record))
    monkeypatch.setattr(
        mainmoved, "main_check", lambda run, at, **_: next(t.check for t in CHAIN if t.sha == at)
    )
    for tip in MAIN:
        if tip.shared:
            machine.append(
                "alpha",
                "ci.jsonl",
                *(one for test in tip.failed for one in flaked(test, "row-a", "row-b")),
            )
        mainmoved.tell(GitHub(state, tip.sha))
    lines = [json.loads(line) for line in (state / mainmoved.REDS).read_text().splitlines()]
    reds = {line["sha"][:9]: line["verdict"] for line in lines if "verdict" in line}
    assert reds == {
        "fb91d403c": "change",
        "8b6c51f76": "change",
        "ac7090388": "change",
        "54d9f0055": "change",
        "072ff1679": "change",
        "d6d1e7754": "change",
    }
    causes = {line["sha"][:9]: line["cause"] for line in lines if "cause" in line}
    assert causes == {
        "fb91d403c": "fix: #1591",
        "ac7090388": "fix: #1628",
        "072ff1679": "no fix",
        "d6d1e7754": "no fix",
    }
    flakes = flakerow.flakes(lines)
    assert {test: [sha[:9] for _, sha in seen] for test, seen in flakes.items()} == {
        SPELL_44: ["072ff1679"],
        SPELL_45: ["d6d1e7754"],
    }
