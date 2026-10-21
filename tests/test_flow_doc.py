"""`docs/flow.html` names only what the repo has.

The page is read with an HTML parser, and each name in a `<code>` element is held against the
repo itself: a path against the tree, a typed command against `skills/`, a `jmerge` line against
the command's own parser, a T3 Code tool against the schemas kept in `tests/fixtures/t3/`.
The page's sentences are not compared with anything.
"""

import re
import shlex
from html.parser import HTMLParser

import pytest

from jmerge.cli import parser as jmerge_parser
from testing.paths import REPO

PAGE = REPO / "docs" / "flow.html"
REPO_TOP_DIRS = ("skills", "templates", "playbooks", "principles", "hooks", "src", "tests", "docs")
DRAWN = {"home", "crew", "scout", "pr-review", "handoff", "grilling"}
TOOL = re.compile(r"t3_[a-z_]+|[a-z]+_pull_request")
TOOLS = {path.stem for path in (REPO / "tests" / "fixtures" / "t3").glob("*.json")}


class Page(HTMLParser):
    """The text of each `<code>` element, and each attribute that loads a file."""

    def __init__(self):
        super().__init__()
        self.codes = []
        self.loads = []
        self.tags = set()
        self.style = ""
        self._open = None

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        attrs = dict(attrs)
        self.loads += [
            f"<{tag} {key}={attrs[key]}>" for key in ("src", "href", "srcset") if key in attrs
        ]
        if tag == "code":
            self._open = ["code", ""]
        elif tag == "style":
            self._open = ["<style>", ""]

    def handle_data(self, data):
        if self._open:
            self._open[1] += data

    def handle_endtag(self, tag):
        if tag == "code" and self._open:
            self.codes.append(" ".join(self._open[1].split()))
            self._open = None
        elif tag == "style" and self._open:
            self.style += self._open[1]
            self._open = None


def read(text):
    page = Page()
    page.feed(text)
    page.close()
    return page


def missing(page):
    wrong = []
    for code in page.codes:
        first = code.split("/")[0]
        if first in REPO_TOP_DIRS and "/" in code:
            if not (REPO / code).exists():
                wrong.append(f"{code}: no such path in the repo")
        elif typed := re.match(r"/([a-z][a-z-]*)(?= |$)", code):
            if not (REPO / "skills" / typed[1] / "SKILL.md").is_file():
                wrong.append(f"{code}: skills/ has no {typed[1]}")
        elif code.split(" ")[0] == "jmerge":
            try:
                jmerge_parser().parse_args(shlex.split(code)[1:])
            except SystemExit:
                wrong.append(f"{code}: jmerge does not take that")
        elif TOOL.fullmatch(code):
            if code not in TOOLS:
                wrong.append(f"{code}: tests/fixtures/t3 has no schema of that tool")
    return wrong


@pytest.fixture(scope="module")
def page():
    return read(PAGE.read_text())


def test_every_name_on_the_page_is_in_the_repo(page):
    assert missing(page) == []


def test_a_name_the_repo_does_not_have_is_caught():
    made_up = read(
        "<code>/crewmate &lt;slug&gt;</code> <code>skills/crewmate/SKILL.md</code>"
        "<code>templates/outcome.md</code> <code>playbooks/hot-fix.md</code>"
        "<code>jmerge --tidy</code> <code>t3_thread_lau</code>"
        "<code>/crew &lt;slug&gt;</code> <code>jmerge --sweep --check</code> <code>plan.md</code>"
    )
    assert [line.split(":")[0] for line in missing(made_up)] == [
        "/crewmate <slug>",
        "skills/crewmate/SKILL.md",
        "templates/outcome.md",
        "playbooks/hot-fix.md",
        "jmerge --tidy",
        "t3_thread_lau",
    ]


def test_the_page_names_each_template_and_each_skill_it_draws(page):
    named = set(page.codes)
    templates = {f"templates/{path.name}" for path in (REPO / "templates").iterdir()}
    units = {name for name in templates if name.endswith((".service", ".timer"))}
    assert templates - named == units
    assert {f"skills/{name}/SKILL.md" for name in DRAWN} - named == set()
    flags = {
        flag
        for action in jmerge_parser()._actions
        for flag in action.option_strings
        if flag.startswith("--") and flag != "--help"
    }
    used = {word for code in page.codes if code.startswith("jmerge") for word in code.split()}
    assert flags - used == set()


def test_the_page_loads_nothing(page):
    assert page.loads == []
    assert page.tags & {"link", "script", "iframe", "img", "object", "embed"} == set()
    assert "@import" not in page.style and "url(" not in page.style


def test_the_plan_page_is_gone():
    assert not (REPO / "docs" / "plan.html").exists()
