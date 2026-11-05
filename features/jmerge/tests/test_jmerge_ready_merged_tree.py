"""The reasons a pull request waits on the fast guards of its merged tree (`jmerge.treeguards`),
as `jmerge.ready` names them: each line carries its own code, and jbus and the view read the
step from it, so a guard the crew must fix is on the `rebase` step and a run that did not end is
on the `check` step."""

import pytest

from jmerge import lines, ready

URL = "https://example.test/pull/7"
FILLED = {"base": "main", "tip": "a" * 12, "guard": "lint", "minutes": 10, "why": "it said no"}


@pytest.mark.parametrize(
    ("reason", "code", "step"),
    [
        (ready.MERGED_TREE_FAILS, "merged-tree-fails", "rebase"),
        (ready.MERGED_TREE_UNENDED, "merged-tree-unended", "check"),
        (ready.MERGED_TREE_UNBUILT, "merged-tree-unbuilt", "check"),
        (ready.MERGED_TREE_NO_TIME, "merged-tree-no-time", "check"),
    ],
)
def test_merged_tree_waits_carry_their_code_and_step_as_printed_and_as_logged(reason, code, step):
    why = reason.format(**FILLED)
    printed = str(lines.waits("wait", 7, URL, why))
    assert lines.logged(lines.waits("wait", 7, URL, why)) == f"{printed} [{code}]"
    assert ready.code_of(str(why)) == code
    assert ready.step_of(code) == step
