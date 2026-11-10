"""Check PrVerdict.tla's rule with TLC: today's code holds MergesOrWaitsOnYou, and each canary,
today's code with one hold taken out (its `Drop`), breaks it. Run it from the repo root:

    python3 features/jmerge/spec/pr_canaries.py

It prints one line for each run and ends 0 when every run says what it should. TLC comes from the
statechart skill's pinned tla2tools.jar, downloaded to the cache on the first run, and Java from
JAVA, else a java on PATH. Each run has a folder of its own, so TLC writes nothing here."""

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

MODULE = "PrVerdict"
RULE = "MergesOrWaitsOnYou"

# Each hold the rule rests on, as the `Drop` that takes it out. The first five keep a merge to
# your word: without one, a pull request merges past a hold of yours (the rule's safety half, its
# `MergesOnlyOnYourWord`). The last four move a ready pull request on: without one, it waits for
# ever on nothing your word can lift (the rule's `~>`).
CANARIES = {
    "go": "its queue row's go (rows.short: ROW_HELD, NO_GO)",
    "touches": "a protected path (needs_the_user: TOUCHES)",
    "declines": "a drop or decline the review did not uphold (drops, declines)",
    "mergeoff": "the merge-off switch (MERGE_OFF)",
    "head": "your accept covers the head it was given at (Repo.lifted, Repo.accept)",
    "release": "the line's holder that waits on its crew or user gives up the line (Repo.waits)",
    "rejudge": "a check that failed is judged again as if it passed (Repo.judge, red_only)",
    "again": "GitHub merges a moved main into a pull request whose check failed (Repo.again)",
    "batch-failed": "a member of a failed batch of one goes alone at its head (Batching.takes)",
}


def config(drop):
    """PrVerdict.cfg with `Drop` set to `drop`."""
    text = (HERE / f"{MODULE}.cfg").read_text()
    return text.replace('Drop = "none"', f'Drop = "{drop}"')


def tlc(found, cfg):
    """TLC's output for the spec with the config `cfg`. A run whose inputs (the spec, the config,
    this script, the jar and the Java) are those of one that finished before returns that run's
    output, kept by `tools.kept`, and starts no Java."""
    spec = HERE / f"{MODULE}.tla"
    inputs = [Path(__file__).read_bytes(), spec.read_bytes(), cfg, *tools.tlc_inputs(found)]
    return tools.kept(lambda: run(found, cfg), inputs, finished)


def run(found, cfg):
    with tempfile.TemporaryDirectory(prefix="pr-verdict-") as folder:
        work = Path(folder)
        shutil.copy(HERE / f"{MODULE}.tla", work)
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
                    f"{MODULE}.tla",
                ]
            ),
            cwd=work,
            capture_output=True,
            text=True,
        )
    return ran.stdout + ran.stderr


def verdict(out):
    """`holds` when TLC found no error, `breaks` when it found the rule broken, its safety half
    as the invariant TLC checks it as or its leads-to as a temporal property, else `error`."""
    if "Model checking completed. No error has been found." in out:
        return "holds"
    if "Invariant MergesOnlyOnYourWord is violated" in out:
        return "breaks"
    if "Temporal properties were violated" in out:
        return "breaks"
    return "error"


def finished(out):
    return verdict(out) != "error"


def states(out):
    found = [line for line in out.splitlines() if "distinct states found" in line]
    return found[-1].split(",")[1].strip() if found else "no state count"


def runs():
    """Each run: what its line starts with, the config, and what TLC must say."""
    yield "today", config("none"), "holds"
    for drop in CANARIES:
        yield f"canary {drop}", config(drop), "breaks"


def main():
    try:
        found = tools.find_tlc()
        tools.workers()
    except tools.NoTlc as e:
        print(e, file=sys.stderr)
        return 2
    wrong = 0
    for label, cfg, want in runs():
        started = time.monotonic()
        out = tlc(found, cfg)
        got = verdict(out)
        mark = "ok" if got == want else "WRONG"
        took = time.monotonic() - started
        print(f"{mark:5} {label}: {RULE} {got} ({states(out)}, {took:.1f} s)", flush=True)
        if got != want:
            wrong += 1
            print(out[-4000:], file=sys.stderr)
    print(f"{wrong} wrong" if wrong else "every run says what it should")
    return 1 if wrong else 0


if __name__ == "__main__":
    tools.rerun_in_test_slot()
    sys.exit(main())
