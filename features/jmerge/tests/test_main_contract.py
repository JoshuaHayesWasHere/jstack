"""The contract between `jmerge` and `jbus`, checked from both sides: the record of `main.json`
(`jmerge.mainjson`) and the lines that `jmerge` prints (`jmerge.lines`).

1. Each formatter's line parses back to the fields it was given, for every reason that
   `ready` names, and `merge.step` puts each reason on the step that declares it.
2. A table of records gives the `Main` that a reader acts on. Every record that the real
   `mainmoved.tell` writes, over every order of events that the red-main model walks, is a
   `Record`.
3. A real `jmerge` that could not ask GitHub prints a line that is about no pull request,
   and a jbus pass reports it as a `jmerge` that did not run.
4. No second copy exists: only `mainjson.py` writes the file's name and its keys, and only
   `lines.py` writes the pattern of a line.
"""

import ast
import string
from unittest import mock

import pytest

from jbus import mainmoved, merge, write_json
from jmerge import lines, mainjson, ready
from main_red_model import Options, walk
from test_gh_said import BAD_GATEWAY, real_jmerge_line
from testing.paths import sources

URL = "https://example.test/pull/7"
HEAD = "c" * 40
GREEN, RED, NEWER = "a" * 40, "b" * 40, "d" * 40


def _filled(template):
    """A reason with each value it names filled in. Each value is a word with no space or
    comma, as a user, a head or a path is. The values that a stale check needs are the
    exception, and they come from `ready` itself."""
    filled = {"needs": getattr(ready, "FRESH_CHECK", "")}
    fields = {name for _, name, _, _ in string.Formatter().parse(template) if name}
    return template.format(**{name: filled.get(name, "x1") for name in fields})


REASONS = {name: (_filled(reason), reason.step) for name, reason in ready.reasons().items()}


@pytest.mark.parametrize("name", sorted(REASONS))
@pytest.mark.parametrize("word", ["wait", "hold"])
def test_a_waiting_line_parses_back_to_its_fields_and_its_reason_is_on_its_step(word, name):
    reason, step = REASONS[name]
    said = lines.waits(word, 7, URL, reason)
    assert lines.parse(said) == [lines.Line(word, 7, URL, reason)]
    (line,) = lines.parse(said)
    assert merge.step(f"{line.word}: {line.reason}") == ("hold" if word == "hold" else step)


def test_a_merged_line_parses_back_to_its_number_and_slug_and_says_how_to_revert_it():
    said = lines.merged(7, "alpha", HEAD, "a title, with a comma: and a colon", ["kept: x"], URL)
    assert lines.parse(said) == [lines.Line("merged", 7, "alpha")]
    assert said.endswith(f", kept: x, revert: gh pr revert {URL}")


def test_a_ready_line_gives_its_number_and_safety_fact_and_is_no_merge_line():
    safe = "safe because only dead entries go (proven at 0123456789ab)"
    said = lines.ready(7, HEAD, "alpha-branch", "alpha", ["accepted: its hold", safe])
    found = lines.READY.match(said)
    assert found is not None and (int(found[1]), found[2]) == (7, safe)
    assert lines.parse(said) == []


def test_parse_reads_each_line_of_a_run_about_a_pull_request_and_skips_the_rest():
    said = "\n".join(
        [
            lines.merged(7, "alpha", HEAD, "t", [], URL),
            "wait: could not ask GitHub: gh exited 1: it said nothing",
            lines.waits("wait", 8, URL, "it has no review"),
            "refused 9 " + URL + ": it is not held, jmerge merges it by itself",
        ]
    )
    assert [(line.word, line.number) for line in lines.parse(said)] == [
        ("merged", 7),
        ("wait", 8),
        ("refused", 9),
    ]


RECORDS = {
    "green": ({"main": GREEN, "at": "", "check": "green"}, mainjson.Main(green=GREEN)),
    "red": (
        {"main": RED, "at": "", "check": "failed", "broken": RED, "green": GREEN},
        mainjson.Main(green=GREEN, red=RED),
    ),
    "red under a pending tip": (
        {"main": NEWER, "at": "", "check": "pending", "broken": RED, "green": GREEN},
        mainjson.Main(green=GREEN, red=RED),
    ),
    "held": (
        {"main": NEWER, "at": "", "check": "green", "broken": RED, "fixed": NEWER, "held": ["a"]},
        mainjson.Main(green=NEWER),
    ),
    "fixed on the owed path": (
        {"main": RED, "at": "", "check": "failed", "broken": RED, "fixed": NEWER},
        mainjson.Main(green=NEWER),
    ),
    "legacy, with no broken": ({"main": RED, "check": "failed"}, mainjson.Main(red=RED)),
    "no record": ({}, mainjson.Main()),
    "not a record": (["main"], mainjson.Main()),
    "a key of the wrong type": ({"main": GREEN, "check": ["green"]}, mainjson.Main()),
}


@pytest.mark.parametrize("name", list(RECORDS))
def test_a_record_gives_the_main_its_readers_act_on(name, tmp_path):
    record, main = RECORDS[name]
    assert mainjson.of(record) == main
    write_json(tmp_path / mainjson.NAME, record)
    assert mainjson.read(tmp_path) == main


def test_a_missing_or_unreadable_file_reads_as_nothing_known(tmp_path):
    assert mainjson.read(tmp_path) == mainjson.Main()
    (tmp_path / mainjson.NAME).write_text("{not json")
    assert mainjson.read(tmp_path) == mainjson.Main()


def test_record_writes_only_what_it_is_given_and_reads_back_as_the_same_main():
    built = mainjson.record(main=RED, at="t", check="failed", broken=RED, green=GREEN)
    assert built == {"main": RED, "at": "t", "check": "failed", "broken": RED, "green": GREEN}
    assert mainjson.of(built) == mainjson.Main(green=GREEN, red=RED)


def test_every_record_the_real_tell_writes_over_the_model_is_a_record():
    """Over every order of events that the red-main model walks, the real `tell` writes
    `main.json` only as a `Record`, and writes it no other way."""
    written = []

    def spy(path, value):
        if path.name == mainjson.NAME:
            written.append(value)
        write_json(path, value)

    with mock.patch.object(mainmoved, "write_json", spy):
        walk.__wrapped__(Options())
    assert written
    required = {"main", "at", "check"}
    assert [one for one in written if mainjson.typed(one) != one or required - one.keys()] == []


def test_a_real_jmerge_that_could_not_ask_github_is_a_jmerge_that_did_not_run(kitchen, tmp_path):
    said = real_jmerge_line(tmp_path, "merge", code=1, said=f"{BAD_GATEWAY}\n")
    assert lines.parse(said) == []
    kitchen.set("jmerge-says", said)
    assert f"wait demo: jmerge did not run ({said})" in kitchen.poll()


KEYS = {"broken", "fixed", "held"}
HOMONYMS = {
    ("jbus/queue.py", "held"): "a queue row's hold",
    ("jmerge/rows.py", "held"): "a queue row's hold",
    ("jbus/view/state.py", "broken"): "the view's section of what is broken",
}
OWNERS = {"mainjson": "jmerge/mainjson.py", "lines": "jmerge/lines.py"}


def _sources():
    for root in sources():
        for path in sorted(root.rglob("*.py")):
            yield path.relative_to(root).as_posix(), ast.parse(path.read_text())


def _keys(tree):
    """Each key that the code writes into a record, either in a dict literal or by assigning
    to a subscript. The type checker already limits reads of a `Record` to its keys, so this
    does not count reads."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            yield from node.keys
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            yield node.slice


def test_the_file_and_its_keys_are_named_only_in_mainjson():
    found = []
    for name, tree in _sources():
        if name == OWNERS["mainjson"]:
            continue
        strings = [node for node in ast.walk(tree) if isinstance(node, ast.Constant)]
        found += [(name, "main.json") for node in strings if node.value == mainjson.NAME]
        for key in _keys(tree):
            if isinstance(key, ast.Constant) and key.value in KEYS:
                if (name, key.value) not in HOMONYMS:
                    found.append((name, key.value))
    assert found == []


def test_the_pattern_of_a_line_is_written_only_in_lines():
    """A regex that reads a line by its first word, `merged`, `wait`, `hold`, `refused` or
    `ready`, is `lines.LINE` or `lines.READY`, and no module but `lines` writes one."""
    words = ("merged", "wait", "hold", "refused")
    found = []
    for name, tree in _sources():
        if name == OWNERS["lines"]:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            text = node.value
            if text.startswith("^ready ") or (
                text.startswith(("^(", "(?:", "^(?:")) and sum(w in text for w in words) >= 2
            ):
                found.append((name, text))
    assert found == []
