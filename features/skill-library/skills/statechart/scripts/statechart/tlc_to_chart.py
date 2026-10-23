"""tlc-to-chart: collapses a TLC state graph onto the reader's states and writes a Mermaid
stateDiagram-v2. `statechart` runs it once for the overview and once for each bug chart."""

import copy
import json
import math
import re
import sys

from statechart.lib import (
    FULL_LABELS,
    GROUP_PALETTE,
    LEGEND_ID,
    PLAIN_FILL,
    STATUS_CLASSES,
    ChartError,
    Facts,
    call,
    compare_charts,
    escape_mermaid_quotes,
    group_class_def,
    group_color_problem,
    is_record,
    join_and,
    join_labels,
    js_string,
    parse_dot,
    parse_mermaid,
    parse_traces,
    product_of,
    rule_sentences,
    state_key,
    tlc_output_warning,
    to_json,
    wrap,
)
from statechart.mapping import load_mapping

USAGE = "Usage: tlc-to-chart --dot FILE --map FILE [options]"
HELP = f"""{USAGE}

Collapses a TLC state graph onto the reader's states and writes a Mermaid stateDiagram-v2.
statechart runs it once for the overview and once for each bug chart.

  --dot FILE             The state graph from TLC -dump dot,actionlabels FILE, for the current code.
                         Required.
  --map FILE             The mapping module, a Python file. Required. It defines state(vars, facts),
                         and optionally detail(vars, facts), step(action, before, after),
                         guard(action, before, after), timer(action, before, after),
                         cause(vars, facts, invariant), group(vars, facts), group_colors,
                         region_names, reader_actions, and legend. guard is when the step
                         can happen, in plain words. An edge reads "step [words]" when every
                         model step behind it has words. timer is how many seconds the code waits
                         before a timer step, and the step reads "after N s, step".
                         cause is the hidden reason a bad state is bad: counterexamples with the
                         same invariant and cause are one bug. When cause returns nothing, the
                         end state stands in for it. reader_actions are the actions the
                         reader takes. group is the group of a state, below. legend, such as
                         {{"works": "Works on main"}}, gives the legend's words for the works,
                         wrong, and fixed statuses. A function may take fewer arguments than
                         these, and gets only the first ones.
                         facts.enabled is the set of actions the state enables. facts.settled is
                         true when only reader actions are enabled, so nothing else happens until
                         the reader acts.
  --traces FILE          TLC output that holds counterexamples. Repeat it. TLC -continue gives one
                         per bad state. It refuses a file from a TLC run that stopped early or hit
                         an error other than a broken rule. When TLC found a rule broken and then
                         failed with a Java exception, it keeps the paths that TLC printed and
                         warns that the chart can miss states that break the rule.
  --fixed-dot FILE       The state graph of the model with the open fix. Each bug's steps replay
                         on it.
  --fixed-traces FILE    TLC output for the same invariants on the fixed model. Repeat it. It marks
                         states fixed or still wrong, and adds the bugs that only the fixed model
                         has after the current model's bugs.
  --fixed-rules LIST     The invariants that the fixed model's TLC runs check, as in A,B. It goes
                         with --fixed-traces. A rule that the fixed model does not check stays
                         as wrong as it is today, and its stories say "not checked".
  --against-dot FILE     The state graph of the spec that the current code must follow.
                         Each bug's steps replay on it. Do not use it with --fixed-dot.
  --against-traces FILE  TLC output for the spec. Repeat it. Its bugs are drawn wrong, and the
                         bugs that only the spec has number after the code's bugs.
  --against-rules LIST   The invariants that the spec's TLC runs check. It goes with
                         --against-traces. Stories of a rule that the spec does not check say
                         "not checked".
  --listed JSON          What the spec's configs expect, as in
                         {{"spec":"Spec.tla","breaks":{{"A.cfg":"Rule"}}}}: each config whose
                         "\\* expect:" line names a rule, and that rule. It goes with
                         --against-dot. Each story then says whether a config of the spec already
                         expects TLC to break its rule, and summary.json has second.listed and
                         each bug's listed configs.
  --label TEXT           The name of the second model in the chart and the stories. Default:
                         "the fix" with --fixed-dot, "the spec" with --against-dot.
  --spec FILE            A TLA+ file whose \\* comment lines above a rule are the rule's sentence in
                         the stories. Repeat it. The first file that has a sentence wins.
  --view NAME            customer (state labels, the default), developer (detail labels), or
                         layered (detail inside state).
  --cover                Keep only the shortest path to each settled reader state, plus the
                         counterexample paths.
  --highlight N          Draw bug N as a numbered path. Default 1. 0 draws none.
  --path-only            Draw only the highlighted path.
  --full-labels          Write each label on an edge in full, joined by " or ", and mark the chart
                         "{FULL_LABELS}". Default: write the leading words that the labels
                         share once, as in "you tap Pay or Back".
  --flat                 Draw every state on its own, with no boxes.
  --regions              When every state reads "context: progress", draw two parallel regions,
                         context and progress, when they are smaller and proved. They draw the
                         steps of the shortest way to each region state, of each bug path, and
                         the nearest step with each label.
                         Otherwise draw the chart the other flags ask for, and print why.
                         Customer view, --highlight 0, no --flat or --path-only.
  --proof FILE           With --regions, write the flat chart that the proof compares with.
  --regions-all FILE     With --regions, also write the regions with every step.
  --title TEXT           The chart title.
  --out FILE             The Mermaid chart. Default: stdout.
  --story FILE           The reader stories, one per bug.
  --summary FILE         The counts for the chart and the bugs, as JSON.
  -h, --help             Print this help, and exit 0.

Each bug replays on the second model by its screens and step words, which are what the reader
sees. The replay takes the second model's steps that keep the screen and that the reader does not
take. A bug step that the reader does not see must keep the screen on the second model too, unless
the second model cannot take it. The replay stops at the first step that the second model shows
the reader differently. There the chart draws "with LABEL, STEP" (or "in LABEL, STEP" for
--against-dot) to where the second model goes, or a loop "... STEP cannot happen" when it cannot
take a step that the reader sees.

The second model may have other variables and actions than the current model. Variables and
record fields that one start state has and the other does not are left out when the two models
are compared. One mapping draws both models, so it may read only what both have. The command
stops when the mapping reads a variable or field of the current model on a state of the second
model that lacks it. Test "name" in v first to label such a state another way. A step of an
action that the second model does not have is skipped when it changes no shared variable, and
matches any step to the same shared state when it does.

In the customer view, states whose labels read "context: progress" with the same context sit in
one box named context, and each shows only its progress. A context with one state stays a plain
state. An arrow from a box's border stands for the same step from every state in the box: it is
drawn only when every state in the box takes that step, with the same labels, to the same state.
The layered view puts each detail state in a box named by its state label.

With --regions, each "context: progress" label is one state in the context region and one in the
progress region. A step that happens beside only some states of the other region gets a guard:
"[when A or B]" or "[unless A or B]", whichever is shorter, and a "%% when [not] ids" line under it.
The mapping's guard words, when the step has them, replace "when A or B" in the label.
The proof combines the regions with every step as compare-charts does, and needs exactly the
flat chart's states, start states, and labeled steps. Each state's color must be the worse color
of its two region states. Then the drawn arrows, combined, must make only steps of the flat chart:
a step that they make wrongly gets back every arrow that the full regions take there.
compare-charts on the --regions-all and --proof files repeats the first proof.
region_names = [context, progress] in the mapping names the two regions.

Outside regions, two states have at most one arrow. Its lines are the numbered steps, then the
current model's steps, then the second model's steps, with a blank line between each group.

Without group(), the legend shows only the statuses the chart uses. A chart with a second model
has the line "%% second model (fix|against): LABEL" right after stateDiagram-v2. Each chart
starts with front matter that keeps Mermaid from shrinking it to the page or rewrapping its labels.

Groups: group(vars, facts) returns the name of the group that a model state is in, such as
"Toast shown", or nothing. A chart state is in a group when all its model states are in it. A
region state is in a group when every state that it is part of is in it. Each group fills its
states with one color, and the legend lists only the groups that the chart draws: first the
groups in group_colors, in that order, then the others from A to Z. group_colors, such as
{{"Toast shown": "#d6eaf8"}}, gives a group a light "#rgb" or "#rrggbb" color. A group with no
color, or None, takes the next free palette color: light blue, orange, purple, yellow, teal, tan,
then pink. A state in no group, or in more than one, is gray. summary.json counts the drawn
states of each group in chartGroups, and lists the chart states with more than one in mixedGroups.
TLC decides the status, and a group cannot change it. On top of the group color, a state that
breaks a rule has a thick red border, and a fixed state or a state only in the second model a
thick green border. The legend then shows that border. A thick blue border marks the bug path on
states that work. On other states of the path, the numbered arrows show it. A group cannot have
the name of a status, such as "Breaks a rule".

Writes only the files that --out, --story, and --summary name.

Exit codes
  0  It wrote the chart.
  1  It cannot use an input: a mapping without state(), a mapping that reads what the second
     model lacks, TLC output that it refuses, or a --highlight with no such bug. The error says
     why.
  2  A bad argument."""
MORE = "Run tlc-to-chart --help for the flags."
SEP = "\0"
CODE_LIKE = re.compile(
    r"\b[a-z]{2,}[A-Z][a-z]|\b\w+_\w+\b|\b[A-Za-z_]\w*\(|\b[A-Z][a-z]+[A-Z][a-z]", re.ASCII
)


class BadArgument(Exception):
    pass


def edge_id(source, target):
    return f"{source}{SEP}{SEP}{target}"


def cap(s):
    return s[:1].upper() + s[1:]


def locale_key(s):
    """A sort key close to JavaScript's localeCompare: spaces, then punctuation, then digits,
    then letters, each letter by its lower case first and its case last."""
    primary = []
    tertiary = []
    for c in s:
        if c.isspace():
            rank = 0
        elif c.isdigit():
            rank = 2
        elif c.isalpha():
            rank = 3
        else:
            rank = 1
        primary.append((rank, c.lower()))
        tertiary.append(0 if c == c.lower() else 1)
    return (primary, tertiary)


def parse_args(argv):
    args = {
        "traces": [],
        "fixedTraces": [],
        "againstTraces": [],
        "fixedRules": [],
        "againstRules": [],
        "specs": [],
        "view": "customer",
        "highlight": 1,
        "dot": None,
        "map": None,
        "fixedDot": None,
        "againstDot": None,
        "listed": None,
        "label": None,
        "pathOnly": False,
        "fullLabels": False,
        "flat": False,
        "regions": False,
        "proof": None,
        "regionsAll": None,
        "cover": False,
        "title": None,
        "out": None,
        "story": None,
        "summary": None,
    }
    one = {
        "--dot": "dot",
        "--map": "map",
        "--fixed-dot": "fixedDot",
        "--against-dot": "againstDot",
        "--listed": "listed",
        "--label": "label",
        "--view": "view",
        "--proof": "proof",
        "--regions-all": "regionsAll",
        "--title": "title",
        "--out": "out",
        "--story": "story",
        "--summary": "summary",
    }
    many = {
        "--traces": "traces",
        "--fixed-traces": "fixedTraces",
        "--against-traces": "againstTraces",
        "--spec": "specs",
    }
    switches = {
        "--path-only": "pathOnly",
        "--full-labels": "fullLabels",
        "--flat": "flat",
        "--regions": "regions",
        "--cover": "cover",
    }
    i = 0
    while i < len(argv):
        a = argv[i]

        def nxt():
            nonlocal i
            i += 1
            return argv[i] if i < len(argv) else None

        if a in ("-h", "--help"):
            return None
        if a in one:
            args[one[a]] = nxt()
        elif a in many:
            args[many[a]].append(nxt())
        elif a in ("--fixed-rules", "--against-rules"):
            value = nxt()
            args["fixedRules" if a == "--fixed-rules" else "againstRules"] += (value or "").split(
                ","
            )
        elif a == "--highlight":
            value = nxt()
            try:
                number = float(value)
            except (TypeError, ValueError):
                number = math.nan
            args["highlight"] = int(number) if number.is_integer() else number
        elif a in switches:
            args[switches[a]] = True
        else:
            raise BadArgument(f"unknown argument {a}. {MORE}")
        i += 1
    return args


def check_args(args):
    def fail(message):
        raise BadArgument(f"{message} {MORE}")

    if not args["dot"] or not args["map"]:
        fail(USAGE)
    if args["view"] not in ("customer", "developer", "layered"):
        fail(f"--view must be customer, developer, or layered, not {args['view']}.")
    if args["fixedDot"] and args["againstDot"]:
        fail("use --fixed-dot or --against-dot, not both.")
    if args["fixedTraces"] and not args["fixedDot"]:
        fail("--fixed-traces needs --fixed-dot.")
    if args["againstTraces"] and not args["againstDot"]:
        fail("--against-traces needs --against-dot.")
    if (not args["fixedTraces"]) != (not args["fixedRules"]):
        fail(
            "--fixed-traces and --fixed-rules go together. The rules are what those TLC runs check."
        )
    if (not args["againstTraces"]) != (not args["againstRules"]):
        fail(
            "--against-traces and --against-rules go together. The rules are what those TLC runs"
            " check."
        )
    if args["listed"] is not None:
        if not args["againstDot"]:
            fail("--listed says what the spec's configs expect; it needs --against-dot.")
        shape = '--listed must be JSON such as {"spec":"Spec.tla","breaks":{"A.cfg":"Rule"}}'
        try:
            args["listed"] = json.loads(args["listed"])
        except json.JSONDecodeError as e:
            fail(f"{shape}: {e}.")
        listed = args["listed"] if is_record(args["listed"]) else {}
        spec, breaks = listed.get("spec"), listed.get("breaks")
        if (
            not isinstance(spec, str)
            or not is_record(breaks)
            or any(not isinstance(r, str) for r in breaks.values())
        ):
            fail(f"{shape}.")
    if args["label"] is not None and not args["fixedDot"] and not args["againstDot"]:
        fail("--label names the second model; it needs --fixed-dot or --against-dot.")
    if args["proof"] and not args["regions"]:
        fail("--proof writes the regions proof; it needs --regions.")
    if args["regionsAll"] and not args["regions"]:
        fail("--regions-all writes every regions arrow; it needs --regions.")
    if args["regions"] and (
        args["view"] != "customer" or args["flat"] or args["pathOnly"] or args["highlight"] != 0
    ):
        fail(
            "--regions draws the whole customer chart: use --highlight 0, without --flat or"
            " --path-only."
        )


class Guarded(dict):
    """A state of the second model that refuses to give the mapping a variable or field that only
    the current model has."""

    def __init__(self, values, missing, deeper, path, label):
        super().__init__(values)
        self._missing = missing
        self._deeper = deeper
        self._path = path
        self._label = label

    def _refuse(self, k):
        name = ".".join([*self._path, k])
        holder = "v" + "".join(f'["{p}"]' for p in self._path)
        raise ChartError(
            f'{self._label} has no {name}, and the mapping reads {holder}["{k}"] on its states.'
            f' Label states and steps only from what both models have, or test "{k}" in'
            f" {holder} first."
        )

    def __getitem__(self, k):
        if k in self._missing and not dict.__contains__(self, k):
            self._refuse(k)
        value = dict.__getitem__(self, k)
        if k in self._deeper:
            return guard(value, self._deeper[k], self._label, [*self._path, k])
        return value

    def get(self, k, default=None):
        if k in self._missing and not dict.__contains__(self, k):
            self._refuse(k)
        return self[k] if dict.__contains__(self, k) else default

    def __deepcopy__(self, memo):
        return copy.deepcopy(dict(self), memo)


def guard(variables, paths, label, path=()):
    if not paths or not is_record(variables):
        return variables
    missing = set()
    deeper = {}
    for k, *rest in paths:
        if not rest:
            missing.add(k)
        else:
            deeper.setdefault(k, []).append(rest)
    return Guarded(variables, missing, deeper, list(path), label)


def given_or(given, key, default):
    value = given.get(key) if is_record(given) else None
    return default if value is None else value


def lacking(a, b, prefix=()):
    out = []
    for k in a:
        if k not in b:
            out.append([*prefix, k])
        elif is_record(a[k]) and is_record(b[k]):
            out += lacking(a[k], b[k], [*prefix, k])
    return out


def omit(variables, paths):
    if not paths:
        return variables
    out = copy.deepcopy(variables)
    for p in paths:
        holder = out
        for k in p[:-1]:
            holder = holder.get(k) if is_record(holder) and is_record(holder.get(k)) else None
        if holder is not None:
            holder.pop(p[-1], None)
    return out


def chart(args):
    role = "fix" if args["fixedDot"] else "against" if args["againstDot"] else None
    L = args["label"] if args["label"] is not None else ("the fix" if role == "fix" else "the spec")
    within = "with" if role == "fix" else "in"

    mapping = load_mapping(args["map"])
    if not callable(getattr(mapping, "state", None)):
        raise ChartError("the mapping module must define state(vars)")
    if args["view"] != "customer" and not callable(getattr(mapping, "detail", None)):
        raise ChartError(f"--view {args['view']} needs detail(vars) in the mapping module")

    def has(name):
        return callable(getattr(mapping, name, None))

    rules = {}
    for f in args["specs"]:
        with open(f, encoding="utf-8") as handle:
            for name, sentence in rule_sentences(handle.read()).items():
                rules.setdefault(name, sentence)

    reader_actions = set(getattr(mapping, "reader_actions", None) or [])

    def facts_from(enabled):
        return Facts(frozenset(enabled), all(a in reader_actions for a in enabled))

    def key_of(variables, facts):
        if args["view"] == "developer":
            return js_string(call(mapping.detail, variables, facts))
        outer = call(mapping.state, variables, facts)
        if not isinstance(outer, str):
            raise ChartError(f"state() must return a string; got {to_json(outer)}")
        if args["view"] == "layered":
            return f"{outer}{SEP}{js_string(call(mapping.detail, variables, facts))}"
        return outer

    def step_label(action, before, after, view=None):
        view = view or args["view"]
        said = call(mapping.step, action, before, after) if has("step") else action
        named = said if view == "customer" or said == action else f"{said} [{action}]"
        seconds = call(mapping.timer, action, before, after) if has("timer") else None
        if seconds is None or seconds == "" or not named:
            return named
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, int | float)
            or not math.isfinite(seconds)
            or seconds <= 0
        ):
            raise ChartError(
                "timer() must return a number of seconds above 0, or nothing; got"
                f" {to_json(seconds)} for {action}"
            )
        return f"after {js_string(seconds)} s, {named}"

    def step_guard(action, before, after):
        if not has("guard"):
            return ""
        said = call(mapping.guard, action, before, after)
        return re.sub(r"[\[\]]", "", "" if said is None else js_string(said)).strip()

    def guarded(guards, label):
        words = guards.get(label) if guards else None
        return f"{label} [{' or '.join(sorted(words))}]" if words and "" not in words else label

    def add_guard(guards, label, words):
        guards.setdefault(label, {})[words] = None

    def model_of(graph):
        by_id = {node_id: set() for node_id in graph["nodes"]}
        for e in [*graph["edges"], *graph["loops"]]:
            by_id[e["from"]].add(e["action"])
        index = {state_key(n["vars"]): by_id[n["id"]] for n in graph["nodes"].values()}

        def facts(variables):
            return facts_from(index.get(state_key(variables), set()))

        return {
            "graph": graph,
            "facts": facts,
            "key": lambda variables: key_of(variables, facts(variables)),
            "customer": lambda variables: js_string(
                call(mapping.state, variables, facts(variables))
            ),
        }

    def quotient(m):
        graph = m["graph"]
        keys = {n["id"]: m["key"](n["vars"]) for n in graph["nodes"].values()}
        nodes = dict.fromkeys(keys.values())
        initial = dict.fromkeys(keys[n["id"]] for n in graph["nodes"].values() if n["init"])
        edges = {}
        for e in graph["edges"]:
            source, target = keys[e["from"]], keys[e["to"]]
            if source == target:
                continue
            eid = edge_id(source, target)
            if eid not in edges:
                edges[eid] = {"from": source, "to": target, "counts": {}, "guards": {}}
            before, after = graph["nodes"][e["from"]]["vars"], graph["nodes"][e["to"]]["vars"]
            label = step_label(e["action"], before, after)
            if not label:
                continue
            counts = edges[eid]["counts"]
            counts[label] = counts.get(label, 0) + 1
            add_guard(edges[eid]["guards"], label, step_guard(e["action"], before, after))
        for e in edges.values():
            e["labels"] = dict.fromkeys(
                label for label, _ in sorted(e["counts"].items(), key=lambda kv: -kv[1])
            )
        settled = dict.fromkeys(
            keys[n["id"]] for n in graph["nodes"].values() if m["facts"](n["vars"]).settled
        )
        return {
            "nodes": nodes,
            "initial": initial,
            "edges": edges,
            "keys": keys,
            "settled": settled,
        }

    with open(args["dot"], encoding="utf-8") as handle:
        graph = parse_dot(handle.read())
    main = model_of(graph)
    now = quotient(main)
    main_init = next(n for n in graph["nodes"].values() if n["init"])["vars"]

    second_dot = args["fixedDot"] or args["againstDot"]
    second_graph = None
    if second_dot:
        with open(second_dot, encoding="utf-8") as handle:
            second_graph = parse_dot(handle.read())
    second_init = (
        second_graph and next(n for n in second_graph["nodes"].values() if n["init"])["vars"]
    )
    lacks = lacking(main_init, second_init) if second_graph else []
    extra = lacking(second_init, main_init) if second_graph else []
    second = None
    if second_graph:
        second = model_of(
            {
                **second_graph,
                "nodes": {
                    node_id: {**n, "raw": n["vars"], "vars": guard(n["vars"], lacks, L)}
                    for node_id, n in second_graph["nodes"].items()
                },
            }
        )
    second_q = quotient(second) if second else None

    def reader_path(trace, key, label_of=step_label):
        steps = trace["steps"]
        out = [{"key": key(steps[0]["vars"]), "label": None, "modelStep": 0}]
        for i in range(1, len(steps)):
            action = steps[i]["action"]
            k = key(steps[i]["vars"])
            if k == out[-1]["key"] and action not in reader_actions:
                continue
            before, after = steps[i - 1]["vars"], steps[i]["vars"]
            label = label_of(action, before, after) or action
            out.append(
                {
                    "key": k,
                    "label": label,
                    "guard": step_guard(action, before, after),
                    "action": action,
                    "modelStep": i,
                }
            )
        return out

    def reader_label(action, before, after):
        return step_label(action, before, after, "customer")

    def read_traces(files, paths=()):
        found = []
        for f in files:
            with open(f, encoding="utf-8") as handle:
                text = handle.read()
            warning = tlc_output_warning(text, f)
            if warning:
                print(f"{f}: {warning}", file=sys.stderr)
            for t in parse_traces(text):
                found.append(
                    {
                        **t,
                        "steps": [
                            {**s, "vars": guard(s["vars"], list(paths), L)} for s in t["steps"]
                        ],
                    }
                )
        return found

    def first_bad(raw):
        bad_states = {}
        for t in raw:
            bad_states.setdefault(t["invariant"], set()).add(state_key(t["steps"][-1]["vars"]))
        cuts = []
        seen = set()
        for t in raw:
            first = next(
                i
                for i, s in enumerate(t["steps"])
                if state_key(s["vars"]) in bad_states[t["invariant"]]
            )
            cut = {"invariant": t["invariant"], "steps": t["steps"][: first + 1]}
            cid = f"{t['invariant']}{SEP}{state_key(cut['steps'][-1]['vars'])}"
            if cid in seen:
                continue
            seen.add(cid)
            cuts.append(cut)
        return cuts

    raw_traces = read_traces(args["traces"])
    second_trace_files = args["fixedTraces"] if role == "fix" else args["againstTraces"]
    second_rules = set(args["fixedRules"] if role == "fix" else args["againstRules"])
    raw_second_traces = read_traces(second_trace_files, lacks)
    traces = first_bad(raw_traces)
    second_traces = first_bad(raw_second_traces)

    def replay_second(trace):
        if not second:
            return None

        def shared(variables):
            return state_key(omit(variables, lacks))

        def shared_of(n):
            return state_key(omit(n["raw"], extra))

        sgraph = second["graph"]
        out = {}
        for e in [*sgraph["edges"], *sgraph["loops"]]:
            out.setdefault(e["from"], []).append(e)
        actions = {e["action"] for e in [*sgraph["edges"], *sgraph["loops"]]}

        def node_of(node_id):
            return sgraph["nodes"][node_id]

        screen = {n["id"]: second["customer"](n["vars"]) for n in sgraph["nodes"].values()}

        def words(e):
            return (
                reader_label(e["action"], node_of(e["from"])["vars"], node_of(e["to"])["vars"])
                or e["action"]
            )

        def settle(ids):
            every = list(dict.fromkeys(ids))
            members = set(every)
            k = 0
            while k < len(every):
                node_id = every[k]
                k += 1
                for e in out.get(node_id, []):
                    if (
                        e["action"] not in reader_actions
                        and screen[e["to"]] == screen[node_id]
                        and e["to"] not in members
                    ):
                        members.add(e["to"])
                        every.append(e["to"])
            return every

        seen = reader_path(trace, main["customer"], reader_label)
        shown_at = {p["modelStep"]: j for j, p in enumerate(seen)}
        here = settle(
            n["id"]
            for n in sgraph["nodes"].values()
            if n["init"] and screen[n["id"]] == seen[0]["key"]
        )
        if not here:
            return {"reason": "starts on another screen"}
        passed = dict.fromkeys(here)
        j = 0
        steps = trace["steps"]
        for i in range(1, len(steps)):
            action = steps[i]["action"]
            hidden = i not in shown_at
            if not hidden:
                j = shown_at[i]
            want = seen[j]
            before, after = steps[i - 1]["vars"], steps[i]["vars"]
            known = action in actions
            if not known and (hidden or shared(before) == shared(after)):
                continue
            tries = [
                e
                for node_id in here
                for e in out.get(node_id, [])
                if (
                    e["action"] == action if known else shared_of(node_of(e["to"])) == shared(after)
                )
            ]
            if hidden and not tries:
                continue
            same = (
                [
                    e
                    for e in tries
                    if screen[e["to"]] == want["key"] and (hidden or words(e) == want["label"])
                ]
                if known
                else tries
            )
            if same:
                here = settle(e["to"] for e in same)
                for node_id in here:
                    passed[node_id] = None
                continue
            outcomes = {}
            for e in tries:
                outcomes.setdefault(f"{screen[e['to']]}{SEP}{words(e)}", []).append(e)
            ranked = sorted(outcomes.values(), key=lambda es: -len(es))
            taken = ranked[0][0] if ranked else None
            source = main["key"](before)
            said = (reader_label(action, before, after) or action) if hidden else want["label"]
            at = {"step": j, "said": said, "from": source, "hidden": hidden}
            if not taken:
                return {
                    **at,
                    "key": source,
                    "label": step_label(action, before, after) or action,
                    "disabled": True,
                }
            b, a = node_of(taken["from"])["vars"], node_of(taken["to"])["vars"]
            return {
                **at,
                "key": second["key"](a),
                "label": step_label(taken["action"], b, a) or taken["action"],
            }
        bad = {
            state_key(t["steps"][-1]["vars"])
            for t in raw_second_traces
            if t["invariant"] == trace["invariant"]
        }
        checked = trace["invariant"] in second_rules
        rule_holds = checked and not any(
            state_key(node_of(node_id)["vars"]) in bad for node_id in passed
        )
        return {"sameEnd": True, "checked": checked, "ruleHolds": rule_holds}

    def group_bugs(cuts, m):
        by_id = {}
        for trace in cuts:
            rp = reader_path(trace, m["customer"])
            last = trace["steps"][-1]["vars"]
            said = (
                call(mapping.cause, last, m["facts"](last), trace["invariant"])
                if has("cause")
                else None
            )
            cause = None if said is None else js_string(said)
            bid = f"{trace['invariant']}{SEP}{cause if cause is not None else rp[-1]['key']}"
            prev = by_id.get(bid)
            if (
                not prev
                or len(rp) < prev["steps"]
                or (len(rp) == prev["steps"] and len(trace["steps"]) < len(prev["trace"]["steps"]))
            ):
                by_id[bid] = {
                    "id": bid,
                    "cause": cause,
                    "steps": len(rp),
                    "trace": trace,
                    "invariant": trace["invariant"],
                    "count": (prev["count"] if prev else 0) + 1,
                }
            else:
                prev["count"] += 1
        return by_id

    def by_order(c):
        return (c["steps"], len(c["trace"]["steps"]), c["id"])

    def in_second(label):
        return f"{within} {L}, {label}"

    model_edges = dict(now["edges"])
    if second_q:
        for eid, e in second_q["edges"].items():
            if eid not in model_edges:
                model_edges[eid] = {
                    **e,
                    "labels": dict.fromkeys(in_second(label) for label in e["labels"]),
                    "guards": {in_second(label): w for label, w in e["guards"].items()},
                    "secondOnly": True,
                }

    def divergence(s):
        if s is None or "key" not in s:
            return s
        plain = edge_id(s["from"], s["key"])
        text = in_second(f"{s['label']}{' cannot happen' if s.get('disabled') else ''}")
        drawn = not s.get("disabled") and any(
            label in (model_edges.get(plain) or {}).get("labels", {})
            for label in (s["label"], text)
        )
        return {**s, "text": text, "edge": plain if drawn else f"{plain}{SEP}second"}

    def with_path(c, m):
        path = reader_path(c["trace"], m["key"])
        return {**c, "path": path, "end": path[-1]["key"]}

    classes_by_id = group_bugs(traces, main)
    main_classes = [
        {**with_path(c, main), "second": divergence(replay_second(c["trace"]))}
        for c in sorted(classes_by_id.values(), key=by_order)
    ]
    introduced = (
        [
            {**with_path(c, second), "second": None, "introduced": True}
            for c in sorted(
                (
                    c
                    for c in group_bugs(second_traces, second).values()
                    if c["id"] not in classes_by_id
                ),
                key=by_order,
            )
        ]
        if second
        else []
    )
    classes = [*main_classes, *introduced]

    def diverges(c):
        return c.get("second") is not None and "key" in c["second"]

    def bad_keys(m, keys, raw):
        g = m["graph"]
        bad = {state_key(t["steps"][-1]["vars"]) for t in raw}
        out = dict.fromkeys(m["key"](t["steps"][-1]["vars"]) for t in raw)

        def ok(node_id):
            return state_key(g["nodes"][node_id]["vars"]) not in bad

        nxt = {}
        for e in g["edges"]:
            nxt.setdefault(e["from"], []).append(e["to"])
        clean = dict.fromkeys(n["id"] for n in g["nodes"].values() if n["init"] and ok(n["id"]))
        queue = list(clean)
        head = 0
        while head < len(queue):
            node_id = queue[head]
            head += 1
            for to in nxt.get(node_id, []):
                if to in clean or not ok(to):
                    continue
                clean[to] = None
                queue.append(to)
        reached = {keys[node_id] for node_id in clean}
        for k in keys.values():
            if k not in reached:
                out[k] = None
        return out

    bad_now = bad_keys(main, now["keys"], raw_traces)
    unchecked_traces = [t for t in raw_traces if t["invariant"] not in second_rules]
    bad_second = (
        {
            **bad_keys(second, second_q["keys"], raw_second_traces),
            **(bad_keys(main, now["keys"], unchecked_traces) if role == "fix" else {}),
        }
        if second
        else {}
    )
    all_nodes = {**now["nodes"], **(second_q["nodes"] if second_q else {})}
    initial = {**now["initial"], **(second_q["initial"] if second_q else {})}

    def only_second(k):
        return bool(second) and k not in now["nodes"]

    def status(k):
        if role == "against":
            return (
                "wrong"
                if k in bad_now or k in bad_second
                else "fixed"
                if only_second(k)
                else "works"
            )
        if role == "fix":
            return (
                "wrong"
                if k in bad_second
                else "fixed"
                if k in bad_now or only_second(k)
                else "works"
            )
        return "wrong" if k in bad_now else "works"

    highlight = args["highlight"]
    chosen = None
    if isinstance(highlight, int) and highlight > 0 and highlight <= len(classes):
        chosen = classes[highlight - 1]
    if isinstance(highlight, int | float) and highlight > 0 and classes and not chosen:
        raise ChartError(f"--highlight {js_string(highlight)}: only {len(classes)} classes")
    on_path = dict.fromkeys(p["key"] for p in chosen["path"]) if chosen else {}
    if chosen and diverges(chosen):
        on_path[chosen["second"]["key"]] = None

    def edges_along(c):
        path = c["path"]
        return [
            {
                "id": edge_id(path[i]["key"], p["key"]),
                "from": path[i]["key"],
                "to": p["key"],
                "label": p["label"],
                "guard": p.get("guard"),
            }
            for i, p in enumerate(path[1:])
        ]

    def chart_edges():
        edges = dict(model_edges)
        for c in classes:
            if not diverges(c):
                continue
            s = c["second"]
            if s["edge"] in model_edges:
                continue
            if s["edge"] not in edges:
                edges[s["edge"]] = {
                    "from": s["from"],
                    "to": s["key"],
                    "labels": {},
                    "secondOnly": True,
                }
            edges[s["edge"]]["labels"][s["text"]] = None
        path_numbers = {}
        for i, step in enumerate(edges_along(chosen) if chosen else []):
            shown = f"{step['label']} [{step['guard']}]" if step["guard"] else step["label"]
            path_numbers.setdefault(step["id"], []).append(
                {"n": i + 1, "label": step["label"], "shown": shown}
            )
            if step["id"] not in edges:
                edges[step["id"]] = {
                    "from": step["from"],
                    "to": step["to"],
                    "labels": {step["label"]: None},
                }
        if not args["cover"]:
            return edges, path_numbers, None

        cover_edges = {}

        def bfs(q, targets):
            parent = dict.fromkeys(q["initial"])
            queue = list(q["initial"])
            out_edges = {}
            for eid, e in q["edges"].items():
                out_edges.setdefault(e["from"], []).append((eid, e))
            head = 0
            while head < len(queue):
                k = queue[head]
                head += 1
                for eid, e in out_edges.get(k, []):
                    if e["to"] in parent:
                        continue
                    parent[e["to"]] = eid
                    queue.append(e["to"])
            for t in targets:
                eid = parent.get(t)
                while eid:
                    cover_edges[eid] = None
                    eid = parent.get(q["edges"][eid]["from"])

        bfs(now, now["settled"])
        if second_q:
            bfs(second_q, [k for k in second_q["settled"] if k not in now["nodes"]])
        path_labels = {}
        for c in classes:
            for step in edges_along(c):
                cover_edges[step["id"]] = None
                path_labels.setdefault(step["id"], {})[step["label"]] = None
            if diverges(c):
                cover_edges[c["second"]["edge"]] = None
        for eid in cover_edges:
            if eid in edges:
                continue
            source, target = eid.split(f"{SEP}{SEP}", 1)
            edges[eid] = {"from": source, "to": target, "labels": path_labels.get(eid, {})}
        return edges, path_numbers, cover_edges

    edges, path_numbers, cover_edges = chart_edges()

    legend_words = getattr(mapping, "legend", None) or {}
    LEGEND = {
        "works": [
            "legendWorks",
            given_or(legend_words, "works", "Works today" if role == "fix" else "Works"),
        ],
        "wrong": [
            "legendWrong",
            given_or(
                legend_words, "wrong", f"Still wrong with {L}" if role == "fix" else "Breaks a rule"
            ),
        ],
        "fixed": [
            "legendFixed",
            given_or(
                legend_words, "fixed", f"Fixed or new with {L}" if role == "fix" else f"Only in {L}"
            ),
        ],
    }

    grouping = has("group")
    groups_of = {}

    def group_of(k):
        gs = groups_of.get(k)
        return next(iter(gs)) if gs and len(gs) == 1 else ""

    group_names = []
    fills = {}
    if grouping:

        def add(k, variables, m):
            g = call(mapping.group, variables, m["facts"](variables))
            if g is not None and not isinstance(g, str):
                raise ChartError(f"group() must return a group name or nothing; got {to_json(g)}")
            groups_of.setdefault(k, {})[re.sub(r"\s+", " ", g or "").strip()] = None

        for n in graph["nodes"].values():
            add(now["keys"][n["id"]], n["vars"], main)
        if second:
            for n in second["graph"]["nodes"].values():
                add(second_q["keys"][n["id"]], n["vars"], second)

        given = getattr(mapping, "group_colors", None)
        given = {} if given is None else given
        if not is_record(given):
            raise ChartError(
                "group_colors must be a dict from a group name to a color such as #d6eaf8"
            )
        status_names = {
            t.lower()
            for t in [
                "Works",
                "Works today",
                "Breaks a rule",
                "Still wrong",
                "Fixed",
                *(t for _, t in LEGEND.values()),
            ]
        }
        found = dict.fromkeys(g for gs in groups_of.values() for g in gs if g)
        for g in found:
            if g.lower() in status_names:
                raise ChartError(
                    f'group "{g}" has the name of a status; TLC decides the status, so name the'
                    " group for what the reader sees"
                )
        group_names += [g for g in given if g in found]
        group_names += sorted(g for g in found if g not in given)
        for g, color in given.items():
            if color is None or color == "":
                continue
            why = group_color_problem(color)
            if why:
                raise ChartError(f'group_colors["{g}"] {to_json(color)} {why}')
            if g in found:
                fills[g] = color.lower()
        free = [c for c in GROUP_PALETTE if c not in fills.values()]
        for g in group_names:
            if g in fills:
                continue
            if not free:
                raise ChartError(
                    f"the mapping has {len(group_names)} groups, more than the {len(GROUP_PALETTE)}"
                    " colors of the palette; give the others a color in group_colors"
                )
            fills[g] = free.pop(0)
    mixed_groups = [k for k, gs in groups_of.items() if len(gs) > 1]

    BORDER = {"works": "", "wrong": "Wrong", "fixed": "Fixed"}

    def class_for(g, s, path):
        if grouping:
            base = f"group{group_names.index(g)}" if g else "plain"
            return f"{base}{BORDER[s] or ('Path' if path else '')}"
        return f"{s}{'Path' if path else ''}"

    def drawn_state(g, s, path=False):
        return {"group": g, "status": s, "cls": class_for(g, s, path)}

    def group_counts(drawn):
        counted = [
            {"name": g, "color": fills.get(g), "states": sum(1 for d in drawn if d["group"] == g)}
            for g in group_names
        ]
        return [g for g in counted if g["states"] > 0]

    def front_matter(title=None):
        return [
            "---",
            *([f"title: {json.dumps(title, ensure_ascii=False)}"] if title else []),
            "config:",
            "  markdownAutoWrap: false",
            "  state:",
            "    useMaxWidth: false",
            "---",
        ]

    def head(drawn):
        out = [*front_matter(args["title"]), "stateDiagram-v2"]
        if role:
            out.append(f"  %% second model ({role}): {L}")
        if args["fullLabels"]:
            out.append(f"  {FULL_LABELS}")
        used = [s for s in LEGEND if any(d["status"] == s for d in drawn)]
        if grouping:
            legend = [
                (
                    f"legendGroup{group_names.index(g['name'])}",
                    g["name"],
                    f"group{group_names.index(g['name'])}",
                )
                for g in group_counts(drawn)
            ]
            legend += [(*LEGEND[s], f"plain{BORDER[s]}") for s in used if BORDER[s]]
        else:
            legend = [(*LEGEND[s], s) for s in used]
        if grouping:
            style_classes = {d["cls"] for d in drawn} | {c for _, _, c in legend}
            bases = [
                ("plain", PLAIN_FILL),
                *((f"group{i}", fills[g]) for i, g in enumerate(group_names)),
            ]
            for base, fill in bases:
                for border in ("", "Wrong", "Fixed", "Path"):
                    if base + border in style_classes:
                        out.append(f"  {group_class_def(base, fill, border)}")
        else:
            out += [f"  {c}" for c in STATUS_CLASSES]
        if legend:
            out.append(f'  state "Legend" as {LEGEND_ID} {{')
            for lid, text, _ in legend:
                out.append(f'    state "{escape_mermaid_quotes(text)}" as {lid}')
            out.append("  }")
            for lid, _, c in legend:
                out.append(f"  class {lid} {c}")
        return out

    def regions_chart(states, starts, edges, classes, proof_path, all_path):
        def norm(s):
            return re.sub(r"\s+", " ", s.replace(";", ",")).strip()

        def split(k):
            at = k.find(": ")
            return (norm(k[:at]), norm(k[at + 2 :])) if at > 0 and at + 2 < len(k) else None

        nodes = sorted(states)
        if not all(split(k) for k in nodes):
            return None
        steps = []
        for e in edges.values():
            if not e["labels"]:
                return {"why": "a step has no label"}
            for label in e["labels"]:
                steps.append(
                    {
                        "from": split(e["from"]),
                        "to": split(e["to"]),
                        "label": norm(label),
                        "words": (e.get("guards") or {}).get(label, {"": None}),
                    }
                )

        def bar(p):
            return " | ".join(p)

        flat = {
            "Main": {
                "states": dict.fromkeys(bar(split(k)) for k in nodes),
                "initial": dict.fromkeys(bar(split(k)) for k in starts),
                "transitions": [
                    {"from": bar(s["from"]), "to": bar(s["to"]), "label": s["label"]} for s in steps
                ],
            }
        }
        ids = {s: f"p{i}" for i, s in enumerate(flat["Main"]["states"])}
        proof = [
            *front_matter(),
            "stateDiagram-v2",
            *(f'  state "{escape_mermaid_quotes(s)}" as {sid}' for s, sid in ids.items()),
            *(f"  [*] --> {ids[s]}" for s in flat["Main"]["initial"]),
            *(f"  {ids[bar(s['from'])]} --> {ids[bar(s['to'])]} : {s['label']}" for s in steps),
        ]
        if proof_path:
            with open(proof_path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(proof) + "\n")

        beside = [{}, {}]
        for k in nodes:
            p = split(k)
            for i in (0, 1):
                beside[i].setdefault(p[i], {})[p[1 - i]] = None
        size = len(beside[0]) + len(beside[1])
        if size >= len(nodes):
            return {"why": f"{size} region states are not fewer than the {len(nodes)} flat states"}

        rank = ["works", "fixed", "wrong"]
        region_status = [{}, {}]
        for k in nodes:
            p = split(k)
            for i in (0, 1):
                prev = region_status[i].get(p[i])
                if not prev or rank.index(status(k)) < rank.index(prev):
                    region_status[i][p[i]] = status(k)
        for k in nodes:
            p = split(k)
            shown = rank[max(rank.index(region_status[i][p[i]]) for i in (0, 1))]
            if shown != status(k):
                return {
                    "why": (
                        f'"{k}" is "{LEGEND[status(k)][1]}", and its two region states would'
                        f' show "{LEGEND[shown][1]}"'
                    )
                }

        moves = [{}, {}]
        for s in steps:
            for i in (0, 1):
                mid = SEP.join([s["from"][i], s["label"], s["to"][i]])
                if mid not in moves[i]:
                    moves[i][mid] = {
                        "from": s["from"][i],
                        "label": s["label"],
                        "to": s["to"][i],
                        "beside": {},
                        "guards": {},
                    }
                moves[i][mid]["beside"][s["from"][1 - i]] = None
                for w in s["words"]:
                    add_guard(moves[i][mid]["guards"], s["label"], norm(w))
        for m in moves:
            for mid, x in list(m.items()):
                if x["from"] == x["to"] and not any(
                    y["from"] == x["from"] and y["label"] == x["label"] and y["to"] != x["from"]
                    for y in m.values()
                ):
                    del m[mid]
        rid = [{s: f"r{i}s{j}" for j, s in enumerate(sorted(m))} for i, m in enumerate(beside)]
        region_group = [{}, {}]
        for k in nodes:
            p = split(k)
            for i in (0, 1):
                prev = region_group[i].get(p[i])
                region_group[i][p[i]] = group_of(k) if prev is None or prev == group_of(k) else ""
        drawn = [
            [drawn_state(region_group[i][s], region_status[i][s]) for s in m]
            for i, m in enumerate(rid)
        ]
        region_names = getattr(mapping, "region_names", None) or []

        def draw(only):
            out = head([d for ds in drawn for d in ds])
            out.append('  state "At the same time" as regions {')
            count = 0
            for i in (0, 1):
                if i:
                    out.append("    --")
                name = region_names[i] if i < len(region_names) else None
                pad = "      " if name else "    "
                if name:
                    out.append(f'    state "{escape_mermaid_quotes(wrap(name))}" as region{i} {{')
                for s in dict.fromkeys(split(k)[i] for k in starts):
                    out.append(f"{pad}[*] --> {rid[i][s]}")
                for s, sid in rid[i].items():
                    out.append(f'{pad}state "{escape_mermaid_quotes(wrap(s))}" as {sid}')
                shown_moves = sorted(
                    (m for mid, m in moves[i].items() if not only or mid in only[i]),
                    key=lambda m: (locale_key(m["from"]), locale_key(m["label"])),
                )
                for m in shown_moves:
                    every = beside[i][m["from"]]
                    no = sorted(s for s in every if s not in m["beside"])
                    yes = sorted(m["beside"])
                    unless = 0 < len(no) < len(yes)
                    which = None if not no else no if unless else yes
                    worded = guarded(m["guards"], m["label"])
                    text = (
                        worded
                        if worded != m["label"] or not which
                        else f"{m['label']} [{'unless' if unless else 'when'} {' or '.join(which)}]"
                    )
                    out.append(f"{pad}{rid[i][m['from']]} --> {rid[i][m['to']]} : {wrap(text, 30)}")
                    if which:
                        names = ", ".join(rid[1 - i][s] for s in which)
                        out.append(f"{pad}%% when {'not ' if unless else ''}{names}")
                    count += 1
                if name:
                    out.append("    }")
            out.append("  }")
            for i in (0, 1):
                for j, sid in enumerate(rid[i].values()):
                    out.append(f"  class {sid} {drawn[i][j]['cls']}")
            return {"mermaid": "\n".join(out) + "\n", "count": count}

        every_arrow = draw(None)
        differences = compare_charts(parse_mermaid(every_arrow["mermaid"])["regions"], flat)
        if differences:
            n = sum(len(xs) for _, xs in differences)
            return {
                "why": (
                    f"the regions do not combine into the flat chart, with {n} difference(s),"
                    f" such as {differences[0][0]}: {differences[0][1][0]}"
                )
            }
        if all_path:
            with open(all_path, "w", encoding="utf-8") as handle:
                handle.write(every_arrow["mermaid"])

        parts = {bar(split(k)): split(k) for k in nodes}

        def key(source, label, target):
            return f"{source} --> {target} : {label}"

        real = {key(bar(s["from"]), s["label"], bar(s["to"])) for s in steps}
        nxt = {}
        for s in steps:
            nxt.setdefault(bar(s["from"]), []).append(s)
        keep = [set(), set()]

        def moves_of(s):
            return [
                (i, SEP.join([s["from"][i], s["label"], s["to"][i]]))
                for i in (0, 1)
                if s["from"][i] != s["to"][i]
            ]

        def price(s):
            return sum(1 for i, mid in moves_of(s) if mid not in keep[i]) * len(nodes) + 1

        wanted = []

        def want(s):
            wanted.append(s)
            for i, mid in moves_of(s):
                keep[i].add(mid)

        def steps_of(e, said):
            labels = [norm(label) for label in e["labels"]]
            return [
                {"from": split(e["from"]), "to": split(e["to"]), "label": label}
                for label in ([said] if said in labels else labels)
            ]

        for c in classes:
            for step in edges_along(c):
                e = edges.get(step["id"])
                if e:
                    for s in steps_of(e, norm(step["label"])):
                        want(s)
            if diverges(c):
                for s in steps_of(edges[c["second"]["edge"]], ""):
                    want(s)

        def cheapest():
            cost = {bar(split(k)): 0 for k in starts}
            parent = {}
            pending = dict.fromkeys(cost)
            while pending:
                k = None
                for candidate in pending:
                    if k is None or cost[candidate] < cost[k]:
                        k = candidate
                del pending[k]
                for s in nxt.get(k, []):
                    c = cost[k] + price(s)
                    if c < cost.get(bar(s["to"]), math.inf):
                        cost[bar(s["to"])] = c
                        parent[bar(s["to"])] = s
                        pending[bar(s["to"])] = None
            return cost, parent

        # A target is a region state to reach, ("at", region, state), or a label that no wanted
        # step has yet, ("ends", label).
        targets = [
            *(("at", i, r) for i in (0, 1) for r in sorted(beside[i])),
            *(
                ("ends", label)
                for label in sorted(
                    label
                    for label in dict.fromkeys(s["label"] for s in steps)
                    if not any(w["label"] == label for w in wanted)
                )
            ),
        ]
        while targets:
            cost, parent = cheapest()
            best = None
            for n, t in enumerate(targets):
                if t[0] == "at":
                    ways = [
                        {"k": k, "c": cost[k], "last": None} for k in cost if parts[k][t[1]] == t[2]
                    ]
                else:
                    ways = [
                        {"k": bar(s["from"]), "c": cost[bar(s["from"])] + price(s), "last": s}
                        for s in steps
                        if s["label"] == t[1] and bar(s["from"]) in cost
                    ]
                for w in ways:
                    if not best or w["c"] < best["c"]:
                        best = {**w, "n": n}
            if not best:
                break
            del targets[best["n"]]
            path = [best["last"]] if best["last"] else []
            s = parent.get(best["k"])
            while s:
                path.append(s)
                s = parent.get(bar(s["from"]))
            for s in path:
                want(s)

        def takes(x, label):
            return [
                (i, mid)
                for i in (0, 1)
                for mid, m in moves[i].items()
                if m["from"] == x[i] and m["label"] == label and x[1 - i] in m["beside"]
            ]

        while True:
            scoped = draw(keep)
            made = product_of(parse_mermaid(scoped["mermaid"])["regions"])
            made_keys = {key(t["from"], t["label"], t["to"]) for t in made["transitions"]}
            redo = [
                *(
                    (parts[t["from"]], t["label"])
                    for t in made["transitions"]
                    if t["from"] in parts and key(t["from"], t["label"], t["to"]) not in real
                ),
                *(
                    (s["from"], s["label"])
                    for s in wanted
                    if bar(s["from"]) in made["states"]
                    and key(bar(s["from"]), s["label"], bar(s["to"])) not in made_keys
                ),
            ]
            before = len(keep[0]) + len(keep[1])
            for x, label in redo:
                for i, mid in takes(x, label):
                    keep[i].add(mid)
            if len(keep[0]) + len(keep[1]) == before:
                break
        sound = all(s in parts for s in made["states"]) and all(
            key(t["from"], t["label"], t["to"]) in real for t in made["transitions"]
        )
        if not sound:
            scoped = every_arrow

        return {
            "mermaid": scoped["mermaid"],
            "states": [len(beside[0]), len(beside[1])],
            "transitions": scoped["count"],
            "all": every_arrow["count"],
            "flat": {"states": len(nodes), "transitions": len(steps)},
            "status": {
                s: sum(sum(1 for x in m.values() if x == s) for m in region_status) for s in rank
            },
            "groups": group_counts([d for ds in drawn for d in ds]),
        }

    regions = (
        regions_chart(all_nodes, list(initial), edges, classes, args["proof"], args["regionsAll"])
        if args["regions"]
        else None
    )
    if regions and regions.get("why"):
        print(f"regions: not drawn, because {regions['why']}", file=sys.stderr)
    drew_regions = bool(regions and regions.get("mermaid"))

    if args["pathOnly"] and chosen:
        flat_states = dict(on_path)
    elif cover_edges is not None:
        flat_states = dict.fromkeys(
            [*initial, *(k for eid in cover_edges for k in (edges[eid]["from"], edges[eid]["to"]))]
        )
    else:
        flat_states = all_nodes
    ordered = sorted(flat_states)
    drawn = [drawn_state(group_of(k), status(k), k in on_path) for k in ordered]

    boxes = {}
    box_of = {}

    def in_box(k, box):
        boxes.setdefault(box, []).append(k)

    if args["view"] == "layered":
        for k in ordered:
            in_box(k, k.split(SEP)[0])
    elif args["view"] == "customer" and not args["flat"]:
        for k in ordered:
            at = k.find(": ")
            if at > 0 and at + 2 < len(k):
                in_box(k, k[:at])
        for box, members in list(boxes.items()):
            if len(members) < 2:
                del boxes[box]
    box_ids = {box: f"g{i}" for i, box in enumerate(boxes)}
    for box, members in boxes.items():
        for k in members:
            box_of[k] = box
    declared = [
        *(k for members in boxes.values() for k in members),
        *(k for k in ordered if k not in box_of),
    ]
    state_ids = {k: f"s{i}" for i, k in enumerate(declared)}

    def caption(k):
        if args["view"] == "layered":
            return k.split(SEP)[1]
        return k[len(box_of[k]) + 2 :] if k in box_of else k

    def numbered(steps):
        runs = []
        for s in steps:
            last = runs[-1] if runs else None
            if last and last["shown"] == s["shown"] and last["n"][-1] == s["n"] - 1:
                last["n"].append(s["n"])
            else:
                runs.append({"shown": s["shown"], "n": [s["n"]]})
        return [f"{', '.join(str(n) for n in r['n'])}. {r['shown']}" for r in runs]

    drawn_labels = {}
    arrows = {}
    chosen_edge = (
        chosen["second"]["edge"]
        if chosen and chosen.get("second") and "edge" in chosen["second"]
        else None
    )
    for eid, e in edges.items():
        if e["from"] not in flat_states or e["to"] not in flat_states:
            continue
        if args["pathOnly"] and chosen and eid not in path_numbers and eid != chosen_edge:
            continue
        if cover_edges is not None and eid not in cover_edges:
            continue
        pair = edge_id(e["from"], e["to"])
        if pair not in arrows:
            arrows[pair] = {
                "from": e["from"],
                "to": e["to"],
                "groups": [[], [], []],
                "plain": True,
                "labels": [],
            }
        a = arrows[pair]
        numbers, current, other = a["groups"]
        every = list(e["labels"])
        shown = [guarded(e.get("guards"), label) for label in every]
        said = " or ".join(shown) if args["fullLabels"] else join_labels(shown)
        p = path_numbers.get(eid)
        chosen_step = chosen_edge is not None and eid == chosen_edge
        if p:
            numbers += numbered(p)
        elif not e.get("secondOnly"):
            current.append(said)
        else:
            other.append(chosen["second"]["text"] if args["pathOnly"] and chosen_step else said)
        if chosen_step and not e.get("secondOnly"):
            other.append(chosen["second"]["text"])
        if p or chosen_step or eid.endswith(f"{SEP}second"):
            a["plain"] = False
        a["labels"] += every
        for label in [s["label"] for s in p] if p else every:
            drawn_labels[label] = None

    transitions = [
        {
            "from": a["from"],
            "to": a["to"],
            # ";" ends a Mermaid statement, even inside a transition label.
            "text": "<br/>#160;<br/>".join(
                text
                for text in (
                    "<br/>".join(wrap(label.replace(";", ","), 30) for label in g if label)
                    for g in a["groups"]
                )
                if text
            ),
            "plain": a["plain"],
            "labels": sorted(a["labels"]),
        }
        for a in arrows.values()
    ]
    from_box = []
    folded = set()
    for box, members in boxes.items():
        mine = set(members)
        by_step = {}
        for t in transitions:
            if not t["plain"] or t["from"] not in mine or t["to"] in mine:
                continue
            by_step.setdefault(f"{t['to']}{SEP}{t['text']}{SEP}{SEP.join(t['labels'])}", []).append(
                t
            )
        for same in by_step.values():
            if len({t["from"] for t in same}) != len(members):
                continue
            folded.update(id(t) for t in same)
            from_box.append({**same[0], "box": box})

    out = head(drawn)
    for box, members in boxes.items():
        out.append(f'  state "{escape_mermaid_quotes(wrap(box))}" as {box_ids[box]} {{')
        for k in members:
            out.append(f'    state "{escape_mermaid_quotes(wrap(caption(k)))}" as {state_ids[k]}')
        out.append("  }")
    for k in ordered:
        if k not in box_of:
            out.append(f'  state "{escape_mermaid_quotes(wrap(caption(k)))}" as {state_ids[k]}')
    for k in ordered:
        if k in initial and (not args["pathOnly"] or (chosen and k == chosen["path"][0]["key"])):
            out.append(f"  [*] --> {state_ids[k]}")

    def arrow(source, t):
        return f"  {source} --> {state_ids[t['to']]}{' : ' + t['text'] if t['text'] else ''}"

    for t in from_box:
        out.append(arrow(box_ids[t["box"]], t))
    for t in transitions:
        if id(t) not in folded:
            out.append(arrow(state_ids[t["from"]], t))
    for k, d in zip(ordered, drawn, strict=True):
        out.append(f"  class {state_ids[k]} {d['cls']}")
    mermaid = regions["mermaid"] if drew_regions else "\n".join(out) + "\n"
    if args["out"]:
        with open(args["out"], "w", encoding="utf-8") as handle:
            handle.write(mermaid)
    else:
        sys.stdout.write(mermaid)

    def show(k):
        return k.replace(SEP, ": ", 1) if args["view"] == "layered" else k

    def rule_of(c):
        return rules.get(c["invariant"], f"`{c['invariant']}`")

    def second_line(c):
        W = cap(within)
        if c.get("introduced"):
            return f"Only {L} has this bug. The steps above happen {within} {L}."
        s = c["second"]
        if not s:
            return None
        if s.get("sameEnd"):
            if not s["checked"]:
                return (
                    f"{W} {L} you see the same screens and steps, but {L} does not check this rule."
                )
            if s["ruleHolds"]:
                return (
                    f"{W} {L} you see the same screens and steps, yet the rule holds, so the"
                    f" state labels do not show what {L} changes."
                )
            return f"{W} {L} you see the same screens and steps, so {L} does not change this path."
        if s.get("reason"):
            return f"{cap(L)} cannot take these steps: it {s['reason']}."
        outcome = (
            "cannot happen, so you stay at"
            if s.get("disabled")
            else "keeps you at"
            if s["key"] == s["from"]
            else "takes you to"
        )
        if s["hidden"]:
            when = f"after step {s['step']}" if s["step"] else "before your first step"
            return f'{W} {L}, {when}, "{s["said"]}" happens and {outcome}: {show(s["key"])}.'
        return f"{W} {L}, step {s['step']} ({s['said']}) {outcome}: {show(s['key'])}."

    def listed_in(c):
        return [cfg for cfg, rule in args["listed"]["breaks"].items() if rule == c["invariant"]]

    def listed_line(c):
        spec, breaks = args["listed"]["spec"], args["listed"]["breaks"]
        cfgs = listed_in(c)
        if cfgs:
            return (
                f"Listed: {join_and(cfgs)}, {'a config' if len(cfgs) == 1 else 'configs'} of"
                f" {spec},"
                f" expect{'s' if len(cfgs) == 1 else ''} TLC to break this rule."
            )
        others = [f"`{r}`" for r in sorted(set(breaks.values()))]
        expects = (
            f"Its configs expect TLC to break {join_and(others)}."
            if others
            else "None of its configs expects TLC to break a rule."
        )
        return f"Not listed: no config of {spec} expects TLC to break this rule. {expects}"

    if args["story"]:
        lines = []
        header = f"New with {L}: " if role == "fix" else f"Only in {L}: "
        for i, c in enumerate(classes):
            lines += [f"## {i + 1}. {header if c.get('introduced') else ''}{show(c['end'])}", ""]
            lines.append(f"Rule broken: {rule_of(c)}")
            if c["cause"]:
                lines.append(f"Why: {re.sub(r'[.]\Z', '', c['cause'])}.")
            if args["listed"]:
                lines.append(listed_line(c))
            lines += [
                "This is the only way to get here in the model."
                if c["count"] == 1
                else f"There are {c['count']} ways to get here in the model. This is the shortest.",
                "",
            ]
            for j, p in enumerate(c["path"]):
                lines.append(
                    f"0. Start: {show(p['key'])}"
                    if j == 0
                    else f"{j}. {cap(p['label'])}. Now: {show(p['key'])}"
                )
            lines.append("")
            said = second_line(c)
            if said:
                lines += [said, ""]
        with open(args["story"], "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))

    code_like = [
        t
        for t in dict.fromkeys(
            [
                *([*ordered, *drawn_labels] if args["view"] == "customer" else []),
                *(c["cause"] for c in classes if c["cause"]),
            ]
        )
        if CODE_LIKE.search(t)
    ]

    def second_of(c):
        if c.get("introduced"):
            return f"new with {L}" if role == "fix" else f"only in {L}"
        s = c["second"]
        if not s:
            return None
        if s.get("sameEnd"):
            if not s["checked"]:
                return "same screens, rule not checked"
            return "same screens, but the rule holds" if s["ruleHolds"] else "unchanged"
        return s["reason"] if s.get("reason") is not None else show(s["key"])

    summary = {"view": args["view"]}
    if role:
        summary["second"] = {
            "role": role,
            "label": L,
            "lacks": [".".join(p) for p in lacks],
            **({"listed": args["listed"]} if args["listed"] else {}),
        }
    summary["modelStates"] = len(graph["nodes"])
    summary["modelTransitions"] = len(graph["edges"])
    summary["chartStates"] = (
        regions["states"][0] + regions["states"][1] if drew_regions else len(flat_states)
    )
    summary["chartTransitions"] = regions["transitions"] if drew_regions else len(transitions)
    summary["chartStatus"] = (
        regions["status"]
        if drew_regions
        else {s: sum(1 for k in flat_states if status(k) == s) for s in ("works", "wrong", "fixed")}
    )
    if grouping:
        summary["chartGroups"] = regions["groups"] if drew_regions else group_counts(drawn)
        summary["mixedGroups"] = sorted(show(k) for k in mixed_groups)
    if regions:
        summary["regions"] = (
            {
                "drawn": True,
                "states": regions["states"],
                "transitions": regions["transitions"],
                "all": regions["all"],
                "flat": regions["flat"],
            }
            if drew_regions
            else {"drawn": False, "why": regions["why"]}
        )
    summary["classes"] = [
        {
            "n": i + 1,
            "end": show(c["end"]),
            "invariant": c["invariant"],
            "rule": rules.get(c["invariant"]),
            "cause": c["cause"],
            "readerSteps": len(c["path"]) - 1,
            "modelSteps": len(c["trace"]["steps"]),
            "counterexamples": c["count"],
            role or "fix": second_of(c),
            **({"listed": listed_in(c)} if args["listed"] else {}),
        }
        for i, c in enumerate(classes)
    ]
    summary["codeLike"] = code_like
    if args["summary"]:
        with open(args["summary"], "w", encoding="utf-8") as handle:
            handle.write(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    extra_bugs = (
        f", {len(introduced)} {f'new with {L}' if role == 'fix' else f'only in {L}'}"
        if introduced
        else ""
    )
    drawn_as = (
        f" of {regions['all']} in 2 regions (proved against {regions['flat']['states']} states,"
        f" {regions['flat']['transitions']} transitions)"
        if drew_regions
        else ""
    )
    print(
        f"chart: {summary['chartStates']} states, {summary['chartTransitions']}"
        f" transitions{drawn_as}"
        f" from {summary['modelStates']} model states; {len(main_classes)} bug(s){extra_bugs}",
        file=sys.stderr,
    )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = parse_args(argv)
        if args is None:
            print(HELP)
            return 0
        check_args(args)
    except BadArgument as e:
        print(e, file=sys.stderr)
        return 2
    try:
        chart(args)
    except ChartError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
