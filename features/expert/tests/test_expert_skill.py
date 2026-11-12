"""The expert skill: these tests lift every shell block the skill gives and run it here, under
a temporary `HOME` with a made-up expert's folder. They check the calls its blocks print against
the tools' schemas, and they read the answer template beside the file that has the tiers."""

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
from jbus import mirror
from test_handoff_pin import T3
from test_home_thread import as_read
from testing.layouts import assembled
from testing.paths import REPO

SKILL = REPO / "features" / "expert" / "SKILL.md"
TEMPLATE = REPO / "features" / "expert" / "templates" / "expert-answer.md"
TIERS = REPO / "features" / "why" / "references" / "epistemics.md"
FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)
NAME = "sage"
THREAD = "mcp:thread-one"
OTHER = "mcp:thread-two"
TASK = "scheduled-task:1c2d3e4f-0000-4000-8000-000000000000"
ADDRESS = "https://relay.example/hooks/a-token-nobody-may-see"
TITLE = f"expert: {NAME}, asks"
READ_AT_START = ["CHARTER.md", "sources.md", "notes/INDEX.md", "corrections.md"]
NO_EXPERT = "no expert: ~/.local/state/home has no folder _{} with a CHARTER.md."
MARKERS = {
    "top": "T=$(realpath",
    "read": "read: $f",
    "id": 'printf \'%s\\n\' "$ME" > "$E/home-id"',
    "webhook": "create: no live webhook",
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
"""
CONTEXT = "the workflow is .github/workflows/release.yml"
OPTIONS = (
    ("leave it", "the workflow stays as it is"),
    ("add the step", "a release can be rolled back"),
)
SENT = (
    GATE
    + f"Context: {CONTEXT}\n"
    + f"Option: {OPTIONS[0][0]} (default, recommended): {OPTIONS[0][1]}\n"
    + f"Option: {OPTIONS[1][0]}: {OPTIONS[1][1]}\n"
)


def blocks():
    return [textwrap.dedent(found) for found in FENCED.findall(as_read(SKILL))]


def block(which):
    (found,) = [body for body in blocks() if MARKERS[which] in body]
    return found


class Scene:
    """A user's home directory, a made-up expert's folder, and a directory outside any repo for
    the blocks to run from. The skill is linked into the home directory the way `install.sh`
    links it."""

    def __init__(self, tmp_path, repo=None):
        self.user = tmp_path / "user"
        skills = self.user / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "expert").symlink_to((repo or assembled()) / "skills" / "expert")
        self.state = self.user / ".local" / "state" / "home"
        self.folder = self.state / f"_{NAME}"
        (self.folder / "notes").mkdir(parents=True)
        (self.state / "_experts").mkdir()
        for name in READ_AT_START:
            (self.folder / name).write_text(f"# {name}\n")
        (self.folder / "notes" / "a-topic.md").write_text("# A topic\n")
        self.bin = wiring.uv(tmp_path / "bin")
        self.elsewhere = tmp_path / "elsewhere"
        self.elsewhere.mkdir()
        self.live = {}
        self.made = 0

    def run(self, which, name=NAME, **filled):
        """Run the block at the top and then the block `which`, with the placeholders filled,
        and return what they print. The exit code comes first when it is not 0."""
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
        """What the ask's block prints for a thread that is the expert now or was the expert
        before."""
        if not (self.folder / "home-id").exists():
            self.run("id", threadId=thread)
        return self.run("playbook", threadId=thread, playbook=playbook)

    def looks(self, thread, refused="", reply=None):
        """What the block of step 4 prints, given the tasks of T3 Code as `list_scheduled_tasks`
        lists them, beside a task of another skill, which the block leaves alone."""
        other = {"scheduledTaskId": "a-home-task", "title": "jbus events: a home"}
        tasks = [{**other, "boundThreadId": thread}, *self.live.values()]
        asked = {
            "threadId": thread,
            "the reply of list_scheduled_tasks": reply or json.dumps({"tasks": tasks}),
            "the ids a call was refused for": refused,
        }
        return self.run("webhook", **asked)

    def creates(self, thread):
        """`schedule_task` called from `thread`: T3 Code makes a webhook that posts into it."""
        self.made += 1
        id = f"{TASK}-{self.made}"
        self.live[id] = {"scheduledTaskId": id, "title": TITLE, "boundThreadId": thread}
        return id

    def does(self, thread, said, url=ADDRESS):
        """Make the call that the block's line names, from `thread`, and after a create run
        the block that keeps what it returned."""
        word, _, rest = said.partition(" ")
        if word == "delete":
            self.live.pop(rest.split(": ")[0], None)
        elif word == "take":
            self.live[rest.split(": ")[0]]["boundThreadId"] = thread
        elif word == "create:":
            made = self.creates(thread)
            self.run("keep", threadId=thread, scheduledTaskId=made, webhookUrl=url)
        else:
            raise AssertionError(said)

    def sees_to_the_webhook(self, thread=THREAD, url=ADDRESS):
        """Step 4: the block and the call it names, again until it says `keep`. The first
        word of each line it printed."""
        words = []
        while len(words) < 6:
            (said,) = self.looks(thread)
            words.append(said.split(" ")[0].rstrip(":"))
            if words[-1] == "keep":
                return words
            self.does(thread, said, url)
        raise AssertionError(words)

    def starts(self, thread=THREAD, url=ADDRESS):
        """Run the blocks of an expert's start in the skill's order. The first word step 4
        said."""
        self.run("read")
        self.run("id", threadId=thread)
        return self.sees_to_the_webhook(thread, url)[0]

    def kept(self):
        """The record of the webhook, and what T3 Code has live."""
        return (self.folder / "webhook").read_text().split(), [
            [task["scheduledTaskId"], task["boundThreadId"]] for task in self.live.values()
        ]


@pytest.fixture
def scene(tmp_path):
    return Scene(tmp_path)


def test_the_block_at_the_top_finds_the_folder_of_the_name_typed(scene):
    assert scene.run("top") == []
    assert scene.run("read") == [
        f"expert {NAME}",
        f"title: expert: {NAME}",
        *(f"read: {scene.folder}/{name}" for name in READ_AT_START),
    ]


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
    assert scene.looks(thread)[0].startswith("not filled in:")
    assert scene.files() == before


@pytest.mark.parametrize("reply", ["{}", '{"tasks": 1}', "not json", '{"tasks": []} {"tasks": []}'])
def test_a_reply_that_is_not_the_whole_list_is_not_read_and_nothing_is_written(scene, reply):
    scene.starts()
    before = scene.files()
    assert scene.looks(THREAD, reply=reply) == [
        "not read: put the whole reply of list_scheduled_tasks in place of the placeholder"
    ]
    assert scene.files() == before


def test_a_webhook_is_created_once_and_a_second_start_finds_nothing_to_do(scene):
    assert scene.sees_to_the_webhook() == ["create", "keep"]
    assert scene.kept() == ([f"{TASK}-1", THREAD], [[f"{TASK}-1", THREAD]])
    assert (scene.folder / "webhook.url").read_text() == f"{ADDRESS}\n"
    once = scene.files()
    assert scene.looks(THREAD) == [f"keep: webhook {TASK}-1 posts into this thread"]
    assert scene.files() == once


def test_the_next_thread_takes_the_webhook_over_at_the_address_it_had(scene):
    scene.starts(OTHER)
    (said,) = scene.looks(THREAD)
    assert (
        said == f"take {TASK}-1: webhook {TASK}-1 posts into {OTHER}, not this thread: take it over"
    )
    assert scene.sees_to_the_webhook(THREAD) == ["take", "keep"]
    assert scene.kept() == ([f"{TASK}-1", THREAD], [[f"{TASK}-1", THREAD]])
    assert (scene.folder / "webhook.url").read_text() == f"{ADDRESS}\n"


def test_a_create_whose_turn_stopped_before_it_kept_the_id_is_deleted_by_the_next_thread(scene):
    """The model's first fault: the webhook thread 1 made and never kept is bound to thread 1,
    and the start in thread 2 deletes it before it creates its own."""
    scene.run("id", threadId=OTHER)
    assert scene.looks(OTHER)[0].startswith("create:")
    scene.creates(OTHER)
    scene.run("id", threadId=THREAD)
    assert scene.sees_to_the_webhook(THREAD) == ["delete", "create", "keep"]
    assert scene.kept() == ([f"{TASK}-2", THREAD], [[f"{TASK}-2", THREAD]])


def test_a_webhook_kept_with_its_address_lost_is_made_again(scene):
    """The model's second fault, as the text before this one left it: the record was written
    and the turn stopped before the address. The start deletes that webhook and makes one whose
    address it keeps."""
    scene.starts()
    (scene.folder / "webhook.url").unlink()
    (said,) = scene.looks(THREAD)
    assert said.startswith(f"delete {TASK}-1: the address of webhook {TASK}-1 is lost")
    assert scene.sees_to_the_webhook(THREAD) == ["delete", "create", "keep"]
    assert scene.kept() == ([f"{TASK}-2", THREAD], [[f"{TASK}-2", THREAD]])
    assert (scene.folder / "webhook.url").read_text() == f"{ADDRESS}\n"


@pytest.mark.parametrize("called", [False, True])
def test_a_takeover_whose_turn_stopped_leaves_a_record_the_next_start_mends(scene, called):
    """The model's third fault: a takeover stops between its record and its call, or after
    both. Whichever thread starts next, the record ends naming the thread the webhook posts
    into."""
    scene.starts(OTHER)
    (said,) = scene.looks(THREAD)
    assert said.startswith("take ")
    assert scene.kept()[0] == [f"{TASK}-1", THREAD]
    if called:
        scene.does(THREAD, said)
    assert scene.sees_to_the_webhook(OTHER) == (["take", "keep"] if called else ["keep"])
    assert scene.kept() == ([f"{TASK}-1", OTHER], [[f"{TASK}-1", OTHER]])


def test_a_webhook_with_no_address_is_kept_and_said_and_kept_again_on_the_next_start(scene):
    scene.run("id", threadId=THREAD)
    made = scene.creates(THREAD)
    (said,) = scene.run("keep", threadId=THREAD, scheduledTaskId=made, webhookUrl="")
    assert said.startswith(f"kept: webhook {made}, with no address:")
    assert (scene.folder / "webhook.url").read_text() == ""
    assert scene.sees_to_the_webhook(THREAD) == ["keep"]


def test_a_takeover_that_is_refused_is_followed_by_a_create_and_the_old_webhook_goes(scene):
    scene.starts(OTHER)
    (said,) = scene.looks(THREAD)
    (said,) = scene.looks(THREAD, refused=f"{TASK}-1")
    assert said.startswith("create:")
    scene.does(THREAD, said)
    assert scene.sees_to_the_webhook(THREAD) == ["delete", "keep"]
    assert scene.kept() == ([f"{TASK}-2", THREAD], [[f"{TASK}-2", THREAD]])


def test_the_webhooks_address_is_kept_for_the_user_alone_and_never_printed(scene):
    said = scene.run("keep", threadId=THREAD, scheduledTaskId=TASK, webhookUrl=ADDRESS)
    assert said == [f"kept: webhook {TASK}, and its address in {scene.folder}/webhook.url"]
    kept = scene.folder / "webhook.url"
    assert kept.read_text() == f"{ADDRESS}\n"
    assert stat.S_IMODE(kept.stat().st_mode) == 0o600
    assert ADDRESS not in (scene.folder / "webhook").read_text()
    scene.live[TASK] = {"scheduledTaskId": TASK, "title": TITLE, "boundThreadId": OTHER}
    for thread in (OTHER, THREAD):
        assert ADDRESS not in "\n".join(scene.looks(thread))


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
    assert scene.looks(THREAD)[0].startswith("keep:")


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
    assert scene.files() == alone.files()
    assert scene.kept() == alone.kept()


def made(tmp_path, playbooks):
    """A repo that holds the skill and the playbooks in `playbooks`. `playbooks` maps the name of
    each playbook to the text that follows its `Run by:`."""
    repo = tmp_path / "repo"
    (repo / "templates").mkdir(parents=True)
    (repo / "source").symlink_to(repo)
    (repo / "skills" / "expert").mkdir(parents=True)
    (repo / "playbooks").mkdir()
    for name, by in playbooks.items():
        (repo / "playbooks" / f"{name}.md").write_text(f"# A kind\n\nRun by: {by}\n")
    wiring.catalogued(repo)
    return repo


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


def gate(scene, project="demo", about="no-rollback", text=GATE):
    """Run the gate block as the expert fills it in: the gate's lines, its context, and the
    two options, the one the block writes and one more under it."""
    (taken, follows), (other, then) = OPTIONS
    filled = {
        "the gate, filled in": text.strip(),
        "what the user needs to know to answer it, in one line, with the links to it": CONTEXT,
        "an option's short name": taken,
        "what follows from it": f"{follows}\nOption: {other}: {then}",
    }
    return scene.run("gate", project=project, about=about, **filled)


def real_jbus(scene):
    """Put the real `jbus` on the PATH, with a config that names the project `demo`, and return
    that project's state directory."""
    (scene.bin / "jbus").symlink_to(Path(sys.executable).parent / "jbus")
    config = scene.user / ".config" / "jbus" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        'server = "http://127.0.0.1:1"\n\n[[project]]\nname = "demo"\n'
        f'checkout = "{scene.elsewhere}"\nprojectId = "a-project"\n'
    )
    config.chmod(0o600)
    return scene.user / ".local/state/jbus/demo"


def test_the_real_jbus_queues_the_gate_the_block_sends_under_its_slug(scene):
    state = real_jbus(scene)
    slug = f"expert-{NAME}-no-rollback"
    assert gate(scene) == ["asked: queued: question 1", "Gate: question 1"]
    logged = [json.loads(line) for line in (state / "events.jsonl").read_text().splitlines()]
    (gated,) = [one for one in logged if one.get("event") == "gate"]
    assert gated["line"] == f"gate {slug}: question 1: the release workflow has no rollback step"
    assert gated["loud"] == "quiet" and not (state / "outbox.json").exists()
    assert gate(scene) == ["asked: already sent: question 1", "Gate: question 1"]
    code, said = gate(scene, project="another")
    assert (code, said.startswith("not asked: refused: no project another")) == (1, True)


@pytest.mark.parametrize("asked_by", ["home", "sage", "expert-sage-another-thing"])
def test_a_gate_is_kept_under_the_slug_it_is_sent_under_whatever_its_asked_by_says(scene, asked_by):
    state = real_jbus(scene)
    assert gate(scene, text=GATE.replace("expert-sage-no-rollback", asked_by))[0] == (
        "asked: queued: question 1"
    )
    logged = [json.loads(line) for line in (state / "events.jsonl").read_text().splitlines()]
    (gated,) = [one for one in logged if one.get("event") == "gate"]
    assert gated["text"] == SENT.strip()
    found = mirror._gates(gated["text"].replace("<n>", "1"))
    assert [one[0] for one in found] == [f"expert-{NAME}-no-rollback"]


def test_a_gate_with_no_jbus_is_not_asked(scene):
    assert gate(scene) == ["not asked: jbus is not installed here"]


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
    """An expert's start, with the calls it makes to a made-up T3 Code. It pins `thread`. It
    also unpins the earlier thread that `thread` takes over from. The block of step 3 names
    that earlier thread."""
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
        """Run the first `steps` steps of a roll-over in the skill's order. The steps are the
        roll-over block, the launch and the rename."""
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


def offered(text):
    """The tiers the template lets an answer pick from, in the order it gives them."""
    (line,) = re.findall(r"^## Confidence\n(.*)$", text, re.M)
    return [tier.strip() for tier in line.split(">")[0].lstrip("<").split("|")]


def tiers(text):
    """The confidence tiers of the epistemics file, in order."""
    numbered = re.findall(r"^### (\d+)\. (\S+)$", text, re.M)
    assert [int(n) for n, _ in numbered] == list(range(1, len(numbered) + 1))
    return [name for _, name in numbered]


def test_the_templates_tiers_are_the_five_of_the_epistemics_file():
    assert len(tiers(TIERS.read_text())) == 5
    assert offered(TEMPLATE.read_text()) == tiers(TIERS.read_text())
