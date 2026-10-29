"""A cleanup row launches once its parent merged, as its brief says (simplify-4's RowLife rule
CleanupAfterParent), replayed with the real `jbus queue add` and pass in the kitchen of
`test_jbus_chains`. The row a review files while its parent's pull request is open is queued
as after-the-review.md queues it (`--depends <slug>`), and jbus launched it at once, stacked on
the open branch."""

from datetime import timedelta

import test_jbus_chains as chains
from test_jbus_chains import head_of, launch_of, queue_add
from test_jbus_kitchen import NOW
from test_jbus_queue import brief, go, rows

kitchen = chains.kitchen


def cleanup_of(slug):
    """The cleanup row of `slug` as `jbus cleanup` writes it while its pull request is open."""
    return (
        brief(
            f"cleanup-{slug}",
            f"Builds on: {slug}: the code of its pull request, which the findings are in\n",
        )
        .replace("Review: review\n", "Review: cleanup\n")
        .replace(
            "Task: ",
            f"Task: {slug} said `Review: review`, and the warning findings of its second review "
            "come here. Its pull request is open and has not merged, so this row launches after "
            "it merges. ",
            1,
        )
    )


def test_a_cleanup_row_filed_while_its_parent_is_open_launches_once_the_parent_merged(kitchen):
    kitchen.config(max_running=8)
    assert queue_add(kitchen, "one")[0] == 0
    assert go(kitchen, "one")[0] == 0
    kitchen.poll()
    pull = {**kitchen.opened("one", 10), "headRefName": "one-branch"}
    with (kitchen.home / "tasks" / "one.md").open("a") as one:
        one.write(f"\n## Result\nBranch: one-branch   Pull request: {pull['url']}\n")
    kitchen.set("open.json", [pull])
    code, said = queue_add(kitchen, "cleanup-one", "--depends", "one", text=cleanup_of("one"))
    assert code == 0, said
    assert rows(kitchen)["cleanup-one"]["approved"], "the follow-up rule gave no go"
    kitchen.poll(NOW + timedelta(minutes=3))
    titles = [given["title"] for given in kitchen.t3.launches]
    assert titles == ["crew: one"], titles

    kitchen.set("open.json", [])
    kitchen.set("merged.json", [kitchen.merged("one", 10, "a" * 40)])
    kitchen.poll(NOW + timedelta(minutes=6))
    assert launch_of(kitchen, "cleanup-one")["workspaceStrategy"]["baseRef"] == "main"
    assert not [line for line in head_of(kitchen, "cleanup-one") if line.startswith("Stacked on:")]
