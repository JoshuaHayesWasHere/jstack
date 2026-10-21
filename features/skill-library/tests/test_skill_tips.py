"""`features/skill-library/hooks/skill-tips.sh`: the one line it gives for a prompt that
matches a skill, and every place it stays silent. Every test runs the hook, on a copy beside a
temporary `skills/`, or the repo's own."""

import json
import os
import re
import shutil
import subprocess
import time

import pytest

from testing.layouts import assembled
from testing.paths import REPO, skills

HOOK = REPO / "features" / "skill-library" / "hooks" / "skill-tips.sh"
INSTALLED = assembled() / "hooks" / "skill-tips.sh"
T3 = ("T3_CODE_MCP_AUTHORIZATION", "T3_MCP_BEARER_TOKEN")
SESSION = "0b1f6c1e-aaaa-4bbb-8ccc-1234567890ab"

BLAST = "finds what a small diff could break elsewhere | blast radius | what could this break"
KETCHUP = "catches you up on this chat | catch me up | catch me up on this chat"
HOW = "explains how a subsystem works | how does * work"


def git(cwd, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", *identity, *args], cwd=cwd, check=True, capture_output=True)


class Scene:
    """A user's home directory, a copy of the hook beside its own `skills/`, and a repo."""

    def __init__(self, tmp_path):
        self.user = tmp_path / "user"
        self.user.mkdir()
        self.state = self.user / ".local" / "state" / "skill-tips"
        self.root = tmp_path / "jstack"
        (self.root / "hooks").mkdir(parents=True)
        self.hook = self.root / "hooks" / "skill-tips.sh"
        shutil.copy(HOOK, self.hook)
        self.skills = self.root / "skills"
        self.main = tmp_path / "code" / "demo"
        self.main.mkdir(parents=True)
        git(self.main, "init", "-q")
        git(self.main, "commit", "-q", "--allow-empty", "-m", "first")
        self.skill("blast-radius", BLAST)
        self.skill("ketchup", KETCHUP)
        self.skill("how", HOW)
        self.skill("bro")

    def skill(self, name, tip=None):
        (self.skills / name).mkdir(parents=True)
        line = f"tip: {tip}\n" if tip else ""
        (self.skills / name / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Does a thing. Use for /{name}.\n{line}"
            f"disable-model-invocation: true\n---\n# {name}\n\ntip: not this | body words\n"
        )

    def send(self, stdin, *, t3=False, path=None, hook=None):
        """Run the hook as the harness does, and give back what it printed. It never fails."""
        env = {key: value for key, value in os.environ.items() if key not in T3}
        env["HOME"] = str(self.user)
        if t3:
            env[T3[0] if t3 is True else t3] = "x"
        if path:
            env["PATH"] = str(path)
        sh = shutil.which("sh")
        done = subprocess.run(
            [sh, str(hook or self.hook)], input=stdin, capture_output=True, env=env
        )
        assert done.returncode == 0
        return done.stdout.decode()

    def type(self, prompt, *, session=SESSION, cwd=None, **how):
        """What the hook prints when a person types this prompt in a thread opened in `cwd`."""
        fields = {
            "session_id": session,
            "cwd": str(cwd or self.main),
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt,
        }
        return self.send(json.dumps(fields).encode(), **how)

    def tip(self, prompt, **how):
        """The line the user is shown in a terminal for this prompt, or None for no tip."""
        said = self.type(prompt, **how)
        if not said:
            return None
        (shown,) = json.loads(said).values()
        return shown


@pytest.fixture
def scene(tmp_path):
    return Scene(tmp_path)


BLAST_TIP = "tip: /blast-radius finds what a small diff could break elsewhere"


def test_a_prompt_that_matches_a_skill_gets_its_one_line(scene):
    assert scene.type("so what could this break if I ship it?") == json.dumps(
        {"systemMessage": BLAST_TIP}, separators=(",", ":")
    )


def test_a_prompt_that_matches_nothing_gets_nothing(scene):
    assert scene.type("rename the function to parse_rows") == ""
    assert not scene.state.exists()


def test_a_skill_added_later_gets_tips_with_no_edit_to_the_hook(scene):
    assert scene.tip("please squash the migrations") is None
    scene.skill("squash", 'folds "old" migrations \\ into one | squash the migrations')
    assert (
        scene.tip("please squash the migrations")
        == 'tip: /squash folds "old" migrations \\ into one'
    )


def test_a_skill_with_no_tip_line_gets_none_whatever_its_body_says(scene):
    assert scene.tip("body words") is None


def test_the_match_is_by_whole_words_and_not_by_case(scene):
    assert scene.tip("BLAST-RADIUS,\nplease", session="a") == BLAST_TIP
    assert scene.tip("Blast  Radius?", session="b") == BLAST_TIP
    for near in [
        "blast radiuses",
        "sandblast radius",
        "blast the radius",
        "what could this breaker",
    ]:
        assert scene.tip(near, session="c") is None


def test_a_star_in_a_trigger_stands_for_one_to_four_words(scene):
    assert scene.tip("how does the start hook work", session="a") == (
        "tip: /how explains how a subsystem works"
    )
    assert scene.tip("how does work", session="b") is None
    assert scene.tip("how does one two three four five work", session="b") is None


def test_one_tip_a_prompt_the_longest_trigger_that_matches(scene):
    assert scene.tip("catch me up on this chat, what could this break", session="a") == (
        "tip: /ketchup catches you up on this chat"
    )
    assert scene.tip("catch me up, and what could this break", session="b") == BLAST_TIP


@pytest.mark.parametrize(
    "prompt", ["/crew what could this break", "  $how blast radius", "\n\t /how blast radius"]
)
def test_a_prompt_that_starts_with_a_skill_gets_no_tip(scene, prompt):
    assert scene.type(prompt) == ""


def test_never_a_tip_for_the_skill_the_prompt_names(scene):
    assert scene.tip("run /blast-radius: what could this break") is None
    assert scene.tip("is $blast-radius the one for what could this break") is None
    assert scene.tip("after /blast-radius, catch me up") == (
        "tip: /ketchup catches you up on this chat"
    )
    assert scene.tip("then /blast-radius-2 says what could this break") == BLAST_TIP


def test_never_the_same_skill_twice_in_a_session(scene):
    assert scene.tip("what could this break") == BLAST_TIP
    assert scene.tip("what could this break") is None
    assert scene.tip("blast radius, and catch me up") == "tip: /ketchup catches you up on this chat"
    assert scene.tip("what could this break", session="another") == BLAST_TIP
    assert (scene.state / SESSION).read_text() == "blast-radius\nketchup\n"


def test_a_pasted_log_does_not_slow_the_prompt(scene):
    log = "x \t\n" * 100_000
    began = time.perf_counter()
    assert scene.tip("what could\nthis break:\n" + log) == BLAST_TIP
    assert time.perf_counter() - began < 0.5


def test_only_the_first_4000_characters_of_a_prompt_are_read(scene):
    assert scene.tip("x" * 3978 + " what could this break") == BLAST_TIP
    assert scene.tip("x" * 3980 + " what could this break", session="b") is None


def test_the_off_file_switches_it_off(scene):
    scene.state.mkdir(parents=True)
    (scene.state / "off").write_text("")
    assert scene.type("what could this break") == ""


def test_silent_in_a_worktree_where_crewmates_scouts_and_reviewers_run(scene, tmp_path):
    worktree = tmp_path / "worktrees" / "a-task"
    git(scene.main, "worktree", "add", "-q", "-b", "a-task", str(worktree))
    assert scene.type("what could this break", cwd=worktree) == ""
    (worktree / "deep").mkdir()
    assert scene.type("what could this break", cwd=worktree / "deep") == ""
    assert scene.tip("what could this break") == BLAST_TIP


def test_a_folder_that_is_no_repo_is_a_place_a_person_types(scene, tmp_path):
    (tmp_path / "plain").mkdir()
    assert scene.tip("what could this break", cwd=tmp_path / "plain") == BLAST_TIP


@pytest.mark.parametrize("t3", T3)
def test_in_t3_code_the_line_goes_to_the_agent_to_pass_on_and_not_to_act_on(scene, t3):
    said = json.loads(scene.type("what could this break", t3=t3))
    assert list(said) == ["hookSpecificOutput"]
    assert said["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    told = said["hookSpecificOutput"]["additionalContext"]
    assert told.count(f"`{BLAST_TIP}`") == 1
    assert "Do not invoke" in told
    assert "\n" not in told


def without(tmp_path, *missing):
    """A PATH with what the hook runs, but for these commands."""
    bin = tmp_path / "bin"
    bin.mkdir()
    for name in ["sh", "cat", "awk", "git", "jq", "dirname", "mkdir"]:
        if name not in missing:
            (bin / name).symlink_to(shutil.which(name))
    return bin


def test_the_path_the_failure_cases_run_on_is_enough_for_a_tip(scene, tmp_path):
    assert scene.tip("what could this break", path=without(tmp_path)) == BLAST_TIP


@pytest.mark.parametrize(
    "missing",
    ["jq", "awk", pytest.param("git", id="git, with which goes the check for a worktree"), "mkdir"],
)
def test_a_command_that_is_not_there_gets_nothing(scene, tmp_path, missing):
    said = scene.type("what could this break", path=without(tmp_path, missing))
    assert said == ""


@pytest.mark.parametrize(
    "stdin",
    [
        b"",
        b"not json",
        b"[1, 2]",
        b'{"prompt": "what could this break"}',
        json.dumps({"session_id": SESSION, "cwd": "/", "prompt": 7}).encode(),
        json.dumps({"session_id": SESSION, "cwd": 7, "prompt": "what could this break"}).encode(),
        json.dumps({"session_id": "../x", "cwd": "/", "prompt": "what could this break"}).encode(),
        json.dumps({"session_id": "off", "cwd": "/", "prompt": "what could this break"}).encode(),
        json.dumps({"session_id": "", "cwd": "/", "prompt": "what could this break"}).encode(),
        json.dumps(
            {"session_id": SESSION, "cwd": "/no/such/place", "prompt": "what could this break"}
        ).encode(),
    ],
)
def test_bad_input_gets_nothing(scene, stdin):
    assert scene.send(stdin) == ""
    assert not (scene.user / ".local").exists()


def test_no_skills_directory_gets_nothing(scene):
    shutil.rmtree(scene.skills)
    assert scene.type("what could this break") == ""


def test_a_skill_file_that_is_no_skill_is_passed_over(scene):
    (scene.skills / "empty").mkdir()
    (scene.skills / "empty" / "SKILL.md").write_text("")
    (scene.skills / "bare").mkdir()
    (scene.skills / "bare" / "SKILL.md").write_text("tip: no frontmatter | what could this break\n")
    (scene.skills / "odd").mkdir()
    (scene.skills / "odd" / "SKILL.md").write_text("---\nname: odd\ntip: | | \n---\n")
    (scene.skills / "nameless").mkdir()
    (scene.skills / "nameless" / "SKILL.md").write_text("---\ntip: x | catch me up\n---\n")
    assert scene.tip("what could this break, catch me up") == BLAST_TIP


def test_a_state_directory_that_cannot_be_written_gets_nothing(scene):
    scene.state.parent.mkdir(parents=True)
    scene.state.write_text("a file where the directory goes")
    assert scene.type("what could this break") == ""


def tip_lines():
    """Each of the repo's skills that has a `tip:` line: its name, what it is for, its triggers."""
    for path in (folder / "SKILL.md" for folder in skills().values()):
        head = path.read_text().split("\n---\n")[0]
        found = re.search(r"^tip: (.*)$", head, re.M)
        if found:
            purpose, *triggers = [part.strip() for part in found.group(1).split("|")]
            yield path.parent.name, purpose, triggers


TIPS = list(tip_lines())


def test_the_repo_has_skills_with_a_tip_line():
    assert len(TIPS) > 10


@pytest.mark.parametrize(("name", "purpose", "triggers"), TIPS, ids=[name for name, *_ in TIPS])
def test_each_trigger_of_the_repos_skills_gets_that_skills_tip(tmp_path, name, purpose, triggers):
    scene = Scene(tmp_path)
    assert triggers
    for count, trigger in enumerate(triggers):
        prompt = f"So, {trigger.replace('*', 'the thing').upper()}?"
        assert scene.tip(prompt, session=f"s{count}", hook=INSTALLED) == f"tip: /{name} {purpose}"


def wired(layout):
    """The hook's command, from the settings the hooks page gives, for one layout."""
    text = (REPO / "docs" / "hooks.md").read_text()
    (found,) = [
        json.loads(block)
        for block in re.findall(r"^```json\n(.*?)^```$", text, re.M | re.S)
        if "skill-tips.sh" in block
    ]
    ((group,),) = found["hooks"].values()
    assert list(found["hooks"]) == ["UserPromptSubmit"]
    (hook,) = group["hooks"]
    assert hook["type"] == "command" and 0 < hook["timeout"] <= 5
    assert hook["command"].count("<layout>") == 1
    return hook["command"].replace("<layout>", str(layout))


def test_the_command_the_readme_wires_runs_the_hook_and_does_nothing_without_it(scene):
    stdin = json.dumps({"session_id": SESSION, "cwd": str(scene.main), "prompt": "blast radius"})
    env = {key: value for key, value in os.environ.items() if key not in T3}
    env["HOME"] = str(scene.user)
    laid = scene.user / ".local" / "share" / "jstack" / "harness" / "claude-code"

    def run():
        done = subprocess.run(
            ["sh", "-c", wired(laid)],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
        )
        assert done.returncode == 0 and done.stderr == ""
        return done.stdout

    assert run() == ""
    laid.parent.mkdir(parents=True)
    laid.symlink_to(scene.root)
    assert json.loads(run()) == {"systemMessage": BLAST_TIP}
