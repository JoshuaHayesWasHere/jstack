"""Prose in docs/, skills/, playbooks/ and templates/ is written one sentence per line, and a
sentence over the limit breaks after a comma, colon or semicolon of its own (semantic line
breaks). A paragraph on one long line is where two branches collide: an edit to any word of it
is a conflict with an edit to any other. This lint holds the length, which is the part a test
can see: a prose line over LIMIT characters fails.

Not prose, and exempt: fenced code, a YAML front matter, an HTML comment or tag line (a
template's `<...>` guide line among them), a table row, a quote (`>`, words kept as they were
said), indented code, a line that is one code span, and a line that a reader takes whole by
line. Those are a template's `Label: value` field line (jbriefs reads the Result's and the
report's labels by that shape) and its `- <name>: <value>` item (the shape jbriefs reads
templates/skill-artifacts.md by), a playbook's `Run by:` line (jbriefs and the crew skill read
it whole) and its numbered steps (the crew and expert skills print them as a checklist by a
grep for a line that starts with a number and a dot), and the templates read whole as one
message (WHOLE)."""

import re
from pathlib import Path

REPO = Path(__file__).parent.parent
DIRS = ("docs", "skills", "playbooks", "templates")
LIMIT = 250
WHOLE = ("templates/hook-message.md", "templates/rerun.md")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
LITERAL = re.compile(r"^(?:(?:[-*+]|\d+[.)])\s+)?`[^`]+`[.,;:]?$")
ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
TEMPLATE = re.compile(r"^(?:[-*] +`?[^`:\s]+`?:|[A-Z][A-Za-z0-9<>]*(?: [A-Za-z0-9<>]+)*:)")
BLOCKS = ("#", "|", "<", ">")
PLAYBOOK = re.compile(r"^(?:\d+\. |Run by: )")
FIELDS = {"templates": TEMPLATE, "playbooks": PLAYBOOK}


def long_lines(text: str, field: re.Pattern | None = None) -> list[int]:
    """The numbers of the prose lines of a markdown text over LIMIT characters."""
    found = []
    fence = None
    front = text.startswith("---\n")
    comment = False
    listed = False
    blank = True
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if front:
            front = number == 1 or stripped != "---"
            continue
        if fence:
            closing = FENCE.match(line)
            if closing and closing[1][0] == fence[0] and len(closing[1]) >= len(fence):
                fence = None
            continue
        if opening := FENCE.match(line):
            fence = opening[1]
            continue
        if comment:
            comment = "-->" not in line
            continue
        if stripped.startswith("<!--"):
            comment = "-->" not in stripped
            continue
        if not stripped:
            blank = True
            continue
        indent = len(line) - len(line.lstrip(" "))
        if ITEM.match(line):
            listed = True
        elif indent == 0 and blank:
            listed = False
        coded = indent >= 4 and blank and not listed
        blank = False
        if (
            len(line) <= LIMIT
            or stripped.startswith(("|", "<", ">"))
            or coded
            or LITERAL.match(stripped)
            or (field and field.match(line))
        ):
            continue
        found.append(number)
    return found


def unwrapped(text: str) -> list[str]:
    """The lines of a markdown text with each prose line a sentence broke off joined back to
    the line it continues, so a test can read a paragraph or a list item as one line, and a
    cap on a page's lines counts what it counted before the text went one sentence a line."""
    found: list[str] = []
    fence = None
    joins = False
    for line in text.splitlines():
        stripped = line.strip()
        if fence:
            closing = FENCE.match(line)
            if closing and closing[1][0] == fence[0] and len(closing[1]) >= len(fence):
                fence = None
            found.append(line)
            continue
        if opening := FENCE.match(line):
            fence = opening[1]
            found.append(line)
            joins = False
            continue
        if joins and stripped and not ITEM.match(line) and not stripped.startswith(BLOCKS):
            found[-1] += " " + stripped
            continue
        found.append(line)
        joins = bool(stripped) and not stripped.startswith(BLOCKS)
    return found


def prose_files():
    for top in DIRS:
        for path in sorted((REPO / top).rglob("*.md")):
            if str(path.relative_to(REPO)) not in WHOLE:
                yield path


def test_no_prose_line_is_over_the_limit():
    over = [
        f"{path.relative_to(REPO)}:{number}"
        for path in prose_files()
        for number in long_lines(path.read_text(), FIELDS.get(path.relative_to(REPO).parts[0]))
    ]
    assert not over, (
        f"{len(over)} prose lines over {LIMIT} characters: break them one sentence per line: {over}"
    )


def test_the_lint_fails_on_one_long_prose_line(tmp_path):
    sentence = "word " * 59 + "ends."
    assert len(sentence) == 300
    page = tmp_path / "page.md"
    page.write_text(f"# A page\n\nA short line.\n{sentence}\nAnother short line.\n")
    assert long_lines(page.read_text()) == [4]


def test_the_lint_leaves_code_tables_guides_and_fields_alone():
    long = "x" * 300
    text = "\n".join(
        [
            "---",
            f"description: {long}",
            "---",
            "```sh",
            f"echo {long}",
            "```",
            f"| a | {long} |",
            f"<{long}>",
            f"> {long}",
            "<!--",
            long,
            "-->",
            "",
            f"    {long}",
            "",
            f"Field: <{long}>",
            f"- name: {long}",
            f"   `{long}`",
            f"1. {long}",
            f"Run by: {long}",
        ]
    )
    assert long_lines(text, TEMPLATE) == [19]
    assert long_lines(text, PLAYBOOK) == [16, 17]
    assert long_lines(text) == [16, 17, 19, 20]
    assert long_lines(f"Not a field: {long}.", PLAYBOOK) == [1]


def test_unwrapped_joins_a_broken_sentence_back_and_leaves_items_and_code_alone():
    text = "One sentence.\nAnother,\n  and its clause.\n- An item.\n  Its second.\n\n"
    text += "```sh\na\nb\n```\n"
    assert unwrapped(text) == [
        "One sentence. Another, and its clause.",
        "- An item. Its second.",
        "",
        "```sh",
        "a",
        "b",
        "```",
    ]
