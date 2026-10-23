"""A scoped home: `/home <scope>` starts a home beside the repo's root home. Its handoff, plan, log
and `home-id` are in a directory of its own under the repo's state directory. It shares the notes,
briefs, requests and pages with the root home. Each test takes every block from the home skill and
runs it in a temporary repo that has both homes."""

import os
import re
import subprocess

import pytest

from test_home_thread import (
    NAME,
    TYPED,
    WHICH,
    Scene,
    about_the_home_id,
    block,
    blocks,
    paths,
    start_block,
)

ROOT = "mcp:the-root-home"
SCOPED = "mcp:the-scoped-home"
LAST_ROOT = "mcp:the-last-root-home"
LAST_SCOPED = "mcp:the-last-scoped-home"
ANOTHER = "mcp:a-third-home"
SCOPE = "second"
SEED = "This message was written by the previous home of a demo repo.\nKeep the queue going."
UNFILLED = "<threadId>"
FILES_OF_ONE_HOME = ["handoff.md", "home-id", "log/2026-10-10-0900.md", "plan.md"]


class Homes(Scene):
    """A repo with a root home and one scoped home, each with every file a home keeps."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.scope_dir = self.home_dir / SCOPE
        for kind in ("tasks", "scouts", "reports"):
            (self.home_dir / kind).mkdir()
        (self.home_dir / "notes.md").write_text("- Check command: make check\n")
        for own, name, last in (
            (self.home_dir, "the root home", LAST_ROOT),
            (self.scope_dir, "the second home", LAST_SCOPED),
        ):
            (own / "log").mkdir(parents=True)
            (own / "log" / "2026-10-10-0900.md").write_text(f"# {name}: an old handoff\n")
            (own / "plan.md").write_text(f"# {name}: plan\n")
            (own / "handoff.md").write_text(f"# {name}: handoff\n\nWas home: {last}\n")
            (own / "home-id").write_text("mcp:an-earlier-home\n")

    def state(self):
        return {
            str(path.relative_to(self.home_dir)): path.read_bytes()
            for path in self.home_dir.rglob("*")
            if path.is_file()
        }

    def changed(self, before):
        after = self.state()
        return sorted(name for name in before.keys() | after if before.get(name) != after.get(name))

    def sent(self, kind, slug, *lines):
        """A brief (`tasks`) or a scout's request (`scouts`), in the repo's shared directory."""
        path = self.home_dir / kind / f"{slug}.md"
        path.write_text("\n".join([f"# {slug}: a title", 'Task: "make it so"', *lines]) + "\n")
        return path

    def step(self, holding, thread, **filled):
        """One of the home skill's blocks, run by the home whose thread id is `thread`."""
        found = block("home", holding)
        for mark, text in filled.items():
            assert mark in found
            found = found.replace(mark, text)
        return self.run("home", found, self.main, thread)

    def start(self, thread):
        """What step 4 of the start prints, by its parts: the lines before the first part
        under `""`, and each part's lines under its heading."""
        ran = self.run("home", start_block(), self.main, thread)
        assert ran.returncode == 0
        parts, heading = {"": []}, ""
        for line in ran.stdout.splitlines():
            if line.startswith("## "):
                heading = line.removeprefix("## ")
                parts[heading] = []
            else:
                parts[heading].append(
                    line.removeprefix("read whole: ").removeprefix(f"{self.home_dir}/")
                )
        return parts

    def to_read(self, thread):
        """The files step 4 of the start says to read: the two it reads whole, then each
        brief and request whose last Result or Report came in since the note."""
        parts = self.start(thread)
        return parts[""] + [line.split(": ")[0] for line in parts["to read"]]

    def marks(self, thread, lines):
        """The block that marks what step 4 printed as read, with the lines that were read."""
        found = block("home", "marked read: ")
        mark = "<the lines step 4 printed that you read>"
        assert mark in found
        return self.run("home", found.replace(mark, "\n".join(lines)), self.main, thread)


@pytest.fixture
def homes(tmp_path):
    return Homes(tmp_path)


def own(directory):
    return {name: (directory / name).read_bytes() for name in FILES_OF_ONE_HOME}


@pytest.mark.parametrize("first", ["the scope", "the root"])
def test_a_start_writes_its_own_home_id_and_no_file_of_the_other_home(homes, first):
    starts = {
        "the scope": (SCOPED, SCOPE, homes.scope_dir, homes.home_dir),
        "the root": (ROOT, "", homes.home_dir, homes.scope_dir),
    }
    for home in (first, *(name for name in starts if name != first)):
        thread, typed, mine, theirs = starts[home]
        before, others = homes.state(), own(theirs)
        homes.home_starts(thread, typed)
        assert (mine / "home-id").read_text() == f"{thread}\n"
        assert own(theirs) == others
        assert homes.changed(before) == [str((mine / "home-id").relative_to(homes.home_dir))]


@pytest.mark.parametrize(
    ("typed", "said"),
    [
        ("", ["root", f"title: home: {NAME}"]),
        (SEED, ["root", f"title: home: {NAME}"]),
        ("nosuch and more words", ["root", f"title: home: {NAME}"]),
        ("../other and more words", ["root", f"title: home: {NAME}"]),
        ("tasks and more words", ["root", f"title: home: {NAME}"]),
        (SCOPE, [f"scope {SCOPE}", f"title: home: {NAME} {SCOPE}"]),
        (f"  {SCOPE}  ", [f"scope {SCOPE}", f"title: home: {NAME} {SCOPE}"]),
        (f"{SCOPE} {SEED}", [f"scope {SCOPE}", f"title: home: {NAME} {SCOPE}"]),
        (f"{SCOPE}\n{SEED}", [f"scope {SCOPE}", f"title: home: {NAME} {SCOPE}"]),
    ],
)
def test_the_first_word_after_home_is_a_scope_when_it_names_one(homes, typed, said):
    (homes.home_dir.parent / "other").mkdir()
    (homes.home_dir.parent / "other" / "plan.md").write_text("")
    (homes.home_dir / "tasks" / "plan.md").write_text("# plan: a brief with that slug\n")
    before = homes.state()
    assert homes.which_home(typed) == said
    assert homes.changed(before) == []


SHARED = ["tasks", "scouts", "reports", "log"]


@pytest.mark.parametrize("word", ["nosuch", *SHARED, "..", "../other", ".", "second/log"])
def test_a_single_word_that_names_no_scope_starts_no_home(homes, word):
    for shared in SHARED:
        (homes.home_dir / shared / "plan.md").write_text("# plan: a brief with that slug\n")
    (homes.home_dir.parent / "other").mkdir()
    (homes.home_dir.parent / "other" / "plan.md").write_text("")
    before = homes.state()
    (said,) = homes.which_home(word)
    assert said == (
        f"no scope: {NAME} has no scope {word}, there is no {homes.home_dir}/{word}/plan.md. "
        "Only the root home makes a scope, when the user asks for one. Nothing is written."
    )
    third = about_the_home_id("home").replace("<threadId>", SCOPED).replace(WHICH, said)
    ran = homes.run("home", third, homes.main, None)
    assert ran.stdout.startswith("not written: ")
    assert homes.changed(before) == []


def test_a_single_word_in_a_repo_with_no_home_makes_none(tmp_path):
    scene = Scene(tmp_path)
    scene.home_dir.rmdir()
    assert scene.which_home("nosuch")[0].startswith("no scope: ")
    assert not scene.home_dir.exists()


def test_a_seed_after_a_scope_starts_that_scope(homes):
    before = homes.state()
    homes.home_starts(SCOPED, f"{SCOPE} {SEED}")
    assert homes.changed(before) == [f"{SCOPE}/home-id"]
    assert (homes.scope_dir / "home-id").read_text() == f"{SCOPED}\n"


@pytest.mark.parametrize("kind", ["tasks", "scouts"])
def test_a_scoped_home_writes_the_thread_line_in_the_shared_directory(homes, kind):
    homes.home_starts(SCOPED, SCOPE)
    out = homes.sent(kind, "sc-out", f"Home: {SCOPED}", "Review: review")
    fast = homes.sent(kind, "sc-fast", f"Home: {SCOPED}", "", "## Result", "Status: done")
    before = homes.state()
    filled = {"<tasks or scouts>": kind, "<the launched thread>": "mcp:the-crewmate"}

    said = homes.step("<the launched thread>", None, **filled, **{"<slug>": "sc-out"}).stdout
    assert said == f"written: Thread: mcp:the-crewmate, in {out}\n"
    assert out.read_text().splitlines()[-2:] == ["Review: review", "Thread: mcp:the-crewmate"]
    homes.step("<the launched thread>", None, **filled, **{"<slug>": "sc-fast"})
    assert fast.read_text().splitlines()[-4:] == [
        "",
        "Thread: mcp:the-crewmate",
        "## Result",
        "Status: done",
    ]
    assert homes.changed(before) == [f"{kind}/sc-fast.md", f"{kind}/sc-out.md"]

    again = {**filled, "<the launched thread>": "mcp:the-second-crewmate"}
    said = homes.step("<the launched thread>", None, **again, **{"<slug>": "sc-fast"}).stdout
    assert said == (
        "written: Thread: mcp:the-second-crewmate, in place of Thread: mcp:the-crewmate, "
        f"in {fast}\n"
    )
    assert fast.read_text().splitlines()[-4:] == [
        "",
        "Thread: mcp:the-second-crewmate",
        "## Result",
        "Status: done",
    ]

    before = homes.state()
    for slug, other in (
        ("sc-out", filled),
        ("no-such", filled),
        ("sc-none", {"<slug>": "sc-none"}),
    ):
        homes.sent(kind, "sc-none")
        ran = homes.step("<the launched thread>", None, **{"<slug>": slug, **other})
        assert ran.stdout.startswith("not written: ")
    assert homes.changed(before) == [f"{kind}/sc-none.md"]


def of_this_home():
    """Every block of the home skill that names `$M`, except the one that sets it and step 3 of
    the start, which sets its own."""
    setting = (block("home", 'echo "no home:'), about_the_home_id("home"))
    named = [text for text in blocks("home") if re.search(r"\$\{?M\b", text)]
    return [text for text in named if text not in setting]


@pytest.mark.parametrize("thread", [UNFILLED, "mcp:a-home-that-handed-off", "<>", "second"])
def test_a_block_run_by_a_thread_that_is_no_home_writes_nothing(homes, thread):
    homes.home_starts(ROOT)
    homes.home_starts(SCOPED, SCOPE)
    before = homes.state()
    found = of_this_home()
    assert len(found) == 15
    finds = block("home", 'echo "no home:').replace(UNFILLED, thread)
    for text in found:
        ran = subprocess.run(
            ["sh", "-c", f"{paths('home')}\n{finds}\n{text}"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(homes.user)},
            cwd=homes.main,
        )
        assert ran.stdout.startswith(f"no home: thread {thread} is no home of {NAME} now")
        assert (ran.returncode, ran.stderr) == (1, "")
    assert homes.changed(before) == []


@pytest.mark.parametrize(
    ("thread", "which"),
    [
        (UNFILLED, "root"),
        (UNFILLED, f"scope {SCOPE}"),
        ("", f"scope {SCOPE}"),
        (ROOT, WHICH),
        (ROOT, ""),
        (ROOT, "scope "),
        (ROOT, "scope nosuch"),
        (ROOT, "scope ../other"),
        (ROOT, "scope ."),
        (ROOT, "scope tasks"),
        (ROOT, "scope log"),
        (ROOT, f"title: home: {NAME}"),
    ],
)
def test_the_start_writes_nothing_with_a_placeholder_left_or_a_home_step_1_did_not_print(
    homes, thread, which
):
    (homes.home_dir.parent / "other").mkdir()
    (homes.home_dir.parent / "other" / "plan.md").write_text("")
    homes.sent("tasks", "root-one", f"Home: {LAST_ROOT}")
    homes.sent("tasks", "plan")
    (homes.home_dir / "log" / "plan.md").write_text("")
    before = homes.state()
    third = about_the_home_id("home").replace(UNFILLED, thread).replace(WHICH, which)
    ran = homes.run("home", third, homes.main, None)
    assert ran.stdout.startswith("not written: ")
    assert homes.changed(before) == []
    assert not (homes.home_dir.parent / "other" / "home-id").exists()


def test_the_first_step_makes_no_home_with_its_placeholder_left(tmp_path):
    scene = Scene(tmp_path)
    ran = scene.run("home", block("home", "title: home:"), scene.main, None)
    assert TYPED in block("home", "title: home:")
    assert ran.stdout.startswith("not filled in: ")
    assert list(scene.home_dir.iterdir()) == []


@pytest.mark.parametrize("first", ["the scope", "the root"])
def test_a_start_rewrites_no_brief_and_its_last_threads_are_told_the_new_id(homes, first):
    sent = [
        homes.sent("tasks", "root-one", f"Home: {LAST_ROOT}"),
        homes.sent("tasks", "root-plain", "Thread: mcp:1"),
        homes.sent("tasks", "sc-one", f"Home: {SCOPE}", "Thread: mcp:2"),
        homes.sent("scouts", "sc-ask", f"Home: {SCOPE} (the second home)"),
    ]
    before = [path.read_bytes() for path in sent]
    starts = {"the scope": (SCOPED, SCOPE), "the root": (ROOT, "")}
    for home in (first, *(name for name in starts if name != first)):
        assert homes.home_starts(*starts[home]) == ""
        assert [path.read_bytes() for path in sent] == before

    told = {"root-one": ROOT, "root-plain": ROOT, "sc-one": SCOPED}
    for slug, thread in told.items():
        crew = f'B="$H/tasks/{slug}.md"\n{about_the_home_id("crew")}'
        assert homes.run("crew", crew, homes.worktree).stdout == f"{thread}\n"
    scout = f'B="$H/scouts/sc-ask.md"\n{about_the_home_id("scout")}'
    assert homes.run("scout", scout, homes.worktree).stdout == f"{SCOPED}\n"


RESULT = ("", "## Result", "Status: done")
REPORT = ("", "## Report", "Status: done")


def two_homes_work(homes):
    """Briefs and requests of both homes in the one `tasks/` and the one `scouts/`."""
    (homes.home_dir / "plan.md").write_text(
        "# the root home: plan\n\n"
        "## root-open: a task that is out\nStatus: with crewmate\nDone when:\n- it works\n\n"
        "## root-plain: a brief with no Home line\nDone when:\n- it works\n\n"
        "## root-done: a task that is merged\nStatus: done (pull request 7 merged)\n\n"
        "## root-out: a task with no result yet\nStatus: with crewmate\n\n"
        "## root-split: an entry split into parts\n"
        "Status: split, the briefs are `tasks/root-part.md` and `tasks/root-later.md`\n\n"
        "## root-old: a split that is merged\nStatus: done\nDecisions:\n- `tasks/root-gone.md`\n"
    )
    (homes.scope_dir / "plan.md").write_text(
        "# the second home: plan\n\n"
        "## sc-open: a task that is out\nStatus: PR https://example.test/pull/8\n"
        "Decisions:\nStatus: done is not what this line says\n\n"
        "## Later, in the order the scout gave\n\n"
        "## sc-done: a task that is merged\nStatus: done\n\n"
        "## sc-plain: a brief with no Home line\nStatus: with crewmate\n"
    )
    for slug in ("root-open", "root-done", "root-gone", "root-part"):
        homes.sent("tasks", slug, f"Home: {LAST_ROOT}", *RESULT)
    homes.sent("tasks", "root-plain", *RESULT)
    homes.sent("tasks", "root-out", f"Home: {LAST_ROOT}")
    homes.sent("tasks", "sc-open", f"Home: {SCOPE}", *RESULT)
    for slug in ("sc-done", "sc-gone"):
        homes.sent("tasks", slug, f"Home: {LAST_SCOPED}  ", *RESULT)
    homes.sent("tasks", "sc-plain", *RESULT)
    homes.sent("tasks", "sc-out", f"Home: {LAST_SCOPED}")
    homes.sent("tasks", "third-open", f"Home: {ANOTHER}", *RESULT)
    homes.sent("scouts", "root-ask", f"Home: {LAST_ROOT}", *REPORT)
    homes.sent("scouts", "plain-ask", *REPORT)
    homes.sent("scouts", "root-asking", f"Home: {LAST_ROOT}")
    homes.sent("scouts", "sc-ask", f"Home: {LAST_SCOPED}", *REPORT)
    homes.sent("scouts", "sc-named", f"Home: {SCOPE} (the second home)", *REPORT)
    homes.sent("scouts", "sc-asking", f"Home: {LAST_SCOPED}")


def read_before_the_note(homes, *paths, own=None):
    """Mark the briefs at `paths` as already shown to the home at an earlier start. The function
    writes them to the home's `read-seen`."""
    with ((own or homes.home_dir) / "read-seen").open("a") as seen:
        for path in paths:
            seen.write(f"{path}: ## Result\n")


ROOTS = [
    "tasks/root-open.md",
    "tasks/root-part.md",
    "tasks/root-plain.md",
    "tasks/sc-plain.md",
    "tasks/third-open.md",
    "scouts/plain-ask.md",
    "scouts/root-ask.md",
]


def test_each_home_is_given_only_its_own_results_to_read(homes):
    two_homes_work(homes)
    read_before_the_note(homes, "tasks/root-done.md", "tasks/root-gone.md")
    read_before_the_note(homes, "tasks/sc-gone.md", own=homes.scope_dir)
    (homes.home_dir / "standing.md").write_text("1. A standing rule.\n")
    homes.home_starts(ROOT)
    homes.home_starts(SCOPED, SCOPE)
    before = homes.state()
    assert homes.to_read(ROOT) == ["standing.md", "handoff.md", *ROOTS]
    assert homes.to_read(SCOPED) == [
        "standing.md",
        f"{SCOPE}/handoff.md",
        "tasks/sc-done.md",
        "tasks/sc-open.md",
        "scouts/sc-ask.md",
        "scouts/sc-named.md",
    ]
    assert homes.to_read(ROOT) == ["standing.md", "handoff.md", *ROOTS]
    homes.marks(ROOT, homes.start(ROOT)["to read"])
    assert homes.to_read(ROOT) == ["standing.md", "handoff.md"]
    with (homes.home_dir / "tasks" / "root-open.md").open("a") as brief:
        brief.write("\n## Review\nFinding: fixed, a thing\n")
    assert homes.to_read(ROOT) == ["standing.md", "handoff.md"]
    with (homes.home_dir / "tasks" / "root-open.md").open("a") as brief:
        brief.write("\n## Result, follow-up (today, a steer)\n")
    assert homes.start(ROOT)["to read"] == [
        "tasks/root-open.md: ## Result, follow-up (today, a steer)"
    ]
    assert homes.changed(before) == ["read-seen", "tasks/root-open.md"]


def test_a_root_home_with_no_thread_id_reads_what_is_the_roots(homes):
    two_homes_work(homes)
    read_before_the_note(homes, "tasks/root-done.md", "tasks/root-gone.md")
    assert homes.to_read("") == ["handoff.md", *ROOTS]


def test_the_first_start_with_no_mark_marks_every_result_there_is_and_shows_none(tmp_path):
    scene = Homes(tmp_path)
    for n in range(40):
        scene.sent("tasks", f"sc-old-{n:02}", f"Home: {SCOPE}", *RESULT)
    scene.sent("tasks", "root-old", *RESULT)
    scene.home_starts(SCOPED, SCOPE)
    seen = scene.scope_dir / "read-seen"
    assert scene.start(SCOPED)["to read"] == [
        f"no mark yet: 40 headings of this home's are marked read in {seen}, and none is shown"
    ]
    assert len(seen.read_text().splitlines()) == 40
    assert scene.to_read(SCOPED) == ["second/handoff.md"]
    scene.sent("tasks", "sc-new", f"Home: {SCOPE}", *RESULT)
    assert scene.to_read(SCOPED) == ["second/handoff.md", "tasks/sc-new.md"]


def test_a_heading_is_shown_until_it_is_marked_and_a_start_cut_before_shows_it_again(homes):
    homes.home_starts(SCOPED, SCOPE)
    (homes.scope_dir / "read-seen").write_text("")
    homes.sent("tasks", "sc-new", f"Home: {SCOPE}", *RESULT)
    shown = homes.start(SCOPED)["to read"]
    assert shown == ["tasks/sc-new.md: ## Result"]
    assert homes.start(SCOPED)["to read"] == shown
    ran = homes.marks(SCOPED, [*shown, "... and 3 more: not a heading"])
    assert ran.stdout == f"marked read: 1 headings in {homes.scope_dir}/read-seen\n"
    homes.marks(SCOPED, shown)
    assert (homes.scope_dir / "read-seen").read_text() == f"{shown[0]}\n"
    assert homes.start(SCOPED)["to read"] == []


@pytest.mark.parametrize("code", [0, 1])
def test_a_start_reads_the_plan_as_jbus_counts_it_and_whole_only_where_jbus_gives_none(
    homes, monkeypatch, code
):
    """The block of step 4 runs the real verb with its words: `plan`, and `--scope` for a scope."""
    stub = homes.user / "bin"
    stub.mkdir()
    (stub / "jbus").write_text(f'#!/bin/sh\necho "jbus $*"\nexit {code}\n')
    (stub / "jbus").chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ['PATH']}")
    homes.home_starts(ROOT)
    homes.home_starts(SCOPED, SCOPE)
    for thread, said, mine in (
        (ROOT, "jbus plan", homes.home_dir),
        (SCOPED, f"jbus plan --scope {SCOPE}", homes.scope_dir),
    ):
        whole = [said] if code == 0 else [f"no jbus plan: read {mine}/plan.md whole"]
        assert homes.start(thread)["plan"] == whole


def test_a_block_run_without_the_block_it_is_run_after_says_so_and_does_nothing(homes):
    homes.home_starts(ROOT)
    before = homes.state()
    guarded = [text for text in blocks("home") if "SEP:?" in text or "SEP=" in text]
    assert len(guarded) == 8
    for text in guarded:
        ran = subprocess.run(
            ["sh", "-c", f"{paths('home')}\n{text}"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(homes.user)},
            cwd=homes.main,
        )
        assert ran.returncode != 0
        assert re.search(r"(M|SEP): run the block that .* first$", ran.stderr.strip())
        assert ran.stdout == ""
    assert homes.changed(before) == []


@pytest.mark.parametrize("answers", [True, False])
def test_a_direct_launch_adds_the_briefs_row_only_where_jbus_has_a_plan_for_this_repo(
    homes, monkeypatch, answers
):
    """`jbus queue add` with no project takes the one project in the config, whatever the
    repo."""
    stub = homes.user / "bin"
    stub.mkdir()
    called = homes.user / "called"
    code = 0 if answers else 1
    (stub / "jbus").write_text(
        f'#!/bin/sh\nif [ "$1" = plan ]; then exit {code}; fi\n'
        f'echo "$*: $(cat)" >> "{called}"\necho "the table"\n'
    )
    (stub / "jbus").chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ['PATH']}")
    homes.home_starts(ROOT)
    homes.sent("tasks", "part-1")
    filled = {"<slug>": "part-1", "<n>": "3", "<entry>": "epic"}
    found = block("home", "no row: jbus has no plan")
    for mark, text in filled.items():
        found = found.replace(mark, text)
    ran = homes.run("home", found, homes.main, ROOT)
    if answers:
        assert ran.stdout == "added: the row part-1, of the entry epic\n"
        assert called.read_text().startswith(
            "queue add part-1 --priority 3 --entry epic: # part-1: a title\n"
        )
    else:
        assert ran.stdout == (
            "no row: jbus has no plan for this repo, so nothing is added to its queue\n"
        )
        assert not called.exists()
