"""A scout goes out on a path of its own: `jbus scout add` stores its request in the home's
`scouts/`, `jbus scout approve` records the user's go, and a pass launches it read-only, as
`/scout <slug>` in the main checkout with no branch. Like `test_jbus_kitchen.py`, the tests run
the real command and the real pass against a faked T3 Code server, `gh` and `jmerge`."""

import json

import pytest

from jbriefs import parse
from jbus import queue
from test_jbus_kitchen import Kitchen
from test_jbus_queue import brief

HEAD = "| slug | state | report | thread | approved |"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def request(slug, more="", asked="find out what X does"):
    """Return a request in the shape of `features/scout/templates/scout-request.md`."""
    return (
        f"# {slug}: what X does\n"
        f'Request: "{asked}"\n'
        "Questions:\n"
        "- What calls X? Start at `src/x.py`.\n"
        "Deliver:\n"
        '- Under "## Report" in this file: the findings with their evidence.\n'
        "Playbook: none\n"
        "Out of bounds: read-only. Run nothing that writes.\n"
        f"{more}"
    )


def add(kitchen, slug, text=None):
    return kitchen.main("scout", "add", slug, stdin=request(slug) if text is None else text)


def sha12(kitchen, slug):
    return queue.brief_sha((kitchen.home / "scouts" / f"{slug}.md").read_text())[:12]


def approve(kitchen, slug, sha=None):
    sha = sha or sha12(kitchen, slug)
    return kitchen.main("scout", "approve", slug, "--sha", sha, "--word", kitchen.word())


def shown(kitchen):
    code, said = kitchen.main("scout", "show")
    assert code == 0, said
    lines = said.splitlines()
    assert lines[0] == HEAD
    return {line.split(" | ")[0].strip("| "): line.split(" | ")[1:] for line in lines[2:]}


def launches(kitchen):
    return [one for one in kitchen.t3.launches if one["title"].startswith("scout: ")]


def test_an_added_request_is_stored_in_the_homes_scouts_and_waits_for_a_go(kitchen):
    code, said = add(kitchen, "alpha")

    assert (code, said) == (0, f"added alpha: request {sha12(kitchen, 'alpha')}, waits for a go\n")
    assert (kitchen.home / "scouts" / "alpha.md").read_text() == request("alpha")
    assert shown(kitchen)["alpha"][:3] == ["requested", "none", ""]
    kitchen.poll()
    assert launches(kitchen) == []


@pytest.mark.parametrize("line", ['Task: "do alpha"', "Size: S", "Pull request: open one"])
def test_a_request_with_a_crewmates_line_is_refused_and_names_the_line(kitchen, line):
    label = line.split(":")[0]

    code, said = add(kitchen, "alpha", request("alpha", f"{line}\n"))

    assert code == 1
    assert f"- a {label}: line, which only a crewmate's brief has" in said
    assert said.startswith("refused: alpha's request has 1 fault, and nothing is stored")
    assert not (kitchen.home / "scouts" / "alpha.md").exists()


@pytest.mark.parametrize(
    "broken, fault",
    [
        (
            request("alpha").replace("Questions:\n- What calls X? Start at `src/x.py`.\n", ""),
            "no Questions: line",
        ),
        (
            request("alpha").replace(
                "Questions:\n- What",
                "Questions:\n- <a question the report must answer, with where to start looking>"
                "\n- What",
            ),
            "Questions: line is the template's own text",
        ),
        (
            request("alpha").replace("read-only. Run", "Run"),
            "Out of bounds: line does not start read-only",
        ),
        (
            request("alpha").replace("# alpha:", "# beta:"),
            "first line is not # alpha: <what to find out>",
        ),
    ],
)
def test_a_request_not_in_the_templates_shape_is_refused(kitchen, broken, fault):
    code, said = add(kitchen, "alpha", broken)

    assert code == 1
    assert f"- {fault}" in said
    assert not (kitchen.home / "scouts" / "alpha.md").exists()


def test_angle_brackets_that_are_not_the_templates_own_text_are_taken(kitchen):
    asked = "find out why a < b and c > d fails in Map<String, Int> handling"

    assert add(kitchen, "alpha", request("alpha", asked=asked))[0] == 0


def test_a_request_line_over_the_limit_is_refused(kitchen):
    asked = "x" * (parse.LONGEST + 1)

    code, said = add(kitchen, "alpha", request("alpha", asked=asked))

    assert code == 1
    longest = f"over the {parse.LONGEST} it may have"
    assert f"- Request: line is {parse.LONGEST + 3} characters, {longest}" in said
    assert add(kitchen, "alpha", request("alpha", asked="x" * (parse.LONGEST - 2)))[0] == 0


def test_a_task_line_over_the_limit_is_refused_by_queue_add_too(kitchen):
    long = brief("alpha").replace('"do alpha"', "y" * (parse.LONGEST + 1))

    code, said = kitchen.main("queue", "add", "alpha", "--priority", "1", stdin=long)

    assert code == 1
    assert f"brief's Task: line is {parse.LONGEST + 1} characters" in said
    assert queue.load(kitchen.state) == []


def test_a_request_a_home_wrote_itself_is_not_taken_over(kitchen):
    (kitchen.home / "scouts" / "alpha.md").write_text(request("alpha"))

    code, said = add(kitchen, "alpha")

    assert code == 1
    assert said.startswith("refused: scouts/alpha.md is there already and jbus did not add it")


def test_approval_takes_the_word_and_the_sha_of_the_request_shown(kitchen):
    add(kitchen, "alpha")

    assert approve(kitchen, "alpha", sha="0" * 12) == (
        1,
        f"refused: alpha's request is {sha12(kitchen, 'alpha')}, not {'0' * 12}\n",
    )
    assert kitchen.main("scout", "approve", "alpha", "--sha", sha12(kitchen, "alpha"))[0] == 1
    code, said = approve(kitchen, "alpha")

    assert code == 0, said
    assert said.startswith(f"approved alpha: request {sha12(kitchen, 'alpha')}, his word, ")
    assert shown(kitchen)["alpha"][0] == "approved"


def test_a_pass_launches_an_approved_scout_read_only_with_no_branch(kitchen):
    add(kitchen, "alpha")
    add(kitchen, "beta")
    approve(kitchen, "alpha")

    said = kitchen.poll()

    (made,) = launches(kitchen)
    assert made["title"] == "scout: alpha"
    assert made["workspaceStrategy"] == {"type": "root"}
    assert made["message"] == "/scout alpha"
    (thread,) = [t for t in kitchen.t3.threads if t["title"] == "scout: alpha"]
    assert thread["branch"] is None
    assert f"launched scout alpha: {thread['threadId']}" in said
    kept = (kitchen.home / "scouts" / "alpha.md").read_text()
    assert kept == request("alpha") + f"Thread: {thread['threadId']}\n"
    assert shown(kitchen)["alpha"][:3] == ["launched", "none", thread["threadId"]]
    assert shown(kitchen)["beta"][0] == "requested"
    assert queue.load(kitchen.state) == []

    kitchen.poll()
    assert len(launches(kitchen)) == 1


def test_a_request_changed_after_its_go_does_not_launch(kitchen):
    add(kitchen, "alpha")
    approve(kitchen, "alpha")
    path = kitchen.home / "scouts" / "alpha.md"
    path.write_text(path.read_text().replace("What calls X?", "What calls Y?"))

    said = kitchen.poll()

    assert launches(kitchen) == []
    assert shown(kitchen)["alpha"][0] == "changed"
    assert any(line.startswith("wait scout alpha: its request changed") for line in said)


def test_show_gives_the_status_of_the_last_report(kitchen):
    add(kitchen, "alpha")
    approve(kitchen, "alpha")
    kitchen.poll()
    path = kitchen.home / "scouts" / "alpha.md"
    path.write_text(path.read_text() + "\n## Report\nStatus: done\nFindings: X calls Y.\n")

    assert shown(kitchen)["alpha"][:2] == ["launched", "reported"]


def test_a_lost_launch_reply_is_adopted_and_never_launched_again(kitchen):
    add(kitchen, "alpha")
    approve(kitchen, "alpha")
    kitchen.t3.lose = "after"

    kitchen.poll()
    assert shown(kitchen)["alpha"][0] == "launching"
    kitchen.t3.lose = None
    said = kitchen.poll()

    assert len(launches(kitchen)) == 1
    (thread,) = [t for t in kitchen.t3.threads if t["title"] == "scout: alpha"]
    assert f"adopted scout alpha: {thread['threadId']}" in said
    assert shown(kitchen)["alpha"][:3] == ["launched", "none", thread["threadId"]]
    assert json.loads((kitchen.state / "scouts.json").read_text())[0]["launch"]["adopted"]
