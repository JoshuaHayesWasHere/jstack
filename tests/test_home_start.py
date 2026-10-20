"""`hooks/home-start.sh` in every repo: where it speaks, where it stays silent, and that the
home skill's first step and the nohome skill agree with it. Every test runs the hook, and the
blocks are lifted from the skill that gives them."""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from skill_blocks import skill_blocks as blocks
from test_jbus_kitchen import complete

REPO = Path(__file__).parent.parent
HOOK = REPO / "hooks" / "home-start.sh"
NAME = "demo"

T3 = ("T3_CODE_MCP_AUTHORIZATION", "T3_MCP_BEARER_TOKEN")
MARK = "$first"
FIRST, USUAL, *REST = (REPO / "templates" / "hook-message.md").read_text().splitlines(keepends=True)


def filled(text, **values):
    """A template's text with its variables filled in, each once, as the hook fills them."""
    return re.sub(r"\$(repo|home_dir|skills)", lambda found: values[found.group(1)], text)


def block(skill, holding):
    (found,) = [text for text in blocks(skill) if holding in text]
    return found


def paths(skill):
    """The block at the top of the skill, which sets `$H`."""
    (found,) = [text for text in blocks(skill) if re.search(r"^H=", text, re.M)]
    return found


def git(cwd, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", *identity, *args], cwd=cwd, check=True, capture_output=True)


class Scene:
    """A user's home directory with the skills, and a repo that never had a home."""

    def __init__(self, tmp_path, name=NAME):
        self.user = tmp_path / "user"
        (self.user / ".claude").mkdir(parents=True)
        (self.user / ".claude" / "skills").symlink_to(REPO / "skills")
        self.home_dir = self.user / ".local" / "state" / "home" / name
        self.main = tmp_path / "code" / name
        self.main.mkdir(parents=True)
        git(self.main, "init", "-q")

    def start(self, cwd=None, *, source="startup", t3=T3[0], **more):
        """Run the session-start hook as the harness does for a thread opened in `cwd`. `t3`
        is the variable T3 Code sets for the thread, or None outside T3 Code."""
        env = {key: value for key, value in os.environ.items() if key not in T3}
        env["HOME"] = str(self.user)
        if t3:
            env[t3] = "x"
        stdin = json.dumps({"source": source, "cwd": str(cwd or self.main), **more})
        done = subprocess.run(
            ["sh", str(HOOK)], input=stdin.encode(), capture_output=True, env=env, check=True
        )
        return done.stdout.decode()

    def run(self, skill, text):
        return subprocess.run(
            ["sh", "-c", f"{paths(skill)}\n{text}"],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.user)},
            cwd=self.main,
            check=True,
        ).stdout

    def said(self, first):
        line = FIRST.removeprefix(MARK) if first else USUAL
        return filled(
            line + "".join(REST),
            repo=self.main.name,
            home_dir=str(self.home_dir),
            skills=str(REPO / "skills"),
        )


@pytest.fixture
def scene(tmp_path):
    return Scene(tmp_path)


@pytest.mark.parametrize("name", [NAME, r"an odd & name | with \n $repo $home_dir"])
def test_a_repo_with_no_state_directory_gets_the_line_for_a_first_home(tmp_path, name):
    scene = Scene(tmp_path, name)
    assert scene.start() == scene.said(first=True)
    assert not scene.home_dir.exists()


def test_a_codex_thread_in_t3_code_gets_the_line(scene):
    said = scene.start(t3="T3_MCP_BEARER_TOKEN", hook_event_name="SessionStart")
    assert said == scene.said(first=True)
    assert scene.start(t3=None, hook_event_name="SessionStart") == ""


def test_a_state_directory_no_home_has_started_in_is_still_a_first_home(scene):
    (scene.home_dir / "tasks").mkdir(parents=True)
    (scene.home_dir / "notes.md").write_text("- Check command: make check\n")
    assert scene.start() == scene.said(first=True)


def test_the_template_marks_the_line_for_a_first_home_and_no_other(scene):
    assert FIRST.startswith(MARK)
    assert MARK not in FIRST.removeprefix(MARK) + USUAL + "".join(REST)
    assert scene.said(first=True) != scene.said(first=False)
    assert MARK not in scene.start()


def test_a_repo_with_a_home_gets_the_line_it_got(scene):
    scene.home_dir.mkdir(parents=True)
    (scene.home_dir / "plan.md").write_text("")
    assert scene.start() == scene.said(first=False)


def first_step(typed=""):
    """Step 1 of the home skill's start, with what was typed after `/home` filled in."""
    found = block("home", "first home")
    assert "<the text after /home>" in found
    return found.replace("<the text after /home>", typed)


ROOT = f"root\ntitle: home: {NAME}\n"


def test_the_home_skills_first_step_makes_the_home_the_hook_said_it_would(scene):
    assert scene.start() == scene.said(first=True)
    assert scene.run("home", first_step()) == f"{ROOT}first home: made {scene.home_dir}\n"
    assert sorted(path.name for path in scene.home_dir.iterdir()) == ["notes.md", "plan.md"]
    assert scene.start() == scene.said(first=False)
    assert scene.run("home", first_step()) == ROOT


def test_the_home_skills_first_step_keeps_the_notes_that_are_there(scene):
    scene.home_dir.mkdir(parents=True)
    (scene.home_dir / "notes.md").write_text("- Check command: make check\n")
    assert scene.run("home", first_step()) == f"{ROOT}first home: made {scene.home_dir}\n"
    assert (scene.home_dir / "notes.md").read_text() == "- Check command: make check\n"
    assert (scene.home_dir / "plan.md").read_text() == ""


def a_worktree(scene, tmp_path):
    git(scene.main, "commit", "-q", "--allow-empty", "-m", "start")
    git(scene.main, "worktree", "add", "-q", str(tmp_path / "trees" / "a-task"))
    return {"cwd": tmp_path / "trees" / "a-task"}


def the_off_file(scene, tmp_path):
    scene.run("nohome", block("nohome", "touch"))
    return {}


def the_off_file_in_a_repo_with_a_home(scene, tmp_path):
    scene.home_dir.mkdir(parents=True)
    (scene.home_dir / "plan.md").write_text("")
    scene.run("nohome", block("nohome", "touch"))
    return {}


def not_a_repo(scene, tmp_path):
    (tmp_path / "plain").mkdir()
    return {"cwd": tmp_path / "plain"}


def the_scratch_folder(scene, tmp_path):
    scratch = scene.user / ".t3" / "scratch"
    (scratch / "2026-10-10-a-thread").mkdir(parents=True)
    git(scratch, "init", "-q")
    return {"cwd": scratch / "2026-10-10-a-thread"}


def a_repo_made_in_the_scratch_folder(scene, tmp_path):
    made = scene.user / ".t3" / "scratch" / "2026-10-10-a-thread"
    made.mkdir(parents=True)
    git(made, "init", "-q")
    return {"cwd": made}


def a_submodule(scene, tmp_path):
    other = tmp_path / "code" / "lib"
    other.mkdir()
    git(other, "init", "-q")
    git(other, "commit", "-q", "--allow-empty", "-m", "start")
    allowed = ["-c", "protocol.file.allow=always"]
    git(scene.main, *allowed, "submodule", "add", "-q", str(other), "lib")
    return {"cwd": scene.main / "lib"}


def a_bare_repo(scene, tmp_path):
    git(tmp_path, "init", "-q", "--bare", str(tmp_path / "code" / "bare.git"))
    return {"cwd": tmp_path / "code" / "bare.git"}


def outside_t3(scene, tmp_path):
    return {"t3": False}


def a_resume(scene, tmp_path):
    return {"source": "resume"}


@pytest.mark.parametrize(
    "case",
    [
        a_worktree,
        the_off_file,
        the_off_file_in_a_repo_with_a_home,
        not_a_repo,
        the_scratch_folder,
        a_repo_made_in_the_scratch_folder,
        a_submodule,
        a_bare_repo,
        outside_t3,
        a_resume,
    ],
    ids=lambda case: case.__name__,
)
def test_the_hook_stays_silent(case, scene, tmp_path):
    assert scene.start(**case(scene, tmp_path)) == ""


def test_nohome_switches_a_repo_off_and_on_before_any_home_has_started_there(scene):
    assert not scene.home_dir.exists()
    scene.run("nohome", block("nohome", "touch"))
    assert scene.start() == ""
    scene.run("nohome", block("nohome", "rm -f"))
    assert scene.start() == scene.said(first=True)
    scene.run("nohome", block("nohome", "touch"))
    scene.run("nohome", block("nohome", "touch"))
    assert scene.start() == ""
    scene.run("nohome", block("nohome", "rm -f"))
    scene.run("nohome", block("nohome", "rm -f"))
    assert scene.start() == scene.said(first=True)


START = "## to read"
LONG = "it waits on a long reason that a pass wrote, " * 6


@pytest.fixture
def bus(tmp_path, monkeypatch):
    """A repo with jbus set up for it: the real command, a made-up queue, plan, questions and
    log, and the root home's note. The home skill's blocks run as the gates test runs them."""
    from test_gates import Home, whole

    made = Home(tmp_path, monkeypatch)
    made.whole = whole
    yield made
    made.kitchen.close()


def rows(bus, *made):
    """Rows of the queue, each `(slug, status, pr, why)`, added by the real verb, then given
    the columns a pass would have derived."""
    for slug, *_ in made:
        added = bus.kitchen.main("queue", "add", slug, "--priority", "1", stdin=complete(slug))
        assert added[0] == 0, added
    table = bus.kitchen.state / "queue.json"
    listed = {row["slug"]: row for row in json.loads(table.read_text())}
    for slug, status, pr, why in made:
        listed[slug].update(status=status, pr=pr, why=why)
    table.write_text(json.dumps(list(listed.values())))


def a_note(bus, *briefs):
    """The note the last home left. Each brief given was shown to a home at its start."""
    for slug in briefs:
        bus.kitchen.brief(slug, "\n## Result\nStatus: done\n")
        with (bus.dir / "read-seen").open("a") as seen:
            seen.write(f"tasks/{slug}.md: ## Result\n")
    (bus.dir / "handoff.md").write_text("Next: the queue\nWas home: mcp:the-home-before\n")


def parts(printed):
    """What the start block printed, by its parts: the lines before the first under `""`."""
    found, heading = {"": []}, ""
    for line in printed.splitlines():
        if line.startswith("## "):
            heading = line.removeprefix("## ")
            found[heading] = []
        else:
            found[heading].append(line)
    return found


def test_a_start_prints_this_homes_part_of_the_bus_and_what_came_in_since_the_note(bus):
    (bus.dir / "plan.md").write_text("# plan\n\n## alpha: the first task\nStage: planned\n")
    (bus.dir / "standing.md").write_text("1. A standing rule.\n")
    rows(bus, ("alpha", "pr", "#7", "wait: a | b, no review yet"), ("gone", "merged", "#5", ""))
    (bus.dir / "handoff.next.md").write_text("Next: cut off before it was put in place\n")
    bus.kitchen.brief("speedy", "Home: speed\n\n## Result\nStatus: done\n")
    rows(bus, ("speedy", "running", "", ""))
    assert bus.kitchen.main("gate", "alpha", stdin=bus.whole())[0] == 0
    a_note(bus, "read-before")
    bus.kitchen.brief("alpha", "\n## Result\nStatus: done\n\n## Result, follow-up (today, why)\n")
    (bus.dir / "merge.log").write_text(
        '2026-10-13 16:57 merged 5 gone abc "an old one", revert: gh pr revert x\n'
        '2026-10-13 17:20 merged 7 alpha def "the first task", revert: gh pr revert y\n'
        '2026-10-13 17:21 merged 8 speedy fed "the scope\'s", revert: gh pr revert z\n'
    )
    (bus.dir / "merge-seen").write_text("1\n")

    printed = bus.home(START)
    assert len(printed) < 6000
    said = parts(printed)
    names = ("standing.md", "handoff.md", "handoff.next.md")
    assert said[""] == [f"read whole: {bus.shown_dir}/{name}" for name in names]
    assert said["plan"] == ["alpha | the first task | 0 of 1 merged, #7 at pr"]
    assert said["queue"] == [
        "alpha | pr | #7 | wait: a | b, no review yet",
        "1 finished row not shown: jbus queue show --all",
    ]
    assert said["questions"] == ["question 1, from alpha: tea or coffee? (default: tea)"]
    assert said["merged"] == [
        '2026-10-13 17:20 merged 7 alpha def "the first task", revert: gh pr revert y'
    ]
    assert said["to read"] == ["tasks/alpha.md: ## Result, follow-up (today, why)"]
    assert (bus.dir / "merge-seen").read_text() == "1\n"
    assert parts(bus.home(START))["to read"] == said["to read"]


def test_a_start_prints_the_new_noticed_lines_of_this_home_by_their_keys(bus):
    from jbus import noticed
    from test_gates import AT, SCOPED

    assert parts(bus.home(START))["noticed"] == ["none is new"]
    said = "the view shows a finished row as stuck."
    for slug in ("speedy", "none-left"):
        bus.kitchen.brief(slug, "Home: speed\n")
    bus.kitchen.poll()
    bus.kitchen.brief("alpha", f"Thread: mcp:crew-alpha\n\n## Result\nNoticed: {said}\n")
    bus.kitchen.brief("speedy", "Home: speed\n\n## Result\nNoticed: the scope's own line\n")
    bus.kitchen.brief("none-left", "Home: speed\n\n## Result\nNoticed: the scope's other line\n")
    bus.kitchen.poll()
    key = noticed.key("alpha", said)
    assert parts(bus.home(START))["noticed"] == [f"{key} alpha, Result, new: {said}"]
    dropped = ("noticed", "drop", key, "--why", "a one-off", "--by", "home", "--at", AT)
    assert bus.kitchen.main(*dropped)[0] == 0
    assert parts(bus.home(START))["noticed"] == []
    scoped = parts(bus.home(START, thread=SCOPED))["noticed"]
    assert [line.rsplit(": ", 1)[1] for line in scoped] == [
        "the scope's own line",
        "the scope's other line",
    ]


def test_however_much_is_there_a_start_prints_under_6000_characters(bus):
    entries = "".join(
        f"## entry-{n}: {'an entry with a long line, ' * 4}\nStage: planned\n\n" for n in range(30)
    )
    (bus.dir / "plan.md").write_text(f"# plan\n\n{entries}")
    rows(bus, *((f"row-{n:02}", "queued", "", LONG) for n in range(40)))
    for n in range(12):
        question = f"question {n}: {'a long question that goes on, ' * 6}?"
        assert bus.kitchen.main("gate", "alpha", stdin=bus.whole(question))[0] == 0
    a_note(bus)
    (bus.dir / "read-seen").write_text("")
    for n in range(30):
        bus.kitchen.brief(f"done-{n:02}", "\n## Result\nStatus: done\n")
    (bus.dir / "merge.log").write_text(
        "".join(
            f'2026-10-13 17:{n:02} merged {n} alpha abc "{LONG}", revert: gh pr revert x\n'
            for n in range(30)
        )
    )
    (bus.dir / "merge-seen").write_text("0\n")

    printed = bus.home(START)
    assert len(printed) < 6000
    said = parts(printed)
    for part, command in (
        ("plan", "jbus plan"),
        ("queue", "jbus --project demo queue show"),
        ("questions", 'the block of "Show the open ones"'),
        ("merged", f"{bus.shown_dir}/merge.log"),
    ):
        assert re.fullmatch(rf"\.\.\. and \d+ more: {re.escape(command)}", said[part][-1]), part
    assert said["to read"][-1] == "... and 22 more: mark these read, then run this block again"
    shown = printed.replace(str(bus.shown_dir), "$H")
    assert [line for line in shown.splitlines() if len(line) > 150] == []


def test_a_start_with_no_jbus_reads_the_plan_whole_and_says_why_it_has_no_queue(scene):
    scene.home_dir.mkdir(parents=True)
    (scene.home_dir / "plan.md").write_text("# plan\n")
    reads = block("home", "OPEN=").replace("command -v jbus", "false")
    start = block("home", START).replace("command -v jbus", "false")
    said = parts(scene.run("home", f'M="$H"\nwhose() {{ echo "$H"; }}\n{reads}\n{start}'))
    assert said["plan"] == [f"no jbus plan: read {scene.home_dir}/plan.md whole"]
    no_jbus = ["no jbus: jbus is not installed here, so it holds no question"]
    assert said["queue"] == said["questions"] == no_jbus
    assert said["merged"] == []
    (line,) = said["to read"]
    assert line.startswith("no mark yet: 0 headings")


def test_a_start_reads_the_repos_context_pack_index_after_the_rules_and_the_note(bus):
    (bus.dir / "standing.md").write_text("1. A standing rule.\n")
    (bus.dir / "handoff.md").write_text("Next: the queue\n")
    before = [f"read whole: {bus.shown_dir}/{name}" for name in ("standing.md", "handoff.md")]
    assert parts(bus.home(START))[""] == before
    index = bus.main / "docs" / "context" / "INDEX.md"
    index.parent.mkdir(parents=True)
    index.write_text("`retries.md`: How many retries? (checked at `3f9c2ab`)\n")
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=bus.main,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert parts(bus.home(START))[""] == [*before, f"read whole: {top}/docs/context/INDEX.md"]
    assert parts(bus.home(START, cwd=bus.worktree))[""] == before
