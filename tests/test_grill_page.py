"""The grilling page: its script is run in node, on a round, with a stand-in `window.lavish`."""

import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
TEMPLATE = REPO / "templates" / "grill-page.html"
GRILLING = REPO / "skills" / "grilling" / "SKILL.md"

HARNESS = Path(__file__).parent / "fixtures" / "grill-page" / "harness.js"

ROUND = {
    "slug": "cutover",
    "round": 2,
    "title": "The `jstack` cutover",
    "lead": "Three questions.",
    "settled": [
        {
            "round": 1,
            "id": "when",
            "title": "The cutover waits for the move",
            "answer": "Yes: after the move",
            "left_as_recommended": True,
            "note": "",
        }
    ],
    "questions": [
        {
            "id": "links",
            "title": "The skill links move first",
            "body": "They are read by every new thread.",
            "options": [
                {"id": "first", "label": "Yes: links first", "why": "w", "recommended": True},
                {"id": "last", "label": "Links last"},
            ],
        },
        {
            "id": "state",
            "title": "The state directory is renamed",
            "body": "One paragraph.\n\nAnd a second.",
            "options": [
                {"id": "rename", "label": "Yes: rename it", "recommended": True},
                {"id": "copy", "label": "Copy it, keep the `old` one"},
                {"id": "leave", "label": "Leave it"},
            ],
        },
        {
            "id": "gate-3",
            "title": "The old command is uninstalled",
            "body": "A gate.",
            "built_on": "the cutover's second step",
            "undo": "`uv tool install` it again",
            "options": [
                {"id": "uninstall", "label": "Yes: uninstall", "recommended": True},
                {"id": "keep", "label": "Keep it"},
            ],
        },
    ],
}
PICKS = [
    {"id": "state", "option": "copy", "note": "  keep it a week\nthen delete "},
    {"id": "gate-3", "note": "fine"},
]
ANSWERS = [
    {
        "id": "links",
        "option": "first",
        "label": "Yes: links first",
        "left_as_recommended": True,
        "note": "",
    },
    {
        "id": "state",
        "option": "copy",
        "label": "Copy it, keep the old one",
        "left_as_recommended": False,
        "note": "keep it a week\nthen delete",
    },
    {
        "id": "gate-3",
        "option": "uninstall",
        "label": "Yes: uninstall",
        "left_as_recommended": True,
        "note": "fine",
    },
]
TEXT = """\
Answers to round 2 of cutover:
- links: first (Yes: links first), left as recommended
- state: copy (Copy it, keep the old one), changed from the recommended. Note: keep it a week then delete
- gate-3: uninstall (Yes: uninstall), left as recommended. Note: fine"""  # noqa: E501
CONTEXT = {"slug": "cutover", "round": 2, "answers": ANSWERS}


def page(round_=ROUND, picks=(), lavish=True, template=TEMPLATE, **more):
    """What the page did with `round_` in its data block, `picks` made and the button pressed."""
    if not shutil.which("node"):
        pytest.skip("no node on PATH to run the page's script in")
    spec = {"round": round_, "picks": list(picks), "lavish": lavish, **more}
    done = subprocess.run(
        ["node", str(HARNESS), str(template)],
        input=json.dumps(spec),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)


def test_the_button_sends_one_prompt_for_the_round():
    sent = page(picks=PICKS)
    assert sent["calls"] == [
        [
            "queuePrompt",
            TEXT,
            {
                "tag": "round",
                "text": "Round 2: 3 answers",
                "queueKey": "cutover-round-2",
                "data": CONTEXT,
            },
        ],
        ["sendQueuedPrompts"],
    ]
    assert sent["state"] == "sent"
    assert sent["copy_hidden"] is True


def test_a_round_nobody_touched_is_sent_as_the_recommended_answers():
    ((_, text, options), _) = page()["calls"]
    assert text == (
        "Answers to round 2 of cutover:\n"
        "- links: first (Yes: links first), left as recommended\n"
        "- state: rename (Yes: rename it), left as recommended\n"
        "- gate-3: uninstall (Yes: uninstall), left as recommended"
    )
    assert [answer["left_as_recommended"] for answer in options["data"]["answers"]] == [True] * 3


def test_with_no_lavish_the_page_shows_the_same_text_to_copy():
    shown = page(picks=PICKS, lavish=False)
    assert shown["calls"] == []
    assert shown["copy_hidden"] is False
    assert shown["copy"] == TEXT + "\n\nContext data:\n" + json.dumps(CONTEXT, indent=2)
    assert shown["state"].startswith("not sent: ")


def test_the_recommended_option_is_checked_and_every_input_is_inside_its_question():
    drawn = page()
    assert drawn["checked"] == {
        "2:links": ["first"],
        "2:state": ["rename"],
        "2:gate-3": ["uninstall"],
    }
    assert drawn["count"] == "3 of 3 left as recommended"
    radios = ["2:links"] * 2 + ["2:state"] * 3 + ["2:gate-3"] * 2
    inputs = [(c["tag"], c["question"]) for c in drawn["controls"]]
    assert sorted(inputs) == sorted(
        [("input", q) for q in radios]
        + [("textarea", q) for q in ("2:links", "2:state", "2:gate-3")]
    )
    assert [c for c in drawn["controls"] if c["details"]] == []


def test_a_gate_shows_what_was_built_on_it_and_how_to_undo_it():
    links, _, gate = page()["cards"]
    assert "Built onthe cutover's second step" in gate
    assert "Undouv tool install it again" in gate
    assert "Built on" not in links
    assert "Undo" not in links


def test_settled_rounds_stay_above_the_open_one():
    drawn = page()
    assert drawn["settled"] == [
        ["1", "The cutover waits for the move", "Yes: after the move", "left as recommended"]
    ]
    assert drawn["settled_hidden"] is False
    assert drawn["settled_above"] is True
    assert drawn["title"] == "The jstack cutover: round 2"
    assert page(round_={**ROUND, "settled": []})["settled_hidden"] is True


def test_the_page_loads_nothing_and_its_script_leaves_no_name_behind():
    drawn = page()
    assert drawn["loads"] == []
    assert drawn["scripts"] == 1
    assert drawn["leaked"] == []


def test_a_name_declared_at_the_top_of_the_script_is_caught():
    opened = "(function () {\n  'use strict';\n"
    assert opened in TEMPLATE.read_text()
    bare = page(script=[opened, "const top = 1;\n(function () {\n  'use strict';\n"])
    assert bare["leaked"] == ["top"]


def test_a_round_written_wrong_says_so_on_the_page_and_sends_nothing():
    first, second, third = (dict(q) for q in ROUND["questions"])
    first["options"] = [{"id": "first", "label": "Links first"}, {"id": "last", "label": "Last"}]
    second["options"] = [
        {"id": "rename", "label": "Yes", "recommended": True},
        {"id": "rename", "label": "Again"},
    ]
    third["id"] = "links"
    drawn = page(round_={**ROUND, "questions": [first, second, third]}, picks=PICKS[:0])
    assert drawn["problems"] == [
        "Two questions have the id links.",
        "Question links has 0 recommended options, not one.",
        "Question state has two options with the id rename.",
    ]
    assert drawn["problems_hidden"] is False
    assert drawn["send_disabled"] is True
    assert drawn["cards"] == []
    assert "calls" not in drawn


def test_a_round_that_is_not_json_says_so_on_the_page():
    drawn = page(raw='{"slug": "cutover",')
    (problem,) = drawn["problems"]
    assert problem.startswith("The round is not valid JSON: ")
    assert drawn["send_disabled"] is True


def test_the_round_the_template_ships_with_is_a_round():
    drawn = page(round_=None)
    assert drawn["checked"] == {"1:first-question": ["yes"]}
    assert drawn["problems"] == []
    assert drawn["problems_hidden"] is True
    ((_, text, options), _) = drawn["calls"]
    assert options["queueKey"] == "example-round-1"
    assert text == (
        "Answers to round 1 of example:\n"
        "- first-question: yes (Yes: the recommended answer), left as recommended"
    )


def on_a_page():
    return GRILLING.read_text().split("\n## On a page\n", 1)[1].split("\n## ", 1)[0]


def a_path_of(tmp_path, *commands):
    """A `PATH` of one directory that holds these commands and no other, so no `lavish-axi`."""
    only = tmp_path / "only"
    only.mkdir()
    for command in commands:
        (only / command).symlink_to(shutil.which(command))
    return str(only)


def test_with_no_lavish_axi_step_one_says_there_is_no_page_and_makes_no_file(tmp_path):
    user = tmp_path / "user"
    (user / ".claude" / "skills").mkdir(parents=True)
    (user / ".claude" / "skills" / "grilling").symlink_to(REPO / "skills" / "grilling")
    checkout = tmp_path / "code" / "alpha"
    checkout.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    bare = a_path_of(tmp_path, "sh", "git", "basename", "dirname", "realpath", "mkdir", "cp")
    found = re.findall(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", on_a_page(), re.M | re.S)
    top, make, *_ = [textwrap.dedent(block) for block in found]
    ran = subprocess.run(
        ["sh", "-c", "\n".join([top, make]).replace("<slug>", "cutover")],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(user), "PATH": bare},
        cwd=checkout,
        check=False,
    )
    assert (ran.returncode, ran.stdout, ran.stderr) == (
        0,
        "no page: lavish-axi is not installed\n",
        "",
    )
    assert not (user / ".local").exists()


def test_the_skills_blocks_make_the_page_from_the_template_and_hold_one_session(tmp_path):
    user = tmp_path / "user"
    (user / ".claude" / "skills").mkdir(parents=True)
    (user / ".claude" / "skills" / "grilling").symlink_to(REPO / "skills" / "grilling")
    checkout = tmp_path / "code" / "alpha"
    checkout.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    stub = bin_ / "lavish-axi"
    stub.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$HOME/called"\n'
        'if [ -f "$HOME/down" ]; then echo "error: the server did not start"; exit 1; fi\n'
        "echo 'session:'\n"
        "echo '  url: \"http://desk.example.test:4387/session/6afaf9554b5a36ca\"'\n"
        "echo '  status: opened'\n"
        "echo 'next_step: \"poll\"'\n"
    )
    stub.chmod(0o755)
    env = {**os.environ, "HOME": str(user), "PATH": f"{bin_}:{os.environ['PATH']}"}
    found = re.findall(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", on_a_page(), re.M | re.S)
    blocks = [textwrap.dedent(block) for block in found]
    done = [
        subprocess.run(
            ["sh", "-c", "\n".join([blocks[0], block]).replace("<slug>", "cutover")],
            capture_output=True,
            text=True,
            env=env,
            cwd=checkout,
            check=True,
        ).stdout
        for block in blocks[1:]
    ]
    made = user / ".local" / "state" / "home" / "alpha" / "reports" / "grill-cutover.html"
    assert made.read_text() == TEMPLATE.read_text()
    assert done[1] == ("  status: opened\nhttp://desk.example.test:4387/session/6afaf9554b5a36ca\n")
    assert (user / "called").read_text().splitlines() == [
        f"{made} --no-open",
        f"poll {made}",
        f"end {made}",
    ]
    made.write_text("round 2")
    first = "\n".join(blocks[:2]).replace("<slug>", "cutover")
    subprocess.run(["sh", "-c", first], capture_output=True, env=env, cwd=checkout, check=True)
    assert made.read_text() == "round 2"
    (user / "down").write_text("")
    opening = "\n".join([blocks[0], blocks[2]]).replace("<slug>", "cutover")
    failed = subprocess.run(
        ["sh", "-c", opening], capture_output=True, text=True, env=env, cwd=checkout, check=False
    )
    assert failed.returncode == 1
    assert failed.stdout == ("error: the server did not start\nno session: the page is not open\n")


def test_an_option_whose_id_is_a_number_is_still_the_answer_sent():
    first = {**ROUND["questions"][0]}
    first["options"] = [{"id": 1, "label": "Yes", "recommended": True}, {"id": 2, "label": "No"}]
    ((_, text, options), _) = page(round_={**ROUND, "questions": [first]})["calls"]
    assert text == "Answers to round 2 of cutover:\n- links: 1 (Yes), left as recommended"
    assert options["data"]["answers"][0]["left_as_recommended"] is True


def test_a_round_of_the_wrong_shape_says_so_and_does_not_stop_the_script():
    first = {**ROUND["questions"][0]}
    first["options"] = [{"label": "Yes", "recommended": True}, {"id": "no", "label": "No"}]
    drawn = page(round_={**ROUND, "settled": "none", "questions": [None, first]})
    assert drawn["problems"] == [
        "The settled answers are not a list of objects.",
        "A question is not an object with an id.",
        "Question links has an option that is not an object with an id.",
        "Question links has 0 recommended options, not one.",
    ]
    assert drawn["send_disabled"] is True
    assert page(raw="null")["problems"] == ["The round is not an object."]


@pytest.mark.parametrize(
    ("sessions", "said"),
    [
        (
            {
                "k1": {
                    "key": "k1",
                    "file": "PAGE",
                    "chat": [
                        {"role": "user", "id": "e1", "text": "first"},
                        {"role": "user", "id": "e2", "text": "picks"},
                        {"role": "agent", "id": "e3", "text": "thanks"},
                    ],
                },
                "k2": {"key": "k2", "file": "/another.html", "chat": []},
            },
            "k1/e2",
        ),
        (
            {"k2": {"key": "k2", "file": "/another.html"}},
            "no entry: Lavish keeps no session of this page",
        ),
        (
            {"k1": {"file": "PAGE", "chat": [{"role": "agent", "id": "e1"}]}},
            "no entry: the page has no send by the user",
        ),
        (
            {"k1": {"file": "PAGE", "chat": [{"role": "user", "text": "go"}]}},
            "no entry: Lavish kept the send with no id, so no approval can name it",
        ),
        (None, "no entry: Lavish's state at STATE could not be read"),
    ],
)
def test_the_skills_block_names_the_last_send_by_the_user_on_the_page(tmp_path, sessions, said):
    user = tmp_path / "user"
    (user / ".claude" / "skills").mkdir(parents=True)
    (user / ".claude" / "skills" / "grilling").symlink_to(REPO / "skills" / "grilling")
    checkout = tmp_path / "code" / "alpha"
    checkout.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    page = user / ".local" / "state" / "home" / "alpha" / "reports" / "grill-cutover.html"
    lavish = tmp_path / "lavish"
    lavish.mkdir()
    if sessions is not None:
        text = json.dumps({"sessions": sessions}).replace('"PAGE"', json.dumps(str(page)))
        (lavish / "state.json").write_text(text)
    found = re.findall(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", on_a_page(), re.M | re.S)
    top, *_ = blocks = [textwrap.dedent(block) for block in found]
    (named,) = [block for block in blocks if "no entry:" in block]
    ran = subprocess.run(
        ["sh", "-c", "\n".join([top, named]).replace("<slug>", "cutover")],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(user), "LAVISH_AXI_STATE_DIR": str(lavish)},
        cwd=checkout,
        check=False,
    )
    state = str(lavish / "state.json")
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, said.replace("STATE", state) + "\n", "")
