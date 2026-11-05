"""The playbook's block that opens a pull request: the outbound check still reads what it sends."""

import re
import textwrap

from jleak import sources
from testing.paths import REPO

FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)


def block(path, about):
    (found,) = [text for text in FENCED.findall((REPO / path).read_text()) if about in text]
    return textwrap.dedent(found)


def opening():
    text = block("features/writing/playbooks/opening-a-pr.md", "gh pr create")
    for word, value in (("that branch", "main"), ("the title", "feat: a"), ("the file", "b.md")):
        text = re.sub(f"<{word}[^>]*>", value, text)
    return text


def test_the_outbound_check_still_reads_the_title_and_the_body_file(tmp_path):
    (tmp_path / "b.md").write_text("the body\n")
    _, sent = sources.command(opening(), tmp_path)
    read = {text.where: [line for _, line in text.lines] for text in sent}
    assert read["body file"] == ["the body"] and "feat: a" in read["command"]
