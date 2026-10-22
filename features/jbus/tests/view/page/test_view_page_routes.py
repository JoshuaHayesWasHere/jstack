"""The routes of the page: a pasted link, back and forward, the breadcrumbs, and an address
read and written again."""

import html
import re

import pytest

from view.page.browser import (
    BROWSES,
    DESK,
    LAUNCH,
    PATIENCE,
    PHONE,
    browse,
    clean,
    look,
    shown,
    walked,
)
from view.scene import Served, said_by_him

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


@pytest.mark.parametrize("screen", [DESK, PHONE])
@pytest.mark.parametrize(
    ("fragment", "system", "dark"),
    [
        ("#theme=light", "dark", False),
        ("#theme=dark", "light", True),
        ("", "light", False),
        ("", "dark", True),
    ],
)
def test_the_page_is_light_dark_or_as_the_browser_asks(
    scene, tmp_path, screen, fragment, system, dark
):
    seen = look(scene, tmp_path, fragment=fragment, screen=screen, system=system)
    red = int(re.match(r"rgb\((\d+)", seen["background"])[1])
    assert (red < 60) is dark, seen["background"]
    clean(seen, screen)


def test_a_drawer_is_opened_by_its_name_in_the_address_under_the_servers_own_policy(
    scene, tmp_path
):
    served = Served(scene)
    try:
        ran = browse(
            f"--user-data-dir={tmp_path / 'profile'}",
            "--virtual-time-budget=3000",
            f"http://127.0.0.1:{served.port}/#/demo/task/oat-bowl",
        )
    finally:
        served.close()
    assert '<dialog class="drawer" id="drawer" aria-labelledby="dw-title" open="">' in ran.stdout
    said = html.unescape(re.sub(r"<[^>]+>", "", ran.stdout))
    assert "the rebase dropped 2 of main's lines" in said
    assert "#11 open" in said


TEA = "#/demo/task/tea-cups"


WORDS_AT = "#/demo/words/approval/tea-cups"


@pytest.mark.parametrize(
    ("route", "drawer"),
    [
        ("#/", ""),
        ("#/demo", ""),
        (TEA, "tea-cups"),
        (WORDS_AT, "things you said"),
        ("#/demo/you/gate", "things wait on you"),
        ("#/demo/steps/queued", "The steps, top to bottom"),
        ("#/demo&open=task:tea-cups", "tea-cups"),
    ],
)
def test_every_route_opens_cold_from_a_pasted_link(scene, tmp_path, route, drawer):
    """A view is a link. Pasted in a new tab, the link opens the view with the drawer it
    names. The page rewrites an old `&open=` link to its route."""
    said_by_him(scene)
    (first,) = walked(scene, tmp_path, route, ["look"])
    assert first["open"] is bool(drawer)
    assert first["hash"] == ("#/demo/task/tea-cups" if "&open=" in route else route)
    if drawer:
        assert drawer in first["title"]
        assert first["crumbs"][:2] == [["All", "#/"], ["demo", "#/demo"]]
        assert first["crumbs"][2] == [first["title"], first["hash"]]
        assert first["back"] == "", "a drawer opened cold has nothing before it"
    elif route == "#/demo":
        assert first["crumbs"] == [["All", "#/"], ["demo", "#/demo"]]


def test_back_closes_a_drawer_forward_opens_it_and_esc_goes_back_one_layer(scene, tmp_path):
    said_by_him(scene)
    steps = walked(
        scene,
        tmp_path,
        TEA,
        ["look", "open:words:approval:tea-cups", "back", "forward", "esc", "esc"]
        + ["open:you", "back", "forward", "close"],
    )
    seen = [(one["step"], one["hash"], one["open"]) for one in steps]
    assert seen == [
        ("look", TEA, True),
        ("open:words:approval:tea-cups", WORDS_AT, True),
        ("back", TEA, True),
        ("forward", WORDS_AT, True),
        ("esc", TEA, True),
        ("esc", "#/demo", False),
        ("open:you", "#/demo/you", True),
        ("back", "#/demo", False),
        ("forward", "#/demo/you", True),
        ("close", "#/demo", False),
    ]
    task, words = steps[0]["title"], steps[1]["title"]
    assert task.startswith("tea-cups")
    assert [one["back"] for one in steps[:5]] == ["", f"← {task}", "", f"← {task}", ""]
    assert steps[1]["crumbs"] == [["All", "#/"], ["demo", "#/demo"], [words, WORDS_AT]]
    assert steps[0]["crumbs"] == [["All", "#/"], ["demo", "#/demo"], [task, TEA]]
    assert steps[4]["focus"] == "words:approval:tea-cups", "back on the button that opened it"


def test_the_arrow_and_the_breadcrumbs_lead_to_real_pages(scene, tmp_path):
    said_by_him(scene)
    steps = walked(
        scene,
        tmp_path,
        "#/demo",
        ["open:task:tea-cups", "open:words:approval:tea-cups", "arrow", "crumb:1", "back"]
        + ["open:task:tea-cups", "crumb:0"],
    )
    seen = [(one["step"], one["hash"], one["open"]) for one in steps]
    assert seen == [
        ("open:task:tea-cups", TEA, True),
        ("open:words:approval:tea-cups", WORDS_AT, True),
        ("arrow", TEA, True),
        ("crumb:1", "#/demo", False),
        ("back", TEA, True),
        ("open:task:tea-cups", TEA, True),
        ("crumb:0", "#/", False),
    ]
    assert steps[1]["back"] == f"← {steps[0]['title']}"


def test_a_way_back_through_an_entry_rewritten_since_lands_on_its_layer(scene, tmp_path):
    """On a drawer that a pasted link opened, Esc rewrites the history entry to the page.
    After going forward again, the back arrow still goes back to that drawer, not to the
    page. A drawer opened over another puts the focus on its own Close."""
    said_by_him(scene)
    steps = walked(
        scene,
        tmp_path,
        TEA,
        ["look", "open:words:approval:tea-cups", "esc", "esc", "forward", "arrow", "cancel"]
        + ["open:words:approval:tea-cups", "cancel-hard"],
    )
    seen = [(one["step"], one["hash"], one["open"]) for one in steps]
    assert seen == [
        ("look", TEA, True),
        ("open:words:approval:tea-cups", WORDS_AT, True),
        ("esc", TEA, True),
        ("esc", "#/demo", False),
        ("forward", WORDS_AT, True),
        ("arrow", TEA, True),
        ("cancel", "#/demo", False),
        ("open:words:approval:tea-cups", WORDS_AT, True),
        ("cancel-hard", "#/demo", False),
    ]
    assert steps[1]["focus"] == "dw-close"
    assert steps[4]["back"] == f"← {steps[0]['title']}"


def test_a_filter_in_a_drawer_redraws_it_in_place(scene, tmp_path):
    """The role filters of the threads drawer add no layers: Esc after two of them shuts it."""
    said_by_him(scene)
    steps = walked(
        scene,
        tmp_path,
        "#/demo",
        [
            "open:threads",
            'tap:#dw [data-open="threads:crew"]',
            'tap:#dw [data-open="threads:scout"]',
        ]
        + ["esc"],
    )
    seen = [(one["hash"], one["open"], one["back"]) for one in steps]
    assert seen == [
        ("#/demo/threads", True, ""),
        ("#/demo/threads/crew", True, ""),
        ("#/demo/threads/scout", True, ""),
        ("#/demo", False, ""),
    ]
    assert [one["focus"] for one in steps[1:3]] == ["threads:crew", "threads:scout"]


@pytest.mark.parametrize(
    ("route", "said"),
    [
        ("#/demo/task/no-such-task", "No task named no-such-task in demo"),
        ("#/demo/gate/999", "No gate named 999 in demo"),
        ("#/demo/thread/scout/no-tin", "No thread named scout no-tin in demo"),
        ("#/demo/nothing", "No drawer called nothing in demo"),
        ("#/nowhere/task/tea-cups", "No project named nowhere"),
    ],
)
def test_a_link_to_a_name_that_is_not_there_says_which(scene, tmp_path, route, said):
    said_by_him(scene)
    (first,) = walked(scene, tmp_path, route, ["look"])
    assert first["hash"] == route
    assert first["notice"].startswith(said), first["notice"]


def test_a_task_drawer_says_its_approval_in_a_line_that_opens_your_words_at_it(scene, tmp_path):
    said_by_him(scene)
    served = Served(scene)
    try:
        task = shown(served.port, tmp_path, "task:tea-cups")
        before = shown(served.port, tmp_path, "task:tea-tray")
        you = shown(served.port, tmp_path, "you")
        ran = browse(
            f"--user-data-dir={tmp_path / 'profile'}",
            "--virtual-time-budget=3000",
            f"http://127.0.0.1:{served.port}/#/demo/words/approval/tea-cups",
        )
    finally:
        served.close()
    assert "Approval on your word, said " in task
    assert "by the elsewhere home" in task.partition("Approval on your word")[2]
    assert "Approval no record: approved before the record was kept" in before
    assert "The questions you answered, in Your words" in you
    drawer = ran.stdout.partition('id="drawer"')[2].partition("</dialog>")[0]
    hit = drawer.partition('<li class="hit">')[2].partition("</li>")[0]
    assert "tea-cups" in hit
    assert "go ahead with the kettle" in html.unescape(hit)
    said = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", drawer)))
    assert "1 questions you answered" in said
    assert "2 words sent down" in said
    assert "Not sent on yet: the home has no home-id." in said


@pytest.mark.parametrize(
    ("route", "hash", "title", "crumbs", "notice", "tap"),
    [
        ("#/", "#/", "", [["All projects", "#/"]], "", "#title .crumbs a[aria-current]"),
        (
            "#/demo",
            "#/demo",
            "",
            [["All", "#/"], ["demo", "#/demo"]],
            "",
            "#title .crumbs a[aria-current]",
        ),
        (
            "#/help",
            "#/help",
            "Every term on the page",
            [["All", "#/"], ["Every term on the page", "#/help"]],
            "",
            "#dw .crumbs a[aria-current]",
        ),
        (
            "#/%E0",
            "#/%E0",
            "",
            [["All", "#/"], ["%E0", "#/%25E0"]],
            "No project named %E0",
            "#title .crumbs a[aria-current]",
        ),
        (
            "?project=demo",
            "#/demo",
            "",
            [["All", "#/"], ["demo", "#/demo"]],
            "",
            "#title .crumbs a[aria-current]",
        ),
    ],
)
def test_an_address_read_and_written_again_names_the_same_view(
    scene, tmp_path, route, hash, title, crumbs, notice, tap
):
    """The page reads where it is from the address alone. It builds each link it draws from
    what it read. `#/` is every project, `#/<project>` is one project, and `#/help` is the
    glossary over every project. A part that is no name (`%E0`) is a project, kept as it was
    written. The page rewrites an old `?project=` link to its route. Following the link to
    where the page is opens the same view again."""
    said_by_him(scene)
    first, again = walked(scene, tmp_path, route, ["look", f"tap:{tap}"])
    assert (first["hash"], first["title"], first["crumbs"]) == (hash, title, crumbs)
    assert first["notice"].startswith(notice), first["notice"]
    assert again["hash"] == crumbs[-1][1]
    assert (again["title"], again["crumbs"]) == (title, crumbs)
    assert again["notice"].startswith(notice), again["notice"]
