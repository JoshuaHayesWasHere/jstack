import fcntl
import json
import os
import re
import shutil
import subprocess
import textwrap
import threading
import time
from pathlib import Path

import pytest

import crew_helpers as crew
import jsettings
import test_home_merge as merge
from jmerge import ready
from test_home_thread import NAMED, as_read
from test_room import BIN, IDLE, machine, says, uv
from testing.layouts import assembled
from testing.paths import REPO

SKILL = REPO / "features" / "pr-review" / "SKILL.md"
REVIEW = REPO / "features" / "pr-review" / "templates" / "review.md"
INTERROGATE = REPO / "features" / "skill-library" / "skills" / "interrogate"

BRIEF = """\
# a-task: a title
Task: "make it so", and a `Review: none` said inside the task counts for nothing.
Done when:
- it's done, with $HOME and "quotes" left as they are
Decisions:
- one
Pull request: open one when done
Thread: mcp:1
"""
URL = "https://github.com/someone/repo/pull/7"

GH = """\
#!/bin/sh
grep -qsx "$2" "$STUB/down" && exit 1
case "$1 $2" in
    "pr diff") cat "$STUB/diff" ;;
    "pr view") cat "$STUB/view.json" ;;
    "pr list") cat "$STUB/list.json" ;;
    *) exit 64 ;;
esac
"""

GIT = """\
#!/bin/sh
if [ "$1" = diff ] && [ "$3" = BASE ] && [ "$4" = HEAD-UNDER-REVIEW ]; then
    case $2 in
    --no-color) grep -qsx diff "$STUB/down" && exit 128; cat "$STUB/diff" ;;
    --name-only) grep -qsx view "$STUB/down" && exit 128; jq -r '.files[].path' "$STUB/view.json" ;;
    *) exit 64 ;;
    esac
    exit
fi
exec {git} "$@"
"""
"""A `git` that gives the diff of the change under review, from the base and the head the
reviewer's Start kept, as the canned diff and files `gh` gives, and runs every other call."""
PLACES = {"'<the base>'": "BASE", "'<the head>'": "HEAD-UNDER-REVIEW"}

DIFF = """\
diff --git a/src/a.py b/src/a.py
index 1111111..2222222 100644
--- a/src/a.py
+++ b/src/a.py
@@ -1,4 +1,5 @@
 one
-two
+TWO
+two and a half
 three
 four
@@ -10,3 +11,2 @@
 ten
--- a comment that was removed
 twelve
diff --git a/new.txt b/new.txt
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/new.txt
@@ -0,0 +1,2 @@
+first
+second
diff --git a/old.txt b/old.txt
deleted file mode 100644
index 4444444..0000000
--- a/old.txt
+++ /dev/null
@@ -1 +0,0 @@
-gone
diff --git a/was.md b/now.md
similarity index 100%
rename from was.md
rename to now.md
diff --git a/logo.png b/logo.png
new file mode 100644
index 0000000..5555555
Binary files /dev/null and b/logo.png differ
"""

BRIEFS = {
    "no line": BRIEF,
    "review": BRIEF + "Review: review\n",
    "a word from before": BRIEF + "Review: review+test\n",
    "none": BRIEF + "Review: none\n",
    "only quoted": BRIEF.replace("- one\n", "- one, with `Review: none` quoted\n"),
    "said again in a result": BRIEF + "Review: review\n\n## Result\nReview: none\n",
}
FENCED = re.compile(r"^[ \t]*```(\w+)\n(.*?)^[ \t]*```$", re.M | re.S)


def section(heading):
    """The text under `heading`, as an agent reads the skill. Under a stub's heading the agent
    finds the stub's trigger line, and then the side file, which opens with the same heading."""
    after = as_read(SKILL).split(f"{heading}\n", 1)[1]
    under = re.split(r"^#{2,3} ", after, maxsplit=1, flags=re.M)[0]
    if NAMED.search(under):
        after = after.split(f"{heading}\n", 1)[1]
        under = re.split(r"^#{2,3} ", after, maxsplit=1, flags=re.M)[0]
    return under


def block(heading, about="", kind="sh"):
    found = [body for fence, body in FENCED.findall(section(heading)) if fence == kind]
    return textwrap.dedent(next(body for body in found if about in body))


@pytest.fixture
def reviewer(tmp_path):
    """Run the skill's blocks as a reviewer does, in a worktree, with a stub `gh`."""
    stub, home = tmp_path / "stub", tmp_path / "home"
    home.mkdir()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tmp").mkdir()
    brief = tmp_path / "tasks" / "a-task.md"
    brief.write_text(BRIEF)
    stub.mkdir()
    machine(tmp_path, **IDLE)
    uv(stub)
    (stub / "gh").write_text(GH)
    (stub / "gh").chmod(0o755)
    (stub / "git").write_text(GIT.format(git=shutil.which("git")))
    (stub / "git").chmod(0o755)
    (stub / "diff").write_text(DIFF)
    env = {
        **os.environ,
        "HOME": str(home),
        "JBUS_HOME_DIR": str(home / ".local" / "state" / "home"),
        "PATH": f"{stub}:{BIN}:{os.environ['PATH']}",
        "STUB": str(stub),
        "H": str(tmp_path),
        "T": str(assembled() / "templates"),
        "PROC": str(tmp_path / "proc"),
        "TMPFS": str(stub / "tmp"),
        "TMPDIR": str(tmp_path / "tmp"),
    }
    work = tmp_path / "worktrees" / "a-task"
    subprocess.run(["git", "init", "-q", work], check=True)

    def start(heading="### The review", about="", findings=(), fill=None, then=None, **more):
        """Run one block. The test calls `then` once the block has printed its first line, while
        the block still runs."""
        script = block(heading, about).replace("<slug>", "a-task").replace("<url>", URL)
        script = script.replace("<the findings, one to a line>", "\n".join(findings))
        for words, value in PLACES.items():
            script = script.replace(words, value)
        for words, value in (fill or {}).items():
            assert words in script
            script = script.replace(words, value)
        ran = subprocess.Popen(
            ["sh", "-c", script],
            env={**env, **more},
            cwd=work,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        first = ran.stdout.readline() if then else ""
        if then:
            then()
        rest, _ = ran.communicate(timeout=20)
        return (first + rest).splitlines(), ran.returncode

    def output(heading, about="", findings=(), **more):
        printed, code = start(heading, about, findings, **more)
        assert code == 0
        return printed

    def built():
        """The directories the first block of the review has made so far."""
        return sorted(path for path in (tmp_path / "tmp").iterdir() if path.is_dir())

    def prompt(**more):
        """The prompt file the first block of the review writes for the two reviewers."""
        (path,), code = start(**more)
        assert code == 0
        assert Path(path).parent in built()
        return Path(path)

    def pull_request(number, *files, title="a title", branch=None):
        listed = {"number": number, "title": title, "files": [{"path": path} for path in files]}
        return {**listed, "headRefName": branch or f"branch-{number}"}

    def gh(diff=DIFF, files=(), others=()):
        here = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"], cwd=work, capture_output=True, text=True
        ).stdout.strip()
        mine = pull_request(7, *files, branch=here)
        (stub / "diff").write_text(diff)
        (stub / "view.json").write_text(json.dumps(mine))
        (stub / "list.json").write_text(json.dumps([mine, *others]))

    start.brief, start.state, start.work, start.stub = brief, tmp_path, work, stub
    start.output, start.gh, start.pull_request = output, gh, pull_request
    start.built, start.prompt = built, prompt
    start.machine = lambda **readings: machine(tmp_path, **{**IDLE, **readings})
    return start


@pytest.mark.parametrize(
    ("brief", "value"),
    [
        ("no line", ""),
        ("review", "review"),
        ("a word from before", "review+test"),
        ("none", "none"),
        ("only quoted", ""),
        ("said again in a result", "review"),
    ],
)
def test_the_review_line_is_read_only_where_it_starts_a_line(reviewer, brief, value):
    reviewer.brief.write_text(BRIEFS[brief])
    assert reviewer.output("## The brief's `Review:` line") == ([value] if value else [])


ASKED = "<the message this thread was started with, whole>"
SECTION = "\n## Review\nVerdict: findings\nHead: " + "a" * 40 + "\n"
NO_SECTION = "Review: review\nReviewer: mcp:thread-9\nTask: a `## Review` said inside a line\n"
RERUN = REPO / "features" / "crew" / "templates" / "rerun.md"


def started(reviewer, asked, brief=""):
    """What the reviewer's step 1 of Start prints for a message and a brief, and how it
    ended."""
    reviewer.brief.write_text(BRIEF + brief)
    return reviewer("### Start", "case $asked", fill={ASKED: asked})


@pytest.mark.parametrize("brief", ["", NO_SECTION, SECTION])
def test_a_reviewer_sent_again_goes_whether_or_not_the_brief_has_a_review(reviewer, brief):
    """Whoever launches a re-run sends it as `again`, and the reviewer goes either way.
    On a brief with a `## Review` section the re-run is a second pass. On a brief with no such
    section it is the review the brief is still owed."""
    said, code = started(reviewer, "/pr-review run a-task again", brief)
    assert code == 0 and said[0].startswith("go: "), said


@pytest.mark.parametrize("brief", ["", NO_SECTION])
def test_a_plain_message_goes_where_the_brief_has_no_review_section(reviewer, brief):
    """The reviewer of pull request 69 refused the plain line on a brief that had no `## Review`
    section. It had read the brief's `Review:` and `Reviewer:` lines as a section."""
    said, code = started(reviewer, "/pr-review run a-task", brief)
    assert code == 0 and said[0].startswith("go: "), said


def test_a_plain_message_under_a_review_stops_and_names_the_line_it_would_accept(reviewer):
    said, code = started(reviewer, "/pr-review run a-task", SECTION)
    assert code == 0 and said[0].startswith("stop: "), said
    (accepted,) = [line for line in said if line.startswith("the line I accept: ")]
    line = accepted.removeprefix("the line I accept: ")
    assert line == "/pr-review run a-task again"
    assert started(reviewer, line, SECTION)[0][0].startswith("go: ")
    assert RERUN.read_text().strip().replace("{slug}", "a-task") in "\n".join(said)


def test_a_scoped_message_goes_under_a_review(reviewer):
    asked = "/pr-review run a-task scoped aaa..bbb ccc..ddd"
    assert started(reviewer, asked, SECTION)[0][0].startswith("go: ")


DUAL = "review: codex gpt-6-sol effort=xhigh\nreview: cursor grok-4.7 effort=xhigh fast=off\n"
CODEX, CURSOR = "By: codex gpt-6-sol xhigh", "By: cursor grok-4.7 xhigh"


CONFIG = "<what t3_thread_configure printed, or nothing where this session has no such tool>"


def by(reviewer, asked, roles=None, thread=None):
    """The `By:` line that Start's first block prints for a message. The block takes the line from
    the thread's own configuration when the thread gives one. Otherwise it takes the line from a
    role map, and a test may give the block neither source."""
    config = reviewer.state / "config"
    if roles is not None:
        (config / "jstack").mkdir(parents=True, exist_ok=True)
        (config / "jstack" / "roles").write_text(roles)
    fill = {ASKED: asked}
    if thread is not None:
        fill[CONFIG] = json.dumps(thread)
    (said,), code = reviewer("### Start", "jroles review", fill=fill, XDG_CONFIG_HOME=str(config))
    assert code == 0
    return said


def test_each_reviewer_names_the_line_of_the_review_list_it_was_launched_on(reviewer):
    assert by(reviewer, "/pr-review run a-task 1", DUAL) == f"{CODEX} #1"
    assert by(reviewer, "/pr-review run a-task 2", DUAL) == f"{CURSOR} #2"
    assert by(reviewer, "/pr-review run a-task", DUAL) == f"{CODEX} #1"
    assert by(reviewer, "/pr-review run a-task scoped aaa..bbb ccc..ddd", DUAL) == f"{CODEX} #1"
    assert by(reviewer, "/pr-review run a-task 2", "review: claudeAgent claude-opus-5-5\n") == (
        "By: inherit #2"
    )
    assert by(reviewer, "/pr-review run a-task", "review: inherit\n") == "By: inherit #1"


SONNET = "review: claudeAgent claude-sonnet-5-5 effort=high\n" * 2


def test_two_reviewers_of_one_model_write_two_by_lines_told_apart_by_their_number(reviewer):
    """The user's word of 2026-10-20 asks for two Sonnet 5.5 reviewers on High, the same model
    twice."""
    one = {"modelSelection": {"instanceId": "claudeAgent", "model": "claude-sonnet-5-5"}}
    one["modelSelection"]["options"] = [{"id": "effort", "value": "high"}]
    first = by(reviewer, "/pr-review run a-task 1", SONNET, one)
    second = by(reviewer, "/pr-review run a-task 2", SONNET, one)
    assert (first, second) == (
        "By: claudeAgent claude-sonnet-5-5 high #1",
        "By: claudeAgent claude-sonnet-5-5 high #2",
    )
    assert by(reviewer, "/pr-review run a-task 2", SONNET) == second
    section = SECTION.replace("## Review\n", f"## Review\n{first}\n")
    said, code = numbered(reviewer, "/pr-review run a-task 2", second, section)
    assert code == 0 and said[0].startswith("go: "), said
    said, code = numbered(reviewer, "/pr-review run a-task 1", first, section)
    assert code == 0 and said[0].startswith("stop: "), said


def test_the_by_line_is_read_from_the_thread_itself_whatever_the_map_says_now(reviewer):
    """A capped pool, a refused map, or a map edited after the launch changes nothing,
    because the thread's own configuration names its provider, model and effort."""
    cursor = {
        "threadId": "mcp:2",
        "modelSelection": {
            "instanceId": "cursor",
            "model": "grok-4.7",
            "options": [
                {"id": "reasoning_effort", "value": "xhigh"},
                {"id": "fastMode", "value": False},
            ],
        },
    }
    assert by(reviewer, "/pr-review run a-task 2", "review: inherit\n", cursor) == f"{CURSOR} #2"
    codex = {
        "modelSelection": {
            "provider": "codex",
            "instanceId": "codex",
            "model": "gpt-6-sol",
            "options": [{"id": "reasoningEffort", "value": "xhigh"}],
        }
    }
    assert by(reviewer, "/pr-review run a-task again", DUAL, codex) == f"{CODEX} #1"
    claude = {"modelSelection": {"instanceId": "claudeAgent", "model": "claude-opus-5-5"}}
    assert (
        by(reviewer, "/pr-review run a-task", None, claude) == "By: claudeAgent claude-opus-5-5 #1"
    )


def numbered(reviewer, asked, mine, brief):
    reviewer.brief.write_text(BRIEF + brief)
    return reviewer(
        "### Start",
        "case $asked",
        fill={ASKED: asked, "<the By: line the block above printed>": mine},
    )


def test_a_second_reviewer_writes_beside_the_first_and_never_twice_for_its_line(reviewer):
    first = SECTION.replace("## Review\n", f"## Review\n{CODEX}\n")
    said, code = numbered(reviewer, "/pr-review run a-task 2", CURSOR, first)
    assert code == 0 and said[0].startswith("go: "), said
    said, code = numbered(reviewer, "/pr-review run a-task 1", CODEX, first)
    assert code == 0 and said[0].startswith("stop: "), said
    assert "the line I accept: /pr-review run a-task again" in said
    said, code = numbered(reviewer, "/pr-review run a-task 1", CODEX, "")
    assert code == 0 and said[0].startswith("go: "), said
    said, code = numbered(reviewer, "/pr-review run a-task again", CODEX, first)
    assert code == 0 and said[0].startswith("go: "), said


def test_a_brief_that_asks_for_no_review_gets_none(reviewer):
    reviewer.brief.write_text(BRIEFS["none"])
    assert reviewer() == ([], 78)
    assert reviewer.built() == []
    assert reviewer.brief.read_text() == BRIEFS["none"]
    assert list(reviewer.state.glob("tasks/*")) == [reviewer.brief]


def test_each_value_the_brief_template_offers_is_one_the_review_knows(reviewer):
    (line,) = [
        line
        for line in (REPO / "features/jbriefs/templates/brief.md").read_text().splitlines()
        if line.startswith("Review:")
    ]
    ends = {}
    for value in line.removeprefix("Review:").split("|"):
        reviewer.brief.write_text(BRIEF + f"Review: {value.strip()}\n")
        ends[value.strip()] = reviewer()[1]
    assert ends == {"review": 0, "none": 78}


@pytest.mark.parametrize(
    ("brief", "says", "then"),
    [
        ("none", ["was none, now review: the user named it"], "review"),
        ("no line", [], ""),
        ("review", [], "review"),
        ("a word from before", [], "review+test"),
        ("only quoted", [], ""),
    ],
)
def test_a_brief_the_user_names_is_reviewed_whatever_its_line_said(reviewer, brief, says, then):
    reviewer.brief.write_text(BRIEFS[brief])
    assert reviewer.output("### A brief the user names") == says
    if not says:
        assert reviewer.brief.read_text() == BRIEFS[brief]
    assert reviewer.output("## The brief's `Review:` line") == ([then] if then else [])
    kept = [line for line in reviewer.brief.read_text().splitlines() if "Review: " not in line]
    assert kept == [line for line in BRIEFS[brief].splitlines() if "Review: " not in line]
    assert list(reviewer.state.glob("tasks/*")) == [reviewer.brief]
    assert reviewer.prompt().is_file()


def test_naming_a_brief_changes_only_its_own_review_line(reviewer):
    reviewer.brief.write_text(BRIEFS["none"] + "\n## Result\nReview: none\n")
    reviewer.output("### A brief the user names")
    assert [line for line in reviewer.brief.read_text().splitlines() if "Review:" in line] == [
        BRIEF.splitlines()[1],
        "Review: review (was none: the user asked for this review by name)",
        "Review: none",
    ]


def scope():
    """The scope rule as the skill's review block writes it, between the heredoc's two
    marks."""
    return block("### The review").split("<<'SCOPE'\n", 1)[1].split("\nSCOPE\n", 1)[0]


def intent(reviewer):
    """The intent the first block of the review wrote down for the two reviewers."""
    return (reviewer.prompt().parent / "intent").read_text()


def asked(text, question):
    after = text.split(f"\n{question}. ", 1)[1]
    return after.split(f"\n{question + 1}. ", 1)[0]


def test_the_two_questions_are_the_ones_the_interrogate_skill_reads_out_of_this_block(reviewer):
    """Step 3 of the interrogate skill finds questions 4 and 5 in this skill by the line each one
    starts on, and reads them out."""
    text = (INTERROGATE / "SKILL.md").read_text()
    (reads,) = [body for kind, body in FENCED.findall(text) if kind == "sh" and "asked=" in body]
    home = reviewer.state / "user"
    (home / ".claude" / "skills").mkdir(parents=True)
    (home / ".claude" / "skills" / "interrogate").symlink_to(assembled() / "skills" / "interrogate")
    read = subprocess.run(
        ["sh", "-c", reads], env={**os.environ, "HOME": str(home)}, capture_output=True, text=True
    )
    assert read.stdout == (reviewer.prompt().parent / "questions").read_text()
    assert read.stdout.startswith("4. Is it correct?")


@pytest.mark.parametrize("diff", ["", None])
def test_a_diff_that_cannot_be_read_gives_the_reviewers_nothing_to_review(reviewer, diff):
    if diff is None:
        (reviewer.stub / "down").write_text("diff\n")
    else:
        reviewer.gh(diff=diff)
    assert reviewer() == ([], 1)


@pytest.mark.parametrize(
    ("was", "now"),
    [
        ("{RUBRIC_CONTENTS}\n", "{RUBRIC_CONTENTS}\n\n{SOMETHING_NEW}\n"),
        ("{RUBRIC_CONTENTS}\n", ""),
        ("> {INTENT}\n", "> {THE_INTENT}\n"),
    ],
)
def test_a_template_this_block_cannot_fill_whole_is_not_sent_half_filled(reviewer, was, now):
    root = reviewer.state / "root"
    shutil.copytree(INTERROGATE / "references", root / "skills" / "interrogate" / "references")
    template = root / "skills" / "interrogate" / "references" / "reviewer-prompt.md"
    (root / "templates").mkdir()
    assert reviewer(T=str(root / "templates"))[1] == 0
    assert was in template.read_text()
    template.write_text(template.read_text().replace(was, now))
    assert reviewer(T=str(root / "templates")) == ([], 1)


SOON = {"--wait 540": "--wait 0.3 --every 0.1"}
OFTEN = {"--wait 540": "--wait 15 --every 0.1"}


def room_calls(tmp_path, **readings):
    """What the home's launch check and the review's run block each print on the machine
    that `readings` describe."""
    env = {**machine(tmp_path, **{**IDLE, **readings}), "T": str(assembled() / "templates")}
    uv(tmp_path / "stub")
    said = []
    for skill, more in (("home", ""), ("pr-review", '\nprintf "%s\\n" "$said"')):
        text = as_read(assembled() / "skills" / skill / "SKILL.md")
        (call,) = [line for line in text.splitlines() if "jgauge room" in line and "`" not in line]
        assert call.count('uv run --project "$T/../source" jgauge room') == 1
        said.append(says(env, call.replace("--wait 540", "--wait 0") + more))
    return said


def test_a_load_that_holds_a_launch_holds_no_review(tmp_path):
    assert room_calls(tmp_path, load="24.00") == [
        "wait: load 24.00 is at or over 200% of 12 cores",
        "go",
    ]


def test_cpu_pressure_that_holds_a_launch_holds_no_review(tmp_path):
    assert room_calls(tmp_path, cpu="90.00") == [
        "wait: CPU pressure 90.00 is at or over 40",
        "go",
    ]


def test_a_review_with_no_room_waits_inside_its_call_and_goes_on_when_the_machine_has_some(
    reviewer,
):
    """The reviewer sends the block once while the machine is busy, and the machine has room half a
    second later. The same call goes on to the prompt, so the reviewer needs no wait of its own."""
    reviewer.machine(pressure="25.00")
    room = threading.Timer(0.5, reviewer.machine)
    room.start()
    try:
        printed, code = reviewer(fill=OFTEN)
    finally:
        room.cancel()
        room.join()
    assert (code, len(printed)) == (0, 1), printed
    assert Path(printed[0]).is_file()


def test_a_room_check_that_cannot_run_is_a_wait_that_ends_at_once(reviewer):
    (reviewer.stub / "jgauge").write_text("#!/bin/sh\nexit 127\n")
    (reviewer.stub / "jgauge").chmod(0o755)
    assert reviewer() == (["wait: jgauge room did not run"], 75)
    assert reviewer.built() == []


KEPT = "c" * 40
GAVE_UP = (
    "\n## Review\nVerdict: not run\n"
    "Why: the run block was sent six times and never went on, and its last answer was "
    '"{why}"\n'
    f"Head: {KEPT}   Unchanged by the review: not checked, no review ran\n"
    "Sent to: not sent, no review ran\n"
)


def gives_up(reviewer, why):
    """Run the block of the "No room" section, filled in as a reviewer fills it."""
    filled = {
        "<the head kept at the start>": KEPT,
        "<the last line the block of step 1 printed>": why,
    }
    return reviewer("### No room", fill=filled)


def test_a_section_that_was_not_run_is_replaced_by_the_same_reviewers_clean_run_at_its_head(
    reviewer,
):
    """The section that "No room" writes has the reviewer's `By:` line, so a clean re-run by
    the same reviewer at the same head becomes the review. When two reviewers review the pull
    request, the other reviewer's section does not replace the one "No room" wrote."""
    reviewer.brief.write_text(BRIEF + "Reviewer: mcp:9\n")
    filled = {
        "<the head kept at the start>": KEPT,
        "<the last line the block of step 1 printed>": "wait: jgauge room did not run",
        "<the By: line Start printed>": "By: claudeAgent claude-opus-5-5",
    }
    assert reviewer("### No room", fill=filled)[1] == 0
    gave_up = reviewer.brief.read_text()
    assert "## Review\nBy: claudeAgent claude-opus-5-5\nVerdict: not run\n" in gave_up
    assert ready.short_of(gave_up, KEPT) == ready.NO_VERDICT
    clean = f"\n## Review\nBy: claudeAgent claude-opus-5-5\nVerdict: clean\nHead: {KEPT}\n"
    clean += "Meets the brief: yes, 1 of 1\n"
    assert ready.short_of(gave_up + clean, KEPT) == ""
    other = clean.replace("claudeAgent claude-opus-5-5", "cursor grok-4.7 xhigh")
    pair = gave_up.replace("Reviewer: mcp:9\n", "Reviewer: mcp:9\nReviewer: mcp:8\n") + other
    assert ready.short_of(pair, KEPT) == ready.NO_VERDICT


def test_a_reviewer_that_gives_up_leaves_a_section_that_is_no_review_and_sends_nothing(
    reviewer,
):
    """The path of "No room": the reviewer sends the block, and the wait ends with no room. The
    reviewer sends nobody anything, and writes a section that says it did not run the review: jbus's
    stall clock reads it as a review with no verdict."""
    reviewer.machine(pressure="25.00")
    (why,), code = reviewer(fill=SOON)
    assert code == 75
    assert ready.short_of(reviewer.brief.read_text(), KEPT) == "it has no review yet"
    written = [f"written: ## Review with Verdict: not run, in {reviewer.brief}"]
    assert gives_up(reviewer, why) == (written, 0)
    brief = reviewer.brief.read_text()
    assert brief == BRIEF + GAVE_UP.format(why="wait: memory pressure 25.00 is at or over 10")
    assert ready.short_of(brief, KEPT) == "its review has no verdict"
    again = [f"no section: the brief already ends in a review of {KEPT} that was not run"]
    assert gives_up(reviewer, why) == (again, 0)
    assert reviewer.brief.read_text() == brief


def test_a_give_up_at_a_later_head_is_a_section_of_its_own(reviewer):
    was = GAVE_UP.format(why="wait: jgauge room did not run").replace(KEPT, "b" * 40)
    reviewer.brief.write_text(BRIEF + was)
    _, code = gives_up(reviewer, "wait: jgauge room did not run")
    assert code == 0
    assert reviewer.brief.read_text() == BRIEF + was + GAVE_UP.format(
        why="wait: jgauge room did not run"
    )


def test_the_sixth_send_with_no_room_says_to_give_up_and_room_forgets_the_count(reviewer):
    said = "wait: memory pressure 25.00 is at or over 10"
    reviewer.machine(pressure="25.00")
    assert [reviewer(fill=SOON) for _ in range(7)] == [
        *5 * [([said], 75)],
        ([said], 69),
        ([said], 75),
    ]
    reviewer.machine()
    assert reviewer.prompt().is_file()
    assert [path for path in (reviewer.state / "tmp").iterdir() if path.is_file()] == []
    reviewer.machine(pressure="25.00")
    assert reviewer(fill=SOON) == ([said], 75)


def test_each_review_builds_in_a_directory_of_its_own(reviewer):
    first, second = reviewer.prompt(), reviewer.prompt()
    assert first.parent != second.parent
    assert first.read_text() == second.read_text()
    assert all(path.name.startswith("pr-review-a-task.") for path in reviewer.built())


@pytest.fixture
def proof(reviewer):
    """Run the proof block of step 5 over a script the reviewer wrote beside the prompt."""
    (reviewer.work / "real.sh").write_text("echo the real code ran\n")
    crew.git(reviewer.work, "add", "-A")
    crew.git(reviewer.work, "commit", "-q", "-m", "the change")
    beside = reviewer.prompt().parent
    kept = crew.git(reviewer.work, "rev-parse", "HEAD")

    def ends(script, limit=None, then=None, **env):
        (beside / "proof.sh").write_text(script)
        fill = {
            "<the directory of the prompt file>": str(beside),
            "<the head kept at the start>": kept,
            "<the proof>": 'sh "$D/proof.sh"',
            "<thread id>": "mcp:thread-1",
        }
        if limit is not None:
            fill["jgauge proof"] = f"jgauge proof --wait {limit}"
        return reviewer("### The review", "jgauge proof", fill=fill, then=then, **env)

    def run(script, **env):
        printed, code = ends(script, **env)
        assert code == 0
        assert printed[0].startswith("started:")
        return printed[1:]

    run.out, run.ends, run.work, run.kept = beside / "proof.out", ends, reviewer.work, kept
    run.ended = lambda: ended(beside)
    run.stub = reviewer.stub
    return run


def ended(beside):
    """Wait for the proof to end while no call waits on it, as happens in a turn between
    two calls."""
    for _ in range(600):
        if (beside / "proof.exit").exists():
            return
        time.sleep(0.1)
    raise AssertionError("the proof did not end")


def test_the_proof_runs_the_real_code_and_prints_its_exit_code_and_last_lines(proof):
    script = "seq 1 20\nsh real.sh\necho not this >&2\necho the fact holds\n"
    assert proof(script) == [
        "exit 0",
        "19",
        "20",
        "the real code ran",
        "not this",
        "the fact holds",
    ]
    assert proof.out.read_text().count("\n") == 23


def test_a_proof_with_every_short_slot_taken_registers_nothing_and_ends_76(proof, tmp_path):
    """With no short slot, `jgauge.runner.proof` registers nothing and says to send again now."""
    home = tmp_path / "taken"
    locks = home / ".local" / "state" / "locks"
    locks.mkdir(parents=True)
    held = []
    for n in range(1, 4):
        fd = os.open(locks / f"test-slot-short.{n}.lock", os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held.append(fd)
    try:
        printed, code = proof.ends(
            "echo the fact holds\n", HOME=str(home), JGAUGE_SHORT_WAIT_SECONDS="0"
        )
    finally:
        for fd in held:
            os.close(fd)
    assert (printed[-1].split(":")[0], code) == ("waiting", 76)
    assert "exit" not in [line.split()[0] for line in printed]
    assert "send this block again now, in this turn" in printed[-1]
    assert "run the same command again now, in this turn" in proof.out.read_text()
    assert not (locks / "test-slot-waiters.json").exists()
    printed, code = proof.ends("echo the fact holds\n")
    assert (printed[0].split(":")[0], printed[1], code) == ("started", "exit 0", 0)


def held_open(go):
    """A proof that runs until the test touches `go`, and for a minute at most, so a test that
    fails before the touch leaves no detached proof behind it."""
    return crew.held_open(go) + "\n"


def test_a_proof_is_waited_on_in_the_turn_and_never_started_twice(proof, tmp_path):
    """A proof can take longer than one call. Each call waits its whole limit and says to send
    the block again. A second call joins the proof the first one started, and the last call gives
    the proof's exit code."""
    runs, go = tmp_path / "runs", tmp_path / "go"
    script = f"echo ran >> {runs}\n" + held_open(go) + "echo the fact holds\n"

    began = time.monotonic()
    said, code = proof.ends(script, limit=1)
    assert (said[0].split(":")[0], said[-1].split(":")[0], code) == ("started", "running", 0)
    assert "never end your turn while it runs" in said[-1]
    assert "exit" not in [line.split()[0] for line in said]
    assert time.monotonic() - began >= 1

    began = time.monotonic()
    said, code = proof.ends(script, limit=1)
    assert (said[0].split(":")[0], said[-1].split(":")[0]) == ("joined", "running")
    assert time.monotonic() - began >= 1

    began = time.monotonic()
    said, code = proof.ends(script, limit=30, then=go.touch)
    assert (said[0].split(":")[0], said[1:3], code) == ("joined", ["exit 0", "the fact holds"], 0)
    assert time.monotonic() - began < 30
    assert runs.read_text() == "ran\n"


def test_a_proof_that_ended_between_calls_is_told_once_and_then_runs_afresh(proof, tmp_path):
    """When a proof ends while no call waits on it, the block gives the proof's answer once.
    When the reviewer fixes the proof and sends the block again, the proof runs afresh."""
    runs = tmp_path / "runs"
    script = f"echo ran >> {runs}\nsleep 1\n[ $(wc -l < {runs}) -gt 1 ]\n"

    said, code = proof.ends(script, limit=0)
    assert (said[0].split(":")[0], said[-1].split(":")[0], code) == ("started", "running", 0)
    proof.ended()

    said, code = proof.ends(script)
    assert (said[0].split(":")[0], said[1], code) == ("checked", "exit 1", 0)
    assert runs.read_text() == "ran\n"

    said, code = proof.ends(script)
    assert (said[0].split(":")[0], said[1], code) == ("started", "exit 0", 0)
    assert runs.read_text() == "ran\nran\n"


def test_a_proof_rewritten_while_it_runs_is_no_proof_of_the_new_one(proof, tmp_path):
    go, begun = tmp_path / "go", tmp_path / "begun"
    said, _ = proof.ends(f"touch {begun}\n" + held_open(go), limit=0)
    assert said[-1].split(":")[0] == "running"
    for _ in range(100):
        if begun.exists():
            break
        time.sleep(0.1)
    said, code = proof.ends("echo the new fact\n", limit=1)
    assert said[0].split(":")[0] == "joined" and said[-1].split(":")[0] == "running"
    said, code = proof.ends("echo the new fact\n", limit=30, then=go.touch)
    assert (said[0].split(":")[0], said[-1].split(":")[0], code) == ("joined", "stale", 75)
    assert "exit 0" not in said
    said, code = proof.ends("echo the new fact\n")
    assert (said[0].split(":")[0], said[1:3], code) == ("started", ["exit 0", "the new fact"], 0)


def test_a_proof_that_fails_is_loud(proof):
    assert proof("echo the fact is false\nexit 3\n") == ["exit 3", "the fact is false"]


def test_a_proof_that_wrote_in_the_worktree_is_shown(proof):
    assert proof("echo left behind > note.txt\n") == ["exit 0", "?? note.txt"]


def test_a_proof_does_not_run_on_a_head_that_is_not_the_one_under_review(proof):
    (proof.work / "real.sh").write_text("echo pushed during the review\n")
    crew.git(proof.work, "commit", "-q", "-am", "pushed during the review")
    said, code = proof.ends("echo ran > ran.txt\n")
    assert code == 1
    assert said == [
        f"unproven: this checkout is not at {proof.kept}, "
        "or a rebase is going on in it, so the proof did not run"
    ]
    assert not (proof.work / "ran.txt").exists() and not proof.out.exists()


def test_a_head_that_moves_under_the_proof_is_said_after_it(proof):
    moves = "git -c user.name=t -c user.email=t@example.com commit -q --allow-empty -m moved\n"
    assert proof(moves + "echo the fact holds\n") == [
        "exit 0",
        "the fact holds",
        "unproven: the head moved under the proof",
    ]


def test_a_proof_sent_without_the_block_at_the_top_runs_nothing(proof):
    said, code = proof.ends("echo ran > ran.txt\n", T="")
    assert (said, code != 0) == ([], True)
    assert not (proof.work / "ran.txt").exists()


class Reviewed(crew.PullRequest):
    """A crewmate's worktree at the head a reviewer kept, pushed to origin, and the base it kept."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path, None, "other.txt")
        self.started = crew.git(self.work, "rev-parse", "HEAD~1")
        self.commit(self.work, "second.txt", "more\n", "the second commit")
        self.pushes(self.head())

    def pushes(self, head):
        crew.git(self.work, "push", "-q", "-f", "origin", f"{head}:refs/heads/a-task")

    def patch_id(self, since, head):
        patch = crew.git(self.work, "diff", since, head) + "\n"
        named = subprocess.run(
            ["git", "patch-id", "--stable"], input=patch, capture_output=True, text=True, check=True
        )
        return named.stdout.split()[0]

    def checked(self, kept):
        crew.git(self.work, "fetch", "-q", "origin")
        base = crew.git(self.work, "merge-base", "origin/main", kept)
        script = block("### After the review", "patch-id")
        script = script.replace("<the head kept at the start>", kept)
        script = script.replace("<the base kept at the start>", base)
        ran = subprocess.run(
            ["sh", "-c", script],
            capture_output=True,
            text=True,
            cwd=self.work,
            env={**os.environ, "PATH": f"{self.stub}:{os.environ['PATH']}", "STUB": str(self.stub)},
        )
        return ran.stdout.splitlines(), ran.returncode


def test_the_head_and_the_patch_reviewed_are_two_lines_of_the_section(tmp_path):
    pr = Reviewed(tmp_path)
    head = pr.head()
    patch = pr.patch_id(pr.started, head)
    assert re.fullmatch(r"[0-9a-f]{40}", patch)
    said, code = pr.checked(head)
    assert code == 0
    assert said == [f"Head: {head}   Unchanged by the review: yes", f"Patch-id: {patch}"]
    template = REVIEW.read_text().splitlines()
    for line in said:
        label = re.split(r": |   ", line)
        assert any(row.startswith(f"{label[0]}: ") for row in template)
    assert any("   Unchanged by the review: yes | no" in row for row in template)


def test_the_patch_id_is_the_same_after_a_rebase_that_left_the_patch_as_it_was(tmp_path):
    pr = Reviewed(tmp_path)
    before = pr.head()
    (_, patch), _ = pr.checked(before)
    crew.git(pr.work, "rebase", "-q", "origin/main")
    assert pr.head() != before
    assert crew.git(pr.work, "rev-parse", "HEAD~2") == pr.landed
    pr.pushes(pr.head())
    assert pr.checked(pr.head()) == (
        [f"Head: {pr.head()}   Unchanged by the review: yes", patch],
        0,
    )
    pr.commit(pr.work, "third.txt", "wider\n", "a fix")
    pr.pushes(pr.head())
    assert pr.checked(pr.head())[0][1] not in (patch, "Patch-id: ")


def moved_on_origin(pr):
    pr.pushes(pr.started)


def moved_here(pr):
    pr.commit(pr.work, "third.txt", "more\n", "pushed during the review")


def left_uncommitted(pr):
    (pr.work / "left.txt").write_text("a proof wrote here\n")


@pytest.mark.parametrize("moved", [moved_on_origin, moved_here, left_uncommitted])
def test_a_head_that_moved_under_the_review_is_said_to_have(moved, tmp_path):
    pr = Reviewed(tmp_path)
    kept = pr.head()
    (_, patch), _ = pr.checked(kept)
    moved(pr)
    assert pr.checked(kept) == ([f"Head: {kept}   Unchanged by the review: no", patch], 0)


def test_the_head_reviewed_is_named_whatever_could_not_be_asked(tmp_path):
    """A section with no `Head:` leaves the crew skill and `jmerge` no reviewed head to read."""
    pr = Reviewed(tmp_path)
    head = pr.head()
    (_, patch), _ = pr.checked(head)
    base = crew.git(pr.work, "merge-base", "origin/main", head)
    shutil.rmtree(tmp_path / "origin.git")
    script = block("### After the review", "patch-id").replace("<the head kept at the start>", head)
    script = script.replace("<the base kept at the start>", base)
    ran = subprocess.run(["sh", "-c", script], capture_output=True, text=True, cwd=pr.work)
    assert (ran.stdout.splitlines(), ran.returncode) == (
        [f"Head: {head}   Unchanged by the review: not checked, could not ask origin", patch],
        1,
    )
    state = tmp_path / "state"
    (state / "tasks").mkdir(parents=True)
    section = ran.stdout.strip()
    brief = f"{crew.BRIEF}\n## Review\nVerdict: findings\n{section}\nFindings:\n- info a.py it\n"
    (state / "tasks" / "alpha.md").write_text(brief)
    ran = subprocess.run(
        ["sh", "-c", crew.block("The review", "--rounds").replace("<slug>", "alpha")],
        capture_output=True,
        text=True,
        cwd=pr.work,
        env={**os.environ, "H": str(state)},
        check=True,
    )
    assert ran.stdout == "write Scoped review: none, one round: the fix merges on its checks\n"


FINDINGS = {
    "error src/a.py:3 a line the pull request added": True,
    "warning src/a.py:2 the line that took the place of a removed one": True,
    "warning src/a.py:12 the line a removal now leaves here": True,
    "warning src/a.py:11 the line before a removal": True,
    "warning src/a.py:4 a line the pull request only shows as context": False,
    "warning src/a.py:10 the line before the one before a removal": False,
    "warning src/a.py:13 the line after the one after a removal": False,
    "error src/b.py:1 a file the pull request did not change": False,
    "info new.txt:2 a line of a file the pull request added": True,
    "warning old.txt:1 a file the pull request removed": True,
    "warning src/a.py the file as a whole, with no line": True,
    "error README.md a file as a whole that the pull request did not change": False,
    "warning - the change as a whole has no test for what it adds": True,
    "info now.md a file the pull request only renamed": True,
    "info logo.png a binary file the pull request added": True,
    "info was.md the name a renamed file had before": False,
}
LEAD = {
    "error src/a.py:3 it runs twice after a crash (both reviewers) (principle: none)": True,
    "warning src/a.py:2 a helper would hold it (principle: principle-laziness-protocol)": True,
    "info new.txt:1 a name that says less than it could (principle: none)": True,
    "warning - the one safety fact is unproven (principle: principle-prove-it-works)": True,
    "error src/a.py:3 the proof failed: two runs wrote the same row (principle: none)": True,
    "error src/b.py:40 a bug in code the pull request calls (principle: none)": False,
    "warning tests/test_b.py a file the reviewers opened that the change left alone": False,
}


TAGGED = {
    f"{finding} (bucket: {'Act on' if n % 2 else 'Consider'})"
    + (" (risk: data)" if n == 1 else ""): kept
    for n, (finding, kept) in enumerate(LEAD.items())
}


@pytest.mark.parametrize(("findings", "dropped"), [(FINDINGS, 6), (LEAD, 2), (TAGGED, 2)])
def test_a_finding_outside_the_diff_is_dropped_and_counted(reviewer, findings, dropped):
    reviewer.gh()
    printed = reviewer.output("### Outside the diff", findings=findings)
    assert printed[:-1] == [finding for finding, kept in findings.items() if kept]
    assert printed[-1] == f"Dropped: {dropped}"


@pytest.mark.parametrize(
    ("heading", "call"),
    [
        ("### Outside the diff", "diff"),
        ("### In flight", "view"),
        ("### In flight", "list"),
    ],
)
def test_a_gh_that_fails_is_not_read_as_nothing_found(reviewer, heading, call):
    reviewer.brief.write_text(BRIEF + "Where: `src/`.\n")
    reviewer.gh(files=["README.md"])
    (reviewer.stub / "down").write_text(f"{call}\n")
    findings = ["error src/a.py:3 a line the pull request added"]
    assert reviewer(heading, findings=findings) == ([], 1)


def branch_of_the_task(reviewer, where, *changed, result=""):
    """The brief in the state `jmerge` reads, and a branch `a-task` of the worktree's repo that
    changes the files named. The skill's block asks `jmerge --scope` about that branch."""
    work = reviewer.work
    brief = reviewer.brief.read_text() + (f"Where: {where}\n" if where else "") + result
    tasks = reviewer.state / "home" / ".local" / "state" / "home" / work.name / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "a-task.md").write_text(brief)
    merge.git(work, "commit", "-q", "--allow-empty", "-m", "start")
    merge.git(work, "update-ref", "refs/remotes/origin/main", "HEAD")
    merge.git(work, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    merge.git(work, "checkout", "-q", "-b", "a-task")
    for path in changed:
        (work / path).parent.mkdir(parents=True, exist_ok=True)
        (work / path).write_text(f"{path}\n")
    merge.git(work, "add", "-A")
    merge.git(work, "commit", "-q", "-m", "the task")


def test_a_brief_whose_where_names_no_path_is_not_read_as_no_wider(reviewer):
    branch_of_the_task(reviewer, "wherever it takes", "README.md")
    assert reviewer("### Wider than the brief") == ([], 1)


def test_the_open_pull_requests_that_share_a_file_are_listed(reviewer):
    reviewer.gh(
        files=["src/a.py", "tests/test_a.py", "README.md"],
        others=[
            reviewer.pull_request(3, "docs/x.md", "README.md", title="tidy the readme"),
            reviewer.pull_request(4, "src/b.py", title="shares nothing"),
            reviewer.pull_request(5, "tests/test_a.py", "src/a.py", "src/c.py", title="more of a"),
        ],
    )
    assert reviewer.output("### In flight") == [
        "pull request 3 (tidy the readme): README.md",
        "pull request 5 (more of a): tests/test_a.py, src/a.py",
    ]


def test_the_briefs_with_no_result_that_claim_a_changed_file_are_listed(reviewer):
    tasks = reviewer.state / "tasks"
    reviewer.brief.write_text(BRIEF + "Where: `src/`.\n")
    (tasks / "claims-a.md").write_text("# claims-a\nWhere: `src/a.py`, `tests/`, `docs/`.\n")
    (tasks / "finished.md").write_text("# finished\nWhere: `src/a.py`.\n\n## Result\n")
    (tasks / "elsewhere.md").write_text("# elsewhere\nWhere: `hooks/`.\n")
    (tasks / "no-where.md").write_text("# no-where\nTask: touch `src/a.py` somehow.\n")
    reviewer.gh(files=["src/a.py", "tests/test_a.py", "README.md"])
    assert reviewer.output("### In flight") == ["brief claims-a: src/a.py, tests/test_a.py"]


def test_nothing_in_flight_prints_nothing(reviewer):
    reviewer.gh(files=["src/a.py"], others=[reviewer.pull_request(4, "src/b.py")])
    assert reviewer.output("### In flight") == []


@pytest.mark.parametrize(
    ("result", "reviewer_thread"),
    [
        ("", ""),
        ("\n## Result\nStatus: done\nReviewer: mcp:9\n", "mcp:9"),
        ("\n## Result\nReviewer: none, no launch tool in this session\n", ""),
        (
            "\n## Result\nReviewer: none, no tool\n\n## Result, follow-up\nReviewer: mcp:9\n",
            "mcp:9",
        ),
        ("\n## Result\nStatus: done\nNoticed: a `Reviewer: mcp:9` line would stop this.\n", ""),
    ],
)
def test_a_brief_that_names_its_reviewer_is_found(reviewer, result, reviewer_thread):
    reviewer.brief.write_text(BRIEF + result)
    assert reviewer.output("## Launching") == [reviewer_thread or "none"]


DONE = f"\n## Result\nStatus: done\nBranch: a-task   Pull request: {URL}\n"
HEAD = "b" * 40


def readiness():
    """The block that a launcher uses to find the ready briefs, as an agent reads it."""
    (found,) = [text for text in as_read(SKILL).split("```") if "PASS=first" in text]
    return textwrap.dedent(found.removeprefix("sh\n"))


class Launcher:
    """A home's state directory with one brief, and a stub `gh` for its pull request."""

    def __init__(self, tmp_path, rollup=crew.ROLLUPS["all passed"][0], state="OPEN", draft=False):
        self.state = tmp_path
        (tmp_path / "tasks").mkdir()
        self.brief = tmp_path / "tasks" / "a-task.md"
        self.brief.write_text(BRIEF + DONE)
        self.stub = tmp_path / "stub"
        crew.stub_gh(self.stub, HEAD, rollup, state, draft)

    def says(self, slug="a-task", again=False):
        """What the readiness block prints, for one brief or for every brief."""
        script = readiness().replace("<slug>", slug)
        if again:
            script = script.replace("PASS=first\n", "PASS=second\n")
        ran = subprocess.run(
            ["sh", "-c", script],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{self.stub}:{os.environ['PATH']}",
                "STUB": str(self.stub),
                "H": str(self.state),
                "T": str(assembled() / "templates"),
            },
            check=True,
        )
        return ran.stdout.splitlines()


def test_a_draft_is_ready_as_any_pull_request_once_its_checks_passed(tmp_path):
    """CI checks a draft as any open pull request, so a draft is ready once its checks passed,
    and not while none is reported, as any pull request's is: the draft field is not read."""
    launcher = Launcher(tmp_path, [], draft=True)
    assert launcher.says() == ["a-task: not ready, its checks, wait: no check is reported yet"]
    (tmp_path / "passed").mkdir()
    passed = Launcher(tmp_path / "passed", draft=True)
    assert passed.says() == [f"a-task: ready, {URL} at {HEAD}"]


def test_with_github_s_budget_at_its_floor_no_brief_is_asked_about_and_the_block_is_held(tmp_path):
    launcher = Launcher(tmp_path)
    crew.spent(launcher.stub)
    script = readiness().replace("<slug>", "*").replace("--wait 540", "--wait 0")
    env = {
        **os.environ,
        "PATH": f"{launcher.stub}:{os.environ['PATH']}",
        "STUB": str(launcher.stub),
        "H": str(launcher.state),
        "T": str(assembled() / "templates"),
    }
    ran = subprocess.run(["sh", "-c", script], capture_output=True, text=True, env=env)
    (line,) = ran.stdout.splitlines()
    assert ran.returncode == 75 and line.startswith("held: GitHub's core budget has 0 of 5000")
    assert "3 calls would take it to -3" in line and line.endswith(
        "run this block again, in this turn"
    )
    crew.spent(launcher.stub, 5000)
    assert launcher.says() == [f"a-task: ready, {URL} at {HEAD}"]


def test_the_budget_counts_only_the_briefs_github_is_asked_about(tmp_path):
    launcher = Launcher(tmp_path)
    for n in range(400):
        (launcher.state / "tasks" / f"past-{n}.md").write_text(BRIEF)
    crew.spent(launcher.stub, 1004)
    assert launcher.says("*") == [f"a-task: ready, {URL} at {HEAD}"]
    crew.spent(launcher.stub, 1003)
    script = readiness().replace("<slug>", "*").replace("--wait 540", "--wait 0")
    env = {
        **os.environ,
        "PATH": f"{launcher.stub}:{os.environ['PATH']}",
        "STUB": str(launcher.stub),
        "H": str(launcher.state),
        "T": str(assembled() / "templates"),
    }
    ran = subprocess.run(["sh", "-c", script], capture_output=True, text=True, env=env)
    assert ran.returncode == 75 and "3 calls would take it to 1000" in ran.stdout


SHORT = {
    "no result": (BRIEF, "its last Result does not say Status: done and name a pull request"),
    "a result that is not done": (
        BRIEF + DONE.replace("Status: done", "Status: blocked"),
        "its last Result does not say Status: done and name a pull request",
    ),
    "a result with no pull request": (
        BRIEF + DONE.replace(URL, "none"),
        "its last Result does not say Status: done and name a pull request",
    ),
    "a follow-up that is not done": (
        BRIEF + DONE + "\n## Result, follow-up (2026-10-10, a steer)\nStatus: not done\n",
        "its last Result does not say Status: done and name a pull request",
    ),
    "a review": (
        BRIEF + DONE + "\n## Review\nVerdict: clean\n",
        "it has a review or a reviewer, and it is one pass per pull request",
    ),
    "a reviewer": (
        BRIEF + DONE + "Reviewer: mcp:9\n",
        "it has a review or a reviewer, and it is one pass per pull request",
    ),
    "Review: none": (BRIEF + "Review: none\n" + DONE, "its brief asks for no review"),
}


@pytest.mark.parametrize("case", SHORT)
def test_a_brief_short_of_ready_is_printed_with_the_first_reason(case, tmp_path):
    text, why = SHORT[case]
    launcher = Launcher(tmp_path)
    launcher.brief.write_text(text)
    assert launcher.says() == [f"a-task: not ready, {why}"]


def test_a_github_that_cannot_be_asked_hides_no_brief_from_a_home(tmp_path):
    launcher = Launcher(tmp_path)
    (launcher.stub / "view.json").unlink()
    said = ["a-task: not ready, GitHub could not be asked for its pull request"]
    assert launcher.says() == said
    assert launcher.says("*") == said


@pytest.mark.parametrize("state", ["MERGED", "CLOSED"])
def test_a_pull_request_that_is_not_open_is_not_ready(state, tmp_path):
    launcher = Launcher(tmp_path, state=state)
    assert launcher.says() == [f"a-task: not ready, its pull request is not open: {state}"]


def test_a_reviewer_that_could_not_be_launched_is_no_reviewer(tmp_path):
    launcher = Launcher(tmp_path)
    launcher.brief.write_text(BRIEF + DONE + "Reviewer: none, no launch tool in this session\n")
    assert launcher.says() == [f"a-task: ready, {URL} at {HEAD}"]


def test_a_home_with_no_slug_is_told_of_the_briefs_that_are_not_of_the_past(tmp_path):
    launcher = Launcher(tmp_path)
    tasks = launcher.brief.parent
    (tasks / "b-no-pull-request.md").write_text(BRIEF + DONE.replace(URL, "none"))
    (tasks / "c-reviewed.md").write_text(BRIEF + DONE + "\n## Review\nVerdict: clean\n")
    (tasks / "d-no-review.md").write_text(BRIEF + "Review: none\n" + DONE)
    assert launcher.says("*") == [
        f"a-task: ready, {URL} at {HEAD}",
        "d-no-review: not ready, its brief asks for no review",
    ]
    (launcher.stub / "view.json").write_text(
        json.dumps({"state": "MERGED", "headRefOid": HEAD, "statusCheckRollup": []})
    )
    assert launcher.says("*") == []


def rebased(reviewer, why="the task replaces it"):
    """A worktree whose rebase took main's line out of n.txt, and a brief in which the crewmate
    says why, at the rebased head. The worktree keeps the head from before the rebase in the ref
    where the crew skill keeps it, and the brief says nothing else of the rebase."""
    work = reviewer.work

    def commit(text):
        (work / "n.txt").write_text(text)
        crew.git(work, "add", "n.txt")
        crew.git(work, "-c", "user.name=a", "-c", "user.email=a@b", "commit", "-q", "-m", "it")
        return crew.git(work, "rev-parse", "HEAD")

    before = commit("one\ntheirs\nours\n")
    crew.git(work, "update-ref", f"refs/jstack/pre-rebase/a-task/{before[:12]}", before)
    head = commit("one\nours\n")
    said = f"Dropped on rebase: n.txt, 1 of main's, 0 of its own, at {head[:12]}: {why}"
    reviewer.brief.write_text(BRIEF + DONE + f"{said}\n")
    return before, head, said


def drops(reviewer, old="<old range>"):
    """What step 4 prints, with `old` as the old range of the message, which by default is no
    range at all, as when the block is run with its words in angle brackets left in."""
    return reviewer.output("### A scoped pass", "Dropped on rebase", fill={"<old range>": old})


def test_a_scoped_pass_reads_each_drop_the_crew_explained_at_the_head(reviewer):
    before, head, said = rebased(reviewer)
    first, line, *diff = drops(reviewer)
    assert (first, line) == ("drop: n.txt", said)
    assert [each for each in diff if each[:1] in "+-" and each[:2] not in ("++", "--")] == [
        "-theirs"
    ]
    text = section("### A scoped pass")
    upheld, against = re.findall(r"`(Drops: (?:not )?upheld <file>[^`]*)`", text)
    lost = (ready.Drop("n.txt", 1, 0),)

    def judged(ruling):
        review = f"## Review\nVerdict: clean\nScope: range-diff x y\n{ruling}\nHead: {head}\n"
        return ready.drops(lost, reviewer.brief.read_text() + review, head, user=jsettings.DEFAULTS)

    assert judged(upheld.replace("<file>, <file>", "n.txt")) == ("", "")
    ruled = against.replace("<file>", "n.txt").replace("<why>", "main still needs it")
    assert judged(ruled) == (
        "hold",
        "needs user, the review did not uphold the drop in n.txt: main still needs it",
    )


def test_a_drop_is_read_from_the_head_the_old_range_ends_on_with_no_ref_kept(reviewer):
    """The old range of the message, the one `jmerge` named in its `scoped review of git
    range-diff` line, ends on the head before the rebase, so the pass needs no ref and no line of
    the brief to find it."""
    before, head, said = rebased(reviewer)
    crew.git(reviewer.work, "update-ref", "-d", f"refs/jstack/pre-rebase/a-task/{before[:12]}")
    first, line, *diff = drops(reviewer, f"{'0' * 40}..{before}")
    assert (first, line) == ("drop: n.txt", said)
    assert [each for each in diff if each[:1] in "+-" and each[:2] not in ("++", "--")] == [
        "-theirs"
    ]


def test_with_no_old_range_the_newest_kept_head_is_the_one_before_the_last_rebase(reviewer):
    work = reviewer.work

    def commit(text, when):
        (work / "n.txt").write_text(text)
        crew.git(work, "add", "n.txt")
        dated = {**os.environ, "GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when}
        author = ("-c", "user.name=a", "-c", "user.email=a@b")
        subprocess.run(
            ["git", *author, "commit", "-q", "-m", "it"], cwd=work, env=dated, check=True
        )
        return crew.git(work, "rev-parse", "HEAD")

    older = commit("one\nstale\nours\n", "2026-10-17T10:00:00")
    crew.git(work, "update-ref", f"refs/jstack/pre-rebase/a-task/{older[:12]}", older)
    newer = commit("one\ntheirs\nours\n", "2026-10-17T11:00:00")
    crew.git(work, "update-ref", f"refs/jstack/pre-rebase/a-task/{newer[:12]}", newer)
    crew.git(work, "update-ref", f"refs/jstack/pre-rebase/b-task/{older[:12]}", older)
    head = commit("one\nours\n", "2026-10-17T12:00:00")
    said = f"Dropped on rebase: n.txt, 1 of main's, 0 of its own, at {head[:12]}: the task is it"
    reviewer.brief.write_text(BRIEF + DONE + said + "\n")
    _, _, *diff = drops(reviewer)
    assert [each for each in diff if each[:1] in "+-" and each[:2] not in ("++", "--")] == [
        "-theirs"
    ]


def test_a_scoped_pass_with_no_drop_explained_at_its_head_rules_on_none(reviewer):
    _, head, said = rebased(reviewer)
    brief = reviewer.brief.read_text()
    reviewer.brief.write_text(brief.replace(f"at {head[:12]}", "at aaaaaaaaaaaa"))
    assert drops(reviewer) == [f"no drops: the brief has no Dropped on rebase line at {head}"]


def test_a_drop_whose_head_before_the_rebase_is_not_kept_is_not_upheld(reviewer):
    before, _, _ = rebased(reviewer)
    crew.git(reviewer.work, "update-ref", "-d", f"refs/jstack/pre-rebase/a-task/{before[:12]}")
    assert drops(reviewer) == [
        "not upheld: the head before the rebase is not a commit here, nor kept under "
        "refs/jstack/pre-rebase/a-task, so no drop can be read",
        "drop: n.txt",
    ]


WAS, FIX = "a" * 40, "c" * 40
AFTER_THE_FIX = (
    "Reviewer: mcp:2\n\n## Review\nVerdict: findings\n"
    f"Head: {WAS}   Unchanged by the review: yes\n"
    "Findings:\n- warning x.conf:25 the comment says one thing and the rule another\n"
    "Sent to: mcp:1\n"
    "Finding: fixed, the comment\n"
    f"Scoped review: needed since {WAS}, the fix changed x.conf\n"
    f"Scoped reviewer: mcp:3, of {FIX}\n"
    "Finding: (scoped pass) clean, no findings\n"
    f"Fixed: {FIX}\n"
)
SCOPED_SECTION = (
    f"\n## Review\nVerdict: clean\nScope: range-diff x..{WAS} x..{FIX}\n"
    f"Head: {FIX}   Unchanged by the review: yes\nMeets the brief: yes, 1 of 1\nFindings:\n- none\n"
    "Sent to: not sent, clean\n"
)


def written(reviewer, head=FIX):
    (said,), code = reviewer(
        "### After the review", "written:", fill={"<the head kept at the start>": head}
    )
    assert code == 0
    return said.split(":")[0]


def test_a_scoped_verdict_sent_before_its_section_is_written_is_told_to_write_it_first(reviewer):
    """The brief of infra #59: the crewmate wrote its `Finding:` and `Fixed:` lines in answer
    to the scoped reviewer's message, and the brief never got the section jmerge waits for."""
    reviewer.brief.write_text(BRIEF + DONE + AFTER_THE_FIX)
    assert ready.short_of(reviewer.brief.read_text(), FIX) == ready.FIX_UNREVIEWED
    assert written(reviewer) == "not yet"
    assert written(reviewer, WAS) == "written"


def test_a_scoped_verdict_with_its_section_written_is_sent_and_jmerge_counts_the_review(reviewer):
    reviewer.brief.write_text(BRIEF + DONE + AFTER_THE_FIX + SCOPED_SECTION)
    assert written(reviewer) == "written"
    assert ready.short_of(reviewer.brief.read_text(), FIX) == ""


def test_the_scoped_pass_a_guarded_fix_is_launched_with_reads_the_fix_alone(tmp_path):
    fix = crew.opened(tmp_path, crew.GUARDED)
    decided = (
        f"Second pass: none, it stayed inside\nScoped review: needed since {fix.saw}, guarded\n"
    )
    (line,) = fix.says(decided)
    message = line.partition(", with ")[2]
    (taken,) = set(
        re.findall(r"`(/pr-review run <slug> scoped [^`]+)`", section("### A scoped pass"))
    )
    old, new = f"{fix.start}..{fix.saw}", f"{fix.start}..{fix.fixed}"
    filled = taken.replace("<slug>", "alpha").replace("<old range>", old)
    assert message == filled.replace("<new range>", new)
    script = block("### A scoped pass", "<old range>")
    ran = subprocess.run(
        ["sh", "-c", script.replace("<old range>", old).replace("<new range>", new)],
        cwd=fix.work,
        capture_output=True,
        text=True,
    )
    scope, head, *pairs = ran.stdout.splitlines()
    assert (scope, head) == (f"Scope: range-diff {old} {new}", f"Head: {fix.fixed}")
    assert [" ".join(pair.split()) for pair in pairs] == [
        f"1: {fix.saw[:7]} = 1: {fix.saw[:7]} the task",
        f"-: ------- > 2: {fix.fixed[:7]} the fix",
    ]


ANSWERED = "Finding: not fixed, it is wrong, because it is asked\nFixed: none needed, declined\n"


@pytest.mark.parametrize(
    ("done", "found", "ready_to_merge"),
    [
        (ANSWERED, "- warning a.txt:1 it is wrong (principle: none)", True),
        ("", "- warning a.txt:1 it is wrong (principle: none)", False),
        ("", "- none", True),
    ],
    ids=["its finding answered", "nothing answered", "files outside Where and no finding"],
)
def test_jmerge_reads_a_review_written_from_the_template_by_one_reader_as_ready(
    tmp_path, done, found, ready_to_merge
):
    made = merge.Merged(merge.Home(tmp_path), tmp_path)
    filled = {
        "Verdict": "clean" if found == "- none" else "findings",
        "Head": f"{made.head}   Unchanged by the review: yes",
        "Patch-id": "0" * 40,
        "Reviewers": "1, 1   Proof: uv run pytest tests/test_a.py, exit 0, 1 passed",
        "Meets the brief": "yes, 0 of 0",
        "In flight": "none",
        "Outside Where": "README.md, hooks/x.sh",
        "Dropped": "0",
        "Noted": "0",
        "Dismissed": "none",
        "Sent to": "mcp:crew",
    }
    template = REVIEW.read_text().splitlines()
    assert template[1].startswith("By: ")
    assert template[5].startswith("Reviewers: 1, ")
    lines = []
    for line in template:
        label = line.split(":")[0]
        if line == "Findings:":
            lines += [line, found]
        elif label in filled:
            lines.append(f"{label}: {filled[label]}")
        elif not line.startswith("- "):
            lines.append(line)
    (made.home.tasks / "alpha.md").write_text(merge.brief("\n".join(lines) + "\n", done))
    said = made.run("--check")
    assert (said == [f"ready 7 {made.head} alpha alpha"]) == ready_to_merge
    assert said[0].startswith("ready" if ready_to_merge else "wait")


SKILLS = "Skills: in-your-own-words, principle-model-the-domain, prove-it-works\n"
SKILLS_RUN = (
    "Skills run:\n"
    "- in-your-own-words: the user wants each skill a brief names to reach the crewmate\n"
    "- model-the-domain: Named(said, path), resolved once; missing() is the gap\n"
    "- principle-prove-it-works: <the command>\n"
)


def test_the_reviewer_reads_the_skills_line_and_each_artifact_as_jmerge_reads_it(reviewer):
    text = BRIEF.replace("Pull request:", f"Design: none, small\n{SKILLS}Pull request:")
    reviewer.brief.write_text(f"{text}\n## Result\nStatus: done\n{SKILLS_RUN}")
    told = intent(reviewer)
    skills_line = SKILLS.removeprefix("Skills: ").strip()
    assert f"\nSkills: {skills_line}. The crewmate loaded each in full" in told
    assert told.count("Skills: in-your-own-words") == 1
    assert (
        "What the Results hold under Skills run:, as jmerge reads it:\n"
        "- in-your-own-words: the user wants each skill a brief names to reach the crewmate\n"
        "- principle-model-the-domain: Named(said, path), resolved once; missing() is the gap\n"
        "- principle-prove-it-works: no artifact\n"
    ) in told


def test_a_reviewer_that_cannot_fetch_closes_its_seat_at_the_worktrees_head(reviewer):
    """Start's step 2 stops where origin cannot be fetched, and a stop with no section left the
    reviewer's seat open and the brief `reviewing`, as #1710's did, until somebody noticed. The
    worktree's own commit is a head the section can name."""
    (reviewer.work / "a.py").write_text("one\n")
    crew.git(reviewer.work, "checkout", "-q", "-b", "a-task")
    crew.git(reviewer.work, "add", "-A")
    crew.git(reviewer.work, "commit", "-q", "-m", "the change")
    here = crew.git(reviewer.work, "rev-parse", "HEAD")
    (stop,) = reviewer.output("### Start", "git fetch -q origin")
    assert stop == f"stop: could not fetch origin's a-task and main, this worktree is at {here}"
    fill = {
        "<the head the review was to be of>": here,
        "<the stop line the step printed>": stop,
        "<the By: line Start printed>": "By: inherit #1",
    }
    assert reviewer.output("### A stop", fill=fill) == [
        f"written: ## Review with Verdict: not run, in {reviewer.brief}"
    ]
    assert reviewer.brief.read_text().endswith(
        f"Head: {here}   Unchanged by the review: not checked, no review ran\n"
        "Sent to: not sent, no review ran\n"
    )
