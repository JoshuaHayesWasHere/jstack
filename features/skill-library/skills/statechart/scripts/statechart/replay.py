"""statechart replay: walks a real run's log over TLC's state graph of the spec that models it, and
names each line no step of the model makes.

The trace file says how a line of the log reads, as `RowLife.trace.py` does for jbus's
`transitions.jsonl`. It defines:

- `verbs`: the actions a verb takes, each of which the log writes as a line of its own. A pass's
  line never crosses one of them unseen.
- `observe(line)`: the line, a dict parsed from one JSON line, as `(unit, before, after, actions)`,
  or None for a line the map does not read. `unit` names what the line is about, such as a row's
  slug. `before` and `after` map a variable of the spec to the value the line says it had before
  and has after the step: `before` may be empty. `actions` is None for a line a pass wrote, which
  any path of one or more steps that are no verb's may make, or the names of the actions that make
  a verb's line, which exactly one step of one of them makes.

The walk keeps, for each unit, the set of the graph's states that its lines so far allow. A unit's
first line starts the set at every state its `before` allows. A line whose `before` no state of
the set allows breaks its unit's chain, as when a unit starts again under the same name: the walk
counts it, and starts the set again at its `before`. A line that leaves the set empty matched no
step: the walk names it, and starts the set again at its `after`.
"""

import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field

from statechart.lib import ChartError, parse_dot

USAGE = "statechart replay SPEC.tla [--config FILE] --trace FILE.py --log FILE.jsonl [--since ISO]"

HELP = f"""Usage: {USAGE}

Walks each line of the log over TLC's state graph of SPEC.tla, as the trace file reads the line,
and names each line no step of the model makes. TLC runs once with -dump dot,actionlabels in a
temporary copy of the spec's folder, with the config's SPECIFICATION and CONSTANTS and none of its
rules. --config is SPEC.cfg unless given. A relative --config or --trace that is not there is read
beside SPEC.tla.

The trace file defines `verbs`, the actions each of which the log writes as a line of its own,
and `observe(line)`, which reads one line as (unit, before, after, actions) or None: see
statechart/replay.py. A line a pass wrote, with actions None, matches a path of one or more steps
that are no verb's and ends in a state whose variables in `after` are the line's. A verb's line
matches exactly one step of one of its actions.

With --since, only lines whose `at` is that ISO time or later are counted; the lines before it
still place each unit.

Prints `<n> lines, <m> matched, <k> matched no step`, one `MISS <unit> <before> -> <after> <at>`
line for each miss, and, when some line's `before` breaks its unit's chain, a line that counts
them and one `BREAK <unit> <was> -> <before> <at>` line each.

Exit codes: 0 every counted line matched, 1 a line matched no step, 2 a wrong argument, a log or
trace file it cannot read, or a TLC run that did not finish."""


class ReplayError(Exception):
    pass


@dataclass(frozen=True)
class Graph:
    """TLC's state graph, its states numbered from 0: each state's variables, the states one step
    of each action leads to, as a bitmask, and the states one or more steps that are no verb's
    lead to, by state."""

    vars: list[dict]
    step: list[dict[str, int]]
    reach: list[int]
    by_value: dict[tuple[str, str], int] = field(default_factory=dict)

    def moves(self, name):
        """Each change of the variable `name` one step makes, as a pair of its values."""
        return {
            (self.vars[a][name], self.vars[b][name])
            for a, steps in enumerate(self.step)
            for led in steps.values()
            for b in _bits(led)
            if self.vars[a][name] != self.vars[b][name]
        }

    def where(self, observed):
        """The states whose variables have the values `observed` names, as a bitmask."""
        mask = (1 << len(self.vars)) - 1
        for name, value in observed.items():
            mask &= self.by_value.get((name, _key(value)), 0)
        return mask


def _key(value):
    return json.dumps(value, sort_keys=True)


def _bits(mask):
    while mask:
        low = mask & -mask
        yield low.bit_length() - 1
        mask ^= low


def graph_of(dot, verbs):
    """The `Graph` of TLC's dot dump `dot`, where `verbs` are the actions no pass takes."""
    parsed = parse_dot(dot)
    ids = list(parsed["nodes"])
    index = {node: i for i, node in enumerate(ids)}
    states = [parsed["nodes"][node]["vars"] for node in ids]
    step = [{} for _ in ids]
    passing = [[] for _ in ids]
    for e in [*parsed["edges"], *parsed["loops"]]:
        a, b = index[e["from"]], index[e["to"]]
        step[a][e["action"]] = step[a].get(e["action"], 0) | (1 << b)
        if e["action"] not in verbs:
            passing[a].append(b)
    by_value = {}
    for i, variables in enumerate(states):
        for name, value in variables.items():
            key = (name, _key(value))
            by_value[key] = by_value.get(key, 0) | (1 << i)
    return Graph(states, step, _reach(passing), by_value)


def _reach(succ):
    """For each state, the states one or more steps of `succ` lead to, as a bitmask: Tarjan's
    strongly connected components, each joined in reverse topological order."""
    n = len(succ)
    comp = [-1] * n
    low, order = [0] * n, [-1] * n
    stack, on, comps = [], [False] * n, []
    counter = 0
    for root in range(n):
        if order[root] != -1:
            continue
        work = [(root, 0)]
        while work:
            v, i = work.pop()
            if i == 0:
                order[v] = low[v] = counter
                counter += 1
                stack.append(v)
                on[v] = True
            if i < len(succ[v]):
                work.append((v, i + 1))
                w = succ[v][i]
                if order[w] == -1:
                    work.append((w, 0))
                elif on[w]:
                    low[v] = min(low[v], order[w])
                continue
            if low[v] == order[v]:
                members = []
                while True:
                    w = stack.pop()
                    on[w] = False
                    comp[w] = len(comps)
                    members.append(w)
                    if w == v:
                        break
                comps.append(members)
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[v])
    # Tarjan closes each component after every component it leads to, so in list order each
    # successor's reach is known.
    reach_of = []
    for c, members in enumerate(comps):
        mask = 0
        for v in members:
            for w in succ[v]:
                mask |= 1 << w
                if comp[w] != c:
                    mask |= reach_of[comp[w]]
        reach_of.append(mask)
    return [reach_of[comp[v]] for v in range(n)]


@dataclass
class Tally:
    lines: int = 0
    matched: int = 0
    misses: list[str] = field(default_factory=list)
    breaks: list[str] = field(default_factory=list)


def _shown(observed):
    return ",".join(str(v) for v in observed.values()) or "-"


def walk(graph, observe, lines, since=""):
    """Walks `lines`, each a dict, over `graph` as `observe` reads them, and returns the
    `Tally` of the lines whose `at` is `since` or later."""
    tally = Tally()
    held = {}
    seen = {}
    for line in lines:
        read = observe(line)
        if read is None:
            continue
        unit, before, after, actions = read
        counted = str(line.get("at", "")) >= since
        at = line.get("at", "")
        start = graph.where(before)
        now = held.get(unit)
        if now is None:
            now = start
        elif not now & start:
            if counted:
                tally.breaks.append(f"BREAK {unit} {_shown(seen[unit])} -> {_shown(before)} {at}")
            now = start
        now &= start
        led = 0
        if actions is None:
            for s in _bits(now):
                led |= graph.reach[s]
        else:
            for s in _bits(now):
                for action in actions:
                    led |= graph.step[s].get(action, 0)
        led &= graph.where(after)
        if counted:
            tally.lines += 1
            if led:
                tally.matched += 1
            else:
                tally.misses.append(f"MISS {unit} {_shown(before)} -> {_shown(after)} {at}")
        held[unit] = led or graph.where(after)
        seen[unit] = after
    return tally


def read_log(path):
    """The log's lines, each parsed, and the count of lines that are not a JSON object."""
    parsed, unread = [], 0
    try:
        with open(path, encoding="utf-8") as handle:
            for text in handle:
                if not text.strip():
                    continue
                try:
                    one = json.loads(text)
                except ValueError:
                    unread += 1
                    continue
                if isinstance(one, dict):
                    parsed.append(one)
                else:
                    unread += 1
    except OSError as e:
        raise ReplayError(f"cannot read the log {path}: {e.strerror or e}") from e
    return parsed, unread


def load_trace(path):
    from statechart.mapping import load_mapping

    try:
        trace = load_mapping(path)
    except (OSError, SyntaxError) as e:
        raise ReplayError(f"cannot read the trace file {path}: {e}") from e
    if not callable(getattr(trace, "observe", None)):
        raise ReplayError(f"{path} defines no observe(line): see statechart replay --help")
    return trace


def dump_graph(spec, cfg_file, verbs):
    """The `Graph` TLC dumps of `spec` under the config `cfg_file`, its rules taken out, in a
    temporary copy of the spec's folder."""
    from statechart.cli import find_tools, local_modules, run_tlc, split_rules

    tools = find_tools()
    with open(cfg_file, encoding="utf-8") as handle:
        cfg = split_rules(handle.read())["cfgWithoutRules"]
    with tempfile.TemporaryDirectory(prefix="statechart-replay-") as work:
        for module in [spec, *local_modules(spec)]:
            shutil.copy(module, work)
        copy = os.path.join(work, os.path.basename(spec))
        dot = os.path.join(work, "graph.dot")
        run_tlc(tools, copy, cfg, os.path.join(work, "graph"), dump=dot)
        try:
            with open(dot, encoding="utf-8") as handle:
                text = handle.read()
        except OSError as e:
            raise ReplayError(f"TLC wrote no graph of {spec}: {e.strerror or e}") from e
    try:
        return graph_of(text, set(verbs))
    except ChartError as e:
        raise ReplayError(f"TLC's graph of {spec}: {e}") from e


def beside(given, spec):
    """`given`, or the file of that name beside `spec` when `given` is relative and not there."""
    if os.path.exists(given) or os.path.isabs(given):
        return given
    return os.path.join(os.path.dirname(spec) or ".", given)


def parse_args(argv):
    flags, spec = {}, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            return {"help": True}
        if a in ("--config", "--trace", "--log", "--since"):
            if i + 1 == len(argv):
                raise ReplayError(f"{a} needs a value. Run statechart replay --help for the flags.")
            i += 1
            flags[a[2:]] = argv[i]
        elif not a.startswith("-") and spec is None:
            spec = a
        else:
            raise ReplayError(f"unknown argument {a}. Run statechart replay --help for the flags.")
        i += 1
    missing = [f"--{f}" for f in ("trace", "log") if f not in flags]
    if spec is None or missing:
        raise ReplayError(f"Usage: {USAGE}")
    return {"spec": spec, **flags}


def main(argv):
    """`statechart replay`: the exit code, after printing the tally."""
    from statechart.cli import CannotFinish

    try:
        args = parse_args(argv)
        if args.get("help"):
            print(HELP)
            return 0
        spec = args["spec"]
        if not os.path.exists(spec):
            raise ReplayError(f"{spec} does not exist")
        cfg = beside(args.get("config") or os.path.basename(spec)[:-4] + ".cfg", spec)
        if not os.path.exists(cfg):
            raise ReplayError(f"{cfg} does not exist: pass --config with the config to run")
        trace = load_trace(beside(args["trace"], spec))
        lines, unread = read_log(args["log"])
        graph = dump_graph(spec, cfg, getattr(trace, "verbs", ()))
        tally = walk(graph, trace.observe, lines, args.get("since", ""))
    except (ReplayError, CannotFinish) as e:
        print(e, file=sys.stderr)
        return 2
    missed = len(tally.misses)
    print(f"{tally.lines} lines, {tally.matched} matched, {missed} matched no step")
    for miss in tally.misses:
        print(miss)
    if tally.breaks:
        print(f"{len(tally.breaks)} lines start where their unit's last line did not end")
        for one in tally.breaks:
            print(one)
    if unread:
        print(f"{unread} lines of the log are not JSON objects, and were not read")
    return 1 if missed else 0
