"""The You panel: what needs the user, across projects, oldest first."""

from dataclasses import asdict

from jbus import questions, threads, waiting, work
from jbus.view.panels.you import panel as panel_you
from test_jbus_kitchen import GATE as PIPED
from view.scene import GATE, PULL, Scene, Served, ago, iso, item, stacked

HOLDING = "Holds: publishes\nFail-safe: the dry run of the post, in the plan\n"


def a_brief(scene, slug, title, task):
    (scene.state / "briefs").mkdir(exist_ok=True)
    (scene.state / "briefs" / f"{slug}.md").write_text(f"# {slug}: {title}\nTask: {task}\n")


def needing(scene):
    """One item of each of the six kinds, over two projects, each with a time of its own:
    a setup 7 hours old, an approval with a brief and a row behind it, a question that holds, a
    leftover, a row at a gate of `pantry`, and a held pull request."""
    stacked(scene)
    a_brief(scene, "tea-kettle", "boil the water first", "Boil the water. Then pour it.")
    a_brief(scene, "oat-honey", "stir the honey in", "Stir it.")
    lines = PIPED.format(n="<n>", asked="post the menu?", status="open", slug="jam-jar")
    held = questions.ask(scene.state, scene.home, "jam-jar", lines + HOLDING, ago(hours=3))[0]
    scene.waiting(
        [
            item("config", "config:webhook", "webhook is not set", hours=7),
            item(
                "approve",
                "approve:tea-kettle",
                "approve tea-kettle: jbus queue approve --sha 1",
                slug="tea-kettle",
                hours=5,
            ),
            item("left", "left:rye-loaf", "left rye-loaf: a note", minutes=100, slug="rye-loaf"),
            item("hold", "#14", f"hold 14 {PULL.format(14)}: needs the user's word", minutes=12)
            | {"number": 14},
        ]
    )
    return held.number


def test_the_stack_lists_what_needs_the_user_across_projects_oldest_first(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    number = needing(scene)
    served = Served(scene)
    try:
        needs = served.json("/stack.json")["needs"]
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    assert [one["kind"] for one in needs] == ["config", "approve", "gate", "left", "row", "hold"]
    assert [one["project"] for one in needs] == ["demo"] * 4 + ["pantry", "demo"]
    assert [one["since"] for one in needs] == sorted(one["since"] for one in needs)
    assert {one["verb"] for one in needs} <= {
        *(one.verb for one in waiting.KINDS),
        panel_you.ANSWER,
    }
    assert [one["verb"] for one in needs] == [
        "Set up",
        "Approve launch",
        "Answer",
        "Close it",
        "Fix brief",
        "Review merge",
    ]
    assert all(set(one) == set(panel_you._NEED) for one in needs)
    assert all("jbus " not in one["what"] + one["why"] for one in needs)
    by = {one["kind"]: one for one in needs}
    assert by["approve"]["what"] == "tea-kettle: boil the water first"
    assert by["approve"]["why"] == "Boil the water."
    assert by["approve"]["unblocks"] == ["tea-cups"]
    assert by["approve"]["open"] == "#/demo/you/approve/tea-kettle"
    assert by["hold"]["what"] == "Pull request #14: oat-honey: stir the honey in"
    assert by["hold"]["why"] == "needs the user's word"
    assert (by["hold"]["risk"], by["hold"]["answerable"]) == ("merge to main", False)
    assert by["hold"]["open"] == "#/demo/you/hold/14"
    assert (by["gate"]["what"], by["gate"]["risk"]) == ("post the menu?", "publishes")
    assert (by["gate"]["answerable"], by["gate"]["default"]) == (True, "the first one")
    assert by["gate"]["open"] == f"#/demo/gate/{number}"
    assert by["gate"]["due"] is None
    assert by["row"]["project"] == "pantry"
    assert by["row"]["open"] == "#/pantry/you/row/fig-tart"
    assert {one["risk"] for one in needs if one["kind"] not in ("gate", "hold")} == {"reversible"}
    assert demo["needs"] == [one for one in needs if one["project"] == "demo"]


def test_the_kinds_are_in_state_json_as_the_page_shows_them_and_an_added_kind_with_them(
    served, monkeypatch
):
    """The drawer of what waits on the user lists the kinds by their `shown` place, and an
    item's button is its kind's verb. So a kind added to `waiting.KINDS` shows in the drawer
    with no other edit."""
    kinds = served.json("/state.json?project=demo")["kinds"]
    assert [one["name"] for one in kinds] == ["row", "left", "hold", "approve", "gate", "config"]
    assert {one["name"]: one["verb"] for one in kinds}["gate"] == "Accept default"
    added = waiting.Kind("chore", "Chores for you", "Do it", 7)
    monkeypatch.setattr(waiting, "KINDS", (*waiting.KINDS, added))
    assert served.json("/state.json?project=demo")["kinds"][-1] == asdict(added)
    assert waiting.kind("chore:sweep") == "chore"


def test_the_roles_are_in_state_json_and_stack_json_and_an_added_role_with_them(
    served, monkeypatch
):
    """The page and its panels name a thread's role from these. So a role added to
    `threads.ROLES` shows in both with no other edit, and a thread's title gives its role."""
    roles = served.json("/state.json?project=demo")["roles"]
    assert [one["name"] for one in roles] == ["crew", "scout", "reviewer", "home", "other"]
    assert served.json("/stack.json")["roles"] == roles
    added = threads.Role("chef", "chef: ", "home", "chef", "chef", "chefs", "Cooks.")
    monkeypatch.setattr(threads, "ROLES", (*threads.ROLES[:-1], added, threads.ROLES[-1]))
    assert asdict(added) in served.json("/state.json?project=demo")["roles"]
    assert served.json("/stack.json")["roles"][-2] == asdict(added)
    assert threads.role_of("chef: oat-milk") == ("chef", "oat-milk")
    crews = (state for facts in work.every() if (state := work.judge(facts)).pattern.who == "crew")
    assert work.holder(next(crews), role="chef").who == "home"


def test_fourteen_waiting_and_one_with_no_default_path_is_the_only_one_that_needs_you(
    tmp_path, monkeypatch
):
    """The scene has eleven questions that go ahead on their default, and a link's conflict,
    whose question goes to its home. It also has a gate of a home's file with a default, and an
    approval. The page's count is one.
    Each countdown is the 2 hours of silence after which jbus closes the question."""
    scene = Scene(tmp_path, monkeypatch)
    asked = [ago(minutes=10 * at) for at in range(11)]
    for at, when_asked in enumerate(asked):
        lines = PIPED.format(n="<n>", asked=f"which tin {at}?", status="open", slug="jam-jar")
        questions.ask(scene.state, scene.home, "jam-jar", lines, when_asked)
    link = PIPED.format(n="<n>", asked=f"oat-honey {questions.LINK}", status="open", slug="oat")
    questions.ask(scene.state, scene.home, "oat-honey", link, ago(hours=1))
    (scene.home / "gates.md").write_text(
        GATE.format(n=40, asked="a lump?", status="open", default="one")
    )
    scene.waiting([item("approve", "approve:tea-kettle", "approve tea-kettle: jbus queue approve")])
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        demo = served.json("/state.json?project=demo")
    finally:
        served.close()
    assert len(demo["waiting"]) == 14
    assert [one["kind"] for one in stack["needs"]] == ["approve"]
    assert [one["waits"] for one in stack["projects"] if one["name"] == "demo"] == [1]
    answerable = [one for one in stack["proceeds"] if one["answerable"]]
    assert len(stack["proceeds"]) == 12 and len(answerable) == 11
    assert not any(questions.LINK in one["what"] for one in stack["proceeds"])
    assert sorted(one["due"] for one in answerable) == sorted(
        iso(when_asked + questions.QUIET) for when_asked in asked
    )
    (home,) = [one for one in stack["proceeds"] if not one["answerable"]]
    assert (home["what"], home["default"], home["due"]) == ("a lump?", "one", None)
    assert [one["due"] for one in stack["proceeds"][:11]] == sorted(
        one["due"] for one in answerable
    )
    assert {one["verb"] for one in answerable} == {"Accept default"}
    assert home["verb"] == "Answer"
