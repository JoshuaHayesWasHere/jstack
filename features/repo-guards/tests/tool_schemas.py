"""The input schemas of the tools a skill calls, from the T3 Code and Claude Code fixtures, and
`strict`, which makes one refuse a key it does not name. A test that checks a call against its
tool imports these from here, and not from `test_tool_calls.py`, whose read set is every skill."""

import copy
import json

from testing.paths import REPO

READ_SET = ("features/jbus/tests/fixtures/t3/", "testing/tests/fixtures/claude/")
SCHEMAS = {
    path.stem: json.loads(path.read_text())
    for tools in READ_SET
    for path in (REPO / tools).glob("*.json")
}


def strict(schema):
    """A tool's schema, changed to refuse unknown keys at every depth. The tool itself accepts
    such keys."""
    schema = copy.deepcopy(schema)
    todo = [schema]
    while todo:
        node = todo.pop()
        if isinstance(node, dict):
            if node.get("additionalProperties") is True:
                node["additionalProperties"] = False
            todo.extend(node.values())
        elif isinstance(node, list):
            todo.extend(node)
    return schema
