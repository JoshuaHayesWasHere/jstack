"""Prose in docs/, skills/, playbooks/ and templates/ is written one sentence per line, and a
sentence over the limit breaks after a comma, colon or semicolon of its own (semantic line
breaks). A paragraph on one long line is where two branches collide: an edit to any word of it
is a conflict with an edit to any other. This lint holds the length, which is the part a test
can see: a prose line over LIMIT characters fails.

Not prose, and exempt: fenced code, a YAML front matter, an HTML comment or tag line (a
template's `<...>` guide line among them), a table row, indented code, a line that is one code
span (a message the skill has an agent send whole, as one line), and a field line that a
parser reads whole by line (a template's `Label: <...>` line, a field its reader fills in, in
the shape jbriefs reads a Result's and a report's labels by, or a `- <name>: <value>` item, the
shape it reads templates/skill-artifacts.md by; and a playbook's numbered step, which the
crew and expert skills print as a checklist by a grep for a line that starts with a number
and a dot, and tests/test_playbooks.py reads one line each)."""

import re
from pathlib import Path

REPO = Path(__file__).parent.parent
DIRS = ("docs", "skills", "playbooks", "templates")
LIMIT = 250
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
LITERAL = re.compile(r"^(?:(?:[-*+]|\d+[.)])\s+)?`[^`]+`$")
ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
BLOCKS = ("#", "|", "<", ">")
LABEL = re.compile(r"^(?:[-*] +`?[^`:\s]+`?|[A-Z][A-Za-z]*(?: [A-Za-z]+)*: .*<)")
STEP = re.compile(r"^\d+\. ")
FIELDS = {"templates": LABEL, "playbooks": STEP}


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
            or stripped.startswith(("|", "<"))
            or coded
            or LITERAL.match(stripped)
            or (field and field.match(stripped))
        ):
            continue
        found.append(number)
    return found


def unwrapped(text: str) -> list[str]:
    """The lines of a markdown text with each prose line a sentence broke off joined back to
    the line it continues, so a test can read a paragraph or a list item as one line."""
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
        yield from sorted((REPO / top).rglob("*.md"))


def test_no_prose_line_is_over_the_limit():
    over = [
        f"{path.relative_to(REPO)}:{number}"
        for path in prose_files()
        for number in long_lines(path.read_text(), FIELDS.get(path.relative_to(REPO).parts[0]))
    ]
    assert not over, (
        f"{len(over)} prose lines over {LIMIT} characters: break them one sentence per line: {over}"
    )


def test_the_lint_fails_on_one_long_prose_line():
    sentence = "word " * 59 + "ends."
    assert len(sentence) == 300
    text = f"# A page\n\nA short line.\n{sentence}\nAnother short line.\n"
    assert long_lines(text) == [4]


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
            "<!--",
            long,
            "-->",
            "",
            f"    {long}",
            "",
            f"Field: <{long}>",
            f"- name: {long}",
            f"   `{long}`",
        ]
    )
    assert long_lines(text, LABEL) == []
    assert long_lines(text) == [15, 16]
    prose = f"Not a field: {long}."
    assert long_lines(prose, LABEL) == [1]
    step = f"1. {long}"
    assert long_lines(step, STEP) == []
    assert long_lines(step) == [1]


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
