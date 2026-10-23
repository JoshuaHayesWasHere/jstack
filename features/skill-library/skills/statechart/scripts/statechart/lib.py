"""What the statechart commands share: TLC's values, states, graphs and traces read into Python,
a Mermaid stateDiagram-v2 read into regions, the machine that regions make together, and the
chart's colors."""

import inspect
import json
import re
from dataclasses import dataclass

A = re.ASCII


class ChartError(Exception):
    """An input that a command cannot use. The command prints it as `Error: <message>`."""


def js_string(v):
    """`String(v)` of JavaScript, so a label reads as it did in pstack's scripts."""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, list | tuple):
        return ",".join("" if x is None else js_string(x) for x in v)
    if isinstance(v, dict):
        return "[object Object]"
    return str(v)


def to_json(v):
    """`JSON.stringify(v)`: no spaces, and text as it is."""
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False)


def call(fn, *args):
    """Calls a mapping's function with as many of `args` as it takes, as JavaScript does: a
    `state(v)` that ignores the facts is a valid mapping."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return fn(*args)
    if any(p.kind is p.VAR_POSITIONAL for p in params):
        return fn(*args)
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return fn(*args[: len(positional)])


@dataclass(frozen=True)
class Facts:
    """What a mapping's function knows of a model state beyond its variables: the actions the
    state enables, and whether only the reader's actions are among them."""

    enabled: frozenset
    settled: bool


def parse_value(text):
    """One TLC value: a string, a number, a boolean, a sequence or set (a list), a record or a
    function (a dict). Text that is none of these comes back as it is."""
    src = text.strip()
    i = 0

    def ws():
        nonlocal i
        while i < len(src) and src[i].isspace():
            i += 1

    def peek(s):
        return src.startswith(s, i)

    def eat(s):
        nonlocal i
        ws()
        if not peek(s):
            raise ValueError(f"expected {s} at {i} in {src}")
        i += len(s)

    def items(close, item):
        nonlocal i
        out = []
        ws()
        if peek(close):
            i += len(close)
            return out
        while True:
            out.append(item())
            ws()
            if peek(","):
                i += 1
                continue
            eat(close)
            return out

    def field():
        nonlocal i
        ws()
        m = re.compile(r"[A-Za-z_][A-Za-z0-9_]*").match(src, i)
        if not m:
            raise ValueError(f"bad record field at {i}")
        i = m.end()
        eat("|->")
        return (m.group(), value())

    def value():
        nonlocal i
        ws()
        if peek("<<"):
            i += 2
            return items(">>", value)
        if peek("{"):
            i += 1
            return items("}", value)
        if peek("["):
            i += 1
            return dict(items("]", field))
        if peek("("):
            i += 1
            fn = {}
            while True:
                k = value()
                eat(":>")
                fn[k if isinstance(k, str) else to_json(k)] = value()
                ws()
                if peek("@@"):
                    i += 2
                    continue
                eat(")")
                return fn
        if peek('"'):
            i += 1
            s = ""
            while i < len(src) and src[i] != '"':
                if src[i] == "\\":
                    i += 1
                if i < len(src):
                    s += src[i]
                i += 1
            i += 1
            return s
        m = re.compile(r"-?[0-9]+|[A-Za-z_][A-Za-z0-9_]*").match(src, i)
        if not m:
            raise ValueError(f"bad value at {i} in {src}")
        i = m.end()
        word = m.group()
        if word == "TRUE":
            return True
        if word == "FALSE":
            return False
        return int(word) if re.fullmatch(r"-?[0-9]+", word) else word

    try:
        v = value()
        ws()
        return v if i == len(src) else src
    except (ValueError, IndexError):
        return src


def parse_state(text):
    """One state as TLC prints it: `/\\ x = 1` lines, or `x = 1` for one variable."""
    conjuncts = []
    for line in (line for line in text.split("\n") if line.strip()):
        if re.match(r"\s*/\\ ", line) or not conjuncts:
            conjuncts.append(re.sub(r"^\s*/\\ ", "", line))
        else:
            conjuncts[-1] += f" {line.strip()}"
    found = {}
    for c in conjuncts:
        eq = c.find(" = ")
        if eq < 0:
            continue
        found[c[:eq].strip()] = parse_value(c[eq + 3 :])
    return found


def is_record(v):
    return isinstance(v, dict)


def state_key(variables):
    """The key of a state: its variables as JSON, with every record's fields in order."""
    return json.dumps(variables, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def rule_sentences(tla):
    """Each definition's sentence: the `\\*` comment lines right above it."""
    out = {}
    lines = tla.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*==", line)
        if not m:
            continue
        said = []
        j = i - 1
        while j >= 0 and re.match(r"\s*\\\*", lines[j]):
            said.insert(0, re.sub(r"^\s*\\\*\s?", "", lines[j]).strip())
            j -= 1
        sentence = " ".join(s for s in said if s)
        if sentence:
            out[m.group(1)] = sentence
    return out


def tla_variables(code):
    return [
        name
        for m in re.finditer(r"\bVARIABLES?\s+(\w+(?:\s*,\s*\w+)*)", code, A)
        for name in re.split(r"\s*,\s*", m.group(1))
    ]


def split_comments_keeping_offsets(text):
    """The text twice, at the same offsets: once with its comments blanked, and once with only
    its comments."""
    code = []
    notes = []
    block = 0
    in_line = False
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        two = text[i : i + 2]
        if c == "\n":
            in_line = in_string = False
            code.append(c)
            notes.append(c)
        elif block:
            if two in ("(*", "*)"):
                block += 1 if two == "(*" else -1
                code.append("  ")
                notes.append(two)
                i += 1
            else:
                code.append(" ")
                notes.append(c)
        elif in_line:
            code.append(" ")
            notes.append(c)
        elif in_string:
            if c == "\\" and i + 1 < n and text[i + 1] != "\n":
                code.append(two)
                notes.append("  ")
                i += 1
            else:
                in_string = c != '"'
                code.append(c)
                notes.append(" ")
        elif two in ("\\*", "(*"):
            if two == "\\*":
                in_line = True
            else:
                block = 1
            code.append("  ")
            notes.append(two)
            i += 1
        else:
            in_string = c == '"'
            code.append(c)
            notes.append(" ")
        i += 1
    return "".join(code), "".join(notes)


IDENTIFIER = re.compile(r"(?<![\\.\w])[A-Za-z_]\w*(?!\w)(?!\s*\|->)", A)
CITATION = re.compile(r"[\w./-]+\.[A-Za-z]\w*:\d+|#L\d+", A)
DEPTH = {"(": 1, "[": 1, "{": 1, ")": -1, "]": -1, "}": -1}
LOOSER_THAN_AND = re.compile(r"(\\/|=>|<=>|~>|-\+->|\\equiv\b)", A)
RUNS_TO_END = re.compile(r"(\\[EA]|IF|LET|CASE|CHOOSE)\b", A)
PRIMES_OR_UNCHANGED = re.compile(r"[\w)\]>}]'|\bUNCHANGED\b", A)


def conjuncts(bare, start, to, line_start):
    """The conjuncts of the formula at `bare[start:to]`, as offset pairs, or None when its
    top level is not a conjunction that can be split."""
    m = re.search(r"\S", bare[start:to])
    if not m:
        return None
    first = start + m.start()
    if re.match(r"\\E\b", bare[first:to], A):
        depth = 0
        for i in range(first, to):
            depth += DEPTH.get(bare[i], 0)
            if depth == 0 and bare[i] == ":":
                return conjuncts(bare, i + 1, to, line_start)
        return None
    if bare.startswith("/\\", first):
        column = first - line_start(first)
        bullets = [first]
        for m in re.finditer(r"\n([ \t]*)(?=\S)", bare[first:to]):
            if len(m.group(1)) < column:
                return None
            at = first + m.end()
            if len(m.group(1)) == column and bare.startswith("/\\", at):
                bullets.append(at)
        out = []
        for i, b in enumerate(bullets):
            end = bullets[i + 1] if i + 1 < len(bullets) else to
            found = conjuncts(bare, b + 2, end, line_start)
            out += found if found is not None else [(b + 2, end)]
        return out
    cuts = []
    depth = 0
    i = first
    while i < to:
        two = bare[i : i + 2]
        ahead = bare[i : i + 7]
        if two in ("<<", ">>"):
            depth += 1 if two == "<<" else -1
            i += 1
        elif DEPTH.get(bare[i]):
            depth += DEPTH[bare[i]]
        elif depth > 0:
            pass
        elif LOOSER_THAN_AND.match(ahead):
            return None
        elif not re.match(r"\w", bare[i - 1] if i > 0 else "", A) and RUNS_TO_END.match(ahead):
            break
        elif two == "/\\":
            cuts.append(i)
            i += 1
        i += 1
    starts = [first, *(c + 2 for c in cuts)]
    return [(a, cuts[i] if i < len(cuts) else to) for i, a in enumerate(starts)]


def uncited_conditions(text):
    """Each condition of an action that no comment ties to code by a file and line: a conjunct
    that changes nothing and reads a variable that the action does not change."""
    code, notes = split_comments_keeping_offsets(text)
    bare = re.sub(r'"(?:[^"\\\n]|\\.)*"', lambda m: " " * len(m.group()), code)
    variables = set(tla_variables(bare))
    starts = [0, *(m.start() + 1 for m in re.finditer(r"\n", bare))]

    def line_of(at):
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) >> 1
            if starts[mid] <= at:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def line_start(at):
        return starts[line_of(at)]

    bare_lines = bare.split("\n")
    note_lines = notes.split("\n")
    defs = {}
    next_item = re.compile(r"^(?![ \t\n]|/\\|\\/)", re.M)
    for m in re.finditer(
        r"^(?:LOCAL[ \t]+)?([A-Za-z_]\w*)[ \t]*(?:\([^)]*\)|\[[^\]]*\])?[ \t]*==", bare, re.M | A
    ):
        start = m.end()
        after = next_item.search(bare, start)
        defs[m.group(1)] = {
            "from": start,
            "to": after.start() if after else len(bare),
            "line": line_of(m.start()),
        }

    def direct(body):
        ids = IDENTIFIER.findall(body)
        calls = []
        for name in ids:
            if name in defs and name not in calls:
                calls.append(name)
        return {
            "reads": [name for name in ids if name in variables],
            "writes": [
                m.group(1)
                for m in re.finditer(r"(?<![\\.\w])([A-Za-z_]\w*)'", body, A)
                if m.group(1) in variables
            ],
            "acts": bool(PRIMES_OR_UNCHANGED.search(body)),
            "calls": calls,
        }

    own = {name: direct(bare[d["from"] : d["to"]]) for name, d in defs.items()}

    def through(begin):
        reads = set(begin["reads"])
        writes = set(begin["writes"])
        acts = begin["acts"]
        seen = set(begin["calls"])
        todo = list(begin["calls"])
        while todo:
            d = own[todo.pop()]
            reads.update(d["reads"])
            writes.update(d["writes"])
            acts = acts or d["acts"]
            for c in d["calls"]:
                if c not in seen:
                    seen.add(c)
                    todo.append(c)
        return {"reads": reads, "writes": writes, "acts": acts}

    def cited(first, last, above):
        for line in range(first, last + 1):
            if CITATION.search(note_lines[line]):
                return True
        line = first - 1
        while above and line >= 0 and not bare_lines[line].strip() and note_lines[line].strip():
            if CITATION.search(note_lines[line]):
                return True
            line -= 1
        return False

    found = []
    for action, d in defs.items():
        if not own[action]["acts"]:
            continue
        changes = through(own[action])["writes"]
        for a, b in conjuncts(bare, d["from"], d["to"], line_start) or []:
            part = through(direct(bare[a:b]))
            if part["acts"] or all(v in changes for v in part["reads"]):
                continue
            nonspace = re.search(r"\S", bare[a:b])
            first = line_of(a + (nonspace.start() if nonspace else -1))
            last = line_of(a + len(bare[a:b].rstrip()) - 1)
            if cited(first, last, first > d["line"]):
                continue
            found.append(
                {
                    "line": first + 1,
                    "action": action,
                    "condition": re.sub(r"\s+", " ", code[a:b]).strip(),
                }
            )
    return found


def unescape_dot(s):
    out = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            i += 1
            out.append("\n" if s[i] == "n" else s[i])
        else:
            out.append(s[i])
        i += 1
    return "".join(out)


_LABEL = r'"((?:[^"\\]|\\.)*)"'
_NODE = re.compile(rf"^(-?\d+) \[label={_LABEL}(.*)\];?\s*$", A)
_EDGE = re.compile(rf"^(-?\d+) -> (-?\d+)(?: \[label={_LABEL})?", A)


def parse_dot(text):
    """TLC's state graph from `-dump dot,actionlabels`: its states by id, its steps between two
    states, and its steps that stay in one state."""
    nodes = {}
    edges = []
    loops = []
    seen = set()
    for line in text.split("\n"):
        m = _EDGE.match(line)
        if m:
            e = {
                "from": m.group(1),
                "to": m.group(2),
                "action": unescape_dot(m.group(3)) if m.group(3) else "",
            }
            key = f"{e['from']} {e['to']} {e['action']}"
            if key in seen:
                continue
            seen.add(key)
            (loops if e["from"] == e["to"] else edges).append(e)
            continue
        m = _NODE.match(line)
        if m:
            nodes[m.group(1)] = {
                "id": m.group(1),
                "vars": parse_state(unescape_dot(m.group(2))),
                "init": bool(re.search(r"style\s*=\s*filled", m.group(3))),
            }
    if not nodes:
        raise ChartError("no states found; dump the graph with TLC -dump dot,actionlabels <file>")
    for e in [*edges, *loops]:
        if e["from"] not in nodes or e["to"] not in nodes:
            raise ChartError(
                f"transition {e['from']} -> {e['to']} names a state the file does not define"
            )
    if edges and all(not e["action"] for e in [*edges, *loops]):
        raise ChartError(
            "the graph has no action names; dump it with TLC -dump dot,actionlabels <file>"
        )
    return {"nodes": nodes, "edges": edges, "loops": loops}


def parse_traces(text):
    """The counterexamples in TLC's output, each with the invariant it breaks and its steps."""
    traces = []
    invariant = None
    current = None
    lines = text.split("\n")

    def state_at(i):
        body = []
        while i + 1 < len(lines) and lines[i + 1].strip() != "":
            i += 1
            body.append(lines[i])
        return parse_state("\n".join(body)), i

    i = 0
    while i < len(lines):
        line = lines[i]
        inv = re.match(r"Error: Invariant (\S+) is violated( by the initial state:)?", line)
        if inv:
            invariant = inv.group(1)
            if inv.group(2):
                variables, end = state_at(i)
                traces.append(
                    {"invariant": invariant, "steps": [{"action": None, "vars": variables}]}
                )
                i = end
            i += 1
            continue
        if line.startswith("Error: ") and not line.startswith(
            "Error: The behavior up to this point is"
        ):
            invariant = None
        head = re.match(r"State (\d+): <([^\s>(]+)", line)
        if not head:
            i += 1
            continue
        variables, end = state_at(i)
        i = end
        if head.group(1) == "1":
            current = {"invariant": invariant, "steps": []}
            traces.append(current)
        if current is not None:
            action = None if head.group(2) == "Initial" else head.group(2)
            current["steps"].append({"action": action, "vars": variables})
        i += 1
    return traces


# TLC words a broken PROPERTY by its form: [](state predicate) as an invariant, [][A]_v as an
# action property, a bare state predicate, which TLC checks only in the initial states, as a
# property of the initial state, and any other formula as a temporal property.
BROKEN_PROPERTY = re.compile(
    r"^Error: (Invariant \S+ is violated|Action property \S+ is violated\.|Property \S+ is violated"
    r" by the initial state:|Temporal properties were violated\.)",
    re.M,
)

_CRASH_REPORTED = re.compile(
    r"^Error: (Invariant \S+ is violated|The behavior up to this point is|Evaluating invariant \S+"
    r" failed\.|TLC threw an unexpected exception\.|The error occurred when TLC was evaluating the"
    r" nested)"
)
_REPORTED = re.compile(
    r"^Error: (Invariant \S+ is violated|Action property \S+ is violated\.|Property \S+ is violated"
    r" by the initial state:|The behavior up to this point is|Temporal properties were"
    r" violated\.|The following behavior constitutes a counter-example:)"
)


def tlc_output_warning(text, file):
    """None for TLC output whose counterexamples are all there, a warning for output where TLC
    found a rule broken and then failed with a Java exception, and ChartError for any other
    output of a run that stopped early or on an error. With -continue, TLC prints "Model
    checking completed" even after broken invariants, and not when it stopped early. An error
    in the rule's formula throws one of TLC's own exceptions in place of java.*."""
    lines = text.split("\n")

    def named(pattern):
        out = []
        for line in lines:
            m = re.match(pattern, line)
            if m and m.group(1) and m.group(1) not in out:
                out.append(m.group(1))
        return out

    broken = set(named(r"Error: Invariant (\S+) is violated"))
    failed = named(r"Error: Evaluating invariant (\S+) failed\.")
    thrown = [
        f"{m.group(2) or m.group(1)}: {m.group(3).strip()}"
        for m in re.finditer(r"^The exception was a (\S+)\n: (?:([\w.$]+):)?(.*)$", text, re.M | A)
    ]
    crashed = (
        bool(failed)
        and all(r in broken for r in failed)
        and bool(thrown)
        and all(t.startswith("java.") for t in thrown)
    )
    reported = _CRASH_REPORTED if crashed else _REPORTED
    for line in lines:
        if line.startswith("Error: ") and not reported.match(line):
            raise ChartError(
                f"{file}: TLC stopped on an error that is not a broken rule: {line[7:]}"
            )
    if crashed:
        rules = ", ".join(failed)
        return (
            f"TLC found that {rules} {'is' if len(failed) == 1 else 'are'} broken, and then failed"
            f" with {thrown[0]}. TLC stopped before it checked every state, so the charts can miss"
            f" states that break {rules}. The failure is in TLC, not in the rule. Do not weaken"
            f" {rules} because of it. A smaller constant can let TLC finish."
        )
    # TLC stops at the first broken temporal property, and at an initial state that breaks a
    # PROPERTY, and then does not print that it completed.
    if not re.search(
        r"^(Model checking completed\.|Error: (Temporal properties were violated\.|Property \S+ is"
        r" violated by the initial state:))",
        text,
        re.M,
    ):
        raise ChartError(
            f"{file}: TLC did not finish, so its counterexamples are not all there; read the file"
        )
    return None


def wrap(text, width=26):
    rows = []
    row = ""
    for w in re.split(r"\s+", js_string(text)):
        if row and len(f"{row} {w}") > width:
            rows.append(row)
            row = w
        else:
            row = f"{row} {w}" if row else w
    if row:
        rows.append(row)
    return "<br/>".join(rows)


def join_and(items):
    items = list(items)
    if len(items) < 3:
        return " and ".join(items)
    return f"{', '.join(items[:-1])}, and {items[-1]}"


OPENS_A_PHRASE = set(
    "a an the your my our their its this that to of in on at for with from by and or".split()
)


def join_labels(labels):
    """Labels joined by "or", with the leading words that they all share written once, as in
    "you tap Pay or Back"."""
    labels = list(labels)
    if len(labels) < 2:
        return " or ".join(labels)
    words = [js_string(label).split(" ") for label in labels]
    n = 0
    while all(n < len(w) - 1 and w[n] == words[0][n] for w in words):
        n += 1
    while n > 0 and words[0][n - 1] in OPENS_A_PHRASE:
        n -= 1
    if n < 2:
        return " or ".join(labels)
    rest = [" ".join(w[n:]) for w in words]
    listed = " or ".join(rest) if len(rest) == 2 else f"{', '.join(rest[:-1])}, or {rest[-1]}"
    return f"{' '.join(words[0][:n])} {listed}"


def unwrap(s):
    s = re.sub(r"<br\s*/?>|#160;", " ", s)
    s = re.sub(r"#(quot|34);", '"', s)
    return re.sub(r"\s+", " ", s).strip()


def escape_mermaid_quotes(s):
    return js_string(s).replace('"', "#quot;")


LEGEND_ID = "legend"
FULL_LABELS = "%% labels in full"

_FRONT_MATTER = re.compile(r"\A\s*---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(\r?\n|\Z)")
_ID = r"[A-Za-z_][A-Za-z0-9_]*"


def parse_mermaid(text):
    """A Mermaid stateDiagram-v2 as regions, each with its states, start states and
    transitions, and the chart's `%% never` rules. Raises ChartError for a chart it cannot read."""
    names = {}
    nevers = []
    last = None

    def new_part():
        return {"children": [], "transitions": []}

    root = {"name": "", "parts": [new_part()]}
    stack = [root]

    def part():
        return stack[-1]["parts"][-1]

    def display(state_id):
        return names.get(state_id, state_id)

    implicit = {}

    def declare(state_id):
        prev = implicit.get(state_id)
        if prev is not None:
            for k, c in enumerate(prev["children"]):
                if c["name"] == state_id:
                    del prev["children"][k]
                    break
        implicit[state_id] = None

    def mention(state_id):
        if state_id == "[*]" or state_id in implicit:
            return
        part()["children"].append({"name": state_id, "leaf": True})
        implicit[state_id] = part()

    body = _FRONT_MATTER.sub("", text, count=1)
    for raw in body.split("\n"):
        line = re.sub(rf"(\[\*\]|{_ID}):::[\w-]+", r"\1", raw.strip(), flags=A)
        when = re.match(r"%%\s*when\s+(not\s+)?(.+)$", line)
        if when:
            if not last:
                raise ChartError(f"a %% when line must come right after a transition: {line}")
            if not last["words"]:
                raise ChartError(
                    f'the guarded step "{last["label"]}" must end its label with the guard\'s words'
                    " in [ ]"
                )
            last["when"] = {
                "not": bool(when.group(1)),
                "ids": [s.strip() for s in when.group(2).split(",")],
            }
            last = None
            continue
        last = None
        never = re.match(rf"%%\s*never\s+({_ID})\s*:\s*(.+?)(?:\s+--\s+(.*))?$", line)
        if never:
            nevers.append(
                {
                    "name": never.group(1),
                    "states": [s.strip() for s in never.group(2).split("&")],
                    "sentence": never.group(3) or "",
                }
            )
            continue
        if (
            not line
            or line.startswith("%%")
            or re.match(r"(stateDiagram|direction|classDef|class |note)", line)
        ):
            continue
        m = re.match(r'state\s+"([^"]*)"\s+as\s+([A-Za-z_]\w*)\s*(\{)?\s*$', line, A)
        if m:
            caption, state_id, opens = m.group(1), m.group(2), m.group(3)
        else:
            plain = re.match(r"state\s+([A-Za-z_]\w*)\s*(\{)?\s*$", line, A)
            caption, state_id, opens = (
                (None, plain.group(1), plain.group(2)) if plain else (None, None, None)
            )
        if state_id is not None:
            if caption is not None and state_id not in names:
                names[state_id] = unwrap(caption)
            declare(state_id)
            if opens:
                node = {"name": state_id, "parts": [new_part()]}
                part()["children"].append(node)
                stack.append(node)
            else:
                part()["children"].append({"name": state_id, "leaf": True})
            continue
        if line == "}":
            if len(stack) == 1:
                raise ChartError("unmatched } in the chart")
            stack.pop()
            continue
        if line == "--":
            stack[-1]["parts"].append(new_part())
            continue
        m = re.match(
            r"(\[\*\]|[A-Za-z_]\w*)\s*-->\s*(\[\*\]|[A-Za-z_]\w*)(?:\s*:\s*(.*))?$", line, A
        )
        if m:
            if m.group(2) == "[*]" and m.group(1) != "[*]":
                raise ChartError(
                    f'cannot read final state in "{line}"; draw the step to the state the reader'
                    " sees next"
                )
            mention(m.group(1))
            mention(m.group(2))
            said = unwrap(m.group(3)) if m.group(3) else ""
            label = re.sub(r"\s*\[[^\]]*\]", "", said)
            last = {"from": m.group(1), "to": m.group(2), "label": label, "words": label != said}
            part()["transitions"].append(last)
            continue
        m = re.match(r"([A-Za-z_]\w*)\s*:\s*(.*)$", line, A)
        if m:
            if m.group(1) not in names:
                names[m.group(1)] = unwrap(m.group(2))
            if m.group(1) in implicit and implicit[m.group(1)] is None:
                continue
            declare(m.group(1))
            part()["children"].append({"name": m.group(1), "leaf": True})
            continue
        raise ChartError(f"cannot read chart line: {line}")
    if len(stack) != 1:
        raise ChartError("the chart has an unclosed {")
    if len(root["parts"]) > 1:
        raise ChartError(
            "the chart has -- outside a composite; to make parallel regions, split one top-level"
            " composite with --"
        )

    def region(p):
        out = {"states": {}, "initial": {}, "transitions": []}
        info = {}
        declared_in_region = set()

        def collect(q):
            for c in q["children"]:
                if c["name"] == LEGEND_ID:
                    continue
                declared_in_region.add(c["name"])
                if not c.get("leaf"):
                    for sub in c["parts"]:
                        collect(sub)

        collect(p)
        transitions = []

        def lookup(state_id):
            found = info.get(state_id)
            if not found:
                raise ChartError(f"transition names {state_id}, which is not in this region")
            return found

        def states(q, prefix, depth):
            local = [c for c in q["children"] if c["name"] != LEGEND_ID]
            for t in q["transitions"]:
                for end in (t["from"], t["to"]):
                    if end == "[*]" or end in declared_in_region:
                        continue
                    declared_in_region.add(end)
                    local.append({"name": end, "leaf": True})
            every = []
            for at, c in enumerate(local):
                if c["name"] in info:
                    first = next(k for k, x in enumerate(local) if x["name"] == c["name"])
                    if at != first:
                        continue
                    raise ChartError(f"state id {c['name']} is declared in two places")
                full = f"{prefix}{display(c['name'])}"
                if c.get("leaf"):
                    if full in out["states"]:
                        raise ChartError(
                            f'two states have the caption "{full}"; give each its own caption'
                        )
                    out["states"][full] = None
                    info[c["name"]] = {"all": [full], "initial": [full], "depth": depth}
                    every.append(full)
                    continue
                if len(c["parts"]) > 1:
                    raise ChartError(
                        f"{display(c['name'])} splits into regions below the top level; make each"
                        " region a top-level region"
                    )
                inner = states(c["parts"][0], f"{full}.", depth + 1)
                initial = [
                    s
                    for t in c["parts"][0]["transitions"]
                    if t["from"] == "[*]"
                    for s in lookup(t["to"])["initial"]
                ]
                if not initial:
                    raise ChartError(
                        f"{display(c['name'])} has no [*] --> start, so a transition into it has"
                        " nowhere to land"
                    )
                info[c["name"]] = {"all": inner, "initial": initial, "depth": depth}
                every += inner
            for t in q["transitions"]:
                if t["from"] != "[*]" and t["to"] != "[*]":
                    transitions.append(t)
            return every

        states(p, "", 0)
        for t in p["transitions"]:
            if t["from"] == "[*]":
                for s in lookup(t["to"])["initial"]:
                    out["initial"][s] = None
        transitions.sort(key=lambda t: -lookup(t["from"])["depth"])
        handled = set()
        pending = []
        depth = None
        for t in transitions:
            source = lookup(t["from"])
            if source["depth"] != depth:
                handled.update(pending)
                pending = []
                depth = source["depth"]
            for f in source["all"]:
                key = f"{f}\0{t['label']}"
                if t["label"] and key in handled:
                    continue
                for to in lookup(t["to"])["initial"]:
                    move = {"from": f, "to": to, "label": t["label"]}
                    if t.get("when"):
                        move["when"] = t["when"]
                    out["transitions"].append(move)
                if t["label"]:
                    pending.append(key)
        return out, info

    owners = {}
    regions = {}
    top = root["parts"][0]
    machine = [c for c in top["children"] if c["name"] != LEGEND_ID]
    parallel = (
        len(machine) == 1
        and not machine[0].get("leaf")
        and len(machine[0]["parts"]) > 1
        and all(t["from"] == "[*]" for t in top["transitions"])
    )
    if parallel:
        for p in machine[0]["parts"]:
            only = p["children"][0] if p["children"] else None
            holder = (
                only
                if len(p["children"]) == 1
                and not only.get("leaf")
                and all(t["from"] == "[*]" and t["to"] == only["name"] for t in p["transitions"])
                else None
            )
            if holder and len(holder["parts"]) > 1:
                raise ChartError(
                    f"{display(holder['name'])} splits into regions below the top level"
                )
            name = display(holder["name"]) if holder else f"Region{len(regions) + 1}"
            r, ids = region(holder["parts"][0] if holder else p)
            regions[name] = r
            for state_id, found in ids.items():
                owners[state_id] = {"name": name, "all": found["all"]}
    else:
        r, ids = region(top)
        regions["Main"] = r
        for state_id, found in ids.items():
            owners[state_id] = {"name": "Main", "all": found["all"]}
    for name, r in regions.items():
        for t in r["transitions"]:
            if not t.get("when"):
                continue
            if not parallel:
                raise ChartError(
                    "a %% when line guards a step on other regions, and the chart has none"
                )
            states = {}
            for state_id in t["when"]["ids"]:
                at = owners.get(state_id)
                if not at:
                    raise ChartError(
                        f"a %% when line names {state_id}, which is not a state id in the chart"
                    )
                if at["name"] == name:
                    raise ChartError(
                        f"a %% when line names {display(state_id)}, which is in the step's own"
                        " region; a guard reads other regions"
                    )
                states[at["name"]] = sorted(set([*states.get(at["name"], []), *at["all"]]))
            t["guard"] = {"not": t["when"]["not"], "states": states}
            del t["when"]
    return {"regions": regions, "nevers": nevers}


def _guard_holds(guard, at):
    if not guard:
        return True
    hits = [at[r] in states for r, states in guard["states"].items()]
    return not any(hits) if guard["not"] else all(hits)


def product_of(regions):
    """The machine that regions make together: each state is the region states joined by " | ",
    and a step moves every region that has a move with its label from where it is."""
    names = list(regions)
    rs = list(regions.values())

    def join(parts):
        return " | ".join(parts)

    by_label = {}
    unlabeled = []
    for ri, r in enumerate(rs):
        for t in r["transitions"]:
            if not t["label"]:
                unlabeled.append(
                    {"ri": ri, "from": t["from"], "to": t["to"], "guard": t.get("guard")}
                )
                continue
            per_region = by_label.setdefault(t["label"], [{} for _ in rs])
            per_region[ri].setdefault(t["from"], []).append(
                {"to": t["to"], "guard": t.get("guard")}
            )
    starts = [[]]
    for r in rs:
        starts = [[*p, s] for p in starts for s in r["initial"]]
    out = {"states": {}, "initial": {join(s): None for s in starts}, "transitions": []}
    seen = {join(s) for s in starts}
    queue = [list(s) for s in starts]

    def step(source, target, label):
        a, b = join(source), join(target)
        if a == b:
            return
        out["transitions"].append({"from": a, "to": b, "label": label})
        if b not in seen:
            seen.add(b)
            queue.append(target)

    head = 0
    while head < len(queue):
        cur = queue[head]
        head += 1
        out["states"][join(cur)] = None
        at = {n: cur[ri] for ri, n in enumerate(names)}
        for u in unlabeled:
            if cur[u["ri"]] != u["from"] or not _guard_holds(u["guard"], at):
                continue
            nxt = list(cur)
            nxt[u["ri"]] = u["to"]
            step(cur, nxt, "")
        for label, per_region in by_label.items():
            open_moves = [
                [m["to"] for m in moves.get(cur[ri], []) if _guard_holds(m["guard"], at)]
                for ri, moves in enumerate(per_region)
            ]
            if all(not tos for tos in open_moves):
                continue
            nexts = [[]]
            for ri, tos in enumerate(open_moves):
                options = list(dict.fromkeys(tos)) if tos else [cur[ri]]
                nexts = [[*p, s] for p in nexts for s in options]
            for nxt in nexts:
                step(cur, nxt, label)
    return out


def compare_charts(expected_regions, actual_regions):
    """The differences between two charts, as (title, sorted items) pairs, without the empty
    ones."""
    expected = product_of(expected_regions)
    actual = product_of(actual_regions)

    def edge_set(m):
        labeled = set()
        out = set()
        for t in m["transitions"]:
            if not t["label"]:
                continue
            labeled.add(f"{t['from']} --> {t['to']}")
            for label in t["label"].split(" or "):
                out.add(f"{t['from']} --> {t['to']} : {label}")
        for t in m["transitions"]:
            if not t["label"] and f"{t['from']} --> {t['to']}" not in labeled:
                out.add(f"{t['from']} --> {t['to']}")
        return out

    def minus(a, b):
        return sorted(x for x in a if x not in b)

    unreached = []
    entries = list(expected_regions.items())
    if len(entries) == 1:
        unreached += [s for s in entries[0][1]["states"] if s not in expected["states"]]
    else:
        for ri, (name, r) in enumerate(entries):
            seen = {s.split(" | ")[ri] for s in expected["states"]}
            unreached += [f"{name}: {s}" for s in r["states"] if s not in seen]
    rows = [
        ("states the agreed chart's own steps never reach", sorted(unreached)),
        (
            "states only in EXPECTED (no path from the start reaches them in the spec, or the spec"
            " renamed them)",
            minus(expected["states"], actual["states"]),
        ),
        ("states only in ACTUAL", minus(actual["states"], expected["states"])),
        ("start states only in EXPECTED", minus(expected["initial"], actual["initial"])),
        ("start states only in ACTUAL", minus(actual["initial"], expected["initial"])),
        (
            "transitions only in EXPECTED (a guard in the spec blocks them, or the spec renamed the"
            " step)",
            minus(edge_set(expected), edge_set(actual)),
        ),
        ("transitions only in ACTUAL", minus(edge_set(actual), edge_set(expected))),
    ]
    return [(title, xs) for title, xs in rows if xs]


STATUS_CLASSES = [
    "classDef works fill:#f4f6f7,stroke:#566573,color:#1b2631",
    "classDef wrong fill:#fdedec,stroke:#c0392b,color:#7b241c",
    "classDef fixed fill:#e9f7ef,stroke:#1e8449,color:#145a32",
    "classDef worksPath fill:#f4f6f7,stroke:#1f3a93,stroke-width:4px,color:#1b2631",
    "classDef wrongPath fill:#fdedec,stroke:#1f3a93,stroke-width:4px,color:#7b241c",
    "classDef fixedPath fill:#e9f7ef,stroke:#1f3a93,stroke-width:4px,color:#145a32",
]

GROUP_PALETTE = ["#d6eaf8", "#fdebd0", "#e8daef", "#fcf3cf", "#d1f2eb", "#ede0d4", "#f6e0ef"]
PLAIN_FILL = "#f4f6f7"


def _rgb(color):
    h = "".join(c + c for c in color[1:]) if len(color) == 4 else color[1:]
    return [int(h[i : i + 2], 16) for i in (0, 2, 4)]


def _wcag_relative_luminance(color):
    def channel(c):
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def group_color_problem(color):
    if not isinstance(color, str) or not re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", color, re.I):
        return 'is not "#rgb" or "#rrggbb"'
    if _wcag_relative_luminance(color) < 0.5:
        return "is too dark for the status borders to show on it"
    return None


_BORDERS = {
    "Wrong": ("stroke:#c0392b,stroke-width:4px", "#7b241c"),
    "Fixed": ("stroke:#1e8449,stroke-width:4px", "#145a32"),
    "Path": ("stroke:#1f3a93,stroke-width:4px", "#1b2631"),
}


def group_class_def(base, fill, border):
    darker = "#" + "".join(f"{(c + 1) // 2:02x}" for c in _rgb(fill))
    stroke, color = _BORDERS.get(
        border, (f"stroke:{'#566573' if fill == PLAIN_FILL else darker}", "#1b2631")
    )
    return f"classDef {base}{border} fill:{fill},{stroke},color:{color}"
