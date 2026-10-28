"""Check the merge flow's rules with TLC: today's code breaks the rules it breaks today, the design
holds all four, and each canary (the design with one fix taken out) breaks the rule that rests on
that fix. Two controls run today's code with an earlier gap of jbus.strays, the code before #427
and the code before #416, and each breaks all four rules. Run it from the repo root:

    python3 features/jmerge/spec/flow_canaries.py

It prints one line for each run and ends 0 when every run says what it should. TLC comes from the
statechart skill's pinned tla2tools.jar, downloaded to the cache on the first run, and Java from
JAVA, else a java on PATH. Each run has a copy of this folder of its own, so TLC writes nothing
here."""

import importlib
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(
    0, str(HERE.parents[2] / "features" / "skill-library" / "skills" / "statechart" / "scripts")
)

tools = importlib.import_module("statechart.tools")

RULES = ["FlowsWhenGreen", "NoMergeTurnsMainRed", "MachineNotLeftFull", "MainFixWaitsOnlyOnYou"]

# Each fix of the design, as a canary that takes it out, and the rules that rest on it.
CANARIES = {
    "NoGuard": ["NoMergeTurnsMainRed"],
    "NoRejudge": ["FlowsWhenGreen"],
    "NoSweep": ["FlowsWhenGreen", "MachineNotLeftFull"],
    "NoProof": ["MainFixWaitsOnlyOnYou"],
}

# Today's code breaks two rules. A check that selects a test reading the whole tree only by
# chance merges a change that breaks it. And once main's fix row closed with its fix in an open
# pull request, that fix merges only when its own check proves it, which it does only when it
# selected the tests main failed and the red run's logs name them: otherwise nothing can merge.
# Since #427 jbus.strays stops what a crew left, busy or idle, once its turn ended, so no
# leftover keeps the machine full.
TODAY_BREAKS = ["NoMergeTurnsMainRed", "MainFixWaitsOnlyOnYou"]

# What jbus.strays stops of an idle process a finished turn left (FlowToday.tla's `Gap`), and
# the rules the code breaks with it. Before #427 an idle one is stopped only once its row ended,
# and before #416 never: either keeps the machine full, so nothing new starts, a follow-up that
# merges after its row waits on a row that never launches, and main's fix cannot launch.
TODAY = "turn"
CONTROLS = {
    "today, before #427 (idle swept once its row ended)": ("ended", RULES),
    "today, before #416 (busy leftovers only)": ("busy", RULES),
}


def config(rules, gap=None):
    lines = ["SPECIFICATION Spec", *([f'CONSTANT Gap = "{gap}"'] if gap else [])]
    lines += ["INVARIANT TypeOK", *(f"INVARIANT {rule}" for rule in rules)]
    return "\n".join(lines) + "\n"


def specs():
    """The .tla files a run copies into its folder."""
    return sorted([*HERE.glob("*.tla"), *HERE.glob("canary/*.tla")])


def tlc(found, module, cfg):
    """TLC's output for `module` with the config `cfg`, run in a copy of this folder. A run whose
    inputs (the specs, the config, this script, the jar and the Java) are those of one that
    finished before returns that run's output, kept by `tools.kept`, and starts no Java."""
    inputs = [Path(__file__).read_bytes(), module, cfg, *tools.tlc_inputs(found)]
    for spec in specs():
        inputs += [spec.name, spec.read_bytes()]
    return tools.kept(lambda: run(found, module, cfg), inputs, finished)


def run(found, module, cfg):
    """TLC's output for `module` with the config `cfg`, run now in a copy of this folder."""
    with tempfile.TemporaryDirectory(prefix="merge-flow-") as folder:
        work = Path(folder)
        for spec in specs():
            shutil.copy(spec, work)
        (work / "run.cfg").write_text(cfg)
        ran = subprocess.run(
            tools.in_test_slot(
                [
                    found.java,
                    "-XX:+UseParallelGC",
                    f"-Djava.io.tmpdir={work}",
                    "-cp",
                    found.jar,
                    "tlc2.TLC",
                    "-workers",
                    tools.workers(),
                    "-deadlock",
                    "-metadir",
                    str(work / "meta"),
                    "-config",
                    "run.cfg",
                    f"{module}.tla",
                ]
            ),
            cwd=work,
            capture_output=True,
            text=True,
        )
    return ran.stdout + ran.stderr


def verdict(out, rule=None):
    """`holds` when TLC found no error, `breaks` when it found `rule` broken, else `error`."""
    if "Model checking completed. No error has been found." in out:
        return "holds"
    if rule and f"Invariant {rule} is violated" in out:
        return "breaks"
    return "error"


def finished(out):
    """Whether TLC ran to its verdict, so its output is kept: it found no error or broke a rule,
    and did not fail or stop short."""
    return any(verdict(out, rule) != "error" for rule in [None, *RULES])


def states(out):
    found = [line for line in out.splitlines() if "distinct states found" in line]
    return found[-1].split(",")[1].strip() if found else "no state count"


def runs():
    """Each run: its label, the module, the config, the rule it is about, and what it must say."""
    yield "design: every rule", "FlowDesign", config(RULES), None, "holds"
    for canary, rules in CANARIES.items():
        for rule in rules:
            yield f"canary {canary}: {rule}", canary, config([rule]), rule, "breaks"
    for label, (gap, breaks) in {"today": (TODAY, TODAY_BREAKS), **CONTROLS}.items():
        for rule in RULES:
            want = "breaks" if rule in breaks else "holds"
            yield f"{label}: {rule}", "FlowToday", config([rule], gap), rule, want


def main():
    try:
        tlc_tools = tools.find_tlc()
        tools.workers()
    except tools.NoTlc as e:
        print(e, file=sys.stderr)
        return 2
    wrong = 0
    for label, module, cfg, rule, want in runs():
        started = time.monotonic()
        out = tlc(tlc_tools, module, cfg)
        got = verdict(out, rule)
        took = time.monotonic() - started
        mark = "ok" if got == want else "WRONG"
        print(f"{mark:5} {label} {got} ({states(out)}, {took:.1f} s)", flush=True)
        if got != want:
            wrong += 1
            print(out, file=sys.stderr)
    print(f"{wrong} wrong" if wrong else "every run says what it should")
    return 1 if wrong else 0


if __name__ == "__main__":
    tools.rerun_in_test_slot()
    sys.exit(main())
