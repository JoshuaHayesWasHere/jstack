"""`features/jdrift/docs/jstack-explained.html` has a card for everything it explains, and loads
nothing.

The tests read the page with an HTML parser and check it against the repo itself. They check
the step numbers of its lead drawing against 1 to 10, the rules file of each command against
the tree, and each attribute that loads a file against the page's own anchors. They compare
none of the page's sentences with anything.

Nobody writes the cards of the skills, playbooks and principles, or the links above them, by
hand: `python -m jdrift.explained` builds them from a card line in each file. So the tests check
the ids of those cards against the directories on the page as built from the tree. They do not
use the committed page, which the docs sweep brings up to date and no task edits.
"""

import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from jdrift.explained import BUILT, build
from jdrift.explained import COMMENT as CARD
from testing.paths import REPO, playbooks, skills

PAGE = REPO / "features/jdrift/docs/jstack-explained.html"
COMMANDS = {"jmerge", "jbus", "jgauge-room", "jroles", "jdrift"}
LOCAL = {"../../home/docs/flow.html"}


VOID = {"meta", "br", "hr", "img", "wbr", "input", "link", "source"}
HEADS = {"h4", "b"}
URL = re.compile(r"url\(\s*['\"]?([^'\")]*)")


class Page(HTMLParser):
    """The page's parts: each id with its text and its heading, each `<code>`, the style, and
    each attribute that loads a file."""

    def __init__(self):
        super().__init__()
        self.cards = {}
        self.heads = {}
        self.codes = []
        self.loads = []
        self.tags = set()
        self.badges = {}
        self.style = ""
        self._stack = []
        self._text = None
        self._cut = None

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        attrs = dict(attrs)
        self.loads += [attrs[key] for key in ("src", "href", "srcset") if key in attrs]
        if "style" in attrs:
            self.loads.append(f"style={attrs['style']}")
        if tag in VOID:
            return
        name = attrs.get("id")
        self._stack.append((tag, name))
        if name:
            self.cards[name] = ""
        if tag == "svg" and attrs.get("class") in ("wide", "tall"):
            self._cut = attrs["class"]
            self.badges[self._cut] = []
        if tag in ("code", "style") or tag in HEADS or attrs.get("class") == "bn":
            self._text = [attrs.get("class") if tag == "text" else tag, ""]

    def handle_data(self, data):
        for _, name in self._stack:
            if name:
                self.cards[name] += data
        if self._text:
            self._text[1] += data

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        assert any(open_tag == tag for open_tag, _ in self._stack), f"</{tag}> closes nothing"
        while self._stack.pop()[0] != tag:
            pass
        if tag == "svg":
            self._cut = None
        if not self._text or self._text[0] not in (tag, "bn"):
            return
        kind, text = self._text
        self._text = None
        text = " ".join(text.split())
        if kind == "code":
            self.codes.append(text)
        elif kind == "style":
            self.style += text
        elif kind == "bn":
            self.badges[self._cut].append(text)
        else:
            card = next((name for _, name in reversed(self._stack) if name), None)
            if card:
                self.heads.setdefault(card, text)


def read(text):
    parsed = Page()
    parsed.feed(text)
    parsed.close()
    assert not parsed._stack, f"left open: {parsed._stack}"
    return parsed


@pytest.fixture(scope="module")
def page():
    return read(PAGE.read_text())


@pytest.fixture(scope="module")
def built():
    return read(build(REPO))


MADE_UP_PAGE = """<h2>Hand-written</h2>
<div class="names">
<!-- built: skill links, Read -->
<a href="#skill-stale">stale</a>
<!-- built: end -->
</div>
<div class="cards">
<!-- built: skill cards, Read -->
<!-- built: end -->
</div>
<div class="names">
<!-- built: playbook links, Build -->
<!-- built: end -->
</div>
<p class="sub">Build</p>
<!-- built: playbook cards, Build -->
<!-- built: end -->
<!-- built: playbook cards, Decide -->
<!-- built: end -->
<h3>Prove it</h3>
<!-- built: principle cards, Prove it -->
<!-- built: end -->
<p>The end.</p>
"""
MADE_UP = {
    "features/how/SKILL.md": '---\nname: how\ncard: "Read | 2 | Says <how> & why. '
    '| When `x` is new. | op: the operator; plain: a step of `one`"\n---\n\n# How\n\n'
    'card: "not this"\n',
    "skills/scout/SKILL.md": '---\nname: scout\ncard: "Read | 1 | Finds out. | When asked. '
    '| model: a home | look: scout"\n---\n\n# Scout\n',
    "playbooks/one.md": "# One\n\n<!-- card: Build | 1 | One thing. -->\n\n1. Do it.\n",
    "playbooks/two.md": "<!-- card: Decide | 1 | Two things. | plain: `Review: none` -->\n",
    "features/principles/skills/principle-prove/SKILL.md": (
        "---\nname: principle-prove\n---\n\n# Prove\n\n"
        "<!-- card: Prove it | 1 | Run it. | `one`; most -->\n"
    ),
}


@pytest.fixture
def tree(tmp_path):
    """A made-up tree of two skills (one of them moved into its feature), two playbooks and a
    principle, with a page of four tiles."""
    for name, text in {
        **MADE_UP,
        "features/jdrift/docs/jstack-explained.html": MADE_UP_PAGE,
    }.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    return tmp_path


def explained(tree, *args):
    command = [sys.executable, "-m", "jdrift.explained", *args]
    return subprocess.run(command, cwd=tree, capture_output=True, text=True)


def part(text, begin):
    """The text of the page between the marker `begin` and the end marker after it."""
    assert text.count(f"<!-- built: {begin} -->") == 1, begin
    return read(text.split(f"<!-- built: {begin} -->")[1].split("<!-- built: end -->")[0])


def hand_written(text):
    return BUILT.sub(lambda found: found["begin"] + found["end"], text)


def carded(page, prefix):
    return {name[len(prefix) :] for name in page.cards if name.startswith(prefix)}


KINDS = {
    "skill-": lambda: {name for name in skills() if not name.startswith("principle-")},
    "playbook-": lambda: set(playbooks()),
    "principle-": lambda: {name for name in skills() if name.startswith("principle-")},
}


@pytest.mark.parametrize("prefix", KINDS)
def test_every_one_has_a_card_and_no_card_is_for_one_that_is_gone(built, prefix):
    there = KINDS[prefix]()
    assert there, f"nothing found for {prefix}"
    assert carded(built, prefix) == there


@pytest.mark.parametrize("prefix", KINDS)
def test_a_card_is_headed_by_the_name_it_is_for(built, prefix):
    for name in carded(built, prefix):
        assert built.heads[prefix + name].split()[0].lstrip("/") == name


@pytest.mark.parametrize("prefix", ["skill-", "playbook-"])
def test_the_picture_above_the_cards_links_every_card(built, prefix):
    linked = {load[1:] for load in built.loads if load.startswith("#" + prefix)}
    assert linked == {prefix + name for name in carded(built, prefix)}


def test_a_card_and_its_link_are_in_the_tile_its_file_names_in_the_order_of_its_place(tree):
    text = build(tree)
    assert list(part(text, "skill cards, Read").cards) == ["skill-scout", "skill-how"]
    assert part(text, "skill links, Read").loads == ["#skill-scout", "#skill-how"]
    assert list(part(text, "playbook cards, Build").cards) == ["playbook-one"]
    assert part(text, "playbook links, Build").loads == ["#playbook-one"]
    assert list(part(text, "playbook cards, Decide").cards) == ["playbook-two"]
    assert list(part(text, "principle cards, Prove it").cards) == ["principle-principle-prove"]
    assert "skill-stale" not in text


def test_a_card_has_the_words_of_its_own_file(tree):
    text = build(tree)
    assert (
        '<article class="card" id="skill-how"><h4>/how</h4><p>Says &lt;how&gt; &amp; why.</p>'
        '<p class="when">When <code>x</code> is new.</p><div class="who">'
        '<span class="chip op">the operator</span>'
        '<span class="chip plain">a step of <code>one</code></span></div></article>\n'
    ) in text
    assert '<article class="card scout" id="skill-scout"><h4>/scout</h4>' in text
    assert (
        '<article class="card" id="playbook-one"><h4>one</h4><p>For: One thing.</p></article>\n'
    ) in text
    assert (
        '<p>For: Two things.</p><div class="who"><span class="chip plain">'
        "<code>Review: none</code></span></div></article>"
    ) in text
    assert (
        '<div id="principle-principle-prove"><b>principle-prove</b><small>Run it.</small>'
        '<div class="leans"><code>one</code><span>most</span></div></div>\n'
    ) in text


def test_a_playbook_added_to_the_tree_gets_its_card_and_its_link_with_no_edit_to_the_page(
    tmp_path,
):
    shutil.copytree(REPO / "features", tmp_path / "features")
    (tmp_path / "docs").mkdir()
    page = Path(shutil.copy(PAGE, tmp_path / "docs"))
    feature = (tmp_path / "features" / "crew" / "playbooks" / "feature.md").read_text()
    tile = CARD.search(feature).group(1).split(" | ")[0]
    card = f"<!-- card: {tile} | 99 | A thing that is `made up`. -->"
    (tmp_path / "features" / "crew" / "playbooks" / "made-up.md").write_text(
        CARD.sub(card, feature)
    )
    before = read(build(REPO))
    text = build(tmp_path)
    assert page.read_text() == PAGE.read_text()
    assert "#playbook-made-up" in part(text, f"playbook links, {tile}").loads
    cards = part(text, f"playbook cards, {tile}")
    assert cards.cards["playbook-made-up"] == "made-upFor: A thing that is made up."
    assert "made up" in cards.codes
    whole = read(text)
    assert carded(whole, "playbook-") == carded(before, "playbook-") | {"made-up"}
    assert set(whole.loads) == set(before.loads) | {"#playbook-made-up"}


def test_the_build_writes_the_page_once_and_changes_nothing_the_second_time(tree):
    page = tree / "features/jdrift/docs/jstack-explained.html"
    first = explained(tree)
    assert (first.returncode, first.stdout) == (
        0,
        "built: features/jdrift/docs/jstack-explained.html\n",
    )
    once = page.read_text()
    assert ' id="playbook-one"' in once
    second = explained(tree)
    assert second.returncode == 0
    assert (
        second.stdout
        == "current: features/jdrift/docs/jstack-explained.html has what the tree has\n"
    )
    assert page.read_text() == once


def test_the_build_leaves_what_is_hand_written(tree):
    text = build(tree)
    assert text != MADE_UP_PAGE
    assert hand_written(text) == hand_written(MADE_UP_PAGE)
    assert "<h2>Hand-written</h2>" in hand_written(text)
    assert "<p>The end.</p>" in hand_written(text)


def test_the_build_of_the_real_page_leaves_what_is_hand_written():
    assert hand_written(build(REPO)) == hand_written(PAGE.read_text())


def test_the_check_says_the_page_is_behind_the_tree_and_writes_nothing(tree):
    page = tree / "features/jdrift/docs/jstack-explained.html"
    assert explained(tree).returncode == 0
    current = explained(tree, "--check")
    assert current.returncode == 0
    assert (
        current.stdout
        == "current: features/jdrift/docs/jstack-explained.html has what the tree has\n"
    )
    (tree / "playbooks" / "made-up.md").write_text("<!-- card: Build | 2 | A thing. -->\n")
    (tree / "features/principles/skills/principle-prove/SKILL.md").unlink()
    before = page.read_text()
    behind = explained(tree, "--check")
    assert behind.returncode == 1
    assert behind.stdout == (
        "behind: features/jdrift/docs/jstack-explained.html lacks playbook-made-up; "
        "still has principle-principle-prove: run uv run python -m jdrift.explained\n"
    )
    assert page.read_text() == before


def test_the_check_finds_a_card_whose_words_changed(tree):
    assert explained(tree).returncode == 0
    (tree / "playbooks" / "one.md").write_text("<!-- card: Build | 1 | Another thing. -->\n")
    behind = explained(tree, "--check")
    assert behind.returncode == 1
    assert behind.stdout == (
        "behind: features/jdrift/docs/jstack-explained.html has other words than the tree: "
        "run uv run python -m jdrift.explained\n"
    )


SKILL_FORM = 'card: "<tile> | <place> | <what it does> | <when to reach for it> | <who>"'
PLAYBOOK_FORM = "<!-- card: <tile> | <place> | <what it is for> -->"
PRINCIPLE_FORM = "<!-- card: <tile> | <place> | <the rule> | <who leans on it> -->"


@pytest.mark.parametrize(
    ("name", "text", "said"),
    [
        (
            "playbooks/made-up.md",
            "# Made up\n",
            f"has no card line: give it one on a line of its own, as `{PLAYBOOK_FORM}`",
        ),
        (
            "skills/made-up/SKILL.md",
            '---\nname: made-up\n---\n\ncard: "Read | 1 | In the body. | Never. | op: nobody"\n',
            f"has no card line: give it one in its front matter, as `{SKILL_FORM}`",
        ),
        (
            "skills/made-up/SKILL.md",
            "---\ncard: Read | 1 | Not quoted. | Never. | op: the operator\n---\n",
            "its card line is not one string in double quotes",
        ),
        (
            "playbooks/made-up.md",
            "<!-- card: Build | last | A thing. -->\n",
            f"its card line is not a tile, a place and its words, as `{PLAYBOOK_FORM}`",
        ),
        (
            "playbooks/made-up.md",
            "<!-- card: Build | 3 | A thing. | owner: somebody -->\n",
            "`owner: somebody` is not a chip: one of op, plain, model, cmd, rev, then `: `",
        ),
        (
            "playbooks/made-up.md",
            "<!-- card: Build | 3 | A thing. | look: scuot -->\n",
            "`look: scuot` is not a look: scout or rev",
        ),
        (
            "features/principles/skills/principle-made-up/SKILL.md",
            "<!-- card: Prove it | 3 | A rule. | `one` | look: scout -->\n",
            "`look: scout` is not a look: it has none",
        ),
    ],
)
def test_a_file_whose_card_line_cannot_be_read_is_named_and_nothing_is_written(
    tree, name, text, said
):
    (tree / name).parent.mkdir(parents=True, exist_ok=True)
    (tree / name).write_text(text)
    refused = explained(tree)
    assert refused.returncode == 2
    assert refused.stderr == f"jdrift.explained: {name}: {said}\n"
    assert (tree / "features/jdrift/docs/jstack-explained.html").read_text() == MADE_UP_PAGE


def test_a_tile_the_page_does_not_have_is_refused_with_the_tiles_it_has(tree):
    (tree / "playbooks" / "made-up.md").write_text("<!-- card: No such tile | 1 | A thing. -->\n")
    refused = explained(tree)
    assert refused.returncode == 2
    assert refused.stderr == (
        "jdrift.explained: playbook-made-up names the tile `No such tile`, and "
        "features/jdrift/docs/jstack-explained.html has no cards of it: it has Build; Decide\n"
    )


def test_the_lead_numbers_each_step_once_and_in_order(page):
    for cut in ("wide", "tall"):
        assert page.badges[cut] == [str(n) for n in range(1, 11)], cut


def test_a_page_without_one_card_is_not_the_tree():
    text = build(REPO)
    assert ' id="playbook-swarm"' in text
    without = read(text.replace(' id="playbook-swarm"', ""))
    assert KINDS["playbook-"]() - carded(without, "playbook-") == {"swarm"}


def test_each_command_has_a_card_with_a_rules_file_of_its_own(page):
    assert carded(page, "command-") == COMMANDS
    rules = {}
    for name in COMMANDS:
        card = page.cards["command-" + name]
        paths = set(re.findall(r"(?:features/[\w-]+/)?src/[\w/-]+\.(?:py|sh)", card))
        assert len(paths) == 1, (name, paths)
        rules[name] = paths.pop()
        assert (REPO / rules[name]).is_file(), rules[name]
        assert re.match(rf"(features/[\w-]+/)?src/{name.split('-')[0]}/", rules[name])
    assert len(set(rules.values())) == len(COMMANDS)


def test_the_page_loads_nothing_but_itself(page):
    assert not page.tags & {"script", "link", "img", "iframe", "object", "embed"}
    for load in page.loads:
        assert load in LOCAL or (load.startswith("#") and load[1:] in page.cards), load
    for name in LOCAL:
        assert (PAGE.parent / name).is_file()
    assert page.style
    assert "@import" not in page.style
    for target in URL.findall(page.style):
        assert target.startswith("#") and target[1:] in page.cards, target


def test_a_style_that_loads_a_file_is_read():
    styled = read("<style>a { background: url(https://example.test/x.png) }</style>")
    assert URL.findall(styled.style) == ["https://example.test/x.png"]


def test_the_page_names_no_place_of_a_person():
    text = PAGE.read_text()
    for banned in ("—", "~/", "github.com"):
        assert banned not in text, banned
    assert not re.search(r"(?<![\w.])/home/", text), "a path under /home/"
