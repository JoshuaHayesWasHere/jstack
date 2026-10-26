"""Check the home tree's rules with TLC: each rule holds in the design in every scene, each canary
(the design with one guard taken out) breaks the rule that rests on that guard, and each rule holds
in today's code in every scene. Run it from the repo root:

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

# Today's code keeps every rule in every scene: the four it broke (NoRetireWithOpen, StallFlagged,
# OneMerger and NoBlindMerge) since the branch hometree-rules gave it the design's guards, and
# CallsReachJosh and ReadyMerges since pull requests 332 and 357. Each scene runs with both modes,
# so the merge switch is shown to play no part.
TODAY_MODES = '{"jbus", "home"}'


# A run of a property checks the scene alone: its children, its calls and their notices. TLC
# carries a branch of the property and the fairness of each message and child it is given, on
# every state, so the three of a scene take a third as long as the six of the whole model and
# find the same states. The run of every invariant checks, on the whole model, that nothing
# outside the scene moves (SceneStill in HomeTree.tla), so the scene alone misses no step.
SCENE_ALONE = ["    Kids <- Made", "    Calls <- Raised", "    Notices <- SceneNotices"]


def config(scene, rules, modes, drop=None):
    made, raised, routes_move = SCENES[scene]
    alone = any(rule in PROPERTIES for rule in rules)
    lines = [
        "CONSTANTS",
        "    K = 2",
        "    Rhythm = 1",
        f"    Modes = {modes}",
        f"    Made = {made}",
        f"    Raised = {raised}",
        f"    RoutesMove = {routes_move}",
        *([f'    Drop = "{drop}"'] if drop is not None else []),
        *(SCENE_ALONE if alone else []),
        "SPECIFICATION Spec",
        "INVARIANT TypeOK",
        *(["INVARIANT SceneStill"] if rules == INVARIANTS else []),
        *(f"INVARIANT {rule}" for rule in rules if rule in INVARIANTS),
        *(f"PROPERTY {rule}" for rule in rules if rule in PROPERTIES),
    ]
    return "\n".join(lines) + "\n"


def specs():
    """The .tla files a run copies into its folder."""
    return sorted(HERE.glob("*.tla"))


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
    with tempfile.TemporaryDirectory(prefix="home-tree-") as folder:
        work = Path(folder)
        for spec in specs():
            shutil.copy(spec, work)
        (work / "run.cfg").write_text(cfg)
        # Java's own cap is a quarter of the machine's memory, and a run grows to some 5 GB of it
        # unasked. The tests run several at once, and a low-memory killer stopped them at that
        # size, while the largest scene runs as fast in 1 GB.
        ran = subprocess.run(
            tools.in_test_slot(
                [
                    found.java,
                    "-Xmx1g",
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
    if rule in INVARIANTS and f"Invariant {rule} is violated" in out:
        return "breaks"
    if rule in PROPERTIES and "Temporal properties were violated" in out:
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
    # TLC walks a scene's whole state graph again for each property, so a run of every rule takes
    # as long as its runs one property at a time: one run for the invariants and one for each
    # property is the same check in pieces a test can take one by one.
    for scene in SCENES:
        for name, rules in [("every invariant", INVARIANTS), *((p, [p]) for p in PROPERTIES)]:
            cfg = config(scene, rules, '{"jbus"}', "none")
            yield f"design, scene {scene}: {name}", "HomeTreeDesign", cfg, None, "holds"
    for guard, (rule, scene) in CANARIES.items():
        cfg = config(scene, [rule], '{"jbus"}', guard)
        yield f"canary {guard}, scene {scene}: {rule}", "HomeTreeDesign", cfg, rule, "breaks"
    for scene in SCENES:
        for name, rules in [("every invariant", INVARIANTS), *((p, [p]) for p in PROPERTIES)]:
            cfg = config(scene, rules, TODAY_MODES)
            yield f"today, scene {scene}: {name}", "HomeTreeToday", cfg, None, "holds"


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
