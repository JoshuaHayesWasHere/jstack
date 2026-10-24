import fcntl
import json
import os
import re
import shutil
import subprocess
import textwrap
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

import crew_helpers as crew
import jsettings
import test_home_merge as merge
import test_jbus_unlock as unlock
import test_jmerge_guarded as guarded
from jbriefs import findings
from jmerge import ready
from test_home_thread import NAMED, as_read
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add
from test_room import BIN, IDLE, machine, says, uv
from testing.layouts import assembled
from testing.paths import REPO

SKILL = REPO / "features" / "pr-review" / "SKILL.md"
REVIEW = REPO / "features" / "pr-review" / "templates" / "review.md"
INTERROGATE = REPO / "features" / "skill-library" / "skills" / "interrogate"
BLAST_RADIUS = REPO / "features" / "skill-library" / "skills" / "blast-radius" / "SKILL.md"

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
INTENT = "".join(BRIEF.splitlines(keepends=True)[1:6]).rstrip("\n")
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
    (stub / "diff").write_text(DIFF)
    env = {
        **os.environ,
        "HOME": str(home),
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

    def start(heading="### The review", about="", findings=(), fill=None, **more):
        script = block(heading, about).replace("<slug>", "a-task").replace("<url>", URL)
        script = script.replace("<the findings, one to a line>", "\n".join(findings))
        for words, value in (fill or {}).items():
            assert words in script
            script = script.replace(words, value)
        ran = subprocess.run(
            ["sh", "-c", script],
            env={**env, **more},
            cwd=work,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return ran.stdout.splitlines(), ran.returncode

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

    def pull_request(number, *files, title="a title"):
        return {"number": number, "title": title, "files": [{"path": path} for path in files]}

    def gh(diff=DIFF, files=(), others=()):
        mine = pull_request(7, *files)
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


CONFIG = "<what t3_thread_configuration printed, or nothing where this session has no such tool>"


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


FULL_RUN = "- Check command: `make check`\n- Full run: reviewer\n"
NOTES = [None, FULL_RUN, "Full run: reviewer (the user, 2026-10-10)\n", "- a note\n"]


@pytest.mark.parametrize("notes", NOTES)
@pytest.mark.parametrize(
    "brief", ["no line", "review", "a word from before", "only quoted", "said again in a result"]
)
def test_every_brief_but_one_that_says_none_is_reviewed(reviewer, brief, notes):
    reviewer.brief.write_text(BRIEFS[brief])
    if notes is not None:
        (reviewer.state / "notes.md").write_text(notes)
    told = "".join(BRIEFS[brief].splitlines(keepends=True)[1:6])
    assert intent(reviewer) == f"{told}\n{scope()}\n"


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
    assert ends == {"twice": 0, "review": 0, "none": 78, "after": 0}


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


def test_the_intent_is_the_brief_from_task_to_the_end_of_decisions_then_the_scope_rule(reviewer):
    assert scope().strip() != ""
    assert intent(reviewer) == f"{INTENT}\n\n{scope()}\n"


def applies(name):
    """The paragraph a principle opens with, under its title, as one line."""
    skill = REPO / "features" / "principles" / "skills" / name / "SKILL.md"
    text = skill.read_text().split("\n---\n\n", 1)[1]
    return " ".join(text.split("\n\n")[1].splitlines())


def test_a_playbook_gives_the_reviewers_its_name_and_when_each_principle_it_cites_applies(
    reviewer,
):
    reviewer.brief.write_text(BRIEF + "Playbook: bug-fix\n")
    cited = [
        "principle-laziness-protocol",
        "principle-fix-root-causes",
        "principle-test-behavior-not-implementation",
        "principle-attack-the-premise",
        "principle-prove-it-works",
        "principle-sequence-verifiable-units",
    ]
    assert all(applies(name).startswith("Apply ") for name in cited)
    lens = "\n".join(f"- {name}: {applies(name)}" for name in cited)
    assert intent(reviewer) == (
        f"{INTENT}\n\nPlaybook: bug-fix, the steps the crewmate worked by.\n"
        f"The principles it cites, and when each applies:\n{lens}\n\n{scope()}\n"
    )


@pytest.mark.parametrize("name", ["fix", "feature.", "../templates/brief"])
def test_a_playbook_name_that_is_no_playbook_is_said_and_no_principle_follows(reviewer, name):
    reviewer.brief.write_text(BRIEF + f"Playbook: {name}\n")
    said = f"no playbook: playbooks/ has no {name}.md: the crewmate worked with none"
    assert intent(reviewer) == f"{INTENT}\n\n{said}\n\n{scope()}\n"


@pytest.mark.parametrize(
    ("name", "by"), [("orchestrate", "the home"), ("investigation", "a scout")]
)
def test_a_playbook_that_is_not_a_crewmates_is_said_and_no_principle_follows(reviewer, name, by):
    reviewer.brief.write_text(BRIEF + f"Playbook: {name}\n")
    said = f"not a crewmate's: playbooks/{name}.md is for {by}: the crewmate worked with none"
    assert intent(reviewer) == f"{INTENT}\n\n{said}\n\n{scope()}\n"


def test_a_brief_whose_playbook_is_none_gives_the_reviewers_the_brief_alone(reviewer):
    reviewer.brief.write_text(BRIEF + "Playbook: none\n")
    assert intent(reviewer) == f"{INTENT}\n\n{scope()}\n"


def test_the_reviewers_are_asked_to_tag_each_finding_with_the_principle_it_breaks(reviewer):
    reviewer.brief.write_text(BRIEF + "Playbook: bug-fix\n")
    told = intent(reviewer)
    assert told.index("- principle-fix-root-causes: ") < told.index("`(principle: <name>)`")
    assert "`(principle: none)`" in told


def asked(text, question):
    after = text.split(f"\n{question}. ", 1)[1]
    return after.split(f"\n{question + 1}. ", 1)[0]


LOOKED_FOR = [
    (4, "Run twice, or after a run that crashed halfway"),
    (4, "kept in step by structure"),
    (4, "A rule in prose"),
    (4, "An old path kept beside a new one"),
    (4, "A proxy"),
    (4, "A bug fix with no test"),
    (5, "Be ambitious about structural simplification"),
    (5, "whole branches, helpers, modes, conditionals or layers disappear"),
    (5, "delete complexity rather than rearrange it"),
    (5, "from under 1,000 lines to over 1,000"),
    (5, "one-off branches put into an existing flow"),
    (5, "pass-through helper"),
    (5, "Logic outside its canonical layer"),
    (5, 'would change a file outside the "Where" line above'),
    (6, "A changed line that does not trace to the task"),
    (6, "already unused before this change is named in the finding, not deleted"),
    (6, "What the change itself made unused goes in the same change"),
]


@pytest.mark.parametrize(("question", "named"), LOOKED_FOR)
def test_the_reviewers_are_told_each_thing_to_look_for_under_its_question(
    reviewer, question, named
):
    assert named in asked(intent(reviewer), question)


def test_what_the_reviewers_look_for_stays_inside_the_changed_lines(reviewer):
    told = intent(reviewer)
    rule = told.index("Review only the lines this pull request changes")
    assert rule < told.index("\n4. ")
    for question in (4, 5, 6):
        assert asked(told, question).splitlines()[0].endswith("in the changed lines:")
    assert [line[:2] for line in told.splitlines() if re.match(r"\d\. ", line)] == [
        f"{n}." for n in range(1, 8)
    ]


def placeholders(text):
    """Each line of a prompt that is still one of the template's places to fill."""
    return [line for line in text.splitlines() if re.fullmatch(r"(> )?\{[A-Z_]+\}", line)]


def test_the_prompt_is_the_interrogate_template_filled_with_what_this_review_reads(reviewer):
    template = (INTERROGATE / "references" / "reviewer-prompt.md").read_text()
    assert len(placeholders(template)) == 5
    prompt = reviewer.prompt()
    text = prompt.read_text()
    assert placeholders(text) == []
    assert text.startswith("\nYou are an adversarial code reviewer.")
    assert "Build each reviewer subagent's prompt" not in text
    told = (prompt.parent / "intent").read_text()
    assert "".join(f"> {line}\n" for line in told.splitlines()) in text
    assert f"\n~~~~~~diff\n{DIFF}~~~~~~\n" in text
    for name in ("rubric.md", "code-quality-review.md"):
        assert (INTERROGATE / "references" / name).read_text() in text
    two = f"4. {asked(told, 4)}\n5. {asked(told, 5)}".split("\n   When the remedy")[0]
    assert two.count("\n   - ") == 11
    assert f"all of it when whole files were given.\n\n{two}\n\n## Instructions" in text


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
        assert call.count('uv run --project "$T/.." jgauge room') == 1
        said.append(says(env, call.replace("--wait 540", "--wait 0") + more))
    return said


@pytest.mark.parametrize("jgauge", ["there", "broken"])
def test_the_review_and_the_launch_both_ask_jgauge_room(tmp_path, jgauge):
    if jgauge == "broken":
        (tmp_path / "stub").mkdir()
        (tmp_path / "stub" / "jgauge").write_text("#!/bin/sh\nexit 127\n")
        (tmp_path / "stub" / "jgauge").chmod(0o755)
    assert room_calls(tmp_path, pressure="25.00") == 2 * [
        "wait: memory pressure 25.00 is at or over 10"
        if jgauge == "there"
        else "wait: jgauge room did not run"
    ]


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


@pytest.mark.parametrize(
    ("readings", "said"),
    [
        ({"memory": 3 * 1048576}, "wait: 3.0 GB of memory available, under 6"),
        ({"pressure": "25.00"}, "wait: memory pressure 25.00 is at or over 10"),
    ],
)
def test_a_review_waits_when_the_machine_has_no_room_and_goes_when_it_has(reviewer, readings, said):
    reviewer.machine(**readings)
    assert reviewer(fill=SOON) == ([said], 75)
    assert reviewer.built() == []
    reviewer.machine()
    assert reviewer.prompt().is_file()


@pytest.mark.parametrize("readings", [{"load": "11.00"}, {"load": "30.00", "cores": "24"}])
def test_a_review_is_not_held_by_load_and_builds_its_prompt_at_once(reviewer, readings):
    """A review takes about 2% of one core, and its proof runs in the short test lane.
    So a review does not wait when the load is over the threshold at which a launch waits, and
    the first check of the machine says `go`."""
    reviewer.machine(**readings)
    printed, code = reviewer(fill=SOON)
    assert (code, len(printed)) == (0, 1), printed
    assert Path(printed[0]).is_file()


def test_a_review_waits_when_the_machine_cannot_be_read(reviewer):
    (reviewer.state / "proc" / "meminfo").unlink()
    printed, code = reviewer(fill=SOON)
    assert code == 75
    assert [line.split(":")[0] for line in printed] == ["wait"]
    assert reviewer.built() == []


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
    "Sent to: mcp:1\n"
)


def gives_up(reviewer, why, sent):
    """Run the block of the "No room" section, filled in as a reviewer fills it."""
    filled = {
        "<the head kept at the start>": KEPT,
        "<the last line the block of step 1 printed>": why,
        '<the thread id the line went to, or the two words "not sent">': sent,
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
        '<the thread id the line went to, or the two words "not sent">': "mcp:1",
        "<the By: line Start printed>": "By: claudeAgent claude-opus-5-5",
    }
    assert reviewer("### No room", fill=filled)[1] == 0
    gave_up = reviewer.brief.read_text()
    assert "## Review\nBy: claudeAgent claude-opus-5-5\nVerdict: not run\n" in gave_up
    assert ready.short_of(gave_up, KEPT) == ready.NO_VERDICT
    clean = f"\n## Review\nBy: claudeAgent claude-opus-5-5\nVerdict: clean\nHead: {KEPT}\n"
    assert ready.short_of(gave_up + clean, KEPT) == ""
    other = clean.replace("claudeAgent claude-opus-5-5", "cursor grok-4.7 xhigh")
    pair = gave_up.replace("Reviewer: mcp:9\n", "Reviewer: mcp:9\nReviewer: mcp:8\n") + other
    assert ready.short_of(pair, KEPT) == ready.NO_VERDICT


def test_a_reviewer_that_gives_up_leaves_a_section_that_is_no_review_and_names_whom_it_told(
    reviewer,
):
    """The path of "No room": the reviewer sends the block, and the wait ends with no room. The
    reviewer tells the thread on the brief's `Thread:` line, and writes a section that says it did
    not run the review."""
    reviewer.machine(pressure="25.00")
    (why,), code = reviewer(fill=SOON)
    assert code == 75
    thread = where(reviewer, "not run").split(": ")[0].removeprefix("crewmate ")
    assert thread == "mcp:1"
    assert ready.short_of(reviewer.brief.read_text(), KEPT) == "it has no review yet"
    written = [f"written: ## Review with Verdict: not run, in {reviewer.brief}"]
    assert gives_up(reviewer, why, thread) == (written, 0)
    brief = reviewer.brief.read_text()
    assert brief == BRIEF + GAVE_UP.format(why="wait: memory pressure 25.00 is at or over 10")
    assert ready.short_of(brief, KEPT) == "its review has no verdict"
    again = [f"no section: the brief already ends in a review of {KEPT} that was not run"]
    assert gives_up(reviewer, why, thread) == (again, 0)
    assert reviewer.brief.read_text() == brief


def test_a_give_up_at_a_later_head_is_a_section_of_its_own(reviewer):
    was = GAVE_UP.format(why="wait: jgauge room did not run").replace(KEPT, "b" * 40)
    reviewer.brief.write_text(BRIEF + was)
    _, code = gives_up(reviewer, "wait: jgauge room did not run", "mcp:1")
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


def test_a_check_that_never_ran_is_the_reason_the_section_gives(reviewer):
    (reviewer.stub / "jgauge").write_text("#!/bin/sh\nexit 127\n")
    (reviewer.stub / "jgauge").chmod(0o755)
    (why,), _ = reviewer()
    gives_up(reviewer, why, "mcp:1")
    assert reviewer.brief.read_text() == BRIEF + GAVE_UP.format(why="wait: jgauge room did not run")


@pytest.mark.parametrize("sent", ["not sent", "not sent, no home", None])
def test_a_give_up_nobody_was_told_of_writes_no_section_so_jbus_still_sees_no_review(
    reviewer, sent
):
    said = "no section: the line went to nobody, so the brief stays as it is and jbus tells the"
    if sent is None:
        printed, code = reviewer("### No room")
    else:
        printed, code = gives_up(reviewer, "wait: jgauge room did not run", sent)
    assert code == 0 and [line[: len(said)] for line in printed] == [said]
    assert reviewer.brief.read_text() == BRIEF
    assert ready.short_of(BRIEF, KEPT) == "it has no review yet"


def test_a_second_pass_that_gives_up_is_written_under_the_review_the_brief_has(reviewer):
    first = "\n## Review\nVerdict: clean\nHead: " + "b" * 40 + "\nSent to: mcp:1\n"
    reviewer.brief.write_text(BRIEF + first)
    _, code = gives_up(reviewer, "wait: jgauge room did not run", "mcp:1")
    assert code == 0
    assert reviewer.brief.read_text() == BRIEF + first + GAVE_UP.format(
        why="wait: jgauge room did not run"
    )


def test_each_review_builds_in_a_directory_of_its_own(reviewer):
    first, second = reviewer.prompt(), reviewer.prompt()
    assert first.parent != second.parent
    assert first.read_text() == second.read_text()
    assert all(path.name.startswith("pr-review-a-task.") for path in reviewer.built())


def calls(text):
    """Every JSON block of a skill, as an agent sends it, with its placeholders filled."""
    return [
        json.loads(body.replace("<model selection>", "null"))
        for kind, body in FENCED.findall(text)
        if kind == "json"
    ]


def test_a_review_starts_no_subagent_only_its_own_thread(reviewer):
    """The interrogate skill's reviewer is an `Agent` call, and `calls` finds it in that skill.
    The pr-review skill makes no such call, so a pull request has one review thread."""
    assert [each["description"] for each in calls((INTERROGATE / "SKILL.md").read_text())] == [
        "interrogate reviewer"
    ]
    made = calls(as_read(SKILL))
    assert [each for each in made if "subagent_type" in each or "description" in each] == []
    assert {each["message"] for each in made} == {
        "/pr-review run <slug> 1",
        "/pr-review run <slug> <n>",
    }
    assert reviewer.prompt().is_file()


def test_each_text_the_review_sends_its_reader_to_is_there(reviewer):
    """The section holds none of pstack's text. It names the files instead, so each file it
    names has to exist."""
    text = section("### The review")
    skills = set(re.findall(r"`\$T/\.\./(skills/[a-z-]+/SKILL\.md)`", text))
    assert skills == {"skills/interrogate/SKILL.md", "skills/blast-radius/SKILL.md"}
    references = set(re.findall(r"`references/([a-z-]+\.md)`", text))
    assert references == {
        "reviewer-prompt.md",
        "rubric.md",
        "code-quality-review.md",
        "lead-judgment.md",
    }
    assert references == {path.name for path in (INTERROGATE / "references").iterdir()}
    steps = re.findall(r"^## Step (\d),", (INTERROGATE / "SKILL.md").read_text(), re.M)
    assert steps == ["1", "2", "3", "4", "5"]
    blast = BLAST_RADIUS.read_text()
    assert "### How sure are you" in blast
    assert re.search(r"^2\. Find the one fact it's safe because of\.", blast, re.M)
    assert re.search(r"^5\. Prove the one fact\.", blast, re.M)
    made = reviewer.prompt().read_text()
    assert (INTERROGATE / "references" / "rubric.md").read_text() in made


@pytest.fixture
def proof(reviewer):
    """Run the proof block of step 5 over a script the reviewer wrote beside the prompt."""
    (reviewer.work / "real.sh").write_text("echo the real code ran\n")
    crew.git(reviewer.work, "add", "-A")
    crew.git(reviewer.work, "commit", "-q", "-m", "the change")
    beside = reviewer.prompt().parent
    kept = crew.git(reviewer.work, "rev-parse", "HEAD")

    def ends(script, limit=None, **env):
        (beside / "proof.sh").write_text(script)
        fill = {
            "<the directory of the prompt file>": str(beside),
            "<the head kept at the start>": kept,
            "<the proof>": 'sh "$D/proof.sh"',
            "<thread id>": "mcp:thread-1",
        }
        if limit is not None:
            fill["limit=540"] = f"limit={limit}"
        return reviewer("### The review", "test-slot", fill=fill, **env)

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


def test_a_proof_with_every_short_slot_taken_registers_the_thread_and_ends_76(proof, tmp_path):
    home = tmp_path / "taken"
    locks = home / ".local" / "state" / "locks"
    locks.mkdir(parents=True)
    held = []
    for n in range(1, 4):
        fd = os.open(locks / f"test-slot-short.{n}.lock", os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held.append(fd)
    try:
        printed, code = proof.ends("echo the fact holds\n", HOME=str(home))
    finally:
        for fd in held:
            os.close(fd)
    assert (printed[-1].split(":")[0], code) == ("waiting", 76)
    assert "exit" not in [line.split()[0] for line in printed]
    assert "mcp:thread-1 is registered as a waiter" in proof.out.read_text()
    waiting = json.loads((locks / "test-slot-waiters.json").read_text())
    assert [one["thread"] for one in waiting] == ["mcp:thread-1"]
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

    go.touch()
    began = time.monotonic()
    said, code = proof.ends(script, limit=30)
    assert (said[0].split(":")[0], said[1:3], code) == ("joined", ["exit 0", "the fact holds"], 0)
    assert time.monotonic() - began < 30
    assert runs.read_text() == "ran\n"


def test_a_proof_slow_to_start_is_neither_lost_nor_started_twice(proof, tmp_path):
    """The block records the proof's pid itself. So when the system starts a proof late, the
    block counts that proof as running from the first call, and no second call may start
    another."""
    delayed = proof.stub / "setsid"
    delayed.write_text(f'#!/bin/sh\nsleep 11\nexec {shutil.which("setsid")} "$@"\n')
    delayed.chmod(0o755)
    runs = tmp_path / "runs"
    script = f"echo ran >> {runs}\necho the fact holds\n"
    began = time.monotonic()
    said, code = proof.ends(script, limit=0)
    assert (said[0].split(":")[0], said[-1].split(":")[0], code) == ("started", "running", 0)
    assert time.monotonic() - began < 8
    said, code = proof.ends(script, limit=0)
    assert (said[0].split(":")[0], said[-1].split(":")[0]) == ("joined", "running")
    assert not runs.exists()


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
    go.touch()
    said, code = proof.ends("echo the new fact\n", limit=30)
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
    """A pull request's worktree at the head a reviewer kept, and what GitHub says its head is."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path, None, "other.txt")
        self.started = crew.git(self.work, "rev-parse", "HEAD~1")
        self.commit(self.work, "second.txt", "more\n", "the second commit")
        self.says_head(self.head())

    def says_head(self, head):
        view = {"baseRefName": "main", "headRefOid": head}
        (self.stub / "view.json").write_text(json.dumps(view))

    def patch_id(self, since, head):
        patch = crew.git(self.work, "diff", since, head) + "\n"
        named = subprocess.run(
            ["git", "patch-id", "--stable"], input=patch, capture_output=True, text=True, check=True
        )
        return named.stdout.split()[0]

    def checked(self, kept):
        script = block("### After the review", "patch-id").replace("<url>", URL)
        script = script.replace("<the head kept at the start>", kept)
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
    pr.says_head(pr.head())
    assert pr.checked(pr.head()) == (
        [f"Head: {pr.head()}   Unchanged by the review: yes", patch],
        0,
    )
    pr.commit(pr.work, "third.txt", "wider\n", "a fix")
    pr.says_head(pr.head())
    assert pr.checked(pr.head())[0][1] not in (patch, "Patch-id: ")


def moved_on_github(pr):
    pr.says_head("c" * 40)


def moved_here(pr):
    pr.commit(pr.work, "third.txt", "more\n", "pushed during the review")


def left_uncommitted(pr):
    (pr.work / "left.txt").write_text("a proof wrote here\n")


@pytest.mark.parametrize("moved", [moved_on_github, moved_here, left_uncommitted])
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
    shutil.rmtree(tmp_path / "origin.git")
    assert pr.checked(head) == (
        [
            f"Head: {head}   Unchanged by the review: yes",
            "Patch-id: not worked out, could not fetch origin/main",
        ],
        1,
    )
    (pr.stub / "view.json").unlink()
    assert pr.checked(head) == (
        [
            f"Head: {head}   Unchanged by the review: not checked, could not ask GitHub",
            "Patch-id: not worked out, could not ask GitHub",
        ],
        1,
    )
    state = tmp_path / "state"
    (state / "tasks").mkdir(parents=True)
    section = "\n".join(pr.checked(head)[0])
    brief = f"{crew.BRIEF}\n## Review\nVerdict: findings\n{section}\nFindings:\n- info a.py it\n"
    (state / "tasks" / "alpha.md").write_text(brief)
    ran = subprocess.run(
        ["sh", "-c", crew.block("The review", "Second pass:").replace("<slug>", "alpha")],
        capture_output=True,
        text=True,
        cwd=pr.work,
        env={**os.environ, "H": str(state)},
        check=True,
    )
    assert ran.stdout == "write Scoped review: none, nothing was pushed for the findings\n"


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


def test_what_the_lead_set_aside_is_no_finding_to_whoever_counts_the_section(reviewer):
    """The lead puts the lines it dismissed under `Dropped:`, where the crew skill stops
    counting."""
    template = REVIEW.read_text()
    labels = [line.split(":")[0] for line in template.splitlines()]
    after = labels[labels.index("Dropped") :]
    assert after[:3] == ["Dropped", "Noted", "Dismissed"]
    (finding,) = [line for line in template.splitlines() if line.startswith("- <severity>")][:1]
    assert "(bucket: Act on | Consider)" in finding
    review = template.replace(
        finding,
        "- warning a.py:3 it runs twice (principle: principle-make-operations-idempotent) "
        "(bucket: Act on)",
        1,
    )
    reviewer.brief.write_text(BRIEF + "\n## Result\nStatus: done\n\n" + review)
    counts = crew.block("The review", "--left").replace("<slug>", "a-task")
    ran = subprocess.run(
        ["sh", "-c", counts],
        env={**os.environ, "H": str(reviewer.state), "T": str(assembled() / "templates")},
        capture_output=True,
        text=True,
        check=True,
    )
    assert ran.stdout == "not yet: 1 of 1 findings have no Finding: line: F1\n"


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


def test_the_count_dropped_is_a_line_of_the_review_section(reviewer):
    reviewer.gh()
    (count,) = reviewer.output("### Outside the diff")
    template = REVIEW.read_text()
    labels = [line.split(":")[0] for line in template.splitlines()]
    assert count == "Dropped: 0"
    assert count.split(":")[0] in labels


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


def test_a_file_outside_the_brief_where_is_listed(reviewer):
    branch_of_the_task(
        reviewer,
        "`src/a.py`, `tests/`",
        "src/a.py",
        "tests/deep/test_a.py",
        "README.md",
        "src/a.pyc",
        "hooks/x.sh",
    )
    assert reviewer.output("### Wider than the brief") == [
        "outside: README.md",
        "outside: hooks/x.sh",
        "outside: src/a.pyc",
    ]


def test_a_file_the_result_gives_a_reason_for_is_wider_and_not_outside(reviewer):
    branch_of_the_task(
        reviewer,
        "`src/a.py`",
        "src/a.py",
        "README.md",
        "hooks/x.sh",
        result="\n## Result\nWider: README.md: a test reads it\n",
    )
    assert reviewer.output("### Wider than the brief") == [
        "wider: README.md: a test reads it",
        "outside: hooks/x.sh",
    ]


def test_a_diff_inside_the_where_prints_nothing(reviewer):
    branch_of_the_task(reviewer, "`src/`", "src/a.py")
    assert reviewer.output("### Wider than the brief") == []


def test_a_brief_whose_where_names_no_path_is_not_read_as_no_wider(reviewer):
    branch_of_the_task(reviewer, "wherever it takes", "README.md")
    assert reviewer("### Wider than the brief") == ([], 1)


def gated(reviewer, gate=None, fill=None):
    """Make a pull request whose branch has one commit on top of main, and a repo state
    with the merge gate `gate`, or with no merge gate when `gate` is None. Run the
    reviewer's "The merge gate" at the head, with the block's words in `fill` changed too.
    Return what the block printed, its exit code, the merge base and the head."""
    work = reviewer.work
    origin = reviewer.state / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True)
    for args in (
        ["checkout", "-q", "-b", "main"],
        ["commit", "-q", "--allow-empty", "-m", "main"],
        ["remote", "add", "origin", str(origin)],
        ["push", "-q", "origin", "main"],
        ["checkout", "-q", "-b", "a-task"],
        ["commit", "-q", "--allow-empty", "-m", "the task"],
    ):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=work, check=True
        )
    fork, head = (
        subprocess.run(
            ["git", "rev-parse", ref], cwd=work, capture_output=True, text=True
        ).stdout.strip()
        for ref in ("main", "HEAD")
    )
    (reviewer.stub / "view.json").write_text(
        json.dumps({"baseRefName": "main", "headRefOid": head})
    )
    if gate is not None:
        (reviewer.state / "merge-gate").write_text(f"\n  {gate}  \n")
    fill = {"<the head kept at the start>": head, **(fill or {})}
    printed, code = reviewer("### The merge gate", fill=fill)
    return printed, code, fork, head


def test_a_failing_merge_gate_is_one_error_finding_on_what_the_change_lacks(reviewer, tmp_path):
    called = tmp_path / "called"
    script = tmp_path / "receipt-check"
    script.write_text(
        '#!/bin/sh\necho "$@" "$BASE" "$HEAD" > "$CALLED"\n'
        "echo 'no passing receipt covers jmerge'\necho 'replay it' >&2\nexit 1\n"
    )
    script.chmod(0o755)
    printed, code, fork, head = gated(reviewer, f"CALLED={called} {script}")
    assert code == 0
    assert printed == [
        f"error - the merge gate fails at {head[:12]}: no passing receipt covers jmerge "
        "(principle: none) (bucket: Act on)"
    ]
    assert called.read_text().split() == [fork, head, fork, head]
    review = f"## Review\nVerdict: findings\nHead: {head}\nFindings:\n- {printed[0]}\n"
    (finding,) = findings.triage(BRIEF + "\n" + review).blocking()
    assert (finding.lead.severity, finding.lead.place) == ("error", "-")


@pytest.mark.parametrize("gate", [None, "true"])
def test_no_merge_gate_or_one_that_passes_prints_nothing(reviewer, gate):
    assert gated(reviewer, gate)[:2] == ([], 0)


def test_a_merge_gate_that_cannot_start_is_a_finding_too(reviewer, tmp_path):
    (printed,), code, _, head = gated(reviewer, str(tmp_path / "missing"))
    assert code == 0
    assert printed.startswith(f"error - the merge gate fails at {head[:12]}: merge-gate: ")
    assert printed.endswith("(principle: none) (bucket: Act on)")


def test_a_merge_gate_that_runs_over_the_limit_is_stopped_and_says_so(reviewer):
    printed, code, _, head = gated(reviewer, "sleep 30; :", fill={"limit=540": "limit=1"})
    assert code == 0
    assert printed == [
        f"error - the merge gate fails at {head[:12]}: it ran over 1 s and was stopped "
        "(principle: none) (bucket: Act on)"
    ]


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
    assert reviewer.output("## Launching") == ([reviewer_thread] if reviewer_thread else [])


def test_the_home_is_told_only_when_it_left_its_thread_id(reviewer):
    assert reviewer.output("### Telling the home", B=str(reviewer.brief)) == []
    (reviewer.state / "home-id").write_text("mcp:home\n")
    assert reviewer.output("### Telling the home", B=str(reviewer.brief)) == ["mcp:home"]


@pytest.mark.parametrize(
    ("thread", "home", "goes", "told"),
    [
        ("Thread: mcp:1\n", None, "crewmate mcp:1", ""),
        ("Thread: mcp:1\n", "", "crewmate mcp:1", ""),
        ("Thread: mcp:1\n", "mcp:home\n", "crewmate mcp:1", "mcp:home"),
        ("", "mcp:home\n", "home", "mcp:home"),
        ("", "", "home", ""),
        ("", None, "home", ""),
        pytest.param(
            "Decisions: a `Thread: mcp:9` line is quoted\n",
            "",
            "home",
            "",
            id="words inside another line are not the brief's own field",
        ),
    ],
)
def test_the_findings_go_to_the_thread_line_with_a_home_or_with_none(
    reviewer, thread, home, goes, told
):
    """The test runs step 4 of "After the review", then the block that finds a home. With no
    `Thread:` line and an empty or missing `home-id`, the block finds nobody, and the section
    says `not sent`."""
    reviewer.brief.write_text(BRIEF.replace("Thread: mcp:1\n", thread))
    if home is not None:
        (reviewer.state / "home-id").write_text(home)
    assert where(reviewer, "findings").split(": ")[0] == goes
    told_now = reviewer.output("### Telling the home", B=str(reviewer.brief))
    assert told_now == ([told] if told else [])


DONE = f"\n## Result\nStatus: done\nBranch: a-task   Pull request: {URL}\n"
HEAD = "b" * 40
VERDICT = "<clean, findings or not run>"
NOT_SENT = "Sent to: not sent, clean"
FOUND = "- warning src/a.py:2 it is wrong\n"
FIXED = f"Finding: fixed, it is wrong\nFixed: {'c' * 40}\n"


def reviewed(verdict, findings="- none\n"):
    return (
        f"\n## Review\nVerdict: {verdict}\nHead: {'b' * 40}\nFindings:\n{findings}Sent to: mcp:1\n"
    )


def where(reviewer, verdict=VERDICT, mergeable="MERGEABLE", checks=(), **more):
    """What step 4 of "After the review" prints for a pass with this verdict. It reads the brief on
    disk and what GitHub says of the pull request."""
    (reviewer.stub / "view.json").write_text(
        json.dumps({"mergeable": mergeable, "headRefOid": HEAD, "statusCheckRollup": list(checks)})
    )
    (said,), code = reviewer(
        "### After the review", "crewmate $thread", fill={VERDICT: verdict}, **more
    )
    assert code == 0
    return said


SECOND = reviewed("findings", FOUND) + FIXED + "Second pass: needed since b, it went wider\n"
SCOPED = reviewed("clean") + "Fixed: none needed, a clean review\nScoped reviewer: mcp:9, of c\n"
CREW = "crewmate mcp:1"
PASSES = {
    "a clean second pass": (SECOND, "clean", "nobody"),
    "a clean scoped pass": (SCOPED, "clean", "nobody"),
    "a clean first pass": ("", "clean", CREW),
    "a clean pass after one that was not run": (reviewed("not run") + FIXED, "clean", CREW),
    "a second pass with findings": (SECOND, "findings", CREW),
    "a second pass that was not run": (SECOND, "not run", CREW),
    "a clean later pass before the Fixed line": (reviewed("findings", FOUND), "clean", CREW),
    "a verdict nobody filled in": (SECOND, VERDICT, "not filled in"),
}


@pytest.mark.parametrize("case", PASSES)
def test_a_clean_pass_after_the_first_is_sent_to_nobody_and_any_other_goes_as_before(
    reviewer, case
):
    result, verdict, goes = PASSES[case]
    reviewer.brief.write_text(BRIEF + DONE + result)
    said = where(reviewer, verdict)
    assert said.split(": ")[0] == goes
    assert said.endswith(NOT_SENT) == (goes == "nobody")


@pytest.mark.parametrize("mergeable", ["CONFLICTING", "UNKNOWN", None])
def test_a_clean_later_pass_is_sent_while_github_does_not_say_mergeable(reviewer, mergeable):
    """While a review is running, the crewmate waits with its rebase until the reviewer
    writes the section, and goes on when the reviewer's message comes."""
    reviewer.brief.write_text(BRIEF + DONE + SECOND)
    assert where(reviewer, "clean").startswith("nobody: ")
    if mergeable is None:
        (reviewer.stub / "down").write_text("view\n")
    assert where(reviewer, "clean", mergeable or "MERGEABLE").startswith("crewmate mcp:1: ")


def asked_to_rebase(tmp_path, monkeypatch, slug, head):
    """Run a pass of the real jbus. The pass tells the crewmate to rebase, because the
    crewmate's pull request is stale at this head. Return the directory where jbus keeps its
    state."""
    kitchen = Kitchen(tmp_path / "kitchen", monkeypatch)
    add(kitchen, slug)
    kitchen.poll(NOW - timedelta(minutes=30))
    kitchen.t3.threads[0]["status"] = "completed"
    kitchen.set("open.json", [{**kitchen.opened(slug, 7), "headRefOid": head}])
    kitchen.set("jmerge.txt", f"wait 7 {URL}: {unlock.CHANGED}: it needs a rebase\n")
    kitchen.poll()
    kitchen.close()
    assert len(unlock.sends(kitchen)) == 1
    return str(kitchen.state_dir)


@pytest.mark.parametrize(
    ("slug", "head", "goes"),
    [("a-task", HEAD, CREW), ("a-task", "d" * 40, "nobody"), ("b-task", HEAD, "nobody")],
    ids=["this head", "a head it left", "another task"],
)
def test_a_clean_later_pass_is_sent_when_jbus_asked_for_a_rebase_at_this_head(
    reviewer, tmp_path, monkeypatch, slug, head, goes
):
    """jbus asks for a rebase once for each head, even while GitHub says MERGEABLE. The crewmate
    puts the rebase off until the review that is running has sent its message."""
    state = asked_to_rebase(tmp_path, monkeypatch, slug, head)
    reviewer.brief.write_text(BRIEF + DONE + SECOND)
    assert where(reviewer, "clean", JBUS_STATE_DIR=state).split(": ")[0] == goes


CHECKS = [
    ([merge.PASSED], "nobody"),
    ([merge.RUNNING], "nobody"),
    ([merge.PASSED, merge.FAILED], CREW),
    ([{"state": "FAILURE"}], CREW),
    ([{"state": "PENDING"}], "nobody"),
]


@pytest.mark.parametrize(("checks", "goes"), CHECKS)
def test_a_clean_later_pass_is_sent_while_a_check_is_red(reviewer, checks, goes):
    """When main moves and a crewmate's pull request is red, jbus tells that crewmate to rebase. The
    crewmate puts the rebase off while a review is running. A check that is still running is no
    reason to rebase, since the watch wakes the crewmate."""
    reviewer.brief.write_text(BRIEF + DONE + SECOND)
    assert where(reviewer, "clean", checks=checks).split(": ")[0] == goes


def test_a_rebase_that_came_while_the_section_was_written_is_seen_on_the_second_run(
    reviewer, tmp_path, monkeypatch
):
    """Step 5 runs the block again over the brief with this pass's own section in it."""
    reviewer.brief.write_text(BRIEF + DONE + SECOND)
    assert where(reviewer, "clean").startswith("nobody: ")
    section = reviewed("clean").replace("Sent to: mcp:1", NOT_SENT)
    reviewer.brief.write_text(reviewer.brief.read_text() + section)
    assert where(reviewer, "clean").startswith("nobody: ")
    state = asked_to_rebase(tmp_path, monkeypatch, "a-task", HEAD)
    assert where(reviewer, "clean", JBUS_STATE_DIR=state).startswith(f"{CREW}: ")


def who_merges(reviewer):
    """What the crew skill's own check prints before a `fixed and green` line."""
    asks = crew.block("Telling the home", "home-thread")
    assert "<fixed or waits>" in asks
    ran = subprocess.run(
        ["sh", "-c", asks.replace("<fixed or waits>", "fixed").replace("<slug>", "a-task")],
        env={**os.environ, "H": str(reviewer.state)},
        capture_output=True,
        text=True,
        check=True,
    )
    return ran.stdout.strip()


@pytest.mark.parametrize("switch", ["", " \n", "mcp:home\n"])
@pytest.mark.parametrize("scope", [None, "id", "handed off", "handed off, by its id", "name"])
def test_a_clean_later_pass_is_quiet_only_where_the_crewmate_would_send_nothing(
    reviewer, switch, scope
):
    """A home that merges hears `fixed and green` from the crewmate. For a scoped home, the crewmate
    parks the pull request as a gate instead. The crew skill's check says that jbus must wake
    the crewmate in both cases."""
    (reviewer.state / "home-thread").write_text(switch)
    home = ""
    if scope:
        (reviewer.state / "speed").mkdir()
        (reviewer.state / "speed" / "plan.md").write_text("# a plan\n")
        named = "handoff.md" if scope.startswith("handed off") else "home-id"
        owner = (
            "# handoff\n\nWas home: mcp:two\n" if scope.startswith("handed off") else "mcp:two\n"
        )
        (reviewer.state / "speed" / named).write_text(owner)
        home = f"Home: {'mcp:two' if scope.endswith('id') else 'speed'}\n"
    reviewer.brief.write_text(BRIEF + home + DONE + SECOND)
    nothing = who_merges(reviewer).startswith("jbus merges: send nothing")
    assert nothing == (not switch.strip() and not scope)
    assert where(reviewer, "clean").startswith("nobody: ") == nothing


def later_pass(made, result, first, files=("a.txt",), run=None):
    """What `jmerge` says of a pull request whose first review had a finding that the head fixes.
    The brief has the lines the crewmate wrote then, and after them whatever a later pass left. The
    crewmate writes nothing after that pass."""
    done = f"Finding: fixed, it is wrong\nFixed: {made.head}\n{result}"
    made.home.open_pull_request(made.head, checks=(guarded.STARTED,), files=list(files))

    def says(section=""):
        (made.home.tasks / "alpha.md").write_text(merge.brief(first + section, done))
        return (run or made.run)("--check")

    return says


def test_jmerge_reads_a_clean_second_pass_nobody_was_sent_as_ready(tmp_path):
    made = merge.Merged(merge.Home(tmp_path), tmp_path)
    says = later_pass(made, merge.WIDER, merge.review("findings"))
    assert says() == [
        f"wait 7 {merge.URL}: its fix changed more than the findings named: "
        "the second pass is not written"
    ]
    assert says(merge.review("clean", made.head) + f"{NOT_SENT}\n") == [
        f"ready 7 {made.head} alpha alpha"
    ]


def test_jmerge_reads_a_guarded_fixs_clean_scoped_pass_nobody_was_sent_as_ready(tmp_path):
    rules = guarded.checkout(tmp_path, guarded.LISTED)
    made = merge.Merged(merge.Home(tmp_path), tmp_path)
    asked = (
        "Second pass: none, the fix stayed inside the files the findings named\n"
        f"Scoped review: needed since {made.start}, guarded\n"
        f"Scoped reviewer: mcp:9, of {made.head}\n"
    )
    says = later_pass(
        made,
        asked,
        guarded.proven("findings", made.start),
        files=[guarded.SKILL],
        run=lambda *flags: guarded.jmerge(made, rules, *flags),
    )
    short = f"no proven safety fact at {made.head[:12]} (blast-radius, review step 5)"
    assert says() == guarded.guarded(short)
    scoped = guarded.proven("clean", made.head) + f"Scope: range-diff a..b a..c\n{NOT_SENT}\n"
    assert says(scoped) == [f"ready 7 {made.head} alpha alpha, guarded: {guarded.SKILL}"]


def readiness():
    """The block that a launcher uses to find the ready briefs, as an agent reads it."""
    (found,) = [text for text in as_read(SKILL).split("```") if "PASS=first" in text]
    return textwrap.dedent(found.removeprefix("sh\n"))


class Launcher:
    """A home's state directory with one brief, and a stub `gh` for its pull request."""

    def __init__(self, tmp_path, rollup=crew.ROLLUPS["all passed"][0], state="OPEN"):
        self.state = tmp_path
        (tmp_path / "tasks").mkdir()
        self.brief = tmp_path / "tasks" / "a-task.md"
        self.brief.write_text(BRIEF + DONE)
        self.stub = tmp_path / "stub"
        crew.stub_gh(self.stub, HEAD, rollup, state)

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


@pytest.mark.parametrize("case", crew.ROLLUPS)
def test_a_brief_is_ready_while_its_checks_run_and_once_they_passed(case, tmp_path):
    rollup, answer = crew.ROLLUPS[case]
    if rollup is None:
        launcher = Launcher(tmp_path, [])
        (launcher.stub / "gh").write_text(
            crew.GH.replace('"pr view")', '"pr view") [ "$5" = state ] &&')
        )
    else:
        launcher = Launcher(tmp_path, rollup)
    (said,) = launcher.says()
    if answer == "passed" or (answer == "wait" and rollup is not None):
        assert said == f"a-task: ready, {URL} at {HEAD}"
    else:
        assert said.startswith(f"a-task: not ready, its checks, {answer}: ")


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


def test_checks_that_could_not_be_read_are_not_ready_though_a_later_call_names_the_head(tmp_path):
    launcher = Launcher(tmp_path, crew.ROLLUPS["one ran and failed"][0])
    rollup = '"pr view") [ "$5" != headRefOid,statusCheckRollup ] &&'
    (launcher.stub / "gh").write_text(crew.GH.replace('"pr view")', rollup))
    assert launcher.says() == ["a-task: not ready, its checks, wait: could not ask GitHub"]


@pytest.mark.parametrize("case", ["none ran", "all skipped"])
def test_checks_that_did_not_run_are_never_ready_whatever_the_result_says_stood_in(case, tmp_path):
    launcher = Launcher(tmp_path, crew.ROLLUPS[case][0])
    unrun = [f"a-task: not ready, its checks, unrun: no check ran at {HEAD}"]
    assert launcher.says() == unrun
    stood_in = f"CI: did not run at {HEAD}, `make check` passed in this worktree at that head\n"
    launcher.brief.write_text(BRIEF + DONE + stood_in)
    assert launcher.says() == unrun


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


@pytest.mark.parametrize("had", ["\n## Review\nVerdict: findings\n", "Reviewer: mcp:9\n"])
def test_a_second_pass_is_ready_with_a_review_and_not_over_a_failed_check(had, tmp_path):
    launcher = Launcher(tmp_path)
    launcher.brief.write_text(BRIEF + DONE + had)
    assert launcher.says(again=True) == [f"a-task: ready, {URL} at {HEAD}"]
    view = {"state": "OPEN", "headRefOid": HEAD, "statusCheckRollup": [crew.RUNNING]}
    (launcher.stub / "view.json").write_text(json.dumps(view))
    assert launcher.says(again=True) == [f"a-task: ready, {URL} at {HEAD}"]
    view["statusCheckRollup"] = crew.ROLLUPS["one ran and failed"][0]
    (launcher.stub / "view.json").write_text(json.dumps(view))
    assert launcher.says(again=True) == [
        "a-task: not ready, its checks, failed: a check ran and failed"
    ]


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


def rebased(reviewer, why="the task replaces it", line=True):
    """A worktree whose rebase took main's line out of n.txt, and a brief in which the crewmate
    says why, at the rebased head. The worktree keeps the head from before the rebase in the ref
    where the crew skill keeps it. The crew skill's rebase writes no `Rebase:` line, so the brief
    that `line=False` makes is the one a crewmate writes."""
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
    told = f"Rebase: patch changed in n.txt, before {before}, head {head}\n" if line else ""
    reviewer.brief.write_text(BRIEF + DONE + f"{told}{said}\n")
    return before, head, said


def drops(reviewer):
    return reviewer.output("### A scoped pass", "Dropped on rebase")


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


def test_a_drop_is_read_from_the_ref_the_crew_kept_when_the_brief_has_no_rebase_line(reviewer):
    before, head, said = rebased(reviewer, line=False)
    first, line, *diff = drops(reviewer)
    assert (first, line) == ("drop: n.txt", said)
    assert [each for each in diff if each[:1] in "+-" and each[:2] not in ("++", "--")] == [
        "-theirs"
    ]


def test_with_no_rebase_line_the_newest_kept_head_is_the_one_before_the_last_rebase(reviewer):
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
        "not upheld: the head before the rebase is not kept under "
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
    f"Head: {FIX}   Unchanged by the review: yes\nFindings:\n- none\nSent to: not sent, clean\n"
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
    ("done", "ready_to_merge"),
    [(ANSWERED, True), ("", False)],
    ids=["its finding answered", "nothing answered"],
)
def test_jmerge_reads_a_review_written_from_the_template_by_one_reader_as_ready(
    tmp_path, done, ready_to_merge
):
    made = merge.Merged(merge.Home(tmp_path), tmp_path)
    filled = {
        "Verdict": "findings",
        "Head": f"{made.head}   Unchanged by the review: yes",
        "Patch-id": "0" * 40,
        "Reviewers": "1, 1   Proof: uv run pytest tests/test_a.py, exit 0, 1 passed",
        "Meets the brief": "yes",
        "In flight": "none",
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
            lines += [line, "- warning a.txt:1 it is wrong (principle: none)"]
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


def test_the_reviewer_is_told_of_no_skill_when_the_line_names_none(reviewer):
    text = BRIEF.replace("Pull request:", "Skills: none, docs\nPull request:")
    reviewer.brief.write_text(text)
    assert "loaded each in full" not in intent(reviewer)
