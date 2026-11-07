"""A pass asks GitHub for the runs of a nightly workflow, browser.yml or macos-nightly.yml, only in
a repo whose `.github/workflows/` holds it: in any other, each ask is a 404 that spends the core
budget. Where GitHub gives no list of the files, the pass still asks for both, as before."""

from jbus import watch
from test_jbus_kitchen import NOW

CHECK = "name: check\non:\n  push:\n    branches: [main]\njobs: {}\n"


def asked_runs(kitchen, flows):
    """Run a pass over a repo whose workflow files are `flows` and return the nightlies it asked
    GitHub for the runs of."""
    kitchen.set("workflows.json", flows)
    kitchen.poll(NOW)
    log = (kitchen.stub / "gh.log").read_text()
    nightlies = [nightly.file for nightly in watch.NIGHTLIES]
    return [file for file in nightlies if f"actions/workflows/{file}/runs" in log]


def test_a_repo_with_neither_nightly_is_asked_for_no_nightlys_runs(kitchen):
    assert asked_runs(kitchen, {"check.yml": CHECK}) == []


def test_a_repo_holding_macos_nightly_is_asked_for_its_runs_alone(kitchen):
    flows = {"check.yml": CHECK, "macos-nightly.yml": CHECK}
    assert asked_runs(kitchen, flows) == ["macos-nightly.yml"]


def test_where_github_gives_no_list_of_the_files_both_nightlies_are_asked_for(kitchen):
    assert asked_runs(kitchen, None) == ["browser.yml", "macos-nightly.yml"]
