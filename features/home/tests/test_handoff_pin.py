"""A home pins itself at its start, and a handoff leaves nothing pointing at the old home. The tests
run the skills' own shell blocks in a temporary state directory, and a fake T3 Code answers their
calls. Each call the blocks make is a JSON block of a skill. The test checks the call against its
tool's schema before the call changes anything."""

import itertools
import json

import pytest

from test_home_thread import NAME, NOTE, OTHER, THREAD, Scene, block
from test_tool_calls import CALLS, FILLED, errors

HOOK = "scheduled-task:hook"
AUDIT = "scheduled-task:audit"
ADDRESS = "https://relay.example/hooks/a-token-nobody-may-see"
TASKS = "<the reply of list_scheduled_tasks>"
THREADS = "<the reply of t3_thread_list>"
REFUSED = "<the ids a call was refused for>"
ID = "<scheduledTaskId>"
TITLE = FILLED["<title>"]


def call(skill, tool, **holding):
    """The one JSON call that the skill gives for `tool` and that sends the values in
    `holding`."""
    found, *same = [
        call
        for call in CALLS
        if call.where.startswith(f"{skill}:")
        and call.tool == tool
        and all(call.given.get(key) == value for key, value in holding.items())
    ]
    assert all(other.given == found.given for other in same)
    return found


class T3:
    """What T3 Code keeps of threads and scheduled tasks, following the rules the skills rely on.
    T3 Code keeps a pin once, and a settle clears it. When a thread settles itself, T3 Code settles
    it once the thread's turn ends without being cut off. T3 Code binds a task to the thread that
    calls. Each run of a task that is on makes active again the thread that the task posts into."""

    def __init__(self):
        self.threads = {}
        self.tasks = {}
        self.pins = 0
        self.refuses = set()
        self.settled_by = []

    def thread(self, id, title=TITLE):
        self.threads[id] = {"threadId": id, "title": title, "settled": False, "pinned": False}

    def ends(self, id, well=True):
        """End the turn of the thread `id`."""
        on = self.threads[id]
        if on.pop("settles", False) and well:
            on.update(pinned=False, settled=True)

    def task(self, id, bound, title="jbus events: demo home", enabled=True):
        self.tasks[id] = {
            "scheduledTaskId": id,
            "title": title,
            "prompt": '{{body.say}} is "data"',
            "enabled": enabled,
            "boundThreadId": bound,
            "webhookUrl": ADDRESS,
        }

    def call(self, caller, call, **filled):
        """Fill in a skill's call and make the call as the thread `caller`. The call goes
        through only if it matches the tool's schema."""
        given = {key: filled.get(value, value) for key, value in call.given.items()}
        assert errors(call, given) == [], call.where
        on = self.threads[given.get("threadId") or caller]
        if call.tool == "t3_thread_organize" and given["action"] == "pin":
            self.pins += not on["pinned"]
            on.update(pinned=True, settled=False)
        elif call.tool == "t3_thread_organize" and given["action"] == "unpin":
            on.update(pinned=False)
        elif call.tool == "t3_thread_organize" and given["action"] == "settle":
            self.settled_by.append(caller)
            if "threadId" in given:
                on.update(pinned=False, settled=True)
            else:
                on["settles"] = True
        elif call.tool == "t3_thread_update":
            on["title"] = given["title"]
        elif call.tool == "update_scheduled_task":
            if given["scheduledTaskId"] in self.refuses:
                return "refused"
            task = self.tasks[given["scheduledTaskId"]]
            if given.get("bindToCurrentThread"):
                task["boundThreadId"] = caller
            task["enabled"] = given.get("enabled", task["enabled"])
        elif call.tool == "delete_scheduled_task":
            del self.tasks[given["scheduledTaskId"]]
        elif call.tool == "t3_thread_list":
            asked = [
                {key: value for key, value in thread.items() if key in SHOWN}
                for thread in self.threads.values()
                if given["titleContains"] in thread["title"]
            ]
            return json.dumps({"threads": asked, "nextCursor": None})
        else:
            raise AssertionError(f"{call.where}: no rule here for {call.tool}")
        return None

    def listed(self):
        return json.dumps({"tasks": list(self.tasks.values())})

    def runs(self, task):
        """Run a task. When the task is on, the run posts a message in its thread, which makes
        that thread active again."""
        if self.tasks[task]["enabled"]:
            self.threads[self.tasks[task]["boundThreadId"]]["settled"] = False

    def pinned(self):
        return [id for id, thread in self.threads.items() if thread["pinned"]]

    def bound(self, thread):
        return [id for id, task in self.tasks.items() if task["boundThreadId"] == thread]


SHOWN = ("threadId", "title", "settled")


class Home(Scene):
    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.t3 = T3()
        (self.home_dir / "plan.md").write_text("# plan\n")

    def tasks_of_the_last(self, thread, reply=None, refused=REFUSED):
        found = block("home", "take \\(")
        assert TASKS in found and REFUSED in found
        found = found.replace(TASKS, self.t3.listed() if reply is None else reply)
        ran = self.run("home", found.replace(REFUSED, refused), self.main, thread)
        return ran.stdout.splitlines()

    def thread_of_the_last(self, thread, reply=None):
        found = block("home", "settle \\(")
        assert THREADS in found
        if reply is None:
            reply = self.t3.call(thread, call("home", "t3_thread_list", titleContains=TITLE))
        return self.run(
            "home", found.replace(THREADS, reply), self.main, thread
        ).stdout.splitlines()

    def takes(self, thread):
        """Run the first steps of a home's start in the order the skill gives. The home writes
        its id, pins itself, then takes over or deletes the last home's tasks. Once the calls are
        made, return what the block says about the tasks."""
        self.t3.threads.get(thread) or self.t3.thread(thread)
        self.home_starts(thread)
        self.t3.call(thread, call("home", "t3_thread_organize", action="pin"))
        refused = []
        for said in self.tasks_of_the_last(thread):
            word, _, rest = said.partition(" ")
            id = rest.split(": ")[0]
            if word == "take":
                take = call("home", "update_scheduled_task")
                if self.t3.call(thread, take, **{FILLED[ID]: id}) == "refused":
                    refused.append(id)
            elif word == "delete":
                self.t3.call(thread, call("home", "delete_scheduled_task"), **{FILLED[ID]: id})
        return self.tasks_of_the_last(thread, refused=" ".join(refused))

    def looks(self, thread):
        """Run the last step of a home's start, which checks the last home's thread, and return
        what the block said."""
        (said,) = self.thread_of_the_last(thread)
        if said.startswith("settle "):
            settle = call("home", "t3_thread_organize", action="settle")
            self.t3.call(thread, settle, **{FILLED["<thread>"]: said.split()[1].rstrip(":")})
        return said

    def starts(self, thread):
        return [*self.takes(thread), self.looks(thread)]

    def listed_at_handoff(self, thread, reply=None):
        """Run the handoff's close once the note is there, with a reply from
        `list_scheduled_tasks`. Return the lines the close printed about the tasks. They come
        after the lines that say whether to launch."""
        if not (self.home_dir / "handoff.next.md").exists():
            (self.home_dir / "handoff.next.md").write_text(NOTE)
        found = block("handoff", "Scheduled task \\(").replace("<threadId>", thread)
        assert TASKS in found
        reply = self.t3.listed() if reply is None else reply
        said = self.run("handoff", found.replace(TASKS, reply), self.main).stdout.splitlines()
        if said[0].startswith(("not the home", "not known")):
            return said
        return [line for line in said[1:] if not line.startswith(("title: ", "message: "))]

    def hands_off(self, thread, next, steps=4):
        """Run the first `steps` of the four steps a handoff ends with, then cut the turn off. The
        four steps write the handoff and remove `home-id`, launch, rename and settle. The next home
        starts while `thread` is still in its turn, and it checks `thread` after that turn ends.
        Return what the next home's start blocks said, or nothing when `thread` is not the
        home."""
        if not self.home_hands_off(thread).stdout.startswith("the home"):
            return None
        said = self.takes(next) if steps > 1 else []
        if steps > 2:
            self.t3.call(thread, call("handoff", "t3_thread_update"))
        if steps > 3:
            self.t3.call(thread, call("handoff", "t3_thread_organize"))
        self.t3.ends(thread, well=steps > 3)
        return [*said, self.looks(next)] if steps > 1 else None


@pytest.fixture
def home(tmp_path):
    return Home(tmp_path)


def test_a_home_pins_itself_at_its_start_and_a_second_start_pins_it_once(home):
    assert call("home", "t3_thread_organize", action="pin").given == {"action": "pin"}
    home.starts(THREAD)
    home.starts(THREAD)
    assert home.t3.pinned() == [THREAD] and home.t3.pins == 1


def test_a_first_home_has_no_home_before_it_to_take_from(home):
    home.t3.task(HOOK, OTHER)
    tasks, threads = home.starts(THREAD)
    assert tasks.startswith("no home before this one:")
    assert threads.startswith("no home before this one:")
    assert home.t3.bound(OTHER) == [HOOK]


def test_the_next_home_takes_each_task_of_the_last_and_keeps_a_webhooks_address(home):
    home.starts(THREAD)
    home.t3.task(HOOK, THREAD)
    home.t3.task("scheduled-task:off", THREAD, title="switched off", enabled=False)
    home.hands_off(THREAD, OTHER, steps=1)
    home.home_starts(OTHER)
    assert home.tasks_of_the_last(OTHER) == [
        f"take {HOOK}: jbus events: demo home posts into {THREAD}, the home before this one",
        f"take scheduled-task:off: switched off posts into {THREAD}, the home before this one",
    ]
    before = json.loads(home.t3.listed())
    assert home.starts(OTHER)[0] == f"none: no scheduled task posts into {THREAD}"
    after = json.loads(home.t3.listed())
    assert home.t3.bound(OTHER) == [HOOK, "scheduled-task:off"]
    for was, now in zip(before["tasks"], after["tasks"], strict=True):
        assert now == {**was, "boundThreadId": OTHER}
    take = call("home", "update_scheduled_task")
    assert take.given == {"scheduledTaskId": FILLED[ID], "bindToCurrentThread": True}


@pytest.mark.parametrize("kept", [f"{AUDIT} {THREAD}\n", f"scheduled-task:its-own {OTHER}\n", None])
def test_the_audit_of_the_last_home_is_deleted_and_what_was_kept_of_it_goes(home, kept):
    home.starts(THREAD)
    home.t3.task(AUDIT, THREAD, title=f"audit: {NAME} queue")
    home.hands_off(THREAD, OTHER, steps=1)
    home.home_starts(OTHER)
    audit = home.home_dir / "audit"
    if kept:
        audit.write_text(kept)
    assert home.tasks_of_the_last(OTHER) == [
        f"delete {AUDIT}: the audit of the home before this one"
    ]
    assert (audit.read_text() if audit.exists() else None) == (
        None if kept and kept.startswith(AUDIT) else kept
    )
    home.starts(OTHER)
    assert home.t3.tasks == {}
    queue = home.run("home", block("home", "schedule: a queue"), home.main, OTHER).stdout
    assert not queue.startswith(("replace:", "delete:")) or AUDIT not in queue


def test_a_task_of_another_home_is_left_where_it_is(home):
    another = "mcp:another-thread"
    home.starts(THREAD)
    home.t3.task(HOOK, another)
    home.hands_off(THREAD, OTHER)
    assert home.t3.bound(another) == [HOOK]


def test_a_tasks_address_is_never_printed(home):
    home.starts(THREAD)
    home.t3.task(HOOK, THREAD)
    assert ADDRESS in home.t3.listed()
    assert ADDRESS not in "\n".join(home.listed_at_handoff(THREAD))
    home.hands_off(THREAD, OTHER, steps=1)
    home.home_starts(OTHER)
    assert ADDRESS not in "\n".join(home.tasks_of_the_last(OTHER))


@pytest.mark.parametrize("reply", [TASKS, "", "{}", '{"tasks": null}', "not json"])
def test_a_reply_that_is_not_filled_in_is_said_and_names_no_task(home, reply):
    home.starts(THREAD)
    home.hands_off(THREAD, OTHER, steps=1)
    home.home_starts(OTHER)
    assert home.tasks_of_the_last(OTHER, reply)[0].startswith("not read:")
    assert home.thread_of_the_last(OTHER, reply)[0].startswith("not read:")
    assert home.listed_at_handoff(OTHER, reply) == [
        "not read: put the whole reply of list_scheduled_tasks in place of the placeholder"
    ]


def test_the_handoff_names_the_tasks_the_next_home_takes_and_deletes_only_its_audit(home):
    home.starts(THREAD)
    assert home.listed_at_handoff(THREAD) == ["none: no scheduled task posts into this thread"]
    home.t3.task(HOOK, THREAD)
    home.t3.task(AUDIT, THREAD, title=f"audit: {NAME} queue")
    home.t3.task("scheduled-task:theirs", OTHER)
    assert home.listed_at_handoff(THREAD) == [
        f"Scheduled task {HOOK}, jbus events: demo home: it posts into the thread that handed "
        "off, and the next home takes it over at its start",
        f"delete {AUDIT}: the audit of a queue, which the home that hands off deletes",
    ]


@pytest.mark.parametrize("thread", ["<threadId>", "", "two words"])
def test_a_handoff_with_no_id_filled_in_does_not_say_it_has_no_task(home, thread):
    home.starts(THREAD)
    home.t3.task(HOOK, THREAD)
    said = home.listed_at_handoff(thread)
    if thread:
        (line,) = said
        assert line.startswith("not known: put this thread's id in place of the placeholder")
        assert (home.home_dir / "handoff.next.md").exists()
    else:
        assert said == ["not the home: start nothing, tell the user"]
    assert home.file.read_text() == f"{THREAD}\n"


def test_a_closed_scopes_home_switches_its_tasks_off_so_no_run_makes_it_active_again(home):
    home.starts(THREAD)
    home.t3.task(HOOK, THREAD)
    off = call("handoff", "update_scheduled_task", enabled=False)
    assert off.given == {"scheduledTaskId": FILLED[ID], "enabled": False}
    for said in home.listed_at_handoff(THREAD):
        assert said.startswith(f"Scheduled task {HOOK}, ")
        home.t3.call(THREAD, off, **{FILLED[ID]: said.split()[2].rstrip(",")})
    home.t3.call(THREAD, call("handoff", "t3_thread_organize"))
    home.t3.ends(THREAD)
    home.t3.runs(HOOK)
    assert home.t3.threads[THREAD]["settled"]
    assert home.t3.tasks[HOOK] == {**home.t3.tasks[HOOK], "enabled": False, "webhookUrl": ADDRESS}
    home.hands_off(THREAD, OTHER, steps=1)
    home.starts(OTHER)
    assert home.t3.bound(OTHER) == [HOOK]


def test_the_next_home_reads_the_last_ones_own_row_and_settles_it_if_it_is_not(home):
    home.starts(THREAD)
    assert call("home", "t3_thread_list", titleContains=TITLE).where != ""
    assert home.hands_off(THREAD, OTHER)[-1] == (
        f"settled: {THREAD} is settled, and a settle clears its pin"
    )
    assert home.t3.settled_by == [THREAD]
    assert home.t3.threads[THREAD]["title"] == f"{TITLE} (handed off 2026-10-10)"
    home.t3.threads[THREAD].update(settled=False, pinned=True)
    assert home.looks(OTHER) == (
        f"settle {THREAD}: the home before this one is still active, and may still be pinned"
    )
    assert home.t3.settled_by == [THREAD, OTHER] and home.t3.pinned() == [OTHER]
    settle = call("home", "t3_thread_organize", action="settle")
    assert settle.given == {"action": "settle", "threadId": FILLED["<thread>"]}


def test_a_last_home_the_list_does_not_have_is_said_and_asked_for_on_the_next_page(home):
    home.starts(THREAD)
    home.hands_off(THREAD, OTHER, steps=1)
    home.home_starts(OTHER)
    page = {"threads": [{"threadId": OTHER, "settled": False}], "nextCursor": 100}
    assert home.thread_of_the_last(OTHER, json.dumps(page)) == [
        f"more: {THREAD} is not on this page, call again with cursor 100"
    ]
    assert home.thread_of_the_last(OTHER, json.dumps({**page, "nextCursor": None})) == [
        f"not found: no thread with this title has the id {THREAD}, so nothing is settled"
    ]


def test_a_task_a_call_is_refused_for_is_named_as_left_and_not_asked_for_again(home):
    home.starts(THREAD)
    home.t3.task(HOOK, THREAD)
    home.t3.task("scheduled-task:theirs", THREAD, title="another modes")
    home.t3.refuses = {"scheduled-task:theirs"}
    said = home.hands_off(THREAD, OTHER)
    assert said[:-1] == [
        f"left scheduled-task:theirs: another modes still posts into {THREAD}, "
        "the call for it was refused"
    ]
    assert home.t3.bound(OTHER) == [HOOK]
    assert home.tasks_of_the_last(OTHER, refused="")[0].startswith("take scheduled-task:theirs")


def test_a_run_of_a_task_left_bound_makes_the_settled_home_active_and_the_start_ends_that(home):
    home.starts(THREAD)
    home.t3.task(HOOK, THREAD)
    home.hands_off(THREAD, OTHER, steps=1)
    home.t3.thread(OTHER)
    home.t3.call(THREAD, call("handoff", "t3_thread_organize"))
    home.t3.ends(THREAD)
    assert home.t3.threads[THREAD]["settled"]
    home.t3.runs(HOOK)
    assert not home.t3.threads[THREAD]["settled"]
    home.starts(OTHER)
    home.t3.runs(HOOK)
    assert home.t3.threads[THREAD]["settled"] and home.t3.pinned() == [OTHER]


@pytest.mark.parametrize(
    ("cut", "again"), list(itertools.product([1, 2, 3, 4], ["the handoff", "the start"]))
)
def test_a_handoff_cut_off_anywhere_and_run_again_ends_in_the_same_state(home, cut, again):
    home.starts(THREAD)
    home.t3.task(HOOK, THREAD)
    home.t3.task(AUDIT, THREAD, title=f"audit: {NAME} queue")
    home.hands_off(THREAD, OTHER, steps=cut)
    home.t3.runs(HOOK)
    if again == "the handoff":
        assert home.hands_off(THREAD, OTHER) is None
        assert (home.home_dir / "handoff.md").read_text().endswith(f"\nWas home: {THREAD}\n")
    home.starts(OTHER)
    assert home.starts(OTHER) == [
        f"none: no scheduled task posts into {THREAD}",
        f"settled: {THREAD} is settled, and a settle clears its pin",
    ]
    assert home.t3.pinned() == [OTHER]
    assert home.t3.threads[THREAD]["settled"] and not home.t3.threads[OTHER]["settled"]
    assert home.t3.bound(THREAD) == [] and home.t3.bound(OTHER) == [HOOK]
    assert home.file.read_text() == f"{OTHER}\n"
    assert (cut > 2) == home.t3.threads[THREAD]["title"].endswith("(handed off 2026-10-10)")
