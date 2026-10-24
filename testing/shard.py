"""`--shard K/N`: run only the K-th of N parts of the tests the run selected, so that N jobs run
the suite side by side. `make check SHARD=K/N` passes it, and the check workflow's matrix runs
the four parts of its check and of its full run that way.

A test's part is a hash of its node id, so each test is in exactly one part, whatever other
tests the run has. The hash is sha256 and not Python's `hash`, which a process salts on its
own: every xdist worker and every job must work out the same part for the same test. The parts
split what the run selected, so the tests `make check-fast` names are split as the whole suite
is. A part that holds none of them passes, since a small selection leaves some parts empty.
`features/repo-guards/tests/test_shards.py` holds the four parts to the whole collection."""

import hashlib

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--shard",
        metavar="K/N",
        help="run only the K-th of N parts of the selected tests, split by a hash of each node id",
    )


def part(nodeid: str, parts: int) -> int:
    """The part, from 1 to `parts`, that the test with this node id is in."""
    return int.from_bytes(hashlib.sha256(nodeid.encode()).digest()[:8], "big") % parts + 1


def shard(config) -> tuple[int, int] | None:
    text = config.getoption("shard")
    if not text:
        return None
    one, _, of = text.partition("/")
    if not (one.isdigit() and of.isdigit() and 1 <= int(one) <= int(of)):
        raise pytest.UsageError(f"--shard takes K/N with 1 <= K <= N, not {text!r}")
    return int(one), int(of)


def pytest_collection_modifyitems(config, items):
    which = shard(config)
    if which is None:
        return
    one, of = which
    kept, left = [], []
    for item in items:
        (kept if part(item.nodeid, of) == one else left).append(item)
    if left:
        config.hook.pytest_deselected(items=left)
        items[:] = kept


def pytest_sessionfinish(session, exitstatus):
    if shard(session.config) and exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED:
        session.exitstatus = pytest.ExitCode.OK
