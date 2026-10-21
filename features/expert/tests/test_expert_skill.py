"""The expert skill: every shell block it gives is lifted from it and run here, under a
temporary `HOME` with a made-up expert's folder, and the calls its blocks print are held
against the tools' schemas. The answer template is read beside the file that has the tiers."""

import json
import os
import re
import stat
import sys
import textwrap
from pathlib import Path
from subprocess import run

import pytest
from jsonschema import Draft202012Validator

import test_playbook_wiring as wiring
import test_tool_calls as calls
import test_understanding_skills as added
from jbus import mirror
from test_handoff_pin import T3
from test_home_thread import as_read
from testing.layouts import assembled
from testing.paths import REPO

SKILL = REPO / "features" / "expert" / "SKILL.md"
TEMPLATE = REPO / "features" / "expert" / "templates" / "expert-answer.md"
TIERS = REPO / "skills" / "why" / "references" / "epistemics.md"
FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)
NAME = "sage"
THREAD = "mcp:thread-one"
OTHER = "mcp:thread-two"
TASK = "scheduled-task:1c2d3e4f-0000-4000-8000-000000000000"
ADDRESS = "https://relay.example/hooks/a-token-nobody-may-see"
READ_AT_START = ["CHARTER.md", "sources.md", "notes/INDEX.md", "corrections.md"]
NO_EXPERT = "no expert: ~/.local/state/home has no folder _{} with a CHARTER.md."
MARKERS = {
    "top": "T=$(realpath",
    "read": "read: $f",
    "id": 'printf \'%s\\n\' "$ME" > "$E/home-id"',
    "webhook": "create: no webhook",
    "taken": "taken: webhook",
    "keep": "url='<webhookUrl>'",
    "playbook": "jbus playbook expert",
    "gate": "THE_GATE_ENDS_HERE",
    "roll": "launch: ",
}
GATE = """\
## Gate <n>: the release workflow has no rollback step
Status: open
Asked by: expert-sage-no-rollback, thread mcp:thread-one
Default: nothing was changed
Built on it: nothing
Undo: nothing to undo
Option: leave it (default, recommended): the workflow stays as it is
Option: add the step: a release can be rolled back
"""


def blocks():
    return [textwrap.dedent(found) for found in FENCED.findall(as_read(SKILL))]


def block(which):
    (found,) = [body for body in blocks() if MARKERS[which] in body]
    return found


class Scene:
    """A user's home directory with the skill linked as `install.sh` links it, a made-up
    expert's folder, and a directory that is in no repo to run from."""

    def __init__(self, tmp_path, repo=None):
        self.user = tmp_path / "user"
        skills = self.user / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "expert").symlink_to((repo or assembled()) / "skills" / "expert")
        self.state = self.user / ".local" / "state" / "home"
        self.folder = self.state / f"_{NAME}"
        (self.folder / "notes").mkdir(parents=True)
        (self.state / "_experts").mkdir()
        (self.state / "_experts" / "README.md").write_text("# Experts\n")
        for name in READ_AT_START:
            (self.folder / name).write_text(f"# {name}\n")
        (self.folder / "notes" / "a-topic.md").write_text("# A topic\n")
        self.bin = wiring.uv(tmp_path / "bin")
        self.elsewhere = tmp_path / "elsewhere"
        self.elsewhere.mkdir()

    def run(self, which, name=NAME, **filled):
        """What the block prints, run after the block at the top with its placeholders filled.
        The exit code comes first when it is not 0."""
        body = block("top").replace("<name>", name)
        if which != "top":
            body += block(which)
        for placeholder, value in filled.items():
            body = body.replace(f"<{placeholder}>", value)
        path = f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"
        done = run(
            ["sh", "-c", body],
            capture_output=True,
            text=True,
            env={"HOME": str(self.user), "PATH": path},
            cwd=self.elsewhere,
        )
        assert done.stderr == ""
        said = done.stdout.splitlines()
        return said if done.returncode == 0 else [done.returncode, *said]

    def files(self):
        return {
            str(path.relative_to(self.user)): path.read_text()
            for path in sorted(self.state.rglob("*"))
            if path.is_file()
        }

    def asked(self, playbook, thread=THREAD):
        """What the block of an ask prints for the thread that is the expert, or was."""
        if not (self.folder / "home-id").exists():
            self.run("id", threadId=thread)
        return self.run("playbook", threadId=thread, playbook=playbook)

    def taken(self, thread, posts_into, **filled):
        """What the block says after the call that takes the webhook over, over a list in
        which the webhook kept posts into `posts_into`, or is not there."""
        id = (self.folder / "webhook").read_text().split()[0]
        tasks = [{"scheduledTaskId": id, "boundThreadId": posts_into, "webhookUrl": ADDRESS}]
        reply = json.dumps({"tasks": tasks if posts_into else []})
        asked = {"threadId": thread, "the reply of list_scheduled_tasks": reply, **filled}
        return self.run("taken", **asked)

    def starts(self, thread=THREAD):
        """The blocks of a start, in its order, with what a `create` returns kept."""
        self.run("read")
        self.run("id", threadId=thread)
        (said,) = self.run("webhook", threadId=thread)
        if said.startswith("take:"):
            self.taken(thread, thread)
        elif not said.startswith("keep:"):
            task = f"{TASK}-{thread[-4:]}"
            self.run("keep", threadId=thread, scheduledTaskId=task, webhookUrl=ADDRESS)
        return said.split(":")[0]


@pytest.fixture
def scene(tmp_path):
    return Scene(tmp_path)


def test_every_shell_block_of_the_skill_is_one_this_file_runs():
    assert sorted(blocks()) == sorted(block(which) for which in MARKERS)


def test_the_skill_is_typed_as_expert_and_names_no_built_in_command():
    fields = added.front(SKILL.read_text())
    assert fields["name"] == "expert" and fields["name"] not in added.BUILT_IN
    assert fields["description"] and fields["user-invocable"] == "true"
    assert added.em_dashes(SKILL) == [] and added.em_dashes(TEMPLATE) == []


def test_the_block_at_the_top_finds_the_folder_of_the_name_typed(scene):
    assert scene.run("top") == []
    assert scene.run("read") == [
        f"expert {NAME}",
        f"title: expert: {NAME}",
        f"read: {scene.state}/_experts/README.md",
        *(f"read: {scene.folder}/{name}" for name in READ_AT_START),
    ]


def test_a_note_is_not_among_what_a_start_reads(scene):
    assert not any("a-topic" in line for line in scene.run("read"))


def test_a_file_the_folder_lacks_is_said_and_the_start_goes_on(scene):
    (scene.folder / "sources.md").unlink()
    said = scene.run("read")
    assert f"missing: {scene.folder}/sources.md" in said
    assert f"read: {scene.folder}/corrections.md" in said


@pytest.mark.parametrize("which", MARKERS)
@pytest.mark.parametrize("name", ["nobody", "", ".hidden", "../sage", "experts", "<name>", "a b"])
def test_with_no_such_folder_every_block_says_so_and_stops_with_nothing_written(scene, which, name):
    (scene.state / "_experts" / "CHARTER.md").write_text("# Not an expert\n")
    before = scene.files()
    code, *said = scene.run(which, name)
    assert code == 1
    assert [line[: len(NO_EXPERT.format(name))] for line in said] == [NO_EXPERT.format(name)]
    assert scene.files() == before


def test_a_folder_with_no_charter_is_no_expert(scene):
    (scene.folder / "CHARTER.md").unlink()
    assert scene.run("read")[0] == 1


def test_the_thread_id_goes_in_home_id_in_the_experts_own_folder(scene):
    before = scene.files()
    assert scene.run("id", threadId=THREAD) == [f"written: {scene.folder}/home-id"]
    key = f".local/state/home/_{NAME}/home-id"
    assert scene.files() == {**before, key: f"{THREAD}\n"}
    assert scene.run("id", threadId=THREAD) == [f"written: {scene.folder}/home-id"]
    assert not list(scene.state.rglob("home-thread"))


def test_a_fresh_thread_takes_the_place_of_the_one_before_and_says_whose(scene):
    scene.run("id", threadId=OTHER)
    (said,) = scene.run("id", threadId=THREAD)
    assert said.endswith(f"in place of {OTHER}, the thread this one takes over from")
    assert (scene.folder / "home-id").read_text() == f"{THREAD}\n"


@pytest.mark.parametrize("thread", ["<threadId>", "", "two words"])
def test_an_id_that_is_not_filled_in_is_not_written(scene, thread):
    before = scene.files()
    assert scene.run("id", threadId=thread)[0].startswith("not written:")
    assert scene.run("webhook", threadId=thread)[0].startswith("not filled in:")
    assert scene.files() == before


def test_a_webhook_is_created_once_kept_by_its_thread_and_taken_over_by_the_next(scene):
    assert scene.run("webhook", threadId=THREAD) == [f"create: no webhook is kept for {NAME}"]
    said = scene.run("keep", threadId=THREAD, scheduledTaskId=TASK, webhookUrl=ADDRESS)
    assert said == [f"kept: webhook {TASK}, and its address in {scene.folder}/webhook.url"]
    assert (scene.folder / "webhook").read_text() == f"{TASK} {THREAD}\n"
    assert scene.run("webhook", threadId=THREAD) == [f"keep: webhook {TASK} posts into this thread"]
    assert scene.run("webhook", threadId=OTHER) == [
        f"take: webhook {TASK} posts into {THREAD}, not this one: take it over"
    ]
    before = scene.files()
    assert scene.taken(OTHER, THREAD) == [
        f"not taken: webhook {TASK} posts into {THREAD}, not this thread: delete it, then create"
    ]
    assert scene.taken(OTHER, None) == [
        f"not taken: webhook {TASK} posts into no thread, not this thread: delete it, then create"
    ]
    assert scene.taken(OTHER, OTHER, **{"the reply of list_scheduled_tasks": "{}"}) == [
        "not written: put the whole reply of list_scheduled_tasks in place of the placeholder"
    ]
    assert scene.files() == before
    said = scene.taken(OTHER, OTHER)
    assert said == [f"taken: webhook {TASK} posts into this thread, at the address it had"]
    assert ADDRESS not in "\n".join(said)
    assert (scene.folder / "webhook").read_text() == f"{TASK} {OTHER}\n"
    assert (scene.folder / "webhook.url").read_text() == f"{ADDRESS}\n"
    assert scene.run("webhook", threadId=OTHER) == [f"keep: webhook {TASK} posts into this thread"]


@pytest.mark.parametrize("thread", ["<threadId>", "", "two words", THREAD])
def test_a_webhook_is_not_taken_with_no_id_filled_in_or_none_kept(scene, thread):
    if thread != THREAD:
        scene.starts(OTHER)
    before = scene.files()
    reply = json.dumps({"tasks": []})
    said = scene.run("taken", threadId=thread, **{"the reply of list_scheduled_tasks": reply})
    assert said[0].startswith("not written:")
    assert scene.files() == before


def test_the_webhooks_address_is_kept_for_the_user_alone_and_never_printed(scene):
    said = scene.run("keep", threadId=THREAD, scheduledTaskId=TASK, webhookUrl=ADDRESS)
    kept = scene.folder / "webhook.url"
    assert kept.read_text() == f"{ADDRESS}\n"
    assert stat.S_IMODE(kept.stat().st_mode) == 0o600
    assert ADDRESS not in "\n".join(said)
    assert ADDRESS not in (scene.folder / "webhook").read_text()


def test_a_webhook_with_no_address_is_kept_and_said_and_an_old_address_goes(scene):
    scene.run("keep", threadId=OTHER, scheduledTaskId="old", webhookUrl=ADDRESS)
    (said,) = scene.run("keep", threadId=THREAD, scheduledTaskId=TASK, webhookUrl="")
    assert said.startswith(f"kept: webhook {TASK}, with no address:")
    assert not (scene.folder / "webhook.url").exists()
    assert (scene.folder / "webhook").read_text() == f"{TASK} {THREAD}\n"


@pytest.mark.parametrize(
    "filled",
    [
        {},
        {"scheduledTaskId": "", "webhookUrl": ADDRESS},
        {"scheduledTaskId": "", "webhookUrl": ""},
        {"scheduledTaskId": "two words", "webhookUrl": ""},
        {"scheduledTaskId": TASK, "webhookUrl": "an address"},
        {"threadId": "", "scheduledTaskId": TASK, "webhookUrl": ADDRESS},
    ],
)
def test_what_a_create_returned_is_not_kept_until_it_is_filled_in(scene, filled):
    scene.starts()
    before = scene.files()
    said = scene.run("keep", **{"threadId": THREAD, **filled})
    assert said[0].startswith("not written:")
    assert scene.files() == before
    assert scene.run("webhook", threadId=THREAD)[0].startswith("keep:")


def test_a_second_start_of_one_thread_changes_nothing(scene):
    assert scene.starts() == "create"
    once = scene.files()
    assert scene.starts() == "keep"
    assert scene.files() == once


def test_a_fresh_thread_started_on_the_folder_ends_in_the_same_state(scene, tmp_path):
    scene.starts(OTHER)
    assert scene.starts(THREAD) == "take"
    alone = Scene(tmp_path / "alone")
    assert alone.starts(THREAD) == "create"
    key = f".local/state/home/_{NAME}/webhook"
    assert scene.files() == {**alone.files(), key: f"{TASK}-{OTHER[-4:]} {THREAD}\n"}


def test_the_skills_calls_rename_pin_and_keep_a_webhook_and_settle_nothing():
    of_an_expert = [call for call in calls.CALLS if call.where.startswith("expert:")]
    assert [call.tool for call in of_an_expert] == [
        "t3_thread_update",
        "t3_thread_organize",
        "t3_thread_organize",
        "update_scheduled_task",
        "schedule_task",
        "delete_scheduled_task",
    ]
    assert {"action": "settle"} not in [call.given for call in of_an_expert]
    take = of_an_expert[3].given
    assert take == {
        "scheduledTaskId": calls.FILLED["<scheduledTaskId>"],
        "bindToCurrentThread": True,
    }
    (webhook,) = [
        call.given
        for call in calls.CALLS
        if call.where.startswith("expert:") and call.tool == "schedule_task"
    ]
    assert webhook["schedule"] == {"type": "webhook"}
    assert "{{body}}" in webhook["prompt"] and "bindToCurrentThread" not in webhook


def made(tmp_path, playbooks):
    """A repo the skill lives in, with these playbooks: each name and what follows `Run by:`."""
    repo = tmp_path / "repo"
    (repo / "templates").mkdir(parents=True)
    (repo / "skills" / "expert").mkdir(parents=True)
    (repo / "playbooks").mkdir()
    for name, by in playbooks.items():
        (repo / "playbooks" / f"{name}.md").write_text(f"# A kind\n\nRun by: {by}\n")
    wiring.catalogued(repo)
    return repo


KINDS = {
    "question": "expert-answer",
    "check": "expert-check",
    "research": "expert-research",
    "study": "expert-study",
    "refresh": "expert-refresh",
}


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_of_ask_opens_its_playbook_and_says_so_while_there_is_none(kind, tmp_path):
    repo = made(tmp_path, {KINDS[kind]: "an expert, for a kind of ask."})
    assert Scene(tmp_path / "with", repo).asked(kind) == [
        str((repo / "playbooks" / f"{KINDS[kind]}.md").resolve())
    ]
    bare = made(tmp_path / "bare", {})
    assert Scene(tmp_path / "without", bare).asked(kind) == [
        f"no playbook: playbooks/ has no {KINDS[kind]}.md"
    ]


def test_a_playbook_given_by_name_is_opened_and_a_kind_not_filled_in_opens_none(tmp_path):
    repo = made(tmp_path, {"a-kind": "an expert, for a kind of ask."})
    scene = Scene(tmp_path / "scene", repo)
    assert scene.asked("a-kind") == [str((repo / "playbooks" / "a-kind.md").resolve())]
    before = scene.files()
    for filled in ({"threadId": THREAD}, {"playbook": "check"}):
        code, said = scene.run("playbook", **filled)
        assert code == 1 and said.startswith("not filled in:")
    assert scene.files() == before
    assert scene.asked("none") == []


def test_a_thread_another_took_the_expert_over_from_is_told_so_on_its_next_ask(tmp_path):
    repo = made(tmp_path, {"expert-answer": "an expert, for a kind of ask."})
    scene = Scene(tmp_path / "scene", repo)
    assert len(scene.asked("question", THREAD)) == 1
    scene.run("id", threadId=OTHER)
    before = scene.files()
    assert scene.asked("question", THREAD) == [
        1,
        f"not the expert: {OTHER} is, by {scene.folder}/home-id. Write nothing in {scene.folder}.",
    ]
    assert len(scene.asked("question", OTHER)) == 1
    assert scene.files() == before


@pytest.mark.parametrize("thread", ["", "<threadId>", "two words"])
@pytest.mark.parametrize("started", [True, False])
def test_a_thread_with_no_id_opens_no_playbook_whoever_the_expert_is(tmp_path, thread, started):
    scene = Scene(tmp_path / "scene", made(tmp_path, {"a-kind": "an expert, for an ask."}))
    if started:
        scene.run("id", threadId=OTHER)
    before = scene.files()
    code, said = scene.run("playbook", threadId=thread, playbook="a-kind")
    assert code == 1 and said.startswith("not filled in:")
    assert scene.files() == before


class Bus:
    """A `jbus` on the PATH that keeps what it was run with and what it read."""

    def __init__(self, scene, exit_code=0, says="queued"):
        self.kept = scene.bin / "kept.json"
        (scene.bin / "jbus").write_text(
            f"#!{sys.executable}\n"
            "import json, sys\n"
            f"json.dump([sys.argv[1:], sys.stdin.read()], open({str(self.kept)!r}, 'w'))\n"
            f"print({says!r})\nsys.exit({exit_code})\n"
        )
        (scene.bin / "jbus").chmod(0o755)

    def got(self):
        return json.loads(self.kept.read_text()) if self.kept.exists() else None


def gate(scene, project="demo", about="no-rollback", text=GATE):
    return scene.run("gate", project=project, about=about, **{"the gate, filled in": text.strip()})


def test_a_finding_goes_to_the_owning_home_as_a_gate_through_jbus(scene):
    bus = Bus(scene)
    assert gate(scene) == [f"sent to demo as expert-{NAME}-no-rollback: queued"]
    assert bus.got() == [["--project", "demo", "gate", f"expert-{NAME}-no-rollback"], GATE]


@pytest.mark.parametrize("asked_by", ["home", "sage", "expert-sage-another-thing"])
def test_a_gate_is_sent_under_the_slug_jbus_would_read_off_its_asked_by_line(scene, asked_by):
    bus = Bus(scene)
    gate(scene, text=GATE.replace("expert-sage-no-rollback", asked_by))
    (slug,), sent = bus.got()[0][3:], bus.got()[1]
    assert sent == GATE
    assert [found[0] for found in mirror._gates(sent.replace("<n>", "1"))] == [slug]


def test_the_real_jbus_queues_the_gate_the_block_sends_under_its_slug(scene):
    (scene.bin / "jbus").symlink_to(Path(sys.executable).parent / "jbus")
    config = scene.user / ".config" / "jbus" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        'server = "http://127.0.0.1:1"\n\n[[project]]\nname = "demo"\n'
        f'checkout = "{scene.elsewhere}"\nprojectId = "a-project"\n'
    )
    config.chmod(0o600)
    slug = f"expert-{NAME}-no-rollback"
    assert gate(scene) == [f"sent to demo as {slug}: queued: question 1"]
    (waiting,) = json.loads((scene.user / ".local/state/jbus/demo/outbox.json").read_text())
    assert waiting["line"] == f"gate {slug}: question 1: the release workflow has no rollback step"
    assert gate(scene) == [f"sent to demo as {slug}: already sent: question 1"]
    (said,) = gate(scene, project="another")
    assert said.startswith("not sent: jbus said: refused: no project another")


@pytest.mark.parametrize(
    ("changed", "why"),
    [
        ({"project": "<project>"}, "put the project"),
        ({"about": "<about>"}, "put the project"),
        ({"about": "no/rollback"}, "what the finding is about is letters"),
        ({"about": "no rollback"}, "what the finding is about is letters"),
        ({"about": ""}, "what the finding is about is letters"),
        ({"text": GATE.replace("Asked by:", "Asked:")}, "the gate has no line 'Asked by:"),
    ],
)
def test_a_gate_that_is_not_filled_in_is_not_sent(scene, changed, why):
    bus = Bus(scene)
    (said,) = gate(scene, **changed)
    assert said.startswith(f"not sent: {why}")
    assert bus.got() is None


def test_a_gate_jbus_refuses_and_one_with_no_jbus_are_said_as_not_sent(scene):
    assert gate(scene) == [
        "not sent: jbus is not installed here: tell the user the finding in this thread"
    ]
    Bus(scene, exit_code=1, says="refused: no project demo")
    assert gate(scene) == ["not sent: jbus said: refused: no project demo"]


def takes(tool, given):
    schema = calls.strict(calls.SCHEMAS[tool])
    return [error.message for error in Draft202012Validator(schema).iter_errors(given)]


def test_a_roll_over_prints_a_launch_and_a_rename_their_tools_take(scene):
    scene.starts()
    before = scene.files()
    launch, rename = scene.run("roll", threadId=THREAD)
    launch = json.loads(launch.removeprefix("launch: "))
    rename = json.loads(rename.removeprefix("rename: "))
    assert takes("t3_thread_launch", launch) == [] and takes("t3_thread_update", rename) == []
    assert launch == {
        "title": f"expert: {NAME}",
        "workspaceStrategy": {"type": "root"},
        "message": f"/expert {NAME}",
    }
    assert re.fullmatch(rf"expert: {NAME} \(rolled over \d{{4}}-\d\d-\d\d\)", rename["title"])
    assert scene.files() == before


def test_the_thread_a_roll_over_launches_starts_on_the_same_folder(scene):
    scene.starts()
    launch = json.loads(scene.run("roll", threadId=THREAD)[0].removeprefix("launch: "))
    skill, name = re.fullmatch(r"/([\w-]+) (\S+)", launch["message"]).groups()
    assert (REPO / "features" / skill / "SKILL.md") == SKILL
    assert scene.run("read", name)[0] == f"expert {NAME}"
    assert scene.starts(OTHER) == "take"
    assert (scene.folder / "home-id").read_text() == f"{OTHER}\n"


def started(scene, t3, thread):
    """An expert's start with its calls made of a made-up T3 Code: the pin, and the unpin of
    the thread the block of step 3 says this one takes over from."""
    pin, unpin = (
        call
        for call in calls.CALLS
        if call.where.startswith("expert:") and call.tool == "t3_thread_organize"
    )
    assert unpin.given == {"action": "unpin", "threadId": calls.FILLED["<thread>"]}
    t3.threads.get(thread) or t3.thread(thread, f"expert: {NAME}")
    t3.call(thread, pin)
    (said,) = scene.run("id", threadId=thread)
    if " in place of " in said:
        was = said.split(" in place of ")[1].split(",")[0]
        t3.call(thread, unpin, **{calls.FILLED["<thread>"]: was})
    scene.starts(thread)


@pytest.mark.parametrize("cut", [0, 1, 2, 3])
def test_a_roll_over_cut_off_anywhere_and_run_again_leaves_one_thread_pinned(scene, cut):
    t3 = T3()

    def rolls_over(steps):
        """The first `steps` of a roll over, in the skill's order: its block, the launch,
        the rename."""
        said = scene.run("roll", threadId=THREAD) if steps else [""]
        if not said[0].startswith("launch: "):
            return
        if steps > 1:
            started(scene, t3, OTHER)
        if steps > 2:
            rename = json.loads(said[1].removeprefix("rename: "))
            assert takes("t3_thread_update", rename) == []
            t3.threads[THREAD]["title"] = rename["title"]

    started(scene, t3, THREAD)
    rolls_over(cut)
    rolls_over(3)
    if OTHER not in t3.threads:
        started(scene, t3, OTHER)
    assert t3.pinned() == [OTHER]
    assert ("rolled over" in t3.threads[THREAD]["title"]) == (cut in (0, 1, 3))


def test_a_thread_that_takes_an_expert_over_with_no_roll_over_unpins_the_one_before(scene):
    t3 = T3()
    started(scene, t3, THREAD)
    started(scene, t3, OTHER)
    started(scene, t3, OTHER)
    assert t3.pinned() == [OTHER]


@pytest.mark.parametrize("started", [True, False])
def test_a_thread_that_is_not_the_expert_launches_nothing(scene, started):
    if started:
        scene.starts()
    (said,) = scene.run("roll", threadId=OTHER)
    assert said.startswith("not the expert:")


@pytest.mark.parametrize("thread", ["<threadId>", "", "two words"])
@pytest.mark.parametrize("started", [True, False])
def test_a_roll_over_with_no_id_filled_in_says_so_and_launches_nothing(scene, thread, started):
    if started:
        scene.starts()
    (said,) = scene.run("roll", threadId=thread)
    assert said.startswith("not filled in:")


def parts(text):
    """A template's headings, in order."""
    return re.findall(r"^## (.+)$", text, re.M)


def offered(text):
    """The tiers the template lets an answer pick from, in the order it gives them."""
    (line,) = re.findall(r"^## Confidence\n(.*)$", text, re.M)
    return [tier.strip() for tier in line.split(">")[0].lstrip("<").split("|")]


def tiers(text):
    """The confidence tiers of the epistemics file, in order."""
    numbered = re.findall(r"^### (\d+)\. (\S+)$", text, re.M)
    assert [int(n) for n, _ in numbered] == list(range(1, len(numbered) + 1))
    return [name for _, name in numbered]


def test_the_answer_template_has_the_four_parts_in_order():
    assert parts(TEMPLATE.read_text()) == ["Answer", "Sources", "Confidence", "Not checked"]


def test_the_templates_tiers_are_the_five_of_the_epistemics_file():
    assert len(tiers(TIERS.read_text())) == 5
    assert offered(TEMPLATE.read_text()) == tiers(TIERS.read_text())


def test_a_tier_added_renamed_or_out_of_order_on_either_side_disagrees():
    template, file = TEMPLATE.read_text(), TIERS.read_text()
    assert offered(template.replace("Inferred | ", "")) != tiers(file)
    assert offered(template.replace("Direct | Supported", "Supported | Direct")) != tiers(file)
    assert offered(template) != tiers(file.replace("### 5. Unknown", "### 5. Unknowable"))
    assert offered(template) != tiers(file + "\n### 6. Guessed\n")
