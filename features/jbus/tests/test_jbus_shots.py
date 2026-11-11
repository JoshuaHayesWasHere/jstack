"""Every brief jbus files itself names a child home on its `Home:` line, so no row it files starts
under the root home, which owns no row, and has no fault `jbus queue add` refuses, such as a
missing `Why:` line, so that no row it files is refused unseen.

`WRITERS` is the list of each function of `jbus` that queues a brief as a pass (`queue.add` with
`ran_by=queue.PASS`), with the builder its brief comes from. A new writer that is not on it fails
`test_each_writer_of_a_pass_row_is_one_this_file_builds`, so its brief is built and read here
before it ships."""

import ast
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from jbriefs import home as homes
from jbus import daywarnings, flakerow, queue, reverts, shots, watch
from jbus.ci import wrongcloses

SOURCE = Path(reverts.__file__).parent


def _shots():
    jobs = [("browser", "https://example.test/job/1", [shots.DRAWN_BY[0]])]
    return shots.brief(
        "shots-2026-11-09", "2026-11-09", "browser.yml", 42660785539, "jbus: ", jobs, "", False
    )


def _fix():
    jobs = [("check", "https://example.test/job/2", ["features/jbus/tests/test_x.py::test_y"])]
    return watch.fix_brief(
        "main-red-abc: a red",
        '"a red"',
        "main is red",
        ["- it passes"],
        "`make check` passes",
        "main",
        jobs,
    )


def _flake():
    test = "features/jbus/tests/test_x.py::test_y"
    pair = (
        (datetime(2026, 11, 2, tzinfo=UTC), "a" * 40),
        (datetime(2026, 11, 5, tzinfo=UTC), "b" * 40),
    )
    return flakerow.brief(flakerow.slug(test), test, pair)


def _warnings():
    kept = daywarnings.Kept("alpha", "w1", "src/alpha/a.py:3", "off by one", "#7", "2026-11-08")
    return daywarnings.brief("2026-11-09", [kept])


def _revert():
    culprit = reverts.Culprit("a" * 40, "alpha", {"number": 7, "headRefName": "alpha"})
    home = reverts.home_of_revert("# alpha: a brief queued under the root\nHome: root\n")
    return reverts.brief("revert-7-alpha", culprit, "https://example.test/pull/8", home)


def _labels():
    start, end = datetime(2026, 11, 2, tzinfo=UTC), datetime(2026, 11, 9, tzinfo=UTC)
    user = SimpleNamespace(stamp=lambda moment: moment.isoformat())
    return wrongcloses.request(date(2026, 11, 2), start, end, ["gate-1"], user)


BUILT = {
    "shots": _shots,
    "fix": _fix,
    "flake": _flake,
    "warnings": _warnings,
    "revert": _revert,
    "labels": _labels,
}
"""Each brief jbus files itself, by the builder that writes it."""

WRITERS = {
    "ci.wrongcloses._label": "labels",
    "daywarnings.keep": "warnings",
    "flakerow.file": "flake",
    "reverts._mac_file": "fix",
    "watch._add_tip": "fix",
    "watch._file": "fix",
    "watch._filed": "shots",
}
"""Each function that queues a brief as a pass, with the builder of that brief. `watch._filed`
queues the nightly run's fix brief too, and `watch._add_tip` a fix brief already filed with a
line added under `Read:`. `reverts.revert` writes its brief to `tasks/` and queues no row."""


@pytest.mark.parametrize("kind", sorted(set(BUILT) - {"revert"}))
def test_each_brief_jbus_queues_has_no_fault_queue_add_refuses(kind):
    """A pass that files a row catches `add`'s refusal and only logs it, so a brief whose shape
    falls behind the lint stops being filed with nobody told: the fix of a red main among them.
    The revert's brief is written to `tasks/` with its Result and never queued."""
    text = BUILT[kind]()
    assert queue.faults(text, text.split(":", 1)[0].removeprefix("# ")) == []


@pytest.mark.parametrize("kind", sorted(BUILT))
def test_each_brief_jbus_files_names_a_child_home(kind):
    named = homes.named(BUILT[kind]())
    assert named and named != homes.ROOT, f"the {kind} brief's Home: line names {named or 'none'}"


def test_the_shots_row_is_the_catch_all_s():
    assert homes.named(_shots()) == homes.UNCATEGORIZED


def _passes_queue(node):
    """Whether a call is `queue.add(..., ran_by=queue.PASS)`."""
    return (
        isinstance(node, ast.Call)
        and ast.unparse(node.func) == "queue.add"
        and any(
            word.arg == "ran_by" and ast.unparse(word.value) == "queue.PASS"
            for word in node.keywords
        )
    )


def test_each_writer_of_a_pass_row_is_one_this_file_builds():
    found = set()
    for path in sorted(SOURCE.rglob("*.py")):
        module = ".".join(path.relative_to(SOURCE).with_suffix("").parts)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and any(
                _passes_queue(inner) for inner in ast.walk(node)
            ):
                found.add(f"{module}.{node.name}")
    assert found == set(WRITERS), "a writer of a pass row: build its brief in BUILT, list it here"
    assert set(WRITERS.values()) <= set(BUILT)
