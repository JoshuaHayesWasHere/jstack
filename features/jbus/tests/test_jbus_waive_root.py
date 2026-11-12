"""`jbus waive <slug> <n>... --as root --from <root thread> --reason <why> --undo <how>` records the
root home's own waiver of a row's `Done when` lines, with no word of the user's, and jmerge's ready
check counts it (`jbus.waive`). Only the root home's thread waives so; a scoped home's, a crew's,
and a waiver with no reason or no undo are refused with one line, and so is a brief that holds for
a one-way door, whose merge cannot be undone. The user still reads each such waiver once, as one
line of `jbus needs` (and so of the catch-up) with nothing to answer.

The tests run the real commands against the faked T3 Code server of `test_jbus_kitchen`, and judge
the row as `jmerge` does: `ready.short_of` with the waivers `jmerge.rows.heard` counts."""

from datetime import timedelta

import pytest

from jbriefs import meets
from jbus import acts, verbs
from jmerge import ready, rows
from test_jbus_kitchen import NOW

ROOT = "mcp:" + "-".join("r" * size for size in (8, 4, 4, 4, 12))
SCOPED = "mcp:" + "-".join("s" * size for size in (8, 4, 4, 4, 12))
CREW = "mcp:" + "-".join("c" * size for size in (8, 4, 4, 4, 12))
HEAD = "a" * 40
LINES = ("the command runs", "the test takes under 15 s", "the docs say it")
DONE = "Done when:\n" + "".join(f"- {one}\n" for one in LINES)
BRIEF = (
    f"# alpha: a task\nTask: do it\n{DONE}Size: S\nReview: review\nThread: {CREW}\n"
    "\n## Result\nStatus: done\nBranch: alpha   Pull request: https://example.test/pull/7\n"
    "Reviewer: mcp:9 #1\n"
    f"\n## Review\nBy: inherit #1\nVerdict: clean\nHead: {HEAD}   Unchanged by the review: yes\n"
    "Meets the brief: no, 2 of 3\n- unmet 2: the test takes 15.2 s\nIn flight: none\n"
    "Findings:\n- none\nDropped: 0\n"
)
REASON = "the test takes 15.2 s where the line asks for 15, and the bound is a guess"
UNDO = "revert the merge, and file a row to cut the test under 15 s"


@pytest.fixture
def homes(kitchen):
    (kitchen.home / "home-id").write_text(f"{ROOT}\n")
    (kitchen.home / "scope").mkdir()
    (kitchen.home / "scope" / "plan.md").write_text("# a plan\n")
    (kitchen.home / "scope" / "home-id").write_text(f"{SCOPED}\n")
    kitchen.brief("alpha", BRIEF)
    kitchen.monkeypatch.setattr(verbs, "clock", lambda: NOW)
    return kitchen


def waive(kitchen, *more, by=ROOT, lines=("2",)):
    return kitchen.main(
        "waive", "alpha", *lines, "--to", "demo", "--as", "root", "--from", by, *more
    )


def brief(kitchen):
    return (kitchen.home / "tasks" / "alpha.md").read_text()


def held(kitchen):
    """What jmerge's ready check says the pull request is short of, with the waivers it counts."""
    text = brief(kitchen)
    heard = {one for one in meets.waivers(text) if not rows.heard(kitchen.checkout, one, "alpha")}
    return ready.short_of(text, HEAD, heard)


def waivers(kitchen):
    return [one for one in acts.read(kitchen.state) if one["action"]["verb"] == "waive"]


def test_the_roots_waiver_clears_the_line_jmerge_holds_the_row_on_with_no_word_of_the_users(homes):
    assert held(homes) == ready.MEETS_NO.format(head=HEAD[:12], met=2, count=3, lines="2")
    code, out = waive(homes, "--reason", REASON, "--undo", UNDO)
    assert code == 0, out
    assert held(homes) == ""
    (act,) = waivers(homes)
    assert act["party"]["kind"] == "root"
    assert act["outcome"] == "done"
    assert (act["action"]["subject"], act["action"]["pre"]) == ("alpha", "2")
    said = act["evidence"]
    assert (said["words"], said["undo"], said["said_in"]) == (REASON, UNDO, ROOT)
    assert f"Waived: {LINES[1]}, root/{act['id']}\n" in brief(homes)
    assert out == f"root waived alpha: line 2, as root/{act['id']}\n"


def test_the_same_waiver_again_logs_and_writes_nothing_new(homes):
    assert waive(homes, "--reason", REASON, "--undo", UNDO)[0] == 0
    text, logged = brief(homes), waivers(homes)
    assert waive(homes, "--reason", REASON, "--undo", UNDO)[0] == 0
    assert (brief(homes), waivers(homes)) == (text, logged)


def test_a_waived_line_names_no_other_line(homes):
    assert waive(homes, "--reason", REASON, "--undo", UNDO)[0] == 0
    (act,) = waivers(homes)
    other = meets.Waiver(1, f"root/{act['id']}", LINES[0])
    assert rows.heard(homes.checkout, other, "alpha") != ""


@pytest.mark.parametrize(
    ("by", "more", "said"),
    [
        (
            SCOPED,
            ("--reason", REASON, "--undo", UNDO),
            f"refused: --from {SCOPED} is not the root home's thread, and only the root waives "
            "on its own judgment: a scoped home sends its pick to the root with jbus stop "
            "--kind decision\n",
        ),
        (
            CREW,
            ("--reason", REASON, "--undo", UNDO),
            f"refused: --from {CREW} is not the root home's thread, and only the root waives "
            "on its own judgment: a scoped home sends its pick to the root with jbus stop "
            "--kind decision\n",
        ),
        (
            ROOT,
            ("--reason", REASON),
            "refused: a root waiver names how to undo it, --undo: one that cannot be undone is "
            "the user's to waive\n",
        ),
        (
            ROOT,
            ("--undo", UNDO),
            "refused: a root waiver names why the line need not hold, --reason\n",
        ),
    ],
    ids=["a scoped home", "a crew", "no undo", "no reason"],
)
def test_a_waiver_the_root_did_not_give_whole_is_refused_with_one_line(homes, by, more, said):
    assert waive(homes, *more, by=by) == (1, said)
    assert "Waived:" not in brief(homes)
    assert waivers(homes) == []


def test_a_brief_that_holds_for_a_door_is_the_users_to_waive(homes):
    homes.brief("alpha", BRIEF.replace("Size: S\n", "Size: S\nHolds: publishes\n"))
    code, out = waive(homes, "--reason", REASON, "--undo", UNDO)
    assert (code, out) == (
        1,
        "refused: alpha holds for publishes, so its merge cannot be undone and the user "
        "waives its lines\n",
    )
    assert "Waived:" not in brief(homes)


def test_the_user_reads_each_root_waiver_once_with_nothing_to_answer(homes):
    assert waive(homes, "--reason", REASON, "--undo", UNDO)[0] == 0
    homes.poll()
    line = (
        f'demo root waived alpha: line 2 "{LINES[1]}", because {REASON}; undo: {UNDO}; '
        "nothing to answer"
    )

    def needs(at):
        homes.monkeypatch.setattr(verbs, "clock", lambda: at)
        code, out = homes.main("needs")
        assert code == 0, out
        return out.splitlines()

    soon = needs(NOW + timedelta(minutes=5))
    assert soon == ["nothing waits on user in any project", line]
    assert needs(NOW + timedelta(days=2)) == ["nothing waits on user in any project"]


def test_the_users_own_waive_still_needs_their_message(homes):
    code, out = homes.main("waive", "alpha", "2", "--to", "demo")
    assert (code, out) == (
        1,
        "refused: --message names the user's own reply to the home's ask; only --as root "
        "waives without one\n",
    )


@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (
            ("--message", f"{ROOT}/yes", "--reason", REASON),
            "refused: --reason is only for --as root, and records nothing here\n",
        ),
        (
            (
                "--as",
                "root",
                "--from",
                ROOT,
                "--reason",
                REASON,
                "--undo",
                UNDO,
                "--message",
                f"{ROOT}/yes",
            ),
            "refused: --as root waives on the root's own judgment, with no --message\n",
        ),
    ],
    ids=["a reason on the user's path", "a message on the root's"],
)
def test_the_two_paths_take_no_word_of_the_other(homes, argv, said):
    assert homes.main("waive", "alpha", "2", "--to", "demo", *argv) == (1, said)
    assert "Waived:" not in brief(homes)
