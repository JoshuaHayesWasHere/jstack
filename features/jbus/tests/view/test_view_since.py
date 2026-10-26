"""What happened since the user last looked: `/stack.json` has it as `since`, a list of what
merged, what is stuck and since when, and which questions jbus closed with their default, over
the last week, oldest first. The page counts what came after its own last look, which it keeps
by itself and never sends (`view/page/test_view_page_since.py`)."""

import json
from dataclasses import asdict

from jbus import questions
from jbus.view.state import iso
from view.scene import Scene, Served, ago, asks, out, row
from view.test_view_wrong import STALL, idle


def quiet(scene):
    """One row at work, nothing merged, nothing at a gate, no question and every source as a day
    of runs leaves it."""
    scene.queue([row("jam-jar", "running", thread="mcp:0000")])
    scene.moves()
    scene.waiting([])
    (scene.home / "gates.md").unlink(missing_ok=True)
    for name in ("ci.jsonl", "ci-prs.jsonl", "stall.json"):
        (scene.state / name).unlink(missing_ok=True)
    scene.passed(20, threads=[out("crew: jam-jar", minutes=1)])


def defaulted(scene, minutes, slug="alpha"):
    """A question of `slug` that jbus closed with its default `minutes` ago, at once, in the
    pass that saw it."""
    number = asks(scene, slug=slug)
    file = questions.path(scene.state)
    kept = json.loads(file.read_text())
    said = questions.Answer(
        "default",
        questions.SOURCE,
        iso(ago(minutes=minutes)),
        questions.UNANSWERED,
        True,
        closed_by=questions.SILENCE,
    )
    for one in kept["records"]:
        if one["number"] == number:
            one["asked_at"] = iso(ago(minutes=minutes))
            one["answer"] = asdict(said)
    file.write_text(json.dumps(kept))


def busy(scene):
    """The quiet scene, then three merges, a merge before them and one more than a week ago, a
    row that stalled, and a question closed with its default."""
    quiet(scene)
    scene.queue(
        [
            row("jam-jar", "running", thread="mcp:0000"),
            row("oat-spoon", "pr", pr="#12", checks="passed", why="wait: it has no review yet"),
            *(row(slug, "merged", pr=f"#{n}") for n, slug in enumerate(MERGED, 20)),
        ]
    )
    scene.moves(
        ("old-jar", "pr", "merged", 8 * 24 * 60),
        ("jam-pot", "pr", "merged", 90),
        ("tea-pot", "pr", "merged", 30),
        ("tea-cup", "pr", "merged", 20),
        ("tea-urn", "pr", "merged", 10),
    )
    scene.events(("stall", "quiet", "oat-spoon", STALL, 6))
    scene.write("expedite.json", {"oat-spoon": idle(12)})
    defaulted(scene, 15)


MERGED = ("old-jar", "jam-pot", "tea-pot", "tea-cup", "tea-urn")


def asked(scene, path):
    served = Served(scene)
    try:
        return served.json(path)
    finally:
        served.close()


def test_what_merged_got_stuck_or_took_its_default_over_the_last_week_oldest_first(
    tmp_path, monkeypatch
):
    scene = Scene(tmp_path, monkeypatch)
    busy(scene)
    since = asked(scene, "/stack.json")["since"]
    assert since["from"] == iso(ago(days=7))
    assert [(one["kind"], one["subj"], one["at"]) for one in since["events"]] == [
        ("merged", "jam-pot", iso(ago(minutes=90))),
        ("merged", "tea-pot", iso(ago(minutes=30))),
        ("merged", "tea-cup", iso(ago(minutes=20))),
        ("default", "alpha", iso(ago(minutes=15))),
        ("merged", "tea-urn", iso(ago(minutes=10))),
        ("stuck", "oat-spoon", iso(ago(minutes=6))),
    ]
    opens = {one["subj"]: (one["project"], one["open"]) for one in since["events"]}
    assert opens["tea-pot"] == ("demo", "#/demo/merged")
    assert opens["oat-spoon"] == ("demo", "#/demo/task/oat-spoon")
    assert opens["alpha"] == ("demo", "#/demo/words")


def test_a_quiet_week_has_nothing_and_the_panel_alone_gives_the_same_list(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    quiet(scene)
    assert asked(scene, "/stack.json")["since"] == {"from": iso(ago(days=7)), "events": []}
    busy(scene)
    alone = asked(scene, "/panel/since.json?project=demo")["data"]["since"]
    assert alone == asked(scene, "/stack.json")["since"]


def test_a_stuck_row_that_moved_since_is_not_stuck_any_more(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    busy(scene)
    scene.moves(("oat-spoon", "pr", "review", 2))
    kinds = [one["kind"] for one in asked(scene, "/stack.json")["since"]["events"]]
    assert "stuck" not in kinds


def test_a_stall_logged_again_while_it_stands_is_as_old_as_its_first(tmp_path, monkeypatch):
    """jbus logs a stall again while it stands (the clock's carry): the row has been stuck since
    the first one, so a look between the two does not count it as new."""
    scene = Scene(tmp_path, monkeypatch)
    busy(scene)
    again = "stall oat-spoon: #12 waited 10 passes after jbus carried its crew on, at 0123456789ab"
    scene.events(
        ("stall", "quiet", "oat-spoon", STALL, 30), ("stall", "quiet", "oat-spoon", again, 4)
    )
    (stuck,) = [
        one for one in asked(scene, "/stack.json")["since"]["events"] if one["kind"] == "stuck"
    ]
    assert stuck["at"] == iso(ago(minutes=30))
