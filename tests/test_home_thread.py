"""`home-id`: a home writes its thread id there, in its own directory. Three skills read the
root home's to know whom to tell, and the handoff removes it. Every block here is lifted from
the skill that gives it."""

import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
NAME = "a demo repo"
SLUG = "fix-login"
THREAD = "mcp:thread-one"
OTHER = "mcp:thread-two"
HANDOFF = "# a demo repo: handoff\n\n## Loose ends\nNone\n"
NOTE = "Next: plan the next task\nOut, not on the bus: none\nDo not redo: none\nUncommitted: none\n"
NOT_THE_HOME = "not the home: start nothing, tell the user\n"
READERS = ["scout", "crew", "pr-review"]
TYPED = "<the text after /home>"
WHICH = "<which home>"
FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)
NAMED = re.compile(r"read `\$T/\.\./skills/([^/`]+)/([^/`]+\.md)` now")


def beside(line, path):
    """The files beside the skill at `path` that `line` says to read now."""
    return [
        path.parent / name
        for skill, name in NAMED.findall(line)
        if skill == path.parent.name and name != "SKILL.md"
    ]


def named(path):
    """Every file beside the skill at `path` that one of its lines says to read now."""
    return [found for line in path.read_text().splitlines() for found in beside(line, path)]


def as_read(path):
    """A skill's text as an agent reads it: each file beside it that a line says to read now
    follows that line. A file the line names that is not there fails the test."""
    out = []
    for line in path.read_text().splitlines(keepends=True):
        out += [line, *("\n" + found.read_text() for found in beside(line, path))]
    return "".join(out)


def blocks(skill):
    """Every shell block the skill gives, as an agent reads it."""
    text = as_read(REPO / "skills" / skill / "SKILL.md")
    return [textwrap.dedent(block) for block in FENCED.findall(text)]


def paths(skill):
    """The block at the top of the skill, which sets `$H`."""
    (found,) = [block for block in blocks(skill) if re.search(r"^H=", block, re.M)]
    return found


def block(skill, holding):
    (found,) = [text for text in blocks(skill) if holding in text]
    return found


FILLED = "<the gate, filled in>"
CONTEXT = "Context: the cups are in pull request 7, https://example.test/pull/7"
PROPOSED = "Option: tea (default, recommended): the cups stay\nOption: coffee: the cups go back"


def a_gate_in(sends, entry):
    """A skill's gate block with a gate in it, as a thread fills it in: the entry in place of
    the block's one line, its `Context:` line filled, and its `Option:` line twice: once as
    the block writes it, both marks kept, and once with no mark."""
    assert FILLED in sends
    (context,) = [line for line in sends.splitlines() if line.startswith("Context: <")]
    (option,) = [line for line in sends.splitlines() if line.startswith("Option: <")]
    words = iter(("tea", "the cups stay"))
    first, second = re.sub(r"<[^>]*>", lambda _: next(words), option), PROPOSED.splitlines()[1]
    assert first == PROPOSED.splitlines()[0]
    sends = sends.replace(FILLED, entry).replace(context, CONTEXT)
    return sends.replace(option, f"{first}\n{second}")


def about_the_home_id(skill):
    """The one block the skill gives that touches the root home's `home-id`. For the home
    skill, the one that writes a home's own: step 3 of its start. For the handoff skill, the
    one that removes a home's own: its step 6."""
    own = {"home": '> "$M/home-id"', "handoff": 'rm -f "$M/home-id"'}
    return block(skill, own.get(skill, 'jbus home "$B"'))


def start_block():
    """Step 4 of a home's start, after the block it is run after that reads jbus ("Gates")."""
    return f"{block('home', 'OPEN=')}\n{block('home', '## to read')}"


def finds_this_home(thread):
    """The home skill's block that sets `$M`, as the home whose thread id is `thread` runs it."""
    found = block("home", 'echo "no home:')
    assert "<threadId>" in found
    return found.replace("<threadId>", thread)


def git(cwd, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", *identity, *args], cwd=cwd, check=True, capture_output=True)


class Scene:
    """A user's home directory with the skills, a repo with a worktree, and that repo's home."""

    def __init__(self, tmp_path):
        self.user = tmp_path / "user"
        (self.user / ".claude").mkdir(parents=True)
        (self.user / ".claude" / "skills").symlink_to(REPO / "skills")
        self.home_dir = self.user / ".local" / "state" / "home" / NAME
        self.home_dir.mkdir(parents=True)
        self.file = self.home_dir / "home-id"

        self.main = tmp_path / "code" / NAME
        self.main.mkdir(parents=True)
        git(self.main, "init", "-q")
        git(self.main, "commit", "-q", "--allow-empty", "-m", "start")
        self.worktree = tmp_path / "trees" / SLUG
        git(self.main, "worktree", "add", "-q", str(self.worktree))

    def run(self, skill, block, checkout, thread=""):
        """Run a block as the skill says to: in one call with the block at the top, and for a
        home with the block that finds it. A home with no id is the root, in a session with no
        tool that gives one. `thread=None` leaves that block out, as the start's first steps do.
        """
        top = paths(skill)
        if skill == "home" and thread is not None:
            top = f"{top}\n{finds_this_home(thread)}"
        ran = subprocess.run(
            ["sh", "-c", f"{top}\n{block}"],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.user)},
            cwd=checkout,
        )
        assert ran.stderr == ""
        return ran

    def which_home(self, typed="", checkout=None):
        """What step 1 of a home's start prints for what was typed after `/home`, in lines."""
        first = block("home", "title: home:")
        assert TYPED in first
        ran = self.run("home", first.replace(TYPED, typed), checkout or self.main, None)
        return ran.stdout.splitlines()

    def home_starts(self, thread=THREAD, typed=""):
        """Steps 1 and 3 of a home's start. What step 3 printed."""
        which, *_ = self.which_home(typed)
        third = about_the_home_id("home")
        assert "<threadId>" in third and WHICH in third
        third = third.replace("<threadId>", thread).replace(WHICH, which)
        done = self.run("home", third, self.main, None)
        assert done.returncode == 0
        return done.stdout

    def home_hands_off(self, thread=THREAD, checkout=None, note=NOTE):
        """Steps 2 and 3 of a handoff: the note written where none is, then the close."""
        for own in (self.home_dir, *self.home_dir.iterdir()):
            ids = own / "home-id"
            mine = ids.is_file() and ids.read_text().split() == [thread]
            if (mine or (own == self.home_dir and not thread)) and note is not None:
                if not (own / "handoff.next.md").exists():
                    (own / "handoff.next.md").write_text(note)
        block = about_the_home_id("handoff")
        assert "<threadId>" in block
        return self.run("handoff", block.replace("<threadId>", thread), checkout or self.main)

    def whom_to_tell(self, skill):
        """What the skill's own check prints in a worktree: the thread to tell, or nothing."""
        block = f'B="$H/tasks/{SLUG}.md"\n{about_the_home_id(skill)}'
        return self.run(skill, block, self.worktree).stdout


@pytest.fixture
def scene(tmp_path):
    return Scene(tmp_path)


@pytest.mark.parametrize("reader", READERS)
def test_the_id_a_home_writes_at_start_is_the_thread_each_skill_tells(scene, reader):
    scene.home_starts()
    assert scene.file.read_text() == f"{THREAD}\n"
    assert scene.whom_to_tell(reader).split() == [THREAD]


@pytest.mark.parametrize("reader", READERS)
def test_with_no_home_id_file_a_skill_has_nobody_to_tell(scene, reader):
    assert scene.whom_to_tell(reader) == ""


def test_a_new_home_takes_the_place_of_one_that_never_handed_off(scene):
    scene.home_starts("mcp:the-last-home")
    scene.home_starts()
    assert scene.file.read_text() == f"{THREAD}\n"


@pytest.mark.parametrize("reader", READERS)
def test_after_a_handoff_nobody_is_told(scene, reader):
    scene.home_starts()
    assert scene.home_hands_off().returncode == 0
    assert not scene.file.exists()
    assert scene.whom_to_tell(reader) == ""


def test_a_handoff_with_no_home_id_file_still_goes_through(scene):
    assert scene.home_hands_off().returncode == 0
    assert not scene.file.exists()


def a_crewmate(scene):
    return OTHER, scene.worktree


def an_ordinary_thread(scene):
    return OTHER, scene.main


def a_home_a_later_home_took_the_place_of(scene):
    scene.home_starts(OTHER)
    return THREAD, scene.main


@pytest.mark.parametrize(
    "not_the_home",
    [
        a_crewmate,
        an_ordinary_thread,
        a_home_a_later_home_took_the_place_of,
    ],
)
def test_a_handoff_by_a_thread_that_is_not_the_home_leaves_the_homes_files_alone(
    scene, not_the_home
):
    scene.home_starts()
    handoff = scene.home_dir / "handoff.md"
    handoff.write_text(HANDOFF)
    thread, checkout = not_the_home(scene)
    before = scene.file.read_bytes(), handoff.read_bytes()

    ran = scene.home_hands_off(thread, checkout)

    assert ran.stdout == NOT_THE_HOME
    assert (scene.file.read_bytes(), handoff.read_bytes()) == before


def test_a_handoff_by_a_second_home_leaves_the_root_homes_files_alone(scene):
    scene.home_starts()
    handoff = scene.home_dir / "handoff.md"
    handoff.write_text(HANDOFF)
    second = scene.home_dir / "second"
    second.mkdir()
    (second / "home-id").write_text(f"{OTHER}\n")
    before = scene.file.read_bytes(), handoff.read_bytes()

    ran = scene.home_hands_off(OTHER)

    assert ran.stdout.startswith("the home")
    assert not (second / "home-id").exists()
    assert (scene.file.read_bytes(), handoff.read_bytes()) == before


def test_a_handoff_by_the_home_removes_its_file_and_names_it_on_the_note(scene):
    scene.home_starts()
    handoff = scene.home_dir / "handoff.md"
    handoff.write_text(HANDOFF)
    scene.home_hands_off()
    assert not scene.file.exists()
    assert handoff.read_text() == f"{NOTE}\nWas home: {THREAD}\n"
    (kept,) = (scene.home_dir / "log").iterdir()
    assert kept.read_text() == HANDOFF


@pytest.mark.parametrize("switch", [None, "", f"{OTHER}\n"])
def test_a_start_and_a_handoff_leave_the_merge_switch_as_it_was(scene, switch):
    """`home-thread` hands merging from jbus to a home, and is set by hand: a home that starts
    and hands off neither writes it nor removes it."""
    merges = scene.home_dir / "home-thread"
    if switch is not None:
        merges.write_text(switch)
    scene.home_starts()
    assert scene.file.read_text() == f"{THREAD}\n"
    assert scene.home_hands_off().stdout.startswith("the home")
    assert not scene.file.exists()
    assert (merges.read_text() if merges.exists() else None) == switch
