"""When a rebase drops lines, `jmerge` holds the pull request until its crew puts the lines
back or says why at that head. Then it waits for the scoped review, which rules on each
reason. Only a drop that the review ruled against goes to the user to decide."""

import pytest

import jsettings
import test_home_merge as merge
from jmerge import ready
from test_jmerge_fresh import Kitchen, url

HEAD = "c" * 40
LOST = (ready.Drop("a.py", 2, 1), ready.Drop("b.py", 0, 3))
ACKS = (
    "Dropped on rebase: a.py, 2 of main's, 1 of its own, at cccccccccccc: the task replaces them\n"
    "Dropped on rebase: b.py, 0 of main's, 3 of its own, at cccccccccccc: main's change, see #7\n"
)


def review(head=HEAD, drops=""):
    return f"## Review\nVerdict: clean\nScope: range-diff x y\n{drops}Head: {head}\nFindings:\n"


def test_nothing_lost_keeps_nothing_from_the_merge():
    assert ready.drops((), "", HEAD, user=jsettings.DEFAULTS) == ("", "")
    assert ready.drops((ready.Drop("a.py", 0, 0),), "", HEAD, user=jsettings.DEFAULTS) == ("", "")


def test_a_drop_with_no_line_at_the_head_waits_on_the_crew():
    every = (
        "the rebase dropped 2 of main's lines in a.py and 1 of its own in a.py and 3 of its "
        "own in b.py with no Dropped on rebase line at cccccccccccc"
    )
    assert ready.drops(LOST, "", HEAD, user=jsettings.DEFAULTS) == ("wait", every)
    older = ACKS.replace("cccccccccccc", "bbbbbbbbbbbb")
    assert ready.drops(LOST, older, HEAD, user=jsettings.DEFAULTS) == ("wait", every)
    assert ready.drops(
        LOST, "Dropped on rebase: a.py, on purpose\n", HEAD, user=jsettings.DEFAULTS
    ) == ("wait", every)
    miscounted = ACKS.replace("a.py, 2 of main's", "a.py, 1 of main's")
    assert ready.drops(
        LOST, miscounted + review(drops="Drops: upheld a.py, b.py\n"), HEAD, user=jsettings.DEFAULTS
    ) == (
        "wait",
        "the rebase dropped 2 of main's lines in a.py and 1 of its own in a.py "
        "with no Dropped on rebase line at cccccccccccc",
    )


RANGES = f"git range-diff --no-color {'1' * 40}..{'a' * 40} {'2' * 40}..{HEAD}"


def test_an_explained_drop_waits_on_the_scoped_review_of_the_range_diff():
    unruled = (
        "wait",
        f"the scoped review has not ruled on the drops in a.py, b.py; scoped review of {RANGES}",
    )
    said = ACKS
    assert ready.drops(LOST, said, HEAD, user=jsettings.DEFAULTS, command=RANGES) == unruled
    said += review("a" * 40, "Drops: upheld a.py, b.py\n")
    assert ready.drops(LOST, said, HEAD, user=jsettings.DEFAULTS, command=RANGES) == unruled


def test_a_drop_a_review_of_the_head_said_nothing_of_is_the_users():
    """Each head gets one review. When that review says nothing about a drop, no later review
    will rule on it, so the drop goes to the user. The review may be a full review written
    at the rebased head, or a scoped one that left a file out."""
    half = review(drops="Drops: upheld a.py\n")
    assert ready.drops(LOST, ACKS + half, HEAD, user=jsettings.DEFAULTS) == (
        "hold",
        "needs user, the review of cccccccccccc did not rule on the drops in b.py",
    )
    assert ready.drops(LOST, ACKS + review(), HEAD, user=jsettings.DEFAULTS) == (
        "hold",
        "needs user, the review of cccccccccccc did not rule on the drops in a.py, b.py",
    )


def test_a_later_review_of_the_head_that_says_nothing_of_the_drops_takes_no_ruling_away():
    ruled = review(drops="Drops: upheld a.py, b.py\n")
    assert ready.drops(LOST, ACKS + ruled + review(), HEAD, user=jsettings.DEFAULTS) == (
        "",
        "",
    )
    again = review(drops="Drops: not upheld b.py: the task needs them\n")
    assert ready.drops(LOST, ACKS + ruled + again + review(), HEAD, user=jsettings.DEFAULTS) == (
        "hold",
        "needs user, the review did not uphold the drop in b.py: the task needs them",
    )


def test_a_drop_the_review_did_not_uphold_is_the_users():
    ruled = review(drops="Drops: upheld a.py\nDrops: not upheld b.py: the task needs them\n")
    assert ready.drops(LOST, ACKS + ruled, HEAD, user=jsettings.DEFAULTS) == (
        "hold",
        "needs user, the review did not uphold the drop in b.py: the task needs them",
    )


def test_drops_explained_and_upheld_keep_nothing_from_the_merge():
    ruled = review(drops="Drops: upheld a.py, b.py\n")
    assert ready.acks(ACKS, HEAD) == {
        "a.py": (2, 1, "the task replaces them"),
        "b.py": (0, 3, "main's change, see #7"),
    }
    assert ready.upheld(ACKS + ruled, HEAD) == {"a.py", "b.py"}
    assert ready.drops(LOST, ACKS + ruled, HEAD, user=jsettings.DEFAULTS) == ("", "")


def test_a_ruling_stands_for_a_fix_pushed_after_it_once_the_crew_says_so_at_the_new_head():
    """The scoped review saw the head that the rebase ended on. A fix moved the head, and the
    `Fixed:` line names it, so the crew explains the drop again at the new head, and `jmerge`
    does not ask for the ruling on the file twice."""
    fixed = "d" * 40
    ruled = review(drops="Drops: upheld a.py, b.py\n") + f"Fixed: {fixed}\n"
    silent, _ = ready.drops(LOST, ACKS + ruled, fixed, user=jsettings.DEFAULTS)
    assert silent == "wait"
    again = ACKS.replace("cccccccccccc", "dddddddddddd")
    assert ready.drops(LOST, ACKS + again + ruled, fixed, user=jsettings.DEFAULTS) == (
        "",
        "",
    )


@pytest.fixture
def notes(tmp_path):
    return Kitchen(tmp_path, {"n.txt": "one\ntwo\nthree\n"})


def dropped(notes):
    """The pull request after a rebase that removed one of main's lines, with its head before
    and after the rebase."""
    notes.crew("two", 7, {"n.txt": "one\ntwo\nthree\nours\n"})
    was = notes.pulls["two"]["headRefOid"]
    head = notes.rebase(
        "two", {"n.txt": "one\ntwo\nthree\ntheirs\n"}, {"n.txt": "one\ntwo\nthree\nours\n"}
    )
    return was, head


def brief(notes, was, head, more):
    """What the pull request's crewmate and the scoped reviewer added to the brief since the
    rebase."""
    notes.brief("two", was, "")
    with (notes.home.tasks / "two.md").open("a") as file:
        file.write(more)


def test_the_command_waits_on_the_crew_then_on_the_review_and_merges_an_upheld_drop(notes):
    was, head = dropped(notes)
    silent = (
        f"wait 7 {url(7)}: the rebase dropped 1 of main's lines in n.txt "
        f"with no Dropped on rebase line at {head[:12]}"
    )
    assert notes.run() == [silent]
    ack = f"Dropped on rebase: n.txt, 1 of main's, 0 of its own, at {head[:12]}: ours replaces it\n"
    brief(notes, was, head, ack)
    (said,) = notes.run()
    assert said.startswith(
        f"wait 7 {url(7)}: the rebase changed the content after its review; scoped review of "
    )
    scoped = merge.review("clean", head)
    brief(notes, was, head, ack + scoped.replace("Head:", "Drops: upheld n.txt\nHead:"))
    (said,) = notes.run()
    assert said.startswith("merged 7 two ")
    assert notes.at_main("n.txt") == "one\ntwo\nthree\nours"


def test_the_command_holds_a_drop_the_review_ruled_against(notes):
    was, head = dropped(notes)
    ack = f"Dropped on rebase: n.txt, 1 of main's, 0 of its own, at {head[:12]}: ours replaces it\n"
    ruled = merge.review("findings", head).replace(
        "Head:", "Drops: not upheld n.txt: main's line is still needed\nHead:"
    )
    brief(notes, was, head, ack + ruled)
    (said,) = notes.run()
    assert said.endswith(": its findings are not handled: the Result has no Fixed line")
    handled = (
        "Finding: not fixed, the drop in n.txt, because ours replaces main's line\n"
        "Fixed: none needed, the drop is on purpose\n"
    )
    brief(notes, was, head, ack + handled + ruled)
    held = (
        f"hold 7 {url(7)}: needs user, the review did not uphold the drop in n.txt: "
        "main's line is still needed"
    )
    assert notes.run("--check") == [held]
    assert notes.run() == [held]
    assert notes.calls() == []
