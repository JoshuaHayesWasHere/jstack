"""A brief whose `Review:` line says `after` merges on its check alone: its review runs
beside the merge or after it, and what it finds goes to a cleanup row, never to a hold.
Driven through `ready.short_of`, the reader the merge goes by, and through `jmerge` itself
against a real origin and a fake `gh` (`tests/test_jmerge_fresh.py`)."""

import json

import jsettings
import test_home_merge as merge
from jmerge import ready
from test_jmerge_fresh import LINES, Kitchen, url

HEAD, FIX = "a" * 40, "b" * 40
PULL = "https://example.test/pull/7"


def brief(mode, result=""):
    return (
        f'# alpha: a task\nTask: "do it"\nPull request: open one when done\nReview: {mode}\n\n'
        f"## Result\nStatus: done\nBranch: alpha   Pull request: {PULL}\n{result}"
    )


def review(verdict="findings", head=HEAD, found=("warning a.py:3 a made up one (bucket: Act on)",)):
    listed = "".join(f"- {one}\n" for one in found) if verdict == "findings" else "- none\n"
    return f"\n## Review\nBy: codex\nVerdict: {verdict}\nHead: {head}\nFindings:\n{listed}"


def test_an_after_brief_with_no_review_is_short_of_nothing_and_a_review_brief_is_not():
    assert ready.short_of(brief("after"), HEAD) == ""
    assert ready.short_of(brief("review"), HEAD) == ready.NO_REVIEW
    assert ready.short_of(brief("none"), HEAD) == ready.REVIEW_NONE


def test_findings_that_land_on_an_after_brief_change_nothing_jmerge_reads():
    """No `Fixed:` line, no answered findings, a decline the scoped pass overruled on a risk:
    each would hold a `Review: review` brief, and none holds this one."""
    bare = brief("after", "Reviewer: mcp:9\n")
    found = bare + review()
    risky = review(found=("error a.py:3 a leak (bucket: Act on) (risk: data)",))
    overruled = (
        bare
        + risky
        + "Finding F1: not fixed, a leak, because a.py:3 is fine\n"
        + review("clean", FIX).replace("Verdict: clean", "Verdict: clean\nScope: range-diff x y")
        + "Declines: not upheld F1: it leaks\n"
    )
    for text in (found, overruled, bare + review("not run")):
        assert ready.short_of(text, HEAD) == ""
        assert ready.short_of(text, FIX) == ""
        assert ready.declines(text, user=jsettings.DEFAULTS) == ("", "")
        assert ready.to_range_diff(None, text, FIX) is None
    assert ready.short_of(found.replace("Review: after", "Review: review"), HEAD) == ready.NO_FIXED


def test_an_after_brief_still_owes_its_skills_and_the_crews_own_drop_lines():
    owed = brief("after").replace("Review: after", "Review: after\nSkills: tdd")
    assert ready.short_of(owed, HEAD) == ready.SKILLS_UNRUN.format(names="tdd")
    lost = (ready.Drop("a.py", 2, 0),)
    kind, _ = ready.drops(lost, brief("after"), HEAD, user=jsettings.DEFAULTS)
    assert kind == "wait"
    said = f"Dropped on rebase: a.py, 2 of main's, 0 of its own, at {HEAD[:12]}: replaced\n"
    assert ready.drops(lost, brief("after", said), HEAD, user=jsettings.DEFAULTS) == ("", "")
    ruled = brief("review", said)
    assert ready.drops(lost, ruled, HEAD, user=jsettings.DEFAULTS)[0] == "wait"


def after(kitchen, slug, extra=""):
    """The brief as an `after` crewmate leaves it: a Result and its reviewer, and whatever
    the review wrote since."""
    pull = kitchen.pulls[slug]
    (kitchen.home.tasks / f"{slug}.md").write_text(
        f'# {slug}: a task\nTask: "do it"\nPull request: open one when done\nReview: after\n\n'
        f"## Result\nStatus: done\nBranch: {slug}   Pull request: {pull['url']}\n"
        f"Reviewer: mcp:9\n{extra}"
    )


def test_jmerge_merges_an_after_pull_request_once_its_check_passed(tmp_path):
    kitchen = Kitchen(tmp_path, {"a.txt": LINES})
    head = kitchen.crew("alpha", 7, {"a.txt": "ours\n" + LINES})
    after(kitchen, "alpha")
    (said,) = kitchen.run("--check")
    assert said == f"ready 7 {head} alpha alpha"
    assert kitchen.calls() == []
    (said,) = kitchen.run()
    assert said.startswith(f"merged 7 alpha {head} ")


def test_a_review_that_lands_while_it_is_open_leaves_its_reasons_as_they_were(tmp_path):
    kitchen = Kitchen(tmp_path, {"a.txt": LINES})
    head = kitchen.crew("alpha", 7, {"a.txt": "ours\n" + LINES})
    kitchen.pulls["alpha"]["statusCheckRollup"] = [merge.FAILED]
    (kitchen.home.stub / "list.json").write_text(json.dumps(list(kitchen.pulls.values())))
    after(kitchen, "alpha")
    before = kitchen.run("--check")
    after(kitchen, "alpha", review(head=head))
    assert kitchen.run("--check") == before == [f"wait 7 {url(7)}: {ready.NOT_PASSED}"]
