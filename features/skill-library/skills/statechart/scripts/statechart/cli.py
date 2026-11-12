"""statechart: draws a Mermaid statechart of what an app's user sees, from TLC's state graph of a
TLA+ spec."""

import base64
import contextlib
import errno
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from statechart import excalidraw
from statechart.lib import (
    BROKEN_PROPERTY,
    FIRST_ONLY,
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
        " | --against AGREED.tla [--against-config FILE]]"
        " [--also-config FILE | --count-config FILE] [--label TEXT] [--map FILE]"
        " [--expect-broken RULE]... [--title TEXT] [--out DIR] [--png] [--keep-work]"
    ),
    "from-chart": (
        "statechart from-chart CHART.mmd [--module NAME] [--expect-broken RULE]... [--title TEXT]"
        " [--out DIR] [--png] [--keep-work]"
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
  --also-config FILE A config of SPEC.tla that TLC checks at other bounds than --config, where
                     drawing it costs too much: two configs of which neither holds the other.
                     The command dumps its state graph too, labels it with the same mapping, and
                     states.tsv and arrows.tsv count what it reaches beside what the chart's
                     config does. summary.json's also counts the chart states and the arrows only
                     it reaches. The chart draws none of them.
  --count-config FILE
                     A config of SPEC.tla that TLC checks at other bounds than --config, where
                     even labelling its states costs too much. TLC counts its states, with no
                     dump, and summary.json's checked names the config and its count, so the
                     chart's tab says what the tables leave out. Not with --also-config.
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
  --keep-work        Keep the temporary folder that the run writes its files and TLC's output in,
                     and print its path, for a look at what TLC did. Without it, the command
                     removes that folder when it ends: when it finishes, when it stops on an error,
                     and when it is interrupted or sent SIGTERM.
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
                     configs that list it. From from-spec, drawnFrom has the command that draws
                     the chart again, run in the folder that holds the output folder, the sha256
                     of each spec, config and mapping that the run read, by its path from that
                     folder, and the sha256 of chart.mmd and of the two tables.
  states.tsv         Every chart state of the model, with its group, its status, whether it is a
                     start, the ids it is drawn as, and, per config TLC ran, its model states and
                     the model steps that stay in it. tlc-to-chart --help says each column.
  arrows.tsv         Every arrow between two chart states, one row per label and TLA+ action,
                     with the arrows the chart draws it as and, per config, its model steps. So
                     each state and step TLC reached is in a table, drawn or not.
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
  Regions draw only the arrows of the shortest way to each state, of each bug path, of the
  nearest step with each label, and one way out of each state that has one, so only a final state
  ends a path. The script checks that these arrows make no step that TLC's graph does not have.
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
     names the folder's new path. When TLC stops on an error, the message names TLC's output, and
     when the command cannot put its files in the output folder, the message says so. Both times
     the command removes its temporary folder, unless --keep-work keeps it, and then the message
     names the folder. The command checks its input files again before --png renders, so a
     changed input stops the run before that."""

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


LOST_FINGERPRINT = re.compile(r"Failed to recover the \S+ state from its fingerprint\.")


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
        "--also-config",
        "--count-config",
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
        elif a == "--keep-work":
            flags["keep-work"] = True
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


def stop_group(child):
    """Stops the process group that `child` leads: SIGTERM, which `jgauge test-slot` passes on to
    TLC, then SIGKILL to what is left once `child` ends or after a grace period. A group with no
    process left is no fault."""
    for number in (signal.SIGTERM, signal.SIGKILL):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(child.pid, number)
        with contextlib.suppress(subprocess.TimeoutExpired):
            child.wait(timeout=5)


def run_in_own_group(command, cwd):
    """Runs `command` in a process group of its own, as subprocess.run does, and on an error, an
    interrupt or SIGTERM stops the whole group, so a TLC under `jgauge test-slot` does not outlive
    the run whose folders it writes in."""
    child = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = child.communicate()
    except BaseException:
        stop_group(child)
        raise
    return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)


def run_tlc(tools, spec, cfg, base, dump=None, workers="1", first_only=False):
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
        *([] if first_only else ["-continue"]),
        *(["-dump", "dot,actionlabels", os.path.abspath(dump)] if dump else []),
        "-config",
        os.path.abspath(f"{base}.cfg"),
        os.path.basename(spec),
    ]
    held = in_test_slot(command)
    try:
        r = run_in_own_group(held, os.path.dirname(os.path.abspath(spec)))
    except OSError as e:
        raise CannotFinish(f"cannot run TLC: {e.strerror or e}") from e
    finally:
        shutil.rmtree(metadir, ignore_errors=True)
    # jgauge, which holds the slot, says so when Java cannot start, as the OSError above does.
    could_not_start = re.search(rf"^test-slot: {re.escape(tools.java)}: (.*)$", r.stderr, re.M)
    if r.returncode in (126, 127) and could_not_start:
        raise CannotFinish(f"cannot run TLC: {could_not_start[1]}")
    # TLC prints its version before anything else, so a slot that ends in a fault with nothing on
    # stdout never ran TLC to its first line: a jgauge that cannot run, such as a venv's shim
    # whose package is gone. Its own words say why, where TLC's empty output would not.
    if held is not command and r.returncode != 0 and not r.stdout:
        jgauge = held[held.index("test-slot") - 1]
        raise CannotFinish(
            f"cannot run TLC: {jgauge} test-slot exited {r.returncode} before TLC printed a"
            f" line:\n{r.stderr.strip()}{resync_hint(jgauge)}"
        )
    stdout = f"{FIRST_ONLY}{r.stdout}" if first_only else r.stdout
    with open(f"{base}.out", "w", encoding="utf-8") as handle:
        handle.write(stdout)
    try:
        warning = tlc_output_warning(stdout, f"{base}.out")
        return {"stdout": stdout, "warning": warning, "firstOnly": first_only}
    except ChartError as e:
        raise TlcStopped(str(e)) from e


def resync_hint(wrapper):
    """The command that clears a `jgauge` this command's own venv holds and its lock does not:
    a shim another checkout's project left there, by a sync that inherited the venv, whose
    package went with that checkout. An exact sync removes it. A wrapper from elsewhere on PATH
    gets no hint, since no sync of this venv mends it."""
    bin_dir = os.path.join(sys.prefix, "bin")
    if os.path.dirname(os.path.abspath(wrapper)) != bin_dir:
        return ""
    project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return (
        "\nThis venv holds a jgauge its lock does not; re-sync it with:\n"
        f"UV_PROJECT_ENVIRONMENT={shlex.quote(sys.prefix)} uv sync --frozen"
        f" --project {shlex.quote(project)} --reinstall-package jgauge"
    )


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

    def run_rule(rule, file, **options):
        try:
            return run(f"{cfg_without_rules}INVARIANT {rule}\nCONSTRAINT {rule}\n", file, **options)
        except TlcStopped as e:
            if not LOST_FINGERPRINT.search(str(e)):
                raise
        # With -continue and the rule as a CONSTRAINT, TLC can fail to rebuild a broken path from
        # its fingerprints on a large model. Plain TLC stops at the first state that breaks the
        # rule, and one worker makes that path the shortest.
        return run(f"{cfg_without_rules}INVARIANT {rule}\n", file, first_only=True)

    traces = []
    for rule in rules:
        file = os.path.join(tlc_dir, f"{name}-{rule}")
        result = run_rule(rule, file, workers=workers())
        # Several workers can reach a bad state by a longer path first. One worker searches breadth
        # first in a fixed order, so the chart's bug paths are the shortest, and the same every run.
        if re.search(r"^Error: Invariant ", result["stdout"], re.M) and not result["firstOnly"]:
            result = run_rule(rule, file)
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
    return {
        "spec": spec,
        "cfgFile": cfg_file,
        "dot": dot,
        "traces": traces,
        "properties": temporal,
        "broken": broken,
    }


def dump_also(tools, model, work):
    """TLC's state graph of `model` at the bounds of its --also-config, with no rule checked:
    its config's own tests check those."""
    name = re.sub(r"\.cfg$", "", os.path.basename(model["cfgFile"]))
    base = os.path.join(work, "tlc", f"also-{name}")
    started = time.monotonic()
    run_tlc(tools, model["spec"], model["cfgWithoutRules"], base, dump=f"{base}.dot")
    print(
        f"TLC dumped {os.path.basename(model['spec'])} with {rel(model['cfgFile'])} for the"
        f" tables in {time.monotonic() - started:.1f} s."
    )
    return {"dot": f"{base}.dot", "cfgFile": model["cfgFile"]}


def count_states(tools, model, work):
    """What TLC reaches at the bounds of `model`, its --count-config, with no rule checked and no
    state graph kept: its config's own tests check the rules."""
    name = re.sub(r"\.cfg$", "", os.path.basename(model["cfgFile"]))
    base = os.path.join(work, "tlc", f"count-{name}")
    started = time.monotonic()
    ran = run_tlc(tools, model["spec"], model["cfgWithoutRules"], base, workers=workers())
    found = re.findall(r"([\d,]+) distinct states found", ran["stdout"])
    if not found:
        raise CannotFinish(f"TLC printed no count of distinct states for {rel(model['cfgFile'])}")
    states = int(found[-1].replace(",", ""))
    print(
        f"TLC counted {states:,} states of {os.path.basename(model['spec'])} with"
        f" {rel(model['cfgFile'])} in {time.monotonic() - started:.1f} s."
    )
    return {"cfg": os.path.basename(model["cfgFile"]), "modelStates": states}


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


def draw(now, map_file, work, out, title, other=None, uncited=None, comparing=False, also=None):
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
        "states": os.path.join(work, "states.tsv"),
        "arrows": os.path.join(work, "arrows.tsv"),
    }
    tables = ["--tables", work, "--cfg", os.path.basename(now["cfgFile"])]
    if other:
        tables += ["--second-cfg", os.path.basename(other["cfgFile"])]
    if also:
        tables += ["--also-dot", also["dot"], "--also-cfg", os.path.basename(also["cfgFile"])]
    proof = os.path.join(work, "tlc", "regions-proof.mmd")
    every_arrow = os.path.join(work, "tlc", "regions-all.mmd")
    script(
        "tlc_to_chart",
        [
            *source,
            *([] if comparing else ["--regions", "--proof", proof, "--regions-all", every_arrow]),
            *tables,
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


# A chart is drawn at twice its size, or smaller where a side would pass PNG_SIDE_LIMIT, so the
# PNG opens in any viewer.
PNG_SIDE_LIMIT = 16384
PNG_SCALE = 2
# Headless Chromium rasterizes a page in tiles within a memory budget, about 256 MB by default,
# and leaves every tile past it blank: HomeTreeToday's chart drew whole up to 70 Mpx and lost
# its right and lower parts at 85 Mpx and above. 4096 MB drew it whole at 281 Mpx, more than
# the 268 Mpx of a PNG at PNG_SIDE_LIMIT on both sides. Chromium takes the memory as it draws.
PNG_BROWSER = {"args": ["--force-gpu-mem-available-mb=4096"]}


def mermaid(chart, out, *extra):
    """Runs the pinned mermaid-cli on one chart: whether it drew `out`, and what it said."""
    try:
        r = subprocess.run(
            ["npx", "-y", MERMAID_CLI, "-i", chart, "-o", out, *extra],
            capture_output=True,
            text=True,
        )
        return r.returncode == 0, r.stderr
    except OSError as e:
        return False, e.strerror or str(e)


def png_scale(svg):
    """The scale to draw a chart at, from its SVG: PNG_SCALE, or less where the chart's longer
    side would pass PNG_SIDE_LIMIT. A chart whose size the SVG does not give keeps PNG_SCALE."""
    box = re.search(r'viewBox="[-\d.e]+ [-\d.e]+ ([\d.e]+) ([\d.e]+)"', svg)
    if not box:
        return PNG_SCALE
    # mermaid-cli clips to the chart's whole pixels, so its sides are rounded up before scaling.
    side = max(math.ceil(float(box[1])), math.ceil(float(box[2]))) + 1
    return min(PNG_SCALE, math.floor(PNG_SIDE_LIMIT / side * 1000) / 1000)


def draw_png(chart, png):
    """Draws one chart to `png` with the pinned mermaid-cli, first to an SVG that sizes it:
    whether it drew it, and what mermaid-cli said."""
    with tempfile.TemporaryDirectory() as scratch:
        svg = os.path.join(scratch, "chart.svg")
        ok, said = mermaid(chart, svg)
        if not ok:
            return ok, said
        with open(svg, encoding="utf-8") as handle:
            scale = png_scale(handle.read())
        browser = os.path.join(scratch, "browser.json")
        with open(browser, "w", encoding="utf-8") as handle:
            json.dump(PNG_BROWSER, handle)
        return mermaid(chart, png, "-s", f"{scale:g}", "-p", browser)


def render(charts, shown):
    pngs = []
    for chart in charts:
        png = re.sub(r"\.mmd$", ".png", chart)
        ok, said = draw_png(chart, png)
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
        for f in [
            *drawn["charts"],
            *pngs,
            *(drawn["files"][k] for k in ("stories", "summary", "states", "arrows")),
        ]
        if os.path.exists(f)
    )
    print(f"\nWrote {written} in {rel(out)}.")
    if png and len(pngs) < len(drawn["charts"]):
        return 2
    return 0 if ok else 1


OWN = re.compile(
    r"^((chart|bug-\d+(-developer|-layered)?)\.(mmd|png)|stories\.md|summary\.json|states\.tsv"
    r"|arrows\.tsv|tlc|\.DS_Store)$"
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


class Terminated(BaseException):
    pass


def terminated(signum, frame):
    raise Terminated


def in_work_folder(body, keep):
    """Runs `body` in a new temporary folder, and removes the folder when it ends, also on an
    error, an interrupt or SIGTERM, unless `keep`. Then it names the folder."""
    work = tempfile.mkdtemp(prefix="statechart-")
    kept = f"The files that this run wrote are in {rel(work)}."
    was = signal.signal(signal.SIGTERM, terminated)
    named = False
    try:
        os.mkdir(os.path.join(work, "tlc"))
        return body(work)
    except CannotFinish as e:
        if not keep:
            if isinstance(e, (TlcStopped, NotPublished)):
                raise type(e)(
                    f"{e} The command removed this run's files: pass --keep-work to keep them."
                ) from e
            raise
        named = True
        raise type(e)(f"{e} {kept}") from e
    except Terminated:
        sys.exit(128 + signal.SIGTERM)
    finally:
        signal.signal(signal.SIGTERM, was)
        if not keep:
            shutil.rmtree(work, ignore_errors=True)
        elif not named:
            sys.stdout.flush()
            print(kept, file=sys.stderr)


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


def expectations(spec):
    """The configs beside `spec` whose header names it as their module and has an expect line, by
    file name, with what each expects."""
    directory = os.path.dirname(spec) or "."
    files = sorted(os.listdir(directory))
    modules = [f for f in files if f.endswith(".tla") and "_TTrace_" not in f]
    only = re.sub(r"\.tla$", "", modules[0]) if len(modules) == 1 else None
    found = {}
    for f in (f for f in files if f.endswith(".cfg")):
        with open(os.path.join(directory, f), encoding="utf-8") as handle:
            cfg = handle.read()
        m = re.search(r"^\\\* module:[ \t]*(\w+)[ \t]*$", cfg, re.M | re.A)
        module = m.group(1) if m else only
        e = re.search(r"^\\\* expect:[ \t]*(\w+)[ \t]*$", cfg, re.M | re.A)
        if module == re.sub(r"\.tla$", "", os.path.basename(spec)) and e:
            found[f] = e.group(1)
    return found


def listed_breaks(spec):
    found = expectations(spec)
    if not found:
        return None
    breaks = {f: e for f, e in found.items() if not re.match(r"^(pass|deadlock)$|^error", e)}
    return {"spec": os.path.basename(spec), "breaks": breaks}


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
                " No comment cites the code that checks"
                f" {'this condition' if len(found) == 1 else 'these conditions'}:\n{listed}\nPut"
                " the file of that code in a comment on each condition, with the code it quotes in"
                " backticks, as in \\* pay.ts `if (sent > 0)`, or its file and line, as in"
                " \\* pay.ts:120, or remove the condition when no code checks it.",
                file=sys.stderr,
            )
        found_by_spec[os.path.basename(spec)] = found
    return found_by_spec


def local_modules(spec, seen=None):
    """The modules beside `spec` that it extends or instantiates, and theirs in turn: TLC reads
    them with it."""
    seen = set() if seen is None else seen
    text = without_comments(spec)
    names = [
        n
        for m in re.finditer(r"\bEXTENDS\s+(\w+(?:\s*,\s*\w+)*)", text, re.A)
        for n in re.split(r"\s*,\s*", m.group(1))
    ]
    names += re.findall(r"\bINSTANCE\s+(\w+)", text, re.A)
    found = []
    for n in names:
        module = os.path.join(os.path.dirname(spec), f"{n}.tla")
        if module not in seen and os.path.exists(module):
            seen.add(module)
            found += [module, *local_modules(module, seen)]
    return found


def sha256(file):
    with open(file, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def drawn_from(given, flags, expected, out, inputs, files):
    """What drew this chart: the command, and the sha256 of each file it read and of chart.mmd,
    with each path taken from the folder that holds the output folder."""
    base = os.path.dirname(os.path.abspath(out))

    def path(f):
        return os.path.relpath(os.path.abspath(f), base)

    command = ["statechart", "from-spec", path(given)]
    for name in (
        "config",
        "fixed",
        "fixed-config",
        "against",
        "against-config",
        "also-config",
        "count-config",
        "map",
    ):
        if flags.get(name):
            command += [f"--{name}", path(flags[name])]
    for name in ("label", "title"):
        if flags.get(name) is not None:
            command += [f"--{name}", flags[name]]
    if expected:
        command += ["--expect-broken", ",".join(expected)]
    if flags.get("png"):
        command.append("--png")
    return {
        "command": shlex.join(command),
        "inputs": {path(f): sha256(f) for f in sorted(inputs, key=path)},
        "chart": sha256(files["overview"]),
        "tables": {
            os.path.basename(files[t]): sha256(files[t])
            for t in ("states", "arrows")
            if os.path.exists(files[t])
        },
    }


def stamp(files, drawn, checked=None):
    with open(files["summary"], encoding="utf-8") as handle:
        summary = json.load(handle)
    if checked:
        summary["checked"] = checked
    with open(files["summary"], "w", encoding="utf-8") as handle:
        handle.write(
            json.dumps({**summary, "drawnFrom": drawn}, indent=2, ensure_ascii=False) + "\n"
        )


def from_spec(given, flags):
    expected = list(flags.pop("expect-broken"))
    name = re.sub(r"\.tla$", "", os.path.basename(given))
    map_file = flags.get("map") or os.path.join(os.path.dirname(given), f"{name}.map.py")
    cfg = flags.get("config") or cfg_of(given)
    other_cfg = second_cfg(cfg, flags)
    also_cfg = flags.get("also-config")
    count_cfg = flags.get("count-config")
    if also_cfg and count_cfg:
        raise CannotFinish("Give --also-config or --count-config, not both.")
    inputs = snapshot(
        [
            given,
            cfg,
            map_file,
            flags.get("fixed") or flags.get("against"),
            other_cfg,
            also_cfg,
            count_cfg,
        ]
    )
    second = second_model(given, other_cfg, flags)
    model = read_input(given, cfg, expected)
    also_model = read_model(given, also_cfg, "--also-config") if also_cfg else None
    count_model = read_model(given, count_cfg, "--count-config") if count_cfg else None
    out = out_dir(flags.get("out"), given, name)
    snapshot(local_modules(given), inputs)
    if second:
        other_spec = second["model"]["spec"]
        snapshot(local_modules(other_spec), inputs)
        if second["role"] == "against":
            beside = os.path.dirname(other_spec)
            snapshot([os.path.join(beside, f) for f in expectations(other_spec)], inputs)
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
        also = dump_also(tools, also_model, work) if also_model else None
        checked = count_states(tools, count_model, work) if count_model else None
        drawn = draw(
            now, map_file, work, out, flags.get("title"), other=other, uncited=uncited, also=also
        )
        stamp(
            drawn["files"],
            drawn_from(given, flags, expected, out, inputs, drawn["files"]),
            checked,
        )
        return finish(
            work, out, inputs, drawn, rules_as_expected(now, other, expected), flags.get("png")
        )

    return in_work_folder(body, flags.get("keep-work"))


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

    return in_work_folder(body, flags.get("keep-work"))


SITE = """Usage: statechart site --out FILE [--root DIR] [--flow MAP.toml] [--lanes]

Draws every features/*/spec/*-statechart/chart.mmd under DIR, from the chart.mmd, stories.md and
summary.json committed there, and runs no TLC unless --lanes asks. It writes, in FILE's folder:
  FILE          One self-contained HTML page that explores every chart. It opens on an Overview
                tab, and each chart's tab shows the chart's overview (statechart overview --help)
                above the chart itself: a tap on an overview's box moves the chart to that group's
                states. Pan and zoom the chart, and tap a state for its whole label, the code line
                it cites and its steps in and out. Under the chart, the states.tsv and arrows.tsv
                beside it are two tables, with a filter: every state of the model's map and every
                arrow, drawn or not, and a tap on a row lights it in the chart. The page fetches
                nothing when it is viewed.
  NAME.png, NAME-bug-N.png
                Each chart and each bug-N.mmd beside it as a PNG, drawn with npx
                {MERMAID_CLI}, so it needs Node.
  NAME.excalidraw, NAME.overview.excalidraw
                Each chart and its overview as an Excalidraw scene, as statechart excalidraw and
                statechart overview --out draw them.

  --out FILE   Where the page goes.
  --root DIR   The repo whose charts it draws. Default: the git repo of the current folder.
  --flow MAP.toml
               The map the Overview tab draws: one box per chart, in the order of its [[chart]]
               tables, each with the chart's name, the thing it charts and, for a chart whose
               title asks no question, its question; and one numbered arrow per [[handoff]], with
               from = "Chart: Group", to = "Chart: Group" and the words it says. The command
               stops when a hand-off names a chart or a group that is not there. Default: the
               flow.toml beside FILE, where there is one. Without one, the tab draws the charts
               in the order of their paths, with no hand-offs.
  --lanes      Draw each chart whose mapping names `lanes` as reference lanes instead: one row of
               boxes per lane, every step of TLC's graph on one arrow, table cell or row, and no
               two lines crossing. It runs TLC on the spec beside the chart, with each config
               the mapping's `lane_configs` names, and the mapping's `seen()` puts real counts on
               the arrows its logs record. It then prints, for each such chart, the steps with
               no single place on the page and the places with no step, and the crossings and
               labels on lines, labels or boxes of each drawing, with label sizes estimated;
               `statechart lanes-check FILE` measures those in a browser.

Exit codes: 0 all written, 1 a lanes count above 0, 2 a chart or map it cannot read, a
hand-off to a group that is not there, a PNG it cannot draw, or a wrong argument. A PNG it
cannot draw leaves the page and the other files written."""


def site_main(argv):
    from statechart import overview, site

    flags = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(SITE.format(MERMAID_CLI=MERMAID_CLI))
            return 0
        if a in ("--out", "--root", "--flow"):
            if i + 1 == len(argv):
                raise CannotFinish(f"{a} needs a value. Run statechart site --help for the flags.")
            i += 1
            flags[a[2:]] = argv[i]
        elif a == "--lanes":
            flags["lanes"] = True
        else:
            raise CannotFinish(f"unknown argument {a}. Run statechart site --help for the flags.")
        i += 1
    if "out" not in flags:
        raise CannotFinish(SITE.split("\n", 1)[0])
    root = flags.get("root") or site.repo_root(os.getcwd())
    beside = os.path.join(os.path.dirname(flags["out"]), "flow.toml")
    if "flow" not in flags and os.path.isfile(beside):
        flags["flow"] = beside
    try:
        tools = find_tools() if flags.get("lanes") else None
        charts = site.build(root, flags["out"], flags.get("flow"), tools)
        folder = Path(flags["out"]).resolve().parent
        for chart in charts:
            text = (chart.folder / "chart.mmd").read_text(encoding="utf-8")
            excalidraw.write(excalidraw.scene(text), folder / f"{chart.name}.excalidraw")
            groups = overview.mermaid(overview.overview_of(site.read_text(text, chart.name)))
            excalidraw.write(excalidraw.scene(groups), folder / f"{chart.name}.overview.excalidraw")
    except ChartError as e:
        raise CannotFinish(str(e)) from e
    states = sum(len(r.states) for c in charts for r in c.regions)
    print(f"wrote {flags['out']}: {len(charts)} charts, {states} states")
    off = sum(lanes_report(c) for c in charts if c.lanes)
    pictures = [
        (mmd, folder / f"{chart.name}{'' if mmd.stem == 'chart' else '-' + mmd.stem}.png")
        for chart in charts
        for mmd in [chart.folder / "chart.mmd", *sorted(chart.folder.glob("bug-*.mmd"))]
    ]
    drawn = 0
    for mmd, png in pictures:
        ok, said = draw_png(str(mmd), str(png))
        if ok:
            drawn += 1
        else:
            print(f"could not draw {png.name}: {said.strip()}", file=sys.stderr)
    print(f"wrote {drawn} PNGs and {2 * len(charts)} Excalidraw scenes beside it")
    return 2 if drawn != len(pictures) else 1 if off else 0


def lanes_report(chart):
    """Prints what the lanes check found on one chart drawn as lanes, and returns how many
    faults it found."""
    lanes = chart.lanes
    totals = ", ".join(
        f"{cfg}: {n:,} states, {s:,} steps" for cfg, (n, s) in lanes.projection.totals.items()
    )
    cov = lanes.coverage
    print(f"{chart.name} lanes, from {totals}")
    print(
        f"  coverage: {cov['steps']:,} steps, {cov['steps_without_place']} with no single place on"
        f" the page, {len(cov['places_without_step'])} arcs, cells or rows with no step"
    )
    off = cov["steps_without_place"] + len(cov["places_without_step"])
    for name, found in lanes.faults.items():
        counts = ", ".join(f"{len(v)} {k.replace('_', ' ')}" for k, v in found.items())
        print(f"  layout, {name}, label sizes estimated: {counts}")
        off += sum(len(v) for v in found.values())
    for line in [
        *cov["examples"],
        *(x for f in lanes.faults.values() for v in f.values() for x in v),
    ][:8]:
        print(f"    {line}")
    return off


OVERVIEW = """Usage: statechart overview CHART.mmd [--out FILE.excalidraw]

Draws the chart at the level of its groups, the groups its mapping's group() made and its Legend
names: each region gives one box per group that has states in it, and one box for its states in no
group. An arrow joins two boxes when a step of the chart leads from a state of one to a state of the
other, and says how many steps do. A box says how many states it holds, and how many steps lead
between two of them. The boxes hold every state of the chart, and the arrows and boxes every step.
An overview of more than {MOST} boxes is no overview: the command warns, and the chart needs fewer
groups.

Without --out it prints the overview as a Mermaid stateDiagram-v2. With --out it writes it as an
Excalidraw scene, laid out as statechart excalidraw lays out a chart; the same chart always writes
the same bytes.

Exit codes: 0 drawn, 2 a chart it cannot read, a file it cannot write, or a wrong argument."""


def overview_main(argv):
    from statechart import site
    from statechart.overview import MOST, mermaid, overview_of

    chart_file = out = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(OVERVIEW.replace("{MOST}", str(MOST)))
            return 0
        if a == "--out":
            if i + 1 == len(argv):
                raise CannotFinish("--out needs a value. Run statechart overview --help.")
            out = argv[i + 1]
            i += 2
            continue
        if a.startswith("-") or chart_file is not None:
            raise CannotFinish(f"unknown argument {a}. Run statechart overview --help.")
        chart_file = a
        i += 1
    if chart_file is None:
        raise CannotFinish(OVERVIEW.split("\n", 1)[0])
    try:
        with open(chart_file, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as e:
        raise CannotFinish(f"cannot read {chart_file}: {e.strerror}") from e
    name = os.path.basename(os.path.dirname(os.path.abspath(chart_file))).removesuffix(
        "-statechart"
    )
    try:
        ov = overview_of(site.read_text(text, name))
        drawn = mermaid(ov)
        if out is not None:
            excalidraw.write(excalidraw.scene(drawn), out)
    except ChartError as e:
        raise CannotFinish(f"{chart_file}: {e}") from e
    except OSError as e:
        raise CannotFinish(f"cannot write {out}: {e.strerror}") from e
    boxes = len(ov.boxes())
    if boxes > MOST:
        print(
            f"warning: {boxes} boxes, more than {MOST}: the chart needs fewer groups",
            file=sys.stderr,
        )
    if out is None:
        print(drawn, end="")
    else:
        print(f"wrote {out}: {boxes} boxes")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["excalidraw"]:
        return excalidraw.main(argv[1:])
    try:
        if argv and argv[0] == "site":
            return site_main(argv[1:])
        if argv and argv[0] == "overview":
            return overview_main(argv[1:])
        if argv and argv[0] == "lanes-check":
            from statechart import lanes_check

            return lanes_check.main(argv[1:])
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
