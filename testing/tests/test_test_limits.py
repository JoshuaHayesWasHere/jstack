"""Each test has a bound of 120 s (`timeout` in pyproject.toml), and a test may set its own with
`pytest.mark.timeout`, on itself or for its module. A limit over LONG_LIMIT seconds is a choice
somebody made: each place that sets one is on LONG, with the reason, so a new long test is a
change to this list and not a number nobody reads. A place is a test function, named by its file
and its name with no parameters, or a module or class whose `pytestmark` sets it for each of its
tests. The list changes no limit: the limits are where the tests set them.

The test asks pytest itself, as the check's parts do: a pytest that collects the whole suite with
a small plugin that writes, for each test, its closest `timeout` mark and the node that set it."""

import json
import os
import subprocess
import sys

from testing.paths import REPO

LONG_LIMIT = 300

PLUGIN = """
import json
import os


def pytest_collection_modifyitems(items):
    found = {}
    for item in items:
        mark = next(item.iter_markers_with_node("timeout"), None)
        if mark is None:
            continue
        node, mark = mark
        if node is item:
            place = f"{item.nodeid.partition('::')[0]}::{item.originalname}"
        else:
            place = node.nodeid
        found[place] = mark.args[0] if mark.args else mark.kwargs["timeout"]
    with open(os.environ["LIMITS_OUT"], "w") as out:
        json.dump(found, out)
"""

LONG = {}


def limits(tmp_path, *args):
    """Each place that sets its tests' own limit, and the seconds, as pytest collects them from
    the repo's config, with `args` passed to it."""
    (tmp_path / "limits_plugin.py").write_text(PLUGIN)
    out = tmp_path / "limits.json"
    path = os.pathsep.join(filter(None, [str(tmp_path), os.environ.get("PYTHONPATH")]))
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
        + ["-p", "limits_plugin", *args],
        cwd=REPO,
        env=os.environ | {"PYTHONPATH": path, "LIMITS_OUT": str(out)},
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stdout[-4000:] + ran.stderr[-4000:]
    return json.loads(out.read_text())


def unlisted(found, listed):
    """Each place over LONG_LIMIT that `listed` gives no reason for, with its seconds."""
    return {
        place: seconds
        for place, seconds in found.items()
        if seconds > LONG_LIMIT and not listed.get(place, "").strip()
    }


def test_a_test_with_its_own_limit_over_300_s_fails_until_the_list_gives_its_reason(tmp_path):
    """A test of a module made here, which sets 301 s on itself, and a module that sets 900 s for
    its tests, are read from pytest's collection; 300 s is not over the line."""
    made = tmp_path / "made"
    made.mkdir()
    (made / "test_made.py").write_text(
        "import pytest\n\n\n@pytest.mark.timeout(301)\n@pytest.mark.parametrize('n', [1, 2])\n"
        "def test_long(n):\n    pass\n\n\n@pytest.mark.timeout(300)\ndef test_at_the_line():\n"
        "    pass\n"
    )
    (made / "test_module.py").write_text(
        "import pytest\n\npytestmark = pytest.mark.timeout(900)\n\n\ndef test_one():\n    pass\n"
    )
    found = limits(tmp_path, "--rootdir", str(made), "-c", os.devnull, str(made))
    assert found == {
        "test_made.py::test_long": 301,
        "test_made.py::test_at_the_line": 300,
        "test_module.py": 900,
    }
    assert unlisted(found, {}) == {
        "test_made.py::test_long": 301,
        "test_module.py": 900,
    }
    assert unlisted(found, {"test_module.py": " "}) == {
        "test_made.py::test_long": 301,
        "test_module.py": 900,
    }
    reasons = {"test_made.py::test_long": "why", "test_module.py": "why"}
    assert unlisted(found, reasons) == {}


def test_every_test_of_the_suite_with_its_own_limit_over_300_s_is_on_the_list(tmp_path):
    """Each place of the suite over LONG_LIMIT is on LONG with its reason, and each place on LONG
    is one that still sets a limit over it, so the list says what the suite does."""
    found = limits(tmp_path)
    assert unlisted(found, LONG) == {}
    assert [place for place in LONG if found.get(place, 0) <= LONG_LIMIT] == []
