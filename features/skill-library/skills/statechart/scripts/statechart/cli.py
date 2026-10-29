"""statechart: draws a Mermaid statechart of what an app's user sees, from TLC's state graph of a
TLA+ spec."""

import base64
import errno
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from statechart.lib import (
    BROKEN_PROPERTY,
    PRIMES_OR_UNCHANGED,
    ChartError,
    join_and,
    parse_dot,
    shared_variables,
    tla_variables,
    tlc_output_warning,
    uncited_conditions,
)
from statechart.mapping import load_mapping
from statechart.tools import MERMAID_CLI, TLA2TOOLS_URL, NoTlc, find_tlc, in_test_slot, workers

USAGE = {
    "from-spec": (
        "statechart from-spec SPEC.tla [--config FILE] [--fixed FIXED.tla [--fixed-config FILE]"
        " | --against AGREED.tla [--against-config FILE]] [--label TEXT] [--map FILE]"
        " [--expect-broken RULE]... [--title TEXT] [--out DIR] [--png]"
    ),
    "from-chart": (
        "statechart from-chart CHART.mmd [--module NAME] [--expect-broken RULE]... [--title TEXT]"
        " [--out DIR] [--png]"
    ),
}


def usage(lines):
    return "Usage: " + "\n       ".join(lines)


FROM_SPEC = """from-spec SPEC.tla
  Checks each INVARIANT in SPEC.cfg in a separate TLC run. TLC stops at the first rule that a state
  breaks, and the separate runs find the rest. Each run also has the rule as a CONSTRAINT, so TLC
  stops each path at its first state that breaks the rule, and a rule that stays broken reports
  only the step that broke it. SPEC.cfg has SPECIFICATION and one INVARIANT line per rule. Each
  PROPERTY, a rule about whole behaviors, gets one TLC run too, and the charts do not draw it. A
  rule listed as both INVARIANT and PROPERTY is checked once, as an INVARIANT. One
  more run dumps the state graph, and then the command draws the charts. TLC names each step after
  the innermost named action that takes it, so give each kind of step its own named action. The
  command warns when steps carry the name of the whole next-state action. The command prints the
  config that it checks each model with, and stops when a config does not exist, with the configs
  beside the spec.

  --config FILE      The config for SPEC.tla. Default: SPEC.cfg next to the spec.
  --fixed FIXED.tla  The model of the open fix. It is a copy of the spec with its own file and
                     module name, such as SpecFixed.tla with MODULE SpecFixed. The command checks
                     it the same way, with FIXED.cfg, or with the config of SPEC.tla when there is
                     no FIXED.cfg. The charts then mark each bad state fixed or still wrong.
  --fixed-config FILE
                     The config for FIXED.tla.
  --against AGREED.tla
                     The spec that SPEC.tla must follow, when SPEC.tla models the code. It needs
                     its own file and module name. The command checks it with AGREED.cfg, and
                     never with the config of SPEC.tla. SPEC.tla may add variables, record fields,
                     and actions that AGREED.tla does not have. The comparison leaves them out.
                     Do not use it with --fixed.
  --against-config FILE
                     The config for AGREED.tla, when it is not AGREED.cfg. Give the config that the
                     spec's authors say the unchanged spec passes. A rule that this config does not
                     check is "not checked" in the stories.
  --label TEXT       The name of the --fixed or --against model in the charts and the stories.
                     Default: "the fix", or "the spec".
  --map FILE         The labels for each model state and step, a Python file. Default:
                     SPEC.map.py next to the spec. When the file does not exist, the command writes
                     one from the spec's VARIABLES and actions to fill in, and exits 2 before it
                     runs TLC. Its comments say what each function gets.

  With --fixed or --against, SPEC.tla (and FIXED.tla) models the code, and the command finds each
  condition of an action that no comment ties to code. A comment cites the code by its file and
  the code it quotes in backticks, as in \\* pay.ts `if (sent > 0)`, or by a file and line, as in
  \\* pay.ts:120, but a quote needs no edit when the lines above it move.
  A condition is a conjunct of the action that changes nothing and reads a variable that the
  action does not change. A rule can hold only because the model waits for a condition that the
  code does not check, so the command prints these conditions when a rule holds.
  With --against, each story says whether a config beside AGREED.tla expects TLC to break the
  bug's rule. A config's "\\* expect: RULE" line says what TLC finds, and "\\* module: NAME" names
  the module it checks when the folder has more than one .tla file. The command warns when no
  config beside AGREED.tla has an expect line for that module."""

FROM_CHART = """from-chart CHART.mmd
  Writes NAME.tla, NAME.cfg, and NAME.map.py next to the chart. When NAME.tla already exists, it
  writes none of them. Then it checks the spec as from-spec does, and compares the chart that the
  spec draws with CHART.mmd.

  --module NAME      The TLA+ module name. Default: the chart's file name in CamelCase, such as
                     NotesApp for notes-app.mmd.

  The chart is a Mermaid stateDiagram-v2. Each transition label is one action. For parallel
  regions, split one top-level composite with --, and put each part in a named composite, such as
  state Connection { ... }. Each region is one variable. A step moves every region whose current
  state has a transition with the step's label, and the other regions stay where they are. Each
  rule is one comment line:
    %% never NAME: A & B -- the rule in one sentence
  Each name after the colon is a state caption or a composite, and each comes from a different
  region. A composite stands for every state in it. The command refuses final, choice, fork, and
  history states, and regions below the top level."""

COMMON = f"""Both commands
  --expect-broken RULE
                     An INVARIANT or PROPERTY that is known to break. Repeat it, or list rules
                     with commas, as in A,B. The command then exits 0 when exactly these rules
                     break, and the --fixed or --against model breaks no other rule.
  --title TEXT       The chart title. Each bug chart adds ", bug N".
  --out DIR          The output folder. Default: NAME-statechart next to the input. A run writes its
                     files in a temporary folder, and then replaces the whole output folder with
                     it. When runs overlap, the output folder has the files of the run that
                     finished last. The command does not use an output folder that has files that
                     it did not write. On a filesystem that cannot rename, the command copies the
                     files into place, and overlapping runs can mix their files.
  --png              Also render each chart to PNG with npx {MERMAID_CLI}, a pinned version.
  -h, --help         Print this help, and exit 0.

Output
  The command prints whether each rule holds, the chart's counts, and one story per bug.
  from-chart also prints the comparison. The command writes these files in the output folder:
  chart.mmd          The overview.
  bug-N.mmd          Only the steps of bug N, numbered. Bugs are numbered by fewest reader steps,
                     then fewest model steps, then rule name, then cause. Bugs that only the
                     --fixed or --against model has come last.
  bug-N-developer.mmd, bug-N-layered.mmd
                     The path of bug N through the developer's states, when the mapping defines
                     detail().
  stories.md         One entry per bug: the rule, why it breaks, the shortest path in reader
                     steps, and what the --fixed or --against model does instead.
  summary.json       The counts behind the chart. With --fixed or --against, uncited has the
                     conditions with no cite for each code model. With --against, second.listed
                     has what each config beside AGREED.tla expects, and each bug has the
                     configs that list it.
  tlc/               The config and the TLC output of each run. When the overview has regions,
                     from-spec also writes tlc/regions-all.mmd, the regions with every arrow, and
                     tlc/regions-proof.mmd, every state and step of TLC's graph in one region.
                     compare-charts tlc/regions-all.mmd tlc/regions-proof.mmd repeats the
                     proof.
  *.png              Each chart as a PNG, with --png. A run without --png deletes them.

Reading a chart
  from-spec draws the overview as two parallel regions when every state reads "context: progress":
  the contexts on one side, the progress on the other, both at the same time. It does so only when
  that has fewer states, and when the regions combine back into exactly every state and step of
  TLC's graph. Otherwise it puts the states of one context in a box named context, and prints why.
  Regions draw only the arrows of the shortest way to each state, of each bug path, and of the
  nearest step with each label. The script checks that these arrows make no step that TLC's graph
  does not have.
  An arrow from a box's border leaves from every state in the box.
  In regions, a step leaves every region that has it. "[when A]" or "[unless A]" says which states
  of the other region the step needs. A loop says the region may also stay.
  Other words in [ ] come from the mapping's guard(), and "after N s" from its timer(). TLC does
  not check them, and has no clock, so a reviewer checks them against the code.
  Gray states work. Red states break a rule. With --fixed, red states stay wrong with the fix, and
  green states are fixed by it or exist only with it. With --against, red states break a rule in
  either model, and green states exist only in the spec.
  When the mapping defines group(), the fill is the state's group, which the legend names, and the
  status is a thick red or green border on top. tlc-to-chart --help tells more.
  A state is bad when it breaks a rule, or when every path from the start to it passes a state
  that breaks one. TLC stops each path at the first state that breaks the rule, so a rule that
  stays broken colors only the states where it first breaks and the states after them that no
  path without a bug reaches.
  A thick blue border and numbered labels mark the bug. Mermaid state diagrams cannot color an
  edge.
  A label "with the fix, STEP" or "in the spec, STEP" is a step that only the other model takes. On
  a bug's path it leaves the state before the first step that the other model shows the reader
  differently, and ends where that model goes instead. "with the fix, STEP cannot happen" or "in
  the spec, STEP cannot happen" loops on the state where that model stops the step. Outside
  regions, two states have at most one arrow between them. Its lines are the numbered steps, then
  SPEC.tla's steps, then the other model's steps, with a blank line between each group.
  An edge lists every step that takes it, most common first. Words that the steps share at the
  start are written once, as in "you tap Pay or Back".

Regenerate
  With --expect-broken, one script rebuilds every chart and stops on any change:
    set -e
    statechart from-spec Code.tla --against Agreed.tla --expect-broken NoLostUpload --png

TLC
  TLA2TOOLS is the path to tla2tools.jar. When it is not set, the command uses tla2tools.jar
  of the pinned version in ~/.cache/jstack/tla2tools, and downloads it there from
  {TLA2TOOLS_URL} the first time, checked against its pinned sha256. With STATECHART_OFFLINE set
  it does not download, and says where to get TLC and exits 2. JAVA is the java binary. When it is
  not set, the command uses the Java of the jdk4py package, which uv installs with the command.
  TLC checks each rule with 2 workers, or as many as TLC_WORKERS says. When a rule is broken, TLC
  checks it again with one worker, which finds the shortest bug paths, the same on every run. The
  command then prints how many times TLC ran and how long that took. Where jgauge is on PATH, each
  run of TLC holds one of its test slots, or runs in the slot a suite around it holds already.
  TLC can find that a rule is broken and then fail with a Java exception while it reports the rule.
  The command then keeps the paths that TLC printed, marks the rule broken, and warns that the
  charts can miss states that break it. The failure is in TLC, so do not weaken the rule because of
  it. A smaller constant can let TLC finish.

Exit codes
  0  Every rule holds, or exactly the --expect-broken rules break. from-chart also draws CHART.mmd
     back unchanged.
  1  Another rule is broken, an expected rule holds, or the chart that the spec draws is not
     CHART.mmd. The output says which.
  2  The command cannot finish: a bad argument, a missing file, a chart or TLC output that it
     cannot read, no TLC, a helper script that cannot start, an output folder with files that the
     command did not write, an input file that changed during the run, a new mapping to fill in,
     or a chart that --png cannot render. When a chart does not render, the command keeps the
     files it wrote and exits 2, whatever the rules give. Otherwise, exit 2 does not change the
     output folder, unless the command moved it aside and cannot put it back. Then the message
     names the folder's new path. When TLC stops on an error, the message names TLC's output, in a
     temporary folder that the command keeps. When the command cannot put its files in the output
     folder, it keeps them in a temporary folder, and the message names it. The command checks
     its input files again before --png renders, so a changed input stops the run before that."""

HELP = {
    "": f"""{usage([*USAGE.values(), "statechart [from-spec|from-chart] --help"])}

Draws a Mermaid statechart of what an app's user sees, from TLC's state graph of a TLA+ spec. The
help calls that user the reader.

{FROM_SPEC}

{FROM_CHART}

{COMMON}""",
    "from-spec": f"{usage([USAGE['from-spec']])}\n\n{FROM_SPEC}\n\n{COMMON}",
    "from-chart": f"{usage([USAGE['from-chart']])}\n\n{FROM_CHART}\n\n{COMMON}",
}


def more(cmd=None):
    return (
        f"Run statechart {cmd + ' ' if cmd else ''}--help for the flags, the output, and the"
        " exit codes."
    )


class CannotFinish(Exception):
    pass


class TlcStopped(CannotFinish):
    pass


class NotPublished(CannotFinish):
    pass


FLAGS = {
    "from-spec": [
        "--map",
        "--config",
        "--fixed",
        "--fixed-config",
        "--against",
        "--against-config",
        "--label",
        "--expect-broken",
        "--title",
        "--out",
    ],
    "from-chart": ["--module", "--expect-broken", "--title", "--out"],
}


def parse_args(argv):
    command, rest = (argv[0], argv[1:]) if argv else (None, [])
    if command in ("-h", "--help"):
        return {"help": HELP[""]}
    if command not in FLAGS:
        raise CannotFinish(f"{usage(list(USAGE.values()))}\n{more()}")
    flags = {"expect-broken": {}}
    given = None
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in ("-h", "--help"):
            return {"help": HELP[command]}
        if a == "--png":
            flags["png"] = True
        elif a in FLAGS[command]:
            if i + 1 == len(rest):
                raise CannotFinish(f"{a} needs a value. {more(command)}")
            name = a[2:]
            i += 1
            if isinstance(flags.get(name), dict):
                for v in rest[i].split(","):
                    flags[name][v] = None
            else:
                flags[name] = rest[i]
        elif not a.startswith("-") and given is None:
            given = a
        else:
            raise CannotFinish(f"unknown argument {a}. {more(command)}")
        i += 1
    if given is None:
        raise CannotFinish(f"{usage([USAGE[command]])}\n{more(command)}")
    return {"command": command, "input": given, "flags": flags}


def rel(file):
    r = os.path.relpath(file) if file else "."
    return os.path.abspath(file) if r == ".." or r.startswith(f"..{os.sep}") else r


def cfg_of(spec):
    return re.sub(r"\.tla$", ".cfg", spec)


def find_tools():
    try:
        workers()
        return find_tlc()
    except NoTlc as e:
        raise CannotFinish(str(e)) from e


def script(module, script_args, about, ok_exits=(0,)):
    """Runs one of the helper commands of this package in its own process, as pstack's scripts
    run each other, so that each keeps its own exit codes."""
    name = module.replace("_", "-")
    try:
        r = subprocess.run(
            [sys.executable, "-m", f"statechart.{module}", *script_args],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PYTHONPATH": os.pathsep.join(
                    filter(None, [PACKAGE_ROOT, os.environ.get("PYTHONPATH")])
                ),
            },
        )
    except OSError as e:
        raise CannotFinish(f"cannot run {name}: {e.strerror or e}") from e
    if r.returncode in ok_exits:
        return r
    thrown = re.search(r"^Error: (.*)$", r.stderr, re.M)
    if thrown:
        raise CannotFinish(f"{rel(about)}: {thrown.group(1)}")
    raise CannotFinish(r.stderr.strip() or f"{name} exited {r.returncode}")


PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYWORD = re.compile(
    r"^(SPECIFICATION|INIT|NEXT|CONSTANTS?|INVARIANTS?|PROPERTY|PROPERTIES|SYMMETRY|VIEW"
    r"|CONSTRAINTS?|ACTION_CONSTRAINTS?|CHECK_DEADLOCK|POSTCONDITION|ALIAS)$"
)


def split_rules(cfg):
    text = re.sub(r"\(\*[\s\S]*?\*\)", " ", cfg)
    text = re.sub(r"\\\*.*", " ", text)
    words = [w for w in re.split(r"\s+", text) if w]
    kept = []
    rules = []
    properties = []
    section = ""
    for w in words:
        if KEYWORD.match(w):
            section = w
        if re.match(r"^INVARIANTS?$", section):
            listed = rules
        elif re.match(r"^PROPERT(Y|IES)$", section):
            listed = properties
        else:
            listed = None
        if listed is None:
            kept.append(f"\n{w}" if KEYWORD.match(w) and kept else w)
        elif w != section and w not in listed:
            listed.append(w)
    # TLC takes only a state predicate as an INVARIANT, and checks a state predicate given as a
    # PROPERTY only in the initial states, which the INVARIANT run checks too.
    return {
        "cfgWithoutRules": f"{' '.join(kept)}\n",
        "rules": rules,
        "properties": [p for p in properties if p not in rules],
    }


def run_tlc(tools, spec, cfg, base, dump=None, workers="1"):
    with open(f"{base}.cfg", "w", encoding="utf-8") as handle:
        handle.write(cfg)
    metadir = tempfile.mkdtemp(prefix="tlc-")
    # TLC writes the standard modules, such as Naturals.tla, to java.io.tmpdir under fixed names,
    # so runs that share that folder can read a module while another run rewrites it.
    java_tmp = os.path.join(metadir, "tmp")
    os.mkdir(java_tmp)
    # -deadlock: a UI at rest has nothing left to do, which TLC would report as a deadlock.
    command = [
        tools.java,
        "-XX:+UseParallelGC",
        f"-Djava.io.tmpdir={java_tmp}",
        "-cp",
        tools.jar,
        "tlc2.TLC",
        "-workers",
        workers,
        "-metadir",
        metadir,
        "-deadlock",
        "-continue",
        *(["-dump", "dot,actionlabels", os.path.abspath(dump)] if dump else []),
        "-config",
        os.path.abspath(f"{base}.cfg"),
        os.path.basename(spec),
    ]
    try:
        r = subprocess.run(
            in_test_slot(command),
            cwd=os.path.dirname(os.path.abspath(spec)),
            capture_output=True,
            text=True,
        )
    except OSError as e:
        raise CannotFinish(f"cannot run TLC: {e.strerror or e}") from e
    finally:
        shutil.rmtree(metadir, ignore_errors=True)
    # jgauge, which holds the slot, says so when Java cannot start, as the OSError above does.
    could_not_start = re.search(rf"^test-slot: {re.escape(tools.java)}: (.*)$", r.stderr, re.M)
    if r.returncode in (126, 127) and could_not_start:
        raise CannotFinish(f"cannot run TLC: {could_not_start[1]}")
    with open(f"{base}.out", "w", encoding="utf-8") as handle:
        handle.write(r.stdout)
    try:
        return {"stdout": r.stdout, "warning": tlc_output_warning(r.stdout, f"{base}.out")}
    except ChartError as e:
        raise TlcStopped(str(e)) from e


def without_comments(spec):
    with open(spec, encoding="utf-8") as handle:
        text = handle.read()
    text = re.sub(r"\(\*[\s\S]*?\*\)", " ", text)
    return re.sub(r"\\\*.*", " ", text)


def warn_unnamed_steps(spec, cfg, dot):
    text = without_comments(spec)
    spec_name = re.search(r"^SPECIFICATION\s+(\w+)", cfg, re.M | re.A)
    spec_body = (
        re.search(rf"^{spec_name.group(1)}\s*==(.*(\n[ \t]+.*)*)", text, re.M)
        if spec_name
        else None
    )
    named = re.search(r"^NEXT\s+(\w+)", cfg, re.M | re.A)
    if named:
        nxt = named.group(1)
    else:
        found = re.search(
            r"\[\]\s*\[\s*(\w+)\s*\]_", spec_body.group(1) if spec_body else text, re.A
        )
        nxt = found.group(1) if found else None
    with open(dot, encoding="utf-8") as handle:
        graph = parse_dot(handle.read())
    unnamed = sum(1 for e in [*graph["edges"], *graph["loops"]] if e["action"] == nxt)
    if unnamed > 0:
        print(
            f"{rel(spec)}: {unnamed} {'step has' if unnamed == 1 else 'steps have'} the name {nxt},"
            " the whole next-state action, because TLC names a step after the innermost named"
            " action"
            " that takes it. If the reader must tell these steps apart, give each part of"
            f" {nxt} its own name, as in Pay == ... and {nxt} == Pay \\/ Charge.",
            file=sys.stderr,
        )


def read_model(spec, cfg_file, flag):
    if not os.path.exists(spec):
        raise CannotFinish(f"{rel(spec)} does not exist")
    if not os.path.exists(cfg_file):
        beside = sorted(f for f in os.listdir(os.path.dirname(spec) or ".") if f.endswith(".cfg"))
        hint = (
            f"The configs beside it: {', '.join(beside)}."
            if beside
            else "A config has SPECIFICATION and one INVARIANT line per rule."
        )
        raise CannotFinish(
            f"{rel(cfg_file)} does not exist. Pass {flag} with the config to check"
            f" {os.path.basename(spec)} with. {hint}"
        )
    with open(cfg_file, encoding="utf-8") as handle:
        return {"spec": spec, "cfgFile": cfg_file, **split_rules(handle.read())}


def read_input(spec, cfg_file, expected):
    model = read_model(spec, cfg_file, "--config")
    names = [*model["rules"], *model["properties"]]
    unknown = [r for r in expected if r not in names]
    if unknown:
        raise CannotFinish(
            f"--expect-broken {', '.join(unknown)}: not a rule in {rel(model['cfgFile'])}, whose"
            f" rules are {', '.join(names) or 'none'}."
        )
    return model


def check(tools, model, work, out, expected):
    spec, cfg_file = model["spec"], model["cfgFile"]
    cfg_without_rules, rules, properties = (
        model["cfgWithoutRules"],
        model["rules"],
        model["properties"],
    )
    started = time.monotonic()
    runs = 0

    def run(cfg, file, **options):
        nonlocal runs
        runs += 1
        return run_tlc(tools, spec, cfg, file, **options)

    name = re.sub(r"\.tla$", "", os.path.basename(spec))
    tlc_dir = os.path.join(work, "tlc")
    dot = os.path.join(tlc_dir, f"{name}.dot")
    # One worker writes the graph in a fixed order, which breaks ties between equally short paths.
    run(cfg_without_rules, os.path.join(tlc_dir, name), dump=dot)
    warn_unnamed_steps(spec, cfg_without_rules, dot)
    print(f"TLC on {os.path.basename(spec)} with {rel(cfg_file)}:")
    if not rules:
        what = "the chart marks no state broken" if properties else "no rule is checked"
        print(f"  {os.path.basename(cfg_file)} has no INVARIANT, so {what}.")

    def said(rule, broken):
        if not broken:
            return f"  {rule} holds."
        return f"  {rule} {'is broken (expected)' if rule in expected else 'is broken'}."

    def shown(file):
        return rel(os.path.join(out, "tlc", os.path.basename(file)))

    traces = []
    for rule in rules:
        file = os.path.join(tlc_dir, f"{name}-{rule}")
        cfg = f"{cfg_without_rules}INVARIANT {rule}\nCONSTRAINT {rule}\n"
        result = run(cfg, file, workers=workers())
        # Several workers can reach a bad state by a longer path first. One worker searches breadth
        # first in a fixed order, so the chart's bug paths are the shortest, and the same every run.
        if re.search(r"^Error: Invariant ", result["stdout"], re.M):
            result = run(cfg, file)
        broken = bool(re.search(r"^Error: Invariant ", result["stdout"], re.M))
        print(said(rule, broken))
        if result["warning"]:
            print(f"{shown(f'{file}.out')}: {result['warning']}", file=sys.stderr)
        traces.append({"file": f"{file}.out", "rule": rule, "broken": broken})
    temporal = []
    for prop in properties:
        file = os.path.join(tlc_dir, f"{name}-{prop}")
        stdout = run(f"{cfg_without_rules}PROPERTY {prop}\n", file, workers=workers())["stdout"]
        broken = bool(BROKEN_PROPERTY.search(stdout))
        read = (
            " The chart draws only INVARIANT rules, so read TLC's counterexample in"
            f" {shown(f'{file}.out')}."
            if broken
            else ""
        )
        print(f"{said(prop, broken)}{read}")
        temporal.append({"file": f"{file}.out", "rule": prop, "broken": broken})
    seconds = f"{time.monotonic() - started:.1f}"
    print(f"  TLC ran {runs} {'time' if runs == 1 else 'times'} in {seconds} s.")
    broken = any(t["broken"] for t in [*traces, *temporal])
    return {"spec": spec, "dot": dot, "traces": traces, "properties": temporal, "broken": broken}


def rules_as_expected(now, other, expected):
    def broken_in(m):
        if not m:
            return []
        return [t["rule"] for t in [*m["traces"], *m["properties"]] if t["broken"]]

    if not expected:
        return not now["broken"] and not (other and other["broken"])
    unexpected = [
        r for r in dict.fromkeys([*broken_in(now), *broken_in(other)]) if r not in expected
    ]
    holds = [r for r in expected if r not in broken_in(now)]
    if unexpected:
        print(f"\nBroken but not expected: {', '.join(unexpected)}.")
    if holds:
        print(f"\nExpected to break but holds: {', '.join(holds)}.")
    if not unexpected and not holds:
        print(f"\nBroken as expected: {', '.join(expected)}.")
    return not unexpected and not holds


def scaffold(name, spec):
    text = without_comments(spec)
    variables = [*tla_variables(text), *shared_variables(spec)]
    # A definition that only another action calls is listed too, though TLC names no step after it.
    actions = sorted(
        {
            m.group(1)
            for d in re.split(r"\n(?=\S)", text)
            if (m := re.match(r"(\w+)\s*(?:\([^)]*\))?\s*==([\s\S]*)", d, re.A))
            and PRIMES_OR_UNCHANGED.search(m.group(2))
        }
    )
    steps = "\n".join(f"    {json.dumps(a)}: {json.dumps(a)}," for a in actions)
    return f"""# Chart labels for {name}, for statechart.
# Write labels in plain words, not variable or action names.
# v, before, and after map each variable to its value.
# Strings, numbers, and booleans keep their kind.
# Sequences, tuples, and sets become lists, indexed from 0. Records and functions become dicts.
# Variables: {", ".join(variables)}.
# Each function may take fewer arguments than it is given, and gets only the first ones.
import json

# The actions the reader takes. facts.settled is True when only these are enabled, and the overview
# keeps the shortest path to each settled state, plus every bug path.
reader_actions = []


# The label for one model state. facts.enabled is the set of actions the state enables,
# including steps that change no variable. Write it as "context: progress", such as
# "Offline: upload queued": the chart puts the states of one context in one box.
# Do not claim a result that a pending step can still change, such as "upload failed" while a
# retry is still queued.
def state(v, facts):
    return json.dumps(v, separators=(",", ":"))


# The names of the two parallel regions, when the overview draws them: contexts, then progress.
# region_names = ["Network", "What happened to the file"]

# The group of one model state, in words the reader sees, such as "Upload done". The chart fills
# the states of one group with one color, and the legend names the groups. TLC still decides
# which states break a rule, and draws them with a thick red border on top of the group color.
# group_colors gives a group a light color. Groups without one take a palette color.
# def group(v, facts): ...
# group_colors = {{"Upload done": "#d1f2eb"}}

# The label for one step. A step that leaves the reader in the same state is not drawn,
# unless the reader takes it on a bug path. "" draws no label, and a numbered bug step shows the
# action.
STEPS = {{
{steps}
}}


def step(action, before, after):
    return STEPS.get(action, action)


# When the step can happen, in plain words, such as "offline or disk full". The chart shows
# "step [words]". "" adds nothing.
# def guard(action, before, after): ...

# For a timer step, how many seconds the code waits, from the constant in the code. The chart
# shows "after N s, step". Return None for other steps.
# def timer(action, before, after): ...

# Why a bad state is bad, in words a product manager reads, such as "the laptop went offline, and
# the app drops an upload it cannot send". No variable, function, or event names.
# Counterexamples that break one rule with one cause are one bug, so two bugs that end on the
# same screen stay apart only if their causes differ. Return None to group by the end state.
# def cause(v, facts, invariant): ...

# The developer's words for one model state. With it, each bug is also drawn through these states.
# def detail(v, facts): ...

# The legend's words for each status, in place of the defaults. Group entries keep their names.
# legend = {{"works": "Works on main", "wrong": "Wrong on main", "fixed": "Fixed in the open PR"}}
"""


def published(work, out):
    return lambda file: rel(os.path.join(out, os.path.relpath(file, work)))


def draw(now, map_file, work, out, title, other=None, uncited=None, comparing=False):
    shown = published(work, out)
    mapping = load_mapping(map_file)
    source = ["--dot", now["dot"], "--map", map_file, "--spec", now["spec"]]
    for t in now["traces"]:
        source += ["--traces", t["file"]]
    if other:
        source += [f"--{other['role']}-dot", other["dot"], "--spec", other["spec"]]
        for t in other["traces"]:
            source += [f"--{other['role']}-traces", t["file"]]
        if other["traces"]:
            source += [f"--{other['role']}-rules", ",".join(t["rule"] for t in other["traces"])]
        if other.get("label") is not None:
            source += ["--label", other["label"]]
        if other.get("listed"):
            source += ["--listed", json.dumps(other["listed"], separators=(",", ":"))]
    if comparing:
        source += ["--full-labels", "--flat"]
    elif getattr(mapping, "reader_actions", None):
        source.append("--cover")

    def titled(suffix):
        return ["--title", f"{title}{suffix}"] if title else []

    files = {
        "overview": os.path.join(work, "chart.mmd"),
        "stories": os.path.join(work, "stories.md"),
        "summary": os.path.join(work, "summary.json"),
    }
    proof = os.path.join(work, "tlc", "regions-proof.mmd")
    every_arrow = os.path.join(work, "tlc", "regions-all.mmd")
    script(
        "tlc_to_chart",
        [
            *source,
            *([] if comparing else ["--regions", "--proof", proof, "--regions-all", every_arrow]),
            *titled(""),
            "--highlight",
            "0",
            "--out",
            files["overview"],
            "--story",
            files["stories"],
            "--summary",
            files["summary"],
        ],
        map_file,
    )
    with open(files["summary"], encoding="utf-8") as handle:
        summary = json.load(handle)
    if uncited:
        with open(files["summary"], "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps({**summary, "uncited": uncited}, indent=2, ensure_ascii=False) + "\n"
            )
    charts = [files["overview"]]
    for c in summary["classes"]:
        views = (
            ["", "-developer", "-layered"] if callable(getattr(mapping, "detail", None)) else [""]
        )
        for view in views:
            file = os.path.join(work, f"bug-{c['n']}{view}.mmd")
            shape = [*(["--view", view[1:]] if view else []), "--path-only"]
            script(
                "tlc_to_chart",
                [
                    *source,
                    *shape,
                    *titled(f", bug {c['n']}"),
                    "--highlight",
                    str(c["n"]),
                    "--out",
                    file,
                ],
                map_file,
            )
            charts.append(file)

    status = summary["chartStatus"]
    works, wrong, fixed_count = status["works"], status["wrong"], status["fixed"]
    L = (summary.get("second") or {}).get("label")
    print(
        f"\nChart: {summary['chartStates']} states and {summary['chartTransitions']} transitions"
        f" from {summary['modelStates']} model states."
    )
    r = summary.get("regions")
    if r and r.get("drawn"):
        print(
            f"It has 2 parallel regions, of {r['states'][0]} and {r['states'][1]} states. Proof:"
            " their"
            f" {r['all']} arrows together make exactly the {r['flat']['states']} states and"
            f" {r['flat']['transitions']} labeled steps of {shown(proof)}, and the"
            f" {r['transitions']} drawn arrows make only steps among them. {shown(every_arrow)} has"
            f" all {r['all']} arrows."
        )
    elif r:
        print(f"It has no parallel regions, because {r['why']}.")
    breaks = f"{wrong} {'breaks' if wrong == 1 else 'break'} a rule"
    role = other["role"] if other else None
    if role == "fixed":
        print(
            f"{works} work today, {wrong} still wrong with {L}, {fixed_count} fixed or new with"
            f" {L}.\n"
        )
    elif role == "against":
        print(f"{works} work, {breaks}, {fixed_count} only in {L}.\n")
    else:
        print(f"{works} work, {breaks}.\n")
    if summary["codeLike"]:
        listed = "\n".join(f"  {t}" for t in summary["codeLike"])
        print(
            "These labels or causes read like code. Write them in the reader's words in"
            f" {rel(map_file)}:\n{listed}\n"
        )
    if summary["classes"]:
        with open(files["stories"], encoding="utf-8") as handle:
            print(handle.read().rstrip())
    else:
        print("No state breaks a rule.")
    return {"files": files, "charts": charts}


def render(charts, shown):
    pngs = []
    for chart in charts:
        png = re.sub(r"\.mmd$", ".png", chart)
        try:
            r = subprocess.run(
                ["npx", "-y", MERMAID_CLI, "-i", chart, "-o", png, "-s", "2"],
                capture_output=True,
                text=True,
            )
            ok, said = r.returncode == 0, r.stderr
        except OSError as e:
            ok, said = False, e.strerror or str(e)
        if ok:
            pngs.append(png)
        else:
            print(f"could not render {shown(chart)}: {said.strip()}", file=sys.stderr)
    return pngs


def finish(work, out, inputs, drawn, ok, png):
    unchanged(inputs, out)
    pngs = render(drawn["charts"], published(work, out)) if png else []
    publish(work, out, inputs)
    written = ", ".join(
        os.path.basename(f)
        for f in [*drawn["charts"], *pngs, drawn["files"]["stories"], drawn["files"]["summary"]]
    )
    print(f"\nWrote {written} in {rel(out)}.")
    if png and len(pngs) < len(drawn["charts"]):
        return 2
    return 0 if ok else 1


OWN = re.compile(
    r"^((chart|bug-\d+(-developer|-layered)?)\.(mmd|png)|stories\.md|summary\.json|tlc|\.DS_Store)$"
)


def foreign(directory):
    try:
        return sorted(f for f in os.listdir(directory) if not OWN.match(f))
    except FileNotFoundError:
        return []
    except OSError as e:
        raise CannotFinish(
            f"cannot use {rel(directory)} as the output folder: {e.strerror or e}"
        ) from e


def refuse_foreign(out, files=None):
    files = foreign(out) if files is None else files
    if files:
        first, others = files[0], files[1:]
        what = (
            f"{len(others) + 1} files that this command did not write, such as {first}"
            if others
            else f"a file that this command did not write: {first}"
        )
        raise CannotFinish(
            f"{rel(out)} has {what}. A run puts its files in place of the whole output folder, so"
            " pass --out with a new folder."
        )


def out_dir(flagged, given, name):
    out = (
        flagged
        if flagged is not None
        else os.path.join(os.path.dirname(given), f"{name}-statechart")
    )
    refuse_foreign(out)
    return out


def fingerprint(file):
    try:
        st = os.stat(file)
        with open(file, "rb") as handle:
            return f"{st.st_ino} {st.st_ctime_ns} {base64.b64encode(handle.read()).decode()}"
    except OSError:
        return None


def snapshot(files, inputs=None):
    inputs = {} if inputs is None else inputs
    for f in files:
        if f and f not in inputs:
            inputs[f] = fingerprint(f)
    return inputs


def in_work_folder(body):
    work = tempfile.mkdtemp(prefix="statechart-")
    os.mkdir(os.path.join(work, "tlc"))
    keep = False
    try:
        return body(work)
    except NotPublished as e:
        keep = True
        raise NotPublished(f"{e} The files that this run wrote are in {rel(work)}.") from e
    except TlcStopped:
        keep = True
        raise
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)


def moved(source, target, *missed):
    """Renames `source` to `target`. False when the rename fails with one of `missed`. Some
    filesystems, such as FUSE mounts, cannot rename a folder that has files. They fail with
    ENOSYS, or with EISDIR when the target exists, and then the folder is copied."""
    missed_codes = {getattr(errno, name) for name in missed}
    try:
        os.rename(source, target)
        return True
    except OSError as e:
        if e.errno in missed_codes:
            return False
        if e.errno not in (errno.ENOSYS, errno.EXDEV, errno.EISDIR):
            raise
    if not os.path.exists(source) and "ENOENT" in missed:
        return False
    if os.path.exists(target):
        if os.listdir(target) and "ENOTEMPTY" in missed:
            return False
        os.rmdir(target)
    try:
        shutil.copytree(source, target)
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    shutil.rmtree(source, ignore_errors=True)
    return True


def unchanged(inputs, out):
    for f, was in inputs.items():
        if fingerprint(f) != was:
            raise NotPublished(
                f"{rel(f)} changed while this run read it, so the run left {rel(out)} as it was."
                " Run the command again."
            )


def publish(work, out, inputs):
    parent = os.path.dirname(os.path.abspath(out))
    os.makedirs(parent, exist_ok=True)
    nxt = tempfile.mkdtemp(prefix=f".{os.path.basename(os.path.abspath(out))}-", dir=parent)
    old = f"{nxt}-old"
    aside = False
    try:
        shutil.copytree(work, nxt, dirs_exist_ok=True)
        unchanged(inputs, out)
        refuse_foreign(out)
        while not moved(nxt, out, "ENOTEMPTY", "EEXIST"):
            if aside:
                refuse_foreign(out)
                shutil.rmtree(old, ignore_errors=True)
                aside = False
            aside = moved(out, old, "ENOENT")
            if aside:
                refuse_foreign(out, foreign(old))
    except Exception as e:
        back = not aside or put_back(old, out)
        shutil.rmtree(nxt, ignore_errors=True)
        detail = e.strerror if isinstance(e, OSError) and e.strerror else str(e)
        why = str(e) if isinstance(e, CannotFinish) else f"cannot replace {rel(out)}: {detail}."
        if not back:
            raise NotPublished(
                f"{why} This run moved the previous {rel(out)} to {rel(old)} and could not put it"
                " back."
            ) from e
        raise NotPublished(
            why if isinstance(e, CannotFinish) else f"{why} The run left {rel(out)} as it was."
        ) from e
    if aside:
        shutil.rmtree(old, ignore_errors=True)


def put_back(old, out):
    try:
        return moved(old, out, "ENOTEMPTY", "EEXIST")
    except OSError:
        return False


def second_cfg(cfg, flags):
    if flags.get("fixed-config") and not flags.get("fixed"):
        raise CannotFinish(f"--fixed-config needs --fixed. {more('from-spec')}")
    if flags.get("against-config") and not flags.get("against"):
        raise CannotFinish(f"--against-config needs --against. {more('from-spec')}")
    if flags.get("fixed"):
        if flags.get("fixed-config"):
            return flags["fixed-config"]
        return cfg_of(flags["fixed"]) if os.path.exists(cfg_of(flags["fixed"])) else cfg
    if flags.get("against"):
        return flags.get("against-config") or cfg_of(flags["against"])
    return None


def second_model(given, cfg, flags):
    fixed, against, label = flags.get("fixed"), flags.get("against"), flags.get("label")
    if fixed and against:
        raise CannotFinish(f"use --fixed or --against, not both. {more('from-spec')}")
    if not fixed and not against:
        if label is None:
            return None
        raise CannotFinish(
            "--label names the --fixed or --against model; it needs one of them."
            f" {more('from-spec')}"
        )
    role, spec = ("fixed", fixed) if fixed else ("against", against)
    name = re.sub(r"\.tla$", "", os.path.basename(given))
    if re.sub(r"\.tla$", "", os.path.basename(spec)) == name:
        raise CannotFinish(
            f"{rel(spec)} needs its own file and module name, such as"
            f" {name}{'Fixed' if fixed else 'Agreed'}.tla."
        )
    return {"role": role, "label": label, "model": read_model(spec, cfg, f"--{role}-config")}


def warn_unchecked(now, other):
    unchecked = [r for r in now["rules"] if r not in other["rules"]]
    if unchecked:
        print(
            f"{rel(other['cfgFile'])} does not check {', '.join(unchecked)}, so the stories cannot"
            " say"
            f" whether {os.path.basename(other['spec'])} keeps"
            f" {'it' if len(unchecked) == 1 else 'them'}.",
            file=sys.stderr,
        )


def listed_breaks(spec):
    directory = os.path.dirname(spec) or "."
    files = sorted(os.listdir(directory))
    modules = [f for f in files if f.endswith(".tla") and "_TTrace_" not in f]
    only = re.sub(r"\.tla$", "", modules[0]) if len(modules) == 1 else None
    breaks = {}
    headed = False
    for f in (f for f in files if f.endswith(".cfg")):
        with open(os.path.join(directory, f), encoding="utf-8") as handle:
            cfg = handle.read()
        m = re.search(r"^\\\* module:[ \t]*(\w+)[ \t]*$", cfg, re.M | re.A)
        module = m.group(1) if m else only
        e = re.search(r"^\\\* expect:[ \t]*(\w+)[ \t]*$", cfg, re.M | re.A)
        expect = e.group(1) if e else None
        if module != re.sub(r"\.tla$", "", os.path.basename(spec)) or not expect:
            continue
        headed = True
        if not re.match(r"^(pass|deadlock)$|^error", expect):
            breaks[f] = expect
    return {"spec": os.path.basename(spec), "breaks": breaks} if headed else None


def warn_unlisted(now, other):
    if other.get("listed") or not any(t["broken"] for t in now["traces"]):
        return
    module = re.sub(r"\.tla$", "", os.path.basename(other["spec"]))
    print(
        f'No config beside {rel(other["spec"])} has an "\\* expect:" line for {module}, so the'
        " stories"
        f" cannot say whether {module} already lists each bug. When"
        f" {os.path.basename(other['spec'])}"
        " is a copy, pass the spec in its own folder.",
        file=sys.stderr,
    )


def warn_uncited(models):
    found_by_spec = {}
    for m in models:
        spec = m["spec"]
        with open(spec, encoding="utf-8") as handle:
            found = uncited_conditions(handle.read(), shared_variables(spec))
        held = [t["rule"] for t in [*m["traces"], *m["properties"]] if not t["broken"]]

        def short(s):
            return f"{s[:87]}..." if len(s) > 90 else s

        if found and held:
            listed = "\n".join(
                f"  {rel(spec)}:{c['line']} {c['action']}: {short(c['condition'])}" for c in found
            )
            print(
                f"{rel(spec)}: {join_and(held)} {'holds' if len(held) == 1 else 'hold'}, but a rule"
                " can"
                " also hold because the model waits for a condition that the code does not check."
                " No"
                " comment gives the file and line of the code that checks"
                f" {'this condition' if len(found) == 1 else 'these conditions'}:\n{listed}\nPut"
                " that"
                " file and line in a comment on each condition, as in \\* pay.ts:120, or remove the"
                " condition when no code checks it.",
                file=sys.stderr,
            )
        found_by_spec[os.path.basename(spec)] = found
    return found_by_spec


def from_spec(given, flags):
    expected = list(flags.pop("expect-broken"))
    name = re.sub(r"\.tla$", "", os.path.basename(given))
    map_file = flags.get("map") or os.path.join(os.path.dirname(given), f"{name}.map.py")
    cfg = flags.get("config") or cfg_of(given)
    other_cfg = second_cfg(cfg, flags)
    inputs = snapshot([given, cfg, map_file, flags.get("fixed") or flags.get("against"), other_cfg])
    second = second_model(given, other_cfg, flags)
    model = read_input(given, cfg, expected)
    out = out_dir(flags.get("out"), given, name)
    if not os.path.exists(map_file):
        with open(map_file, "w", encoding="utf-8") as handle:
            handle.write(scaffold(name, given))
        raise CannotFinish(
            f"Wrote {rel(map_file)}. Fill in its labels, then run this command again."
        )
    tools = find_tools()

    def body(work):
        now = check(tools, model, work, out, expected)
        other = None
        if second:
            other = {
                "role": second["role"],
                "label": second["label"],
                "listed": listed_breaks(second["model"]["spec"])
                if second["role"] == "against"
                else None,
                **check(tools, second["model"], work, out, expected),
            }
        uncited = None
        if second:
            warn_unchecked(model, second["model"])
            if second["role"] == "against":
                warn_unlisted(now, other)
            uncited = warn_uncited([now, other] if second["role"] == "fixed" else [now])
        drawn = draw(now, map_file, work, out, flags.get("title"), other=other, uncited=uncited)
        return finish(
            work, out, inputs, drawn, rules_as_expected(now, other, expected), flags.get("png")
        )

    return in_work_folder(body)


def from_chart(given, flags):
    expected = list(flags.pop("expect-broken"))
    stem = os.path.splitext(os.path.basename(given))[0]
    name = flags.get("module") or re.sub(
        r"(^|[^A-Za-z0-9]+)([A-Za-z0-9])", lambda m: m.group(2).upper(), stem
    )
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
        raise CannotFinish(f"cannot make a TLA+ module name from {given}; add --module NAME")
    spec = os.path.join(os.path.dirname(given), f"{name}.tla")
    map_file = re.sub(r"\.tla$", ".map.py", spec)
    inputs = snapshot([given])
    if os.path.exists(spec):
        print(f"Kept {rel(spec)}. Delete it to write the spec again from {rel(given)}.")
    else:
        script("chart_to_tla", [given, "--module", name], given)
        print(f"Wrote {name}.tla, {name}.cfg, and {name}.map.py from {rel(given)}.")
    snapshot([spec, cfg_of(spec), map_file], inputs)
    tools = find_tools()
    model = read_input(spec, cfg_of(spec), expected)
    out = out_dir(flags.get("out"), given, name)

    def body(work):
        now = check(tools, model, work, out, expected)
        drawn = draw(now, map_file, work, out, flags.get("title"), comparing=True)
        compared = script(
            "compare_charts", [given, drawn["files"]["overview"]], given, ok_exits=(0, 1)
        )
        if compared.returncode == 0:
            print(f"\nThe spec draws {rel(given)} back unchanged.")
        else:
            indented = re.sub(r"^", "  ", compared.stdout.rstrip(), flags=re.M)
            print(f"\nThe spec does not draw {rel(given)}:\n{indented}")
        ok = rules_as_expected(now, None, expected) and compared.returncode == 0
        return finish(work, out, inputs, drawn, ok, flags.get("png"))

    return in_work_folder(body)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        parsed = parse_args(argv)
        if "help" in parsed:
            print(parsed["help"])
            return 0
        run = from_spec if parsed["command"] == "from-spec" else from_chart
        status = run(parsed["input"], parsed["flags"])
        sys.stdout.flush()
        return status
    except CannotFinish as e:
        sys.stdout.flush()
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
