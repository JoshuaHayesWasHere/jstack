"""The Find panel: every row of the queue with the title of its brief, its stage, its pull
request and when it merged, for the page to match what the user types against."""

from view.scene import ago, iso, row, table


def briefs(scene, **titles):
    made = scene.state / "briefs"
    made.mkdir(exist_ok=True)
    for slug, title in titles.items():
        (made / f"{slug}.md").write_text(f"# {slug}: {title}\nTask: bake\n")


def found(served):
    return {
        one["slug"]: one for one in served.json("/panel/find.json?project=demo")["data"]["found"]
    }


def test_each_row_is_found_with_its_title_stage_pull_request_and_merged_time(scene, served):
    briefs(scene, **{"rye-loaf": "bake the rye loaf", "oat-milk": "pour the oat milk"})
    said = found(served)
    assert set(said) == {one["slug"] for one in table()}
    assert said["rye-loaf"] == {
        "slug": "rye-loaf",
        "title": "bake the rye loaf",
        "stage": "Merged",
        "pr": "#9",
        "merged": iso(ago(minutes=40)),
    }
    tasks = {one["slug"]: one for one in served.json("/state.json?project=demo")["tasks"]}
    assert said["oat-milk"] == {
        "slug": "oat-milk",
        "title": "pour the oat milk",
        "stage": tasks["oat-milk"]["state"]["name"],
        "pr": "#13",
        "merged": None,
    }
    assert said["tea-kettle"]["title"] == "", "a row with no brief has no title"
    assert said["tea-kettle"]["stage"] == tasks["tea-kettle"]["state"]["name"]


def test_a_row_that_merged_days_ago_is_found_with_the_time_it_merged(scene, served):
    scene.queue([*table(), row("rye-crust", "merged", pr="#5")])
    scene.moves(("rye-loaf", "pr", "merged", 40), ("rye-crust", "pr", "merged", 3 * 24 * 60))
    briefs(scene, **{"rye-crust": "rye-crust: the crust, not the loaf"})
    said = found(served)["rye-crust"]
    assert said == {
        "slug": "rye-crust",
        "title": "rye-crust: the crust, not the loaf",
        "stage": "Merged",
        "pr": "#5",
        "merged": iso(ago(minutes=3 * 24 * 60)),
    }
    assert "found" not in served.json("/state.json?project=demo"), "it is not on the first screen"


def test_open_rows_come_first_and_merged_rows_newest_first(scene, served):
    scene.queue([*table(), row("rye-crust", "merged", pr="#5")])
    scene.moves(("rye-loaf", "pr", "merged", 40), ("rye-crust", "pr", "merged", 90))
    slugs = [one["slug"] for one in served.json("/panel/find.json?project=demo")["data"]["found"]]
    assert slugs[-2:] == ["rye-loaf", "rye-crust"]


def test_a_row_that_moved_back_from_merged_has_no_merged_time(scene, served):
    scene.moves(
        ("rye-loaf", "pr", "merged", 40),
        ("tea-tray", "queued", "merged", 30),
        ("tea-tray", "merged", "queued", 29),
    )
    said = found(served)
    assert said["tea-tray"]["merged"] is None
    assert said["rye-loaf"]["merged"] == iso(ago(minutes=40))
