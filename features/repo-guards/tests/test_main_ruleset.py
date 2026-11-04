"""`main-ruleset.json` beside this file is the body of the ruleset on main, as
`gh api -X PUT repos/JoshuaHayesWasHere/jstack/rulesets/25665226 --input main-ruleset.json`
applies it. Its `required_status_checks` rule requires the `check` context with strict required
status checks, so GitHub merges no pull request whose branch does not hold main's tip, and a
merge by hand cannot skip the bar `jmerge` merges on. The test fails when the file stops
requiring `check` or drops the strict flag."""

import json

from testing.paths import REPO

RULESET = REPO / "features" / "repo-guards" / "tests" / "main-ruleset.json"


def required_status_checks() -> dict:
    rules = json.loads(RULESET.read_text())["rules"]
    found = [rule["parameters"] for rule in rules if rule["type"] == "required_status_checks"]
    assert len(found) == 1, f"{RULESET.name} has {len(found)} required_status_checks rules"
    return found[0]


def test_main_requires_check():
    contexts = [one["context"] for one in required_status_checks()["required_status_checks"]]
    assert "check" in contexts, f"{RULESET.name} does not require check: {contexts}"


def test_main_requires_checks_up_to_date():
    assert required_status_checks()["strict_required_status_checks_policy"] is True, (
        f"{RULESET.name} lets a pull request merge on a check over an old main"
    )
