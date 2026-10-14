"""The `Home:` line: a brief or a scout's request names its home by its scope, and never by a
thread. A thread reads the id in that home's `home-id` each time it sends, so a new home
rewrites no brief. Every block here is lifted from the skill that gives it."""

import shutil
import subprocess

import pytest

from test_home_thread import READERS, THREAD, Scene, about_the_home_id, paths

OTHER = "mcp:another-home-of-the-same-repo"
NEXT = "mcp:the-home-that-came-after"
SCOPE = "second"
HOME_LINE_IN = {"scout": "scouts", "crew": "tasks", "pr-review": "tasks"}
ROOT_OR_SCOPED = [("", ()), (SCOPE, (f"Home: {SCOPE}",))]


class Homes(Scene):
    """A repo's root home and one scoped home beside it, with briefs and requests out."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        for kind in set(HOME_LINE_IN.values()):
            (self.home_dir / kind).mkdir()
        (self.home_dir / "plan.md").write_text("# a demo repo: plan\n")
        (self.home_dir / SCOPE).mkdir()
        (self.home_dir / SCOPE / "plan.md").write_text("# the second home: plan\n")

    def sent(self, reader, slug, *lines):
        """A brief or a request the reader's thread was launched from."""
        text = "\n".join([f"# {slug}: a title", 'Task: "make it so"', *lines])
        (self.home_dir / HOME_LINE_IN[reader] / f"{slug}.md").write_text(text + "\n")
        return slug

    def reports_to(self, reader, slug, shell="sh"):
        """What the skill's block prints with `B` set as the skill says: the thread to tell."""
        block = f'B="$H/{HOME_LINE_IN[reader]}/{slug}.md"\n{about_the_home_id(reader)}'
        if shell == "sh":
            return self.run(reader, block, self.worktree).stdout
        ran = subprocess.run(
            [shell, "-c", f"{paths(reader)}\n{block}"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(self.user)},
            cwd=self.worktree,
        )
        assert (ran.stderr, ran.returncode) == ("", 0)
        return ran.stdout

    def hands_off(self, thread, scope=""):
        own = self.home_dir / scope
        (own / "handoff.md").write_text("# a demo repo: handoff\n\n## Loose ends\nNone\n")
        assert self.home_hands_off(thread).stdout.startswith("the home")
        assert not (own / "home-id").exists()

    def sums(self):
        """`sha256sum` of every brief and every request, as the shell prints it."""
        ran = subprocess.run(
            "sha256sum tasks/* scouts/*",
            shell=True,
            capture_output=True,
            text=True,
            cwd=self.home_dir,
            check=True,
        )
        return ran.stdout


@pytest.fixture
def homes(tmp_path):
    return Homes(tmp_path)


def test_the_three_skills_find_the_home_with_one_text():
    crew = about_the_home_id("crew")
    assert [about_the_home_id(reader) for reader in READERS] == [crew] * len(READERS)


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize(("scope", "line"), ROOT_OR_SCOPED)
def test_a_thread_is_told_the_id_its_home_holds_when_it_sends(homes, reader, scope, line):
    slug = homes.sent(reader, "a-task", *line, "Pull request: open one when done")
    homes.home_starts(THREAD, scope)
    assert homes.reports_to(reader, slug) == f"{THREAD}\n"
    homes.home_starts(NEXT, scope)
    assert homes.reports_to(reader, slug) == f"{NEXT}\n"


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize(("scope", "line"), ROOT_OR_SCOPED)
def test_between_a_handoff_and_the_next_start_nobody_is_told(homes, reader, scope, line):
    slug = homes.sent(reader, "a-task", *line)
    assert homes.reports_to(reader, slug) == ""
    homes.home_starts(THREAD, scope)
    assert homes.reports_to(reader, slug) == f"{THREAD}\n"
    homes.hands_off(THREAD, scope)
    assert homes.reports_to(reader, slug) == ""
    homes.home_starts(NEXT, scope)
    assert homes.reports_to(reader, slug) == f"{NEXT}\n"


@pytest.mark.parametrize("reader", READERS)
def test_each_home_is_told_of_its_own_and_of_no_other_homes(homes, reader):
    mine = homes.sent(reader, "mine")
    theirs = homes.sent(reader, "theirs", f"Home: {SCOPE} (a second home of this repo)")
    homes.home_starts(THREAD)
    homes.home_starts(OTHER, SCOPE)
    homes.hands_off(THREAD)
    assert (homes.reports_to(reader, mine), homes.reports_to(reader, theirs)) == ("", f"{OTHER}\n")
    homes.home_starts(NEXT)
    homes.hands_off(OTHER, SCOPE)
    assert (homes.reports_to(reader, mine), homes.reports_to(reader, theirs)) == (f"{NEXT}\n", "")


@pytest.mark.parametrize("reader", READERS)
def test_a_brief_written_before_names_a_thread_and_still_finds_its_home(homes, reader):
    """An id in a `home-id` is that home, and so is the id of the thread a scoped home's
    handoff names. Any other id is the root home."""
    scoped = homes.sent(reader, "scoped", f"Home: {OTHER}")
    root = homes.sent(reader, "root", f"Home: {THREAD}  ")
    gone = homes.sent(reader, "gone", "Home: mcp:a-home-of-long-ago (the root home)")
    assert [homes.reports_to(reader, slug) for slug in (scoped, root, gone)] == [""] * 3
    homes.home_starts(THREAD)
    homes.home_starts(OTHER, SCOPE)
    told = [f"{OTHER}\n", f"{THREAD}\n", f"{THREAD}\n"]
    assert [homes.reports_to(reader, slug) for slug in (scoped, root, gone)] == told
    homes.home_starts(NEXT)
    told = [f"{OTHER}\n", f"{NEXT}\n", f"{NEXT}\n"]
    assert [homes.reports_to(reader, slug) for slug in (scoped, root, gone)] == told

    homes.hands_off(OTHER, SCOPE)
    homes.hands_off(NEXT)
    assert [homes.reports_to(reader, slug) for slug in (scoped, root, gone)] == [""] * 3
    homes.home_starts(THREAD)
    assert homes.reports_to(reader, scoped) == ""
    homes.home_starts("mcp:the-next-scoped-home", SCOPE)
    assert homes.reports_to(reader, scoped) == "mcp:the-next-scoped-home\n"


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize(
    "line",
    [
        "Home:",
        "Home: ",
        "Decisions: the Home: second line is the home's",
        "Homes: second",
        "Home: <scope>",
        "Home: tasks",
        "Home: .",
        "Home: ../other",
        f"Home: {SCOPE}/log",
        "Home: nosuch",
    ],
)
def test_a_line_that_names_no_scope_is_the_root_homes(homes, reader, line):
    (homes.home_dir / "tasks" / "plan.md").write_text("# plan: a brief with that slug\n")
    (homes.home_dir.parent / "other").mkdir()
    (homes.home_dir.parent / "other" / "home-id").write_text(f"{OTHER}\n")
    (homes.home_dir / SCOPE / "log").mkdir()
    (homes.home_dir / SCOPE / "log" / "plan.md").write_text("")
    (homes.home_dir / SCOPE / "log" / "home-id").write_text(f"{OTHER}\n")
    slug = homes.sent(reader, "a-task", line)
    assert homes.reports_to(reader, slug) == ""
    homes.home_starts()
    assert homes.reports_to(reader, slug) == f"{THREAD}\n"
    assert homes.reports_to(reader, "no-such-file") == f"{THREAD}\n"


@pytest.mark.parametrize("reader", READERS)
def test_the_first_home_line_is_the_one_read_and_only_its_first_word(homes, reader):
    slug = homes.sent(reader, "a-task", f"Home:\t{SCOPE}  ", "## Result", "Home: nosuch")
    homes.home_starts(THREAD)
    homes.home_starts(OTHER, SCOPE)
    assert homes.reports_to(reader, slug) == f"{OTHER}\n"


def test_the_start_of_a_second_home_changes_no_brief_and_no_request(homes):
    for reader in ("crew", "scout"):
        homes.sent(reader, "plain", "Thread: mcp:1")
        homes.sent(reader, "scoped", f"Home: {SCOPE}", "Thread: mcp:2", "## Result", "Done")
        homes.sent(reader, "before", f"Home: {THREAD}")
        homes.sent(reader, "before-scoped", f"Home: {OTHER}  ")
    assert homes.home_starts(THREAD) == ""
    assert homes.home_starts(OTHER, SCOPE) == ""
    before = homes.sums()
    assert before.count("\n") == 8

    homes.hands_off(THREAD)
    assert homes.home_starts(NEXT) == ""
    homes.hands_off(OTHER, SCOPE)
    assert homes.home_starts("mcp:the-next-scoped-home", SCOPE) == ""

    assert homes.sums() == before
    assert homes.file.read_text() == f"{NEXT}\n"
    assert homes.reports_to("crew", "before") == f"{NEXT}\n"
    assert homes.reports_to("scout", "scoped") == "mcp:the-next-scoped-home\n"


@pytest.mark.parametrize("reader", READERS)
def test_a_scope_no_home_has_run_in_is_no_home_and_its_brief_is_the_roots(homes, reader):
    """A directory with a plan and no `home-id` and no `Was home:` line is no home to
    `jmerge`, which counts the brief as the root's: the thread tells the root home."""
    slug = homes.sent(reader, "a-task", f"Home: {SCOPE}")
    (homes.home_dir / SCOPE / "handoff.md").write_text("# the second home: handoff\n")
    homes.home_starts(THREAD)
    assert homes.reports_to(reader, slug) == f"{THREAD}\n"
    (homes.home_dir / SCOPE / "home-id").write_text(f"{OTHER} \n")
    assert homes.reports_to(reader, slug) == f"{OTHER}\n"


def test_a_handoff_with_no_note_written_changes_nothing(homes):
    homes.home_starts()
    ran = homes.home_hands_off(note=None)
    assert (ran.returncode, ran.stdout.split(": ")[0]) == (1, "not written")
    assert not (homes.home_dir / "handoff.md").exists()
    assert homes.file.exists()


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh is not installed")
@pytest.mark.parametrize("reader", READERS)
def test_the_block_runs_in_zsh_in_a_repo_with_no_scope(tmp_path, reader):
    """zsh stops a call at a pattern that matches no file, and a crewmate's shell may be zsh."""
    scene = Homes(tmp_path)
    shutil.rmtree(scene.home_dir / SCOPE)
    slug = scene.sent(reader, "a-task", f"Home: {OTHER}")
    assert scene.reports_to(reader, slug, "zsh") == ""
    scene.home_starts()
    assert scene.reports_to(reader, slug, "zsh") == f"{THREAD}\n"
