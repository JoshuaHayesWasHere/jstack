"""Check the home tree's rules with TLC: each rule holds in the design in every scene, each canary
(the design with one guard taken out) breaks the rule that rests on that guard, and today's code
breaks the rules it breaks today. Run it from the repo root:

    python3 features/home/spec/canaries.py

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

# A scene is the children the root makes in one run, the calls they raise, and whether the
# routes move. Two siblings that both raise calls are too many states for one run.
SCENES = {
    "a": ('{"a"}', '{"a1", "a2"}', "TRUE"),
    "b": ('{"b"}', '{"b1", "b2"}', "TRUE"),
    "siblings": ('{"a", "b"}', "{}", "FALSE"),
}
INVARIANTS = [
    "NoRetireWithOpen",
    "StallFlagged",
    "FirstStrike",
    "NudgesBounded",
    "OneMerger",
    "NoBlindMerge",
]
PROPERTIES = ["CallsReachJosh", "AsksAfterTwo", "ReadyMerges"]
RULES = INVARIANTS + PROPERTIES

# Each guard of the design, the rule that rests on it, and the scene that shows it.
CANARIES = {
    "retire-guard": ("NoRetireWithOpen", "a"),
    "rehome": ("CallsReachJosh", "a"),
    "flag": ("StallFlagged", "a"),
    "beat": ("StallFlagged", "b"),
    "strike": ("FirstStrike", "a"),
    "nudge-cap": ("NudgesBounded", "a"),
    "ask": ("AsksAfterTwo", "a"),
    "one-merger": ("OneMerger", "a"),
    "lock": ("NoBlindMerge", "siblings"),
    "all-homes": ("ReadyMerges", "a"),
    "drop-release": ("ReadyMerges", "siblings"),
}

# The rules today's code breaks, and in which scene. The others hold today only because nothing
# today flags, nudges or asks, except the two TODAY_HOLDS checks.
TODAY_BREAKS = {
    "NoRetireWithOpen": "a",
    "StallFlagged": "a",
    "OneMerger": "a",
    "NoBlindMerge": "siblings",
}

# The rules today's code keeps. CallsReachJosh holds since pull request 332 moved what waits for a
# dropped route, and ReadyMerges since pull request 357 let jbus merge a child's pull request.
TODAY_HOLDS = ["CallsReachJosh", "ReadyMerges"]


def config(scene, rules, modes, drop=None):
    made, raised, routes_move = SCENES[scene]
    lines = [
        "CONSTANTS",
        "    K = 2",
        "    Rhythm = 1",
        f"    Modes = {modes}",
        f"    Made = {made}",
        f"    Raised = {raised}",
        f"    RoutesMove = {routes_move}",
        *([f'    Drop = "{drop}"'] if drop is not None else []),
        "SPECIFICATION Spec",
        "INVARIANT TypeOK",
        *(f"INVARIANT {rule}" for rule in rules if rule in INVARIANTS),
        *(f"PROPERTY {rule}" for rule in rules if rule in PROPERTIES),
    ]
    return "\n".join(lines) + "\n"


def tlc(found, module, cfg):
    """TLC's output for `module` with the config `cfg`, run in a copy of this folder."""
    with tempfile.TemporaryDirectory(prefix="home-tree-") as folder:
        work = Path(folder)
        for spec in HERE.glob("*.tla"):
            shutil.copy(spec, work)
        (work / "run.cfg").write_text(cfg)
        ran = subprocess.run(
            [
                found.java,
                "-XX:+UseParallelGC",
                f"-Djava.io.tmpdir={work}",
                "-cp",
                found.jar,
                "tlc2.TLC",
                "-workers",
                "auto",
                "-deadlock",
                "-metadir",
                str(work / "meta"),
                "-config",
                "run.cfg",
                f"{module}.tla",
            ],
            cwd=work,
            capture_output=True,
            text=True,
        )
    return ran.stdout + ran.stderr


def verdict(out, rule=None):
    """`holds` when TLC found no error, `breaks` when it found `rule` broken, else `error`."""
    if "Model checking completed. No error has been found." in out:
        return "holds"
    if rule in INVARIANTS and f"Invariant {rule} is violated" in out:
        return "breaks"
    if rule in PROPERTIES and "Temporal properties were violated" in out:
        return "breaks"
    return "error"


def states(out):
    found = [line for line in out.splitlines() if "distinct states found" in line]
    return found[-1].split(",")[1].strip() if found else "no state count"


def runs():
    """Each run: its label, the module, the config, the rule it is about, and what it must say."""
    for scene in SCENES:
        cfg = config(scene, RULES, '{"jbus"}', "none")
        yield f"design, scene {scene}: every rule", "HomeTreeDesign", cfg, None, "holds"
    for guard, (rule, scene) in CANARIES.items():
        cfg = config(scene, [rule], '{"jbus"}', guard)
        yield f"canary {guard}, scene {scene}: {rule}", "HomeTreeDesign", cfg, rule, "breaks"
    for rule, scene in TODAY_BREAKS.items():
        cfg = config(scene, [rule], '{"jbus", "home"}')
        yield f"today, scene {scene}: {rule}", "HomeTreeToday", cfg, rule, "breaks"
    for rule in TODAY_HOLDS:
        cfg = config("a", [rule], '{"jbus", "home"}')
        yield f"today, scene a: {rule}", "HomeTreeToday", cfg, rule, "holds"


def main():
    try:
        tlc_tools = tools.find_tlc()
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
    sys.exit(main())
