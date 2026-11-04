"""`features/repo-guards/main-ruleset.json` is the body of the ruleset on main, as
`gh api -X PUT repos/JoshuaHayesWasHere/jstack/rulesets/25665226 --input <that file>` applies
it. Its `required_status_checks` rule requires the contexts `check`, `borders` and `macos`, the
ones jmerge merges on, so a merge by hand cannot skip the bar jmerge holds. Strict required
status checks are off (Josh, 2026-11-04): a pull request need not hold main's tip, so one merge
does not send every other open pull request back through its checks. No actor may bypass the
ruleset. `testing/tests/test_workflows.py` checks that each required context is a job that
posts on every pull request into main."""

import json

from testing.paths import REPO

RULESET = REPO / "features" / "repo-guards" / "main-ruleset.json"


def ruleset() -> dict:
    return json.loads(RULESET.read_text())


def required_status_checks() -> dict:
    found = [r["parameters"] for r in ruleset()["rules"] if r["type"] == "required_status_checks"]
    assert len(found) == 1, f"{RULESET.name} has {len(found)} required_status_checks rules"
    return found[0]


def test_main_requires_check_borders_and_macos():
    contexts = sorted(one["context"] for one in required_status_checks()["required_status_checks"])
    assert contexts == ["borders", "check", "macos"], f"{RULESET.name} requires {contexts}"


def test_main_does_not_require_a_branch_to_hold_mains_tip():
    assert required_status_checks()["strict_required_status_checks_policy"] is False, (
        f"{RULESET.name} sends every open pull request back through its checks on each merge"
    )


def test_no_actor_may_bypass_the_ruleset():
    assert ruleset()["bypass_actors"] == [], f"{RULESET.name} lets an actor bypass the ruleset"
