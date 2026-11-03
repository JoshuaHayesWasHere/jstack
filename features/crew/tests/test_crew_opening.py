"""The block a crewmate opens its pull request with, in `opening-a-pr.md` step 6, runs the prose
lint over the title and the body and opens nothing while a line of them holds two sentences.
Each test runs the block as an agent runs it, with `T` set as the crew skill's top block sets
it, against a `gh` that records what it is asked. Step 5 asks for no skill to be read: the
lint is the bar, and the two writing skills stay where a model can load them by itself."""

import os
import re
import subprocess
import textwrap

import pytest

from jbriefs.skills import listed
from jinstall import layout
from testing.layouts import assembled
from testing.paths import REPO

PLAYBOOK = REPO / "features" / "writing" / "playbooks" / "opening-a-pr.md"
FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)
URL = "https://example.test/ada/demo/pull/7"
GH = f"""\
#!/bin/sh
echo "$*" >> "$(dirname "$0")/gh.log"
case $2 in
create) printf 'Creating pull request for alpha into main\\n{URL}\\n' ;;
esac
"""
BODY = """\
## Why
The crew skipped the writing skills at opening.
A check on the text holds the bar instead.

## Scope
- The opening block only.
"""


def step(number):
    return re.search(rf"^{number}\. .*?(?=^\d\. )", PLAYBOOK.read_text(), re.M | re.S).group()


@pytest.fixture
def opened(tmp_path):
    """Run step 6's block with a title and a body, and give what it printed and what `gh` was
    asked."""
    (tmp_path / "gh").write_text(GH)
    (tmp_path / "gh").chmod(0o755)
    (found,) = FENCED.findall(step(6))

    def run(title, body):
        (tmp_path / "body.md").write_text(body)
        text = textwrap.dedent(found)
        for word, value in (("that branch", "main"), ("the title", title), ("the file", "body.md")):
            text = re.sub(f"<{word}[^>]*>", value, text)
        env = {
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "T": str(assembled() / "templates"),
        }
        ran = subprocess.run(
            ["bash", "-c", text], cwd=tmp_path, capture_output=True, text=True, env=env
        )
        log = tmp_path / "gh.log"
        return ran.stdout.splitlines(), log.read_text().splitlines() if log.exists() else []

    return run


def test_a_body_with_a_line_of_two_sentences_opens_nothing_and_says_which_line(opened):
    line = "The crew skipped the writing skills. A check holds the bar instead."
    said, asked = opened(
        "feat(crew): lint the text", BODY.replace("## Scope", f"{line}\n\n## Scope")
    )
    assert asked == []
    assert said[0] == f"<stdin>:5: more than one sentence, break it at sentence ends: {line}"
    assert said[-1].startswith("not opened:")


def test_a_title_of_two_sentences_opens_nothing(opened):
    said, asked = opened("feat(crew): lint the text. It holds the bar", BODY)
    assert asked == []
    assert said[-1].startswith("not opened:")


def test_a_title_and_body_one_sentence_a_line_open_and_lock(opened):
    said, asked = opened("feat(crew): lint the text", BODY)
    assert said == [f"opened and locked: {URL}"]
    assert [line.split()[:2] for line in asked] == [["pr", "create"], ["pr", "lock"]]


def test_a_crew_opens_its_pull_request_ready_and_never_as_a_draft(opened):
    """CI checks a pull request on each push, beside its review, and jmerge marks no draft ready
    (fl-no-draft): a draft would wait for good, so step 6 opens it ready."""
    _, asked = opened("feat(crew): lint the text", BODY)
    assert asked[0].startswith("pr create --base main ") and "--draft" not in asked[0]
    assert "open it ready, never as a draft" in step(6)


def test_step_five_names_no_skill_to_read():
    named = {REPO / path for path in re.findall(r"`([^`]+\.md)`", step(5))}
    assert named & set(listed("skill", REPO).values()) == set()


@pytest.mark.parametrize("name", ["technical-writing", "unslop"])
def test_a_writing_skill_stays_one_a_model_may_load_by_itself(name):
    assert name in listed("skill", REPO)
    assert name not in layout.hidden(REPO)
