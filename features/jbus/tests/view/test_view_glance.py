"""The band at the top of `#/`: in one look, what is wrong, then what waits on the user, then
whether the work moves. `/stack.json` has it as `glance`: its items in the order the band draws
them, each with its subject, its cause and since when, and `calm` where nothing is wrong and
nothing waits on the user, when the band is the one line that says the work moves."""

from datetime import timedelta

import pytest

import jsettings
from jbus.view import state as built
from jbus.view.state import iso
from jmerge import lines as jlines
from jmerge import ready
from test_jbus_kitchen import rate_limit
from view.days import DAYS
from view.scene import NOW, PULL, Scene, Served, ago, et, item, logged, out, row
from view.test_view_wrong import STALL, idle
from view.walk import runs, sources

RED = "badc0de" + "1" * 33


def stack(scene):
    served = Served(scene)
    try:
        return served.json("/stack.json")
    finally:
        served.close()


def quiet(scene):
    """One row at work, nothing at a gate, no question and every source as a day of runs
    leaves it."""
    scene.queue([row("jam-jar", "running", thread="mcp:0000")])
    scene.waiting([])
    (scene.home / "gates.md").unlink()
    for name in ("ci.jsonl", "ci-prs.jsonl", "stall.json"):
        (scene.state / name).unlink()
    scene.passed(20, threads=[out("crew: jam-jar", minutes=1)])


def troubled(scene):
    """The quiet scene with a red main, a stall, a hung thread and two rows that wait for the
    user's approval, which jbus's list of what waits on the user holds."""
    quiet(scene)
    scene.queue(
        [
            row("tea-kettle", approved="", why="not approved", since=et(ago(minutes=50))),
            row("tea-pot", approved="", why="not approved", since=et(ago(minutes=20))),
            row("jam-jar", "running", thread="mcp:0000"),
            row("oat-spoon", "pr", pr="#12", checks="passed", why="wait: it has no review yet"),
        ]
    )
    scene.waiting(
        [
            item("approve", f"approve:{slug}", f"approve {slug}: it", slug=slug, minutes=minutes)
            for slug, minutes in (("tea-kettle", 50), ("tea-pot", 20))
        ]
    )
    scene.passed(20, threads=[out("crew: jam-jar", "hung", minutes=25)])
    scene.write("main.json", {"at": iso(ago(minutes=12)), "main": RED, "check": "failed"})
    scene.events(("stall", "quiet", "oat-spoon", STALL, 6))
    scene.write("expedite.json", {"oat-spoon": idle(12)})


def drawn(glance):
    return [(one["tier"], one["kind"], one["subj"]) for one in glance["items"]]


def test_wrong_comes_first_then_what_waits_on_you_then_whether_it_moves(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    troubled(scene)
    glance = stack(scene)["glance"]
    assert drawn(glance) == [
        ("wrong", "thread", "crew: jam-jar"),
        ("wrong", "main", "main"),
        ("wrong", "stall", "oat-spoon"),
        ("yours", "approve", "2 approvals"),
        ("moving", "moving", "moving"),
    ]
    assert glance["calm"] is False
    by = {one["subj"]: one for one in glance["items"]}
    assert by["crew: jam-jar"]["since"] == iso(ago(minutes=25))
    assert by["main"]["since"] == iso(ago(minutes=12))
    assert by["oat-spoon"]["since"] == iso(ago(minutes=6))
    assert by["2 approvals"]["since"] == iso(ago(minutes=50))
    assert "badc0de" in by["main"]["cause"]
    assert "hung" in by["crew: jam-jar"]["cause"]
    assert "no review" in by["oat-spoon"]["cause"]
    assert by["2 approvals"]["cause"] == "tea-kettle, tea-pot"
    assert (by["2 approvals"]["verb"], by["2 approvals"]["count"]) == ("Approve 2", 2)
    for one in glance["items"]:
        assert one["cause"] and one["since"] and one["open"].startswith("#/")


def test_the_verdict_names_its_word_and_the_top_cause_with_its_age(tmp_path, monkeypatch):
    """A red main holds every merge, so it is the top cause though a hung thread is older. The
    two rows not approved are the largest group of rows that do not move, so the word is that
    the user holds the work."""
    scene = Scene(tmp_path, monkeypatch)
    troubled(scene)
    verdict = stack(scene)["glance"]["verdict"]
    assert verdict["top"] == {
        "tier": "wrong",
        "kind": "main",
        "subj": "main",
        "cause": f"red at {RED[:7]}",
        "since": iso(ago(minutes=12)),
    }
    assert (verdict["word"], verdict["last_merge"]) == ("HELD BY YOU", iso(ago(minutes=40)))
    assert verdict["cause"].startswith("2 not approved wait on you; slowed too by ")
    assert (verdict["per_hour"], verdict["window"]) == (0.3, 3)


def test_merges_an_hour_count_the_window_and_none_in_it_is_still(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    quiet(scene)
    scene.moves(*((f"rye-{n}", "pr", "merged", minutes) for n, minutes in enumerate((5, 50, 170))))
    verdict = stack(scene)["glance"]["verdict"]
    assert (verdict["word"], verdict["per_hour"]) == ("MOVING", 1.0)
    assert verdict["merges"] == [iso(ago(minutes=m)) for m in (170, 50, 5)]
    scene.moves(("rye-loaf", "pr", "merged", 200))
    verdict = stack(scene)["glance"]["verdict"]
    assert (verdict["word"], verdict["per_hour"]) == ("MOVING", 0.0)
    assert verdict["last_merge"] == iso(ago(minutes=200))
    assert verdict["top"]["tier"] == ""


def test_a_merge_before_midnight_counts_in_the_window_after_it(tmp_path, monkeypatch):
    """The window of the verdict crosses the start of the user's day: an hour after midnight,
    a merge ten minutes before it is the last merge and counts in the merges an hour."""
    scene = Scene(tmp_path, monkeypatch)
    quiet(scene)
    midnight = jsettings.load().local(NOW).replace(hour=0, minute=0, second=0, microsecond=0)
    before = iso(midnight - timedelta(minutes=10))
    scene.lines("transitions.jsonl", [{"slug": "rye", "from": "pr", "to": "merged", "at": before}])
    verdict = built.stack(sources(scene), midnight + timedelta(hours=1), runs)["glance"]["verdict"]
    assert (verdict["word"], verdict["last_merge"]) == ("MOVING", before)
    assert verdict["per_hour"] == 0.3


def test_a_quiet_machine_is_one_calm_line(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    quiet(scene)
    glance = stack(scene)["glance"]
    assert glance["calm"] is True
    assert drawn(glance) == [("moving", "moving", "moving")]
    (line,) = glance["items"]
    assert line["cause"] == "1 open in 1 project, 1 merged today, 1 thread out"
    assert line["since"] == iso(ago(seconds=20))


def test_jbus_stopped_is_wrong_and_first(tmp_path, monkeypatch):
    """A stopped jbus is the band's own entry: the wrong list leaves it to the band."""
    scene = Scene(tmp_path, monkeypatch)
    quiet(scene)
    scene.timer(active="inactive", sub="dead")
    given = stack(scene)
    assert drawn(given["glance"])[0] == ("wrong", "jbus", "jbus")
    assert given["glance"]["items"][0]["cause"] == "stopped: the timer is not active"
    assert given["glance"]["calm"] is False
    assert all(one["kind"] != "jbus" for one in given["wrong"])


def test_failed_passes_are_wrong_with_their_count(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    quiet(scene)
    since = iso(ago(minutes=4))
    scene.write("streaks.json", {"pass": {"count": 3, "since": since}}, scene.state_dir)
    (first,) = [one for one in stack(scene)["glance"]["items"] if one["tier"] == "wrong"]
    assert (first["kind"], first["cause"], first["since"]) == ("jbus", "3 passes failed", since)


def test_an_unreadable_streaks_file_is_a_wrong_source_and_says_no_pass_failed(
    tmp_path, monkeypatch
):
    """With `streaks.json` unreadable the band cannot say whether passes fail, so it says the
    file is unreadable instead; with no file, no streak is open and nothing is wrong."""
    scene = Scene(tmp_path, monkeypatch)
    quiet(scene)
    assert stack(scene)["glance"]["calm"] is True
    (scene.state_dir / "streaks.json").write_text("{not json")
    glance = stack(scene)["glance"]
    assert ("wrong", "source", "streaks.json") in drawn(glance)
    assert all(one["kind"] != "jbus" for one in glance["items"])


def stalled(scene):
    """The quiet scene with its one row a pull request whose check failed, the last merge
    200 minutes ago and the last act 45 minutes ago."""
    quiet(scene)
    why = "wait: check has not passed"
    scene.queue([row("oat-spoon", "pr", pr="#12", checks="failed", why=why)])
    scene.moves(("rye-loaf", "pr", "merged", 200))
    scene.events(("result", "quiet", "oat-spoon", "result oat-spoon: Status: done", 45))
    scene.merge_log(logged(50, "wait", 12, "check has not passed"))


def at_rest(scene):
    """The quiet scene with nothing open."""
    quiet(scene)
    scene.queue([])


def blind(scene):
    """The quiet scene with jbus stopped."""
    quiet(scene)
    scene.timer(active="inactive", sub="dead")


SCENES = {"stalled": stalled, "rest": at_rest, "blind": blind, "troubled": troubled, **DAYS}


def verdict_of(scene, name):
    SCENES[name](scene)
    given = stack(scene)
    return given, given["glance"]["verdict"]


def test_the_t_moment_moves_slowed_by_18_failing_checks_and_8_stacked(scene):
    """At T merges come every 11 minutes, and of the rows that do not move the 18 failing checks
    are the largest group; the 8 stacked count the one held and the one left that the user
    holds, as the check split counts them."""
    given, verdict = verdict_of(scene, "t")
    assert verdict["word"] == "MOVING"
    assert verdict["cause"].startswith("slowed by 18 failing checks, 8 stacked (")
    stacked = next(one for one in verdict["groups"] if one["kind"] == "stacked")
    assert stacked["count"] == 8
    checks = next(one for one in given["slow"]["stages"] if one["key"] == "check")["checks"]
    assert checks["stacked"] == stacked["count"]
    assert verdict["quiet_since"] is None


PARENTS = {
    "pull-failed-alert": ["owed-entry"],
    "plan-builds-on-fires": ["owed-entry", "jv-overview-desk"],
    "root-stall-watch": ["owed-entry"],
    "prose-lint": ["owed-entry"],
    "memories-to-code": ["plan-builds-on-fires"],
    "cleanup-plan-builds-on-fires": ["plan-builds-on-fires"],
    "cleanup-root-stall-watch": ["root-stall-watch"],
    "jv-overview-phone": ["jv-overview-desk"],
    "cleanup-jv-overview-desk": ["jv-overview-desk"],
    "cleanup-jv-overview-phone": ["jv-overview-phone"],
}
"""Ten stacked rows of round-2026-10-28's jstack, with 11 parent links between them: seven go
back to owed-entry and three to jv-overview-desk."""


def test_stacked_rows_are_counted_once_each_and_named_by_the_rows_they_go_back_to(scene):
    """H-09: the verdict said "their parents: 6 running, 3 stacked, 2 merge", 11 parents for 10
    rows, as it summed each row's parent links."""
    rows, log = [], []
    for number, slug in enumerate(("owed-entry", "jv-overview-desk"), 40):
        reason = "macos has not passed"
        rows.append(row(slug, "pr", pr=f"#{number}", checks="pending", why=f"wait: {reason}"))
        log.append(logged(5, "wait", number, reason))
    for number, (slug, parents) in enumerate(PARENTS.items(), 50):
        reason = ready.STACKED_ON.format(branch=parents[0], slug=parents[0], default="main")
        why = f"wait: {reason}"
        rows.append(row(slug, "pr", pr=f"#{number}", checks="passed", why=why, merge_after=parents))
        said = jlines.waits("wait", number, PULL.format(number), reason)
        log.append(f"{et(ago(minutes=10)).removesuffix(' ET')} {jlines.logged(said)}")
    scene.queue(rows)
    scene.merge_log(*log)
    verdict = stack(scene)["glance"]["verdict"]
    stacked = next(one for one in verdict["groups"] if one["kind"] == "stacked")
    assert stacked["count"] == 10
    assert stacked["text"] == "stacked (on owed-entry, jv-overview-desk)"
    assert "10 stacked (on owed-entry, jv-overview-desk)" in verdict["cause"]


def test_a_row_stacked_on_a_merged_parent_is_not_named_as_its_own_head(scene):
    """The board keeps only open rows as links, so a row whose parent merged waits on none and
    is its own head."""
    reason = ready.STACKED_ON.format(branch="owed-entry", slug="owed-entry", default="main")
    said = jlines.waits("wait", 51, PULL.format(51), reason)
    scene.queue(
        [
            row("owed-entry", "merged", pr="#50"),
            row(
                "prose-lint",
                "pr",
                pr="#51",
                checks="passed",
                why=f"wait: {reason}",
                merge_after=["owed-entry"],
            ),
        ]
    )
    scene.merge_log(f"{et(ago(minutes=10)).removesuffix(' ET')} {jlines.logged(said)}")
    verdict = stack(scene)["glance"]["verdict"]
    stacked = next(one for one in verdict["groups"] if one["kind"] == "stacked")
    assert stacked["text"] == "stacked (on a merged or gone row)"


HEADS = ("owed-entry", "jv-overview-desk", "root-stall-watch", "prose-lint", "memories-to-code")
"""Heads of stacks, each with one more stacked row than the one after it."""


@pytest.mark.parametrize(
    ("heads", "text"),
    [
        (4, "stacked (on owed-entry, jv-overview-desk, root-stall-watch, prose-lint)"),
        (5, "stacked (on owed-entry, jv-overview-desk, root-stall-watch and 2 more)"),
    ],
)
def test_stacked_rows_name_their_heads_most_rows_first_and_never_hide_just_one(scene, heads, text):
    """A cap of three names that hid a fourth said "and 1 more", a name hidden to save no room."""
    rows, log, number = [], [], 40
    for place, head in enumerate(HEADS[:heads]):
        reason = "macos has not passed"
        rows.append(row(head, "pr", pr=f"#{number}", checks="pending", why=f"wait: {reason}"))
        log.append(logged(5, "wait", number, reason))
        number += 1
        for one in range(heads - place):
            reason = ready.STACKED_ON.format(branch=head, slug=head, default="main")
            slug = f"{head}-{one}"
            rows.append(
                row(
                    slug,
                    "pr",
                    pr=f"#{number}",
                    checks="passed",
                    why=f"wait: {reason}",
                    merge_after=[head],
                )
            )
            said = jlines.waits("wait", number, PULL.format(number), reason)
            log.append(f"{et(ago(minutes=10)).removesuffix(' ET')} {jlines.logged(said)}")
            number += 1
    scene.queue(rows)
    scene.merge_log(*log)
    verdict = stack(scene)["glance"]["verdict"]
    stacked = next(one for one in verdict["groups"] if one["kind"] == "stacked")
    assert stacked["text"] == text


def test_the_overloaded_day_is_held_by_you_with_12_behind_its_head(scene):
    """The 12 rows behind `tea-kettle`, which is not approved, are the largest group, and they
    wait on the user, so the user holds the work; the 8 ready for a launch slot come after."""
    _, verdict = verdict_of(scene, "many")
    assert verdict["word"] == "HELD BY YOU"
    assert verdict["cause"] == (
        "12 behind tea-kettle, 4 not approved and 3 at a gate wait on you; "
        "slowed too by 8 ready for a launch slot, 3 waiting for a review and 3 passed and not moved"
    )
    behind = verdict["groups"][0]
    assert (behind["kind"], behind["head"], behind["count"]) == ("behind", "tea-kettle", 12)


def test_no_merge_in_3_hours_and_no_act_in_30_minutes_is_stalled(scene):
    _, verdict = verdict_of(scene, "stalled")
    assert verdict["word"] == "STALLED"
    assert verdict["cause"] == (
        "nothing merged in the last 3 h and nothing done in the last 30 min; still: 1 failing check"
    )
    assert verdict["quiet_since"] == iso(ago(minutes=45))


def test_an_act_in_the_last_30_minutes_keeps_it_moving(scene):
    stalled(scene)
    scene.events(("result", "quiet", "oat-spoon", "result oat-spoon: Status: done", 10))
    verdict = stack(scene)["glance"]["verdict"]
    assert (verdict["word"], verdict["quiet_since"]) == ("MOVING", None)
    assert verdict["cause"] == "slowed by 1 failing check"


def test_nothing_open_is_at_rest(scene):
    _, verdict = verdict_of(scene, "rest")
    assert (verdict["word"], verdict["cause"], verdict["groups"]) == (
        "AT REST",
        "nothing is open",
        [],
    )


def test_jbus_stopped_is_cannot_see_whatever_else_holds(scene):
    _, verdict = verdict_of(scene, "blind")
    assert verdict["word"] == "CANNOT SEE"
    assert verdict["cause"] == "jbus stopped: the timer is not active"


def test_an_unreadable_source_is_cannot_see(scene):
    stalled(scene)
    (scene.state_dir / "streaks.json").write_text("{not json")
    verdict = stack(scene)["glance"]["verdict"]
    assert (verdict["word"], verdict["cause"]) == ("CANNOT SEE", "streaks.json cannot be read")


@pytest.mark.parametrize("name", sorted(SCENES))
def test_needs_you_in_the_band_is_the_count_of_needs(scene, name):
    """The verdict says how many things need the user, the same count as `needs`, and the band's
    tier of what waits on the user counts as many, its batch of approvals as each one."""
    given, verdict = verdict_of(scene, name)
    assert verdict["needs"] == len(given["needs"])
    yours = [one for one in given["glance"]["items"] if one["tier"] == "yours"]
    assert sum(one["count"] for one in yours) == verdict["needs"]


def test_ci_github_refuses_for_the_rate_limit_is_cannot_see_with_the_limit_named(scene):
    """The stand-in `gh` refuses the list of runs with GitHub's 403 for a spent allowance, and
    answers `gh api rate_limit`: the view cannot see CI, and says why in place of no reason."""
    stalled(scene)
    scene.write("rate-limit.json", rate_limit(0), scene.root)
    scene.script(
        "gh",
        'case "$*" in\n'
        f'"api rate_limit") cat {scene.root}/rate-limit.json ;;\n'
        '*) echo "gh: API rate limit exceeded for user ID 1. (HTTP 403)" >&2; exit 1 ;;\n'
        "esac\n",
    )
    verdict = stack(scene)["glance"]["verdict"]
    assert verdict["word"] == "CANNOT SEE"
    assert verdict["cause"].startswith(
        "CI could not be read: GitHub refused it for its API rate limit: its core window has 0 of "
        "5000 calls left until 2026-10-12 16:00 UTC"
    )
