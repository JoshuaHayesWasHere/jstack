"""The view's kept shots: the pictures under `KEPT` that the view's shot tests compare each page
with, and the row that redraws them.

Only one browser draws them, the Chrome for Testing build browser.yml pins, so only browser.yml
redraws them. A pull request keeps main's shots: its diff changes a kept shot only where it
changes nothing else (`mixed`, which the borders check runs as `features/jbus/scripts/
kept_shots.py`), and that pull request is the shots row's. A feature that changes the look
merges with main's shots, and its own browser run skips each shot that moved
(`test_view_page_look.judged`). The next nightly run on main then fails that shot, and jbus files
the shots row of the day from it (`jbus.watch._nightly_red`): its pull request keeps the run's
`ARTIFACT`, so the look a feature changed is looked at once it merged.

The module uses the standard library only, so the borders check, which runs with no uv sync,
loads it by its path."""

from __future__ import annotations

KEPT = "features/jbus/tests/fixtures/jbus-view/shots"
"""The directory of the kept shots and of `browser.txt`, which names the browser that drew them."""
PREFIX = "shots-"
"""The start of the shots row's slug, before the day."""
ARTIFACT = "jbus-view-shots"
"""The artifact of a failed browser run, with every shot as that run drew it (browser.yml)."""
MOVED = f"keep the shots of this run's {ARTIFACT} artifact"
"""What a shot test says where it fails on main: the run's shots are the ones to keep."""
BROWSER_MOVED = "the shots were drawn by"
"""How a shot test starts to say that the browser that drew the kept shots is not this one."""
DRAWN_BY = (
    "features/jbus/tests/view/page/test_view_page_look.py::test_each_route_looks_as_its_kept_shot",
    "features/jbus/tests/view/page/test_view_page_days.py::"
    "test_view_shot_draws_the_overview_of_each_day_at_each_width",
)
"""The tests that compare the page with a kept shot, each of which fails on main where its shot
moved, its shot is missing or the browser moved."""


def drawn(test: str) -> bool:
    """Whether the failed test `test`, as pytest names it, is one of the shot tests."""
    return test.split("[")[0] in DRAWN_BY


def kept(path: str) -> bool:
    """Whether `path`, from the repo's root, is a kept shot or the `browser.txt` beside them."""
    return path.startswith(f"{KEPT}/")


def mixed(paths: list[str]) -> list[str]:
    """The paths of a diff that may not be in it: where it changes a kept shot, every path that is
    not one, and otherwise none."""
    if not any(kept(path) for path in paths):
        return []
    return [path for path in paths if not kept(path)]


def brief(
    name: str,
    day: str,
    run: str,
    number: object,
    filed: str,
    jobs: list[tuple[str, str, list[str]]],
    read: str,
    moved: bool,
) -> str:
    """Return the shots row's brief, in the shape of `features/jbriefs/templates/brief.md`: keep
    the shots that the run `number` of browser.yml drew over main. `run` names that workflow's
    run, `filed` is the start of the `Decisions:` line of a row jbus filed, `jobs` each failed
    job's name, URL and failed shot tests, `read` the line that names the run, and `moved` whether
    its log says the browser that draws them moved."""
    tests = [test for _, _, failed in jobs for test in failed]
    said = f"{len(tests)} shot{'' if len(tests) == 1 else 's'} moved"
    why = "the browser that draws them moved" if moved else "a merge changed the look of main"
    return "\n".join(
        [
            f"# {name}: the view's kept shots are redrawn over main on {day}",
            f'Task: "{run} {number} failed on {day}, {said}" (jbus, from browser.yml)',
            "Done when:",
            f"- the shots under `{KEPT}/` and their `browser.txt` are those of the run's "
            f"`{ARTIFACT}` artifact, which the browser that draws them drew over main: "
            f"`gh run download {number} -n {ARTIFACT} -D {KEPT}`",
            f"- the pull request changes nothing outside `{KEPT}/`",
            "- the Result names each shot that moved and the merge that moved it, or the "
            "browser that moved, so the look is looked at",
            "Proves it: the pull request's borders check passes, and its browser run skips no "
            "shot as moved",
            "Size: S",
            f"Where: `{KEPT}/`",
            f"Do not touch: anything outside `{KEPT}/`",
            f"Decisions: {filed}nightly run: {why}, and only the shots row redraws the shots",
            f"Design: none, the shots are the run's `{ARTIFACT}` artifact",
            "Pull request: open one when done",
            "Review: review",
            "Playbook: none",
            "Read:",
            *(
                f"- the job `{job}`, {url or 'with no URL'}: "
                + ", ".join(f"`{test}`" for test in failed)
                for job, url, failed in jobs
            ),
            read,
            "",
        ]
    )
