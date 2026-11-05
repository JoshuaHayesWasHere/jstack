"""The A/B harness: two revisions on the same task set, with a paired verdict.

    uv run python features/evals/ab/ab.py run --a <rev> --b <rev> --tasks <file>
        [--kind prompt|replay] [--out <dir>] [--seed <n>] [--trials <n>] [--model <id>]
        [--effort <level>] [--workers <n>]
    uv run python features/evals/ab/ab.py rescore <run dir> [--seed <n>] [--tasks <file>]
        [--out <file>]

`run` reads the revisions from the git repository of the current directory.
- `prompt`: each task's files are read from each revision with `git show`, never from the working
  tree, and asked of `claude -p` with no tools, `--trials` times in each of three arms: A, A-again
  (the same prompts as A, so the noise floor) and B. The jobs are shuffled together by
  `random.Random(seed)`, each answer kept as it comes, scored blind from its text and its task, and
  `results.md` says the verdict of `README.md`, "The rule", per family.
- `replay`: `features/evals/benchmark/replay.sh` of this checkout, once per arm, each arm in its own
  `git worktree`, and a diff of every event's decision. No model runs.

`rescore` reports a kept run again and calls no model: a run of this harness, or a kept run of the
skill-cut eval (`features/evals/evals/skill-cut/run-*`), read from its `key.json` and `scores.json`
as `score.py` wrote them, base as A, base again as A-again and the variant as B. It writes into no
run directory: `--out` names the file `results.md` goes to.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _stats():
    """`stats.py` beside this file, loaded under a name of its own."""
    name = "ab_stats"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, HERE / "stats.py")
        sys.modules[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules[name])
    return sys.modules[name]


stats = _stats()

ARMS = ("A", "A-again", "B")
SKILL_CUT_ARMS = {"base": "A", "base-again": "A-again", "variant": "B"}
SKILL_CUT_KINDS: dict[str, stats.Kind] = {"lead": "graded", "steps": "pass/fail"}
REPLAY = HERE.parent / "benchmark" / "replay.sh"
REPLAY_EVENTS = ("plain", "conflict", "redmain", "findings", "limit", "launch", "batch")
MODEL, EFFORT, TRIALS, WORKERS = "claude-opus-5-5", "medium", 3, 6


class Refused(SystemExit):
    def __init__(self, said: str):
        super().__init__(f"ab.py: {said}")


@dataclass(frozen=True)
class Job:
    """One call of one task in one arm: what every source becomes before any statistics."""

    task: str
    family: str
    arm: str
    trial: int


@dataclass(frozen=True)
class Call:
    usd: float
    tokens: int


@dataclass(frozen=True)
class Run:
    """A run of any source. `calls` and `errors` are None where the source kept no cost or no
    count of failed calls, as a skill-cut run did not."""

    meta: dict
    families: dict[str, tuple[stats.Kind, float]]
    jobs: dict[str, Job]
    scores: dict[str, float]
    calls: dict[str, Call] | None
    errors: dict[str, int] | None


def by_arm(run: Run, family: str) -> dict[str, dict[str, list[float]]]:
    out: dict[str, dict[str, list[float]]] = {arm: {} for arm in ARMS}
    for name in sorted(run.jobs, key=lambda n: (run.jobs[n].task, run.jobs[n].trial, n)):
        job = run.jobs[name]
        if job.family == family:
            out[job.arm].setdefault(job.task, []).append(run.scores[name])
    return out


def report(run: Run, seed: int) -> tuple[list[str], str]:
    """The verdict line of each family, and `results.md`. The same run and seed give the same
    bytes."""
    lines, verdicts = [], []
    for family in sorted(run.families):
        kind, mde = run.families[family]
        arms = by_arm(run, family)
        said = stats.verdict(kind, mde, arms["A"], arms["A-again"], arms["B"], f"{seed}:{family}")
        verdicts.append((family, arms, said))
        lines.append(verdict_line(run, family, arms, said))
    m = run.meta
    md = [
        "# A/B: results",
        "",
        "Written by `features/evals/ab/ab.py`, never by hand.",
        'The rule is `features/evals/ab/README.md`, "The rule".',
        "",
        f"A: `{m['a']['sha']}` (`{m['a']['rev']}`).",
        f"B: `{m['b']['sha']}` (`{m['b']['rev']}`).",
        f"Source: {m['source']}.",
        f"Model: `{m['model']}` at `{m['effort']}` effort, {m['trials']} trials a task and arm.",
        f"Bootstrap seed: {seed}, {stats.RESAMPLES} resamples over tasks, "
        "2.5 and 97.5 percentiles.",
    ]
    for (family, arms, _), line in zip(verdicts, lines, strict=True):
        kind, _ = run.families[family]
        md += [
            "",
            f"## Family `{family}` ({kind}): each task, the mean of its trials",
            "",
            "| Task | A | A-again | B |",
            "|---|---|---|---|",
        ]
        for task in sorted(arms["A"]):
            cells = " | ".join(f"{sum(arms[arm][task]) / len(arms[arm][task]):.3f}" for arm in ARMS)
            md.append(f"| `{task}` | {cells} |")
        md += ["", line]
    md += [
        "",
        "## How to read it",
        "",
        "Each verdict line gives B minus A over the tasks with its 95% interval, the same for "
        "A-again minus A (the noise floor), and the mde, the smallest mean difference the rule "
        "calls.",
        "`no measurable difference` with an interval of [-0.02, +0.02] says the run could not have "
        "shown a change smaller than about 0.02, not that there is none.",
    ]
    return lines, "\n".join(md) + "\n"


def fmt(i: stats.Interval) -> str:
    return f"{i.mean:+.3f} [{i.low:+.3f}, {i.high:+.3f}]"


def verdict_line(run: Run, family: str, arms: dict, said: stats.Verdict) -> str:
    tasks = len(arms["A"])
    per_arm = sum(len(v) for v in arms["A"].values())
    parts = [
        f"{family}: {said.word}",
        f"B - A {fmt(said.diff)}",
        f"A/A {fmt(said.aa)}"
        + (", excludes 0 below the mde" if said.aa_excludes_below_mde else ""),
        f"mde {said.mde:.3f}",
        f"{tasks} tasks, {per_arm} runs an arm",
    ]
    if said.exact is not None and said.exact_aa is not None:
        f, t = said.exact.failed, said.exact.total
        parts.append(
            f"failed trials A {f[0]}/{t[0]}, "
            f"A-again {said.exact_aa.failed[1]}/{said.exact_aa.total[1]}, "
            f"B {f[1]}/{t[1]}, Fisher p B {said.exact.p:.3f}, A/A {said.exact_aa.p:.3f}"
        )
    names = {
        arm: [n for n, j in run.jobs.items() if j.family == family and j.arm == arm] for arm in ARMS
    }
    if run.errors is None:
        parts.append("errors not recorded")
    else:
        parts.append(
            "errors "
            + ", ".join(f"{arm} {sum(run.errors.get(n, 0) for n in names[arm])}" for arm in ARMS)
        )
    if run.calls is None:
        parts.append("cost not recorded")
    else:
        cost = {
            arm: (
                sum(run.calls[n].usd for n in names[arm]),
                sum(run.calls[n].tokens for n in names[arm]),
            )
            for arm in ARMS
        }
        parts.append(
            "cost "
            + ", ".join(f"{arm} ${usd:.2f} {tokens} tokens" for arm, (usd, tokens) in cost.items())
        )
    return "; ".join(parts)


def read_skill_cut(path: Path) -> Run:
    """A kept skill-cut run, as `score.py` scored it: nothing is scored again, and no model is
    asked."""
    ran = json.loads((path / "run.json").read_text())
    key = json.loads((path / "key.json").read_text())
    scores = json.loads((path / "scores.json").read_text())
    if set(key) != set(scores):
        raise Refused(f"{path.name}: key.json and scores.json name different answers")
    left = [n for n, s in scores.items() if s["value"] is None]
    if left:
        raise Refused(
            f"{path.name}: {len(left)} answers are unsettled: "
            "the skill-cut eval's judge has not run"
        )
    jobs = {
        n: Job(k["case"], k["case"].split("/", 1)[0], SKILL_CUT_ARMS[k["arm"]], k["trial"])
        for n, k in key.items()
    }
    families = {
        f: (SKILL_CUT_KINDS[f], stats.MDE[SKILL_CUT_KINDS[f]])
        for f in {j.family for j in jobs.values()}
    }
    meta = {
        "a": {"rev": "base", "sha": ran["base"]},
        "b": {"rev": "variant", "sha": ran["variant"]},
        "source": f"the kept skill-cut run `{path.name}`, scored by its `score.py`",
        "model": ran["model"],
        "effort": ran["effort"],
        "trials": ran["trials"],
    }
    return Run(meta, families, jobs, {n: s["value"] for n, s in scores.items()}, None, None)


def read_ab(path: Path, tasks: Path | None) -> Run:
    """A run of this harness, scored again from its answers and its task file."""
    ran = json.loads((path / "run.json").read_text())
    if ran["kind"] != "prompt":
        raise Refused(
            f"{path.name} is a {ran['kind']} run: only a prompt run has a verdict to rescore"
        )
    file = tasks or Path(ran["tasks"]["path"])
    if not file.is_file() or sha256(file) != ran["tasks"]["sha256"]:
        raise Refused(
            f"{file} is not the task file {path.name} was answered against "
            f"(sha256 {ran['tasks']['sha256'][:12]})"
        )
    spec = load_tasks(file)
    key = json.loads((path / "key.json").read_text())
    answers = kept(path / "answers.jsonl")
    missing = [n for n in key if n not in answers]
    if missing:
        raise Refused(
            f"{path.name}: {len(missing)} of {len(key)} jobs have no answer: "
            "run the same `run` again"
        )
    tasks_by_id = {t["id"]: t for t in spec["tasks"]}
    jobs = {
        n: Job(k["task"], tasks_by_id[k["task"]]["family"], k["arm"], k["trial"])
        for n, k in key.items()
    }
    scores = {
        n: score(answers[n]["answer"], tasks_by_id[jobs[n].task], spec, file.parent)
        for n in sorted(key)
    }
    calls = {n: Call(answers[n]["usd"], answers[n]["tokens"]) for n in key}
    errors: dict[str, int] = {}
    for line in read_lines(path / "errors.jsonl"):
        errors[line["id"]] = errors.get(line["id"], 0) + 1
    meta = {
        **ran,
        "source": f"a prompt run of this harness, task file sha256 `{ran['tasks']['sha256'][:12]}`",
    }
    return Run(meta, families_of(spec), jobs, scores, calls, errors)


def families_of(spec: dict) -> dict[str, tuple[stats.Kind, float]]:
    return {
        name: (f["kind"], float(f.get("mde", stats.MDE[f["kind"]])))
        for name, f in sorted(spec["families"].items())
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_tasks(path: Path) -> dict:
    """A prompt task file, checked once here so the rest trusts it."""
    try:
        spec = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise Refused(f"--tasks {path}: {error}") from None
    families, tasks = spec.get("families"), spec.get("tasks")
    if not isinstance(families, dict) or not isinstance(tasks, list) or not tasks:
        raise Refused(f"--tasks {path}: a prompt task file holds `families` and a list of `tasks`")
    for name, f in families.items():
        if f.get("kind") not in stats.KINDS:
            raise Refused(
                f"--tasks {path}: family {name}: `kind` is one of {', '.join(stats.KINDS)}"
            )
        if f["kind"] == "graded" and not f.get("score"):
            raise Refused(f"--tasks {path}: family {name} is graded: it names a `score` command")
    ids = [t.get("id") for t in tasks]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) and i for i in ids):
        raise Refused(f"--tasks {path}: every task has an `id` of its own")
    for t in tasks:
        if t.get("family") not in families or not isinstance(t.get("prompt"), str):
            raise Refused(
                f"--tasks {path}: task {t['id']} names a family of the file and a `prompt`"
            )
        if families[t["family"]]["kind"] == "pass/fail" and not t.get("must"):
            raise Refused(
                f"--tasks {path}: task {t['id']} is pass/fail: it names `must` expressions"
            )
    return spec


def score(answer: str, task: dict, spec: dict, where: Path) -> float:
    """One answer, from its text and its task alone: the arm is not given."""
    family = spec["families"][task["family"]]
    if family["kind"] == "pass/fail":
        return 1.0 if all(re.search(m, answer, re.M | re.S) for m in task["must"]) else 0.0
    ran = subprocess.run(
        family["score"],
        input=answer,
        capture_output=True,
        text=True,
        cwd=where,
        env={**os.environ, "AB_TASK": json.dumps(task)},
    )
    try:
        value = float(ran.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        raise Refused(
            f"the score command of {task['family']} printed no number for {task['id']}: "
            f"{ran.stderr.strip()[-300:]}"
        ) from None
    if ran.returncode or not 0 <= value <= 1:
        raise Refused(
            f"the score command of {task['family']} gave {value} for {task['id']}, "
            f"exit {ran.returncode}"
        )
    return value


def git(*args: str) -> str:
    ran = subprocess.run(["git", *args], capture_output=True, text=True)
    if ran.returncode:
        raise Refused(f"git {' '.join(args)}: {ran.stderr.strip()}")
    return ran.stdout


def resolve(rev: str) -> str:
    return git("rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []


def kept(path: Path) -> dict[str, dict]:
    return {line["id"]: line for line in read_lines(path)}


def plan(spec: dict, trials: int, seed: int) -> list[tuple[str, Job]]:
    """Every job with its blind id, in the order they are asked: all arms shuffled together by
    `random.Random(seed)`, so no arm runs in a block, and the ids drawn from the same generator,
    so the same seed gives the same ids and the same order."""
    jobs = [
        Job(t["id"], t["family"], arm, trial)
        for t in spec["tasks"]
        for arm in ARMS
        for trial in range(1, trials + 1)
    ]
    rng = random.Random(seed)
    rng.shuffle(jobs)
    ids: list[str] = []
    while len(ids) < len(jobs):
        name = f"{rng.getrandbits(48):012x}"
        if name not in ids:
            ids.append(name)
    return list(zip(ids, jobs, strict=True))


def prompt_of(task: dict, files: dict[str, str]) -> str:
    blocks = [f'<file path="{p}">\n{files[p].strip()}\n</file>' for p in task.get("files", [])]
    return "\n\n".join([*blocks, task["prompt"]])


def claude(text: str, model: str, effort: str) -> dict:
    """One call with no tools, its answer and its cost from `--output-format json`. One try: a
    failure is kept, and the next run asks again for it alone."""
    ran = subprocess.run(
        [
            "claude",
            "-p",
            "--model",
            model,
            "--effort",
            effort,
            "--output-format",
            "json",
            "--tools",
            "",
            "--strict-mcp-config",
            "--setting-sources",
            "",
            "--no-session-persistence",
        ],
        input=text,
        capture_output=True,
        text=True,
        cwd=tempfile.gettempdir(),
        timeout=900,
    )
    try:
        said = json.loads(ran.stdout)
    except json.JSONDecodeError:
        said = {}
    if ran.returncode or said.get("is_error") or not str(said.get("result", "")).strip():
        raise RuntimeError(
            f"claude exited {ran.returncode}: {(ran.stderr or ran.stdout).strip()[-300:]}"
        )
    usage = said.get("usage") or {}
    return {
        "answer": said["result"].strip() + "\n",
        "usd": float(said.get("total_cost_usd") or 0),
        "tokens": sum(v for k, v in usage.items() if k.endswith("_tokens") and isinstance(v, int)),
        "turns": said.get("num_turns"),
        "ms": said.get("duration_ms"),
    }


def identity(args, kind: str, a: str, b: str, tasks: Path) -> dict:
    """What a run is: the same identity resumes it, any other is refused in its directory."""
    return {
        "kind": kind,
        "seed": args.seed,
        "a": {"rev": args.a, "sha": a},
        "b": {"rev": args.b, "sha": b},
        "tasks": {"path": str(tasks.resolve()), "sha256": sha256(tasks)},
        "model": args.model if kind == "prompt" else None,
        "effort": args.effort if kind == "prompt" else None,
        "trials": args.trials if kind == "prompt" else 1,
    }


def start(out: Path, ran: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    was = out / "run.json"
    if was.is_file() and json.loads(was.read_text()) != ran:
        raise Refused(f"{out} holds another run (its run.json differs): give another --out")
    was.write_text(json.dumps(ran, indent=2) + "\n")


def run_prompt(args, out: Path, a: str, b: str) -> int:
    tasks = Path(args.tasks)
    spec = load_tasks(tasks)
    ran = identity(args, "prompt", a, b, tasks)
    order = plan(spec, args.trials, args.seed)
    start(out, ran)
    (out / "jobs.json").write_text(json.dumps([n for n, _ in order], indent=2) + "\n")
    (out / "which.json").write_text(
        json.dumps({n: j.task for n, j in sorted(order)}, indent=2) + "\n"
    )
    key = {n: {"task": j.task, "arm": j.arm, "trial": j.trial} for n, j in sorted(order)}
    (out / "key.json").write_text(json.dumps(key, indent=2) + "\n")
    answers = kept(out / "answers.jsonl")
    missing = [(n, j) for n, j in order if n not in answers]
    if missing and not shutil.which("claude"):
        raise Refused("run: no claude on PATH, nothing is asked")
    paths = sorted({p for t in spec["tasks"] for p in t.get("files", [])})
    files = {sha: {p: git("show", f"{sha}:{p}") for p in paths} for sha in {a, b}}
    tasks_by_id = {t["id"]: t for t in spec["tasks"]}
    sha_of = {"A": a, "A-again": a, "B": b}

    def ask(item):
        name, job = item
        try:
            return (
                name,
                claude(
                    prompt_of(tasks_by_id[job.task], files[sha_of[job.arm]]),
                    args.model,
                    args.effort,
                ),
                None,
            )
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            return name, None, str(error)

    failed = 0
    with (
        concurrent.futures.ThreadPoolExecutor(args.workers) as pool,
        (out / "answers.jsonl").open("a") as keep,
        (out / "errors.jsonl").open("a") as errs,
    ):
        for name, said, error in pool.map(ask, missing):
            if error is not None:
                failed += 1
                errs.write(json.dumps({"id": name, "error": error}) + "\n")
                errs.flush()
                continue
            keep.write(json.dumps({"id": name, **said}, ensure_ascii=False) + "\n")
            keep.flush()
            answers[name] = said
    print(f"run: {len(answers)} of {len(order)} answered, {failed} failed now", flush=True)
    if failed:
        print(
            f"ab.py: run: {failed} calls failed and are kept in {out}/errors.jsonl: "
            "run the same command again, which asks only for those",
            file=sys.stderr,
        )
        return 1
    run = read_ab(out, tasks)
    (out / "scores.json").write_text(json.dumps(run.scores, indent=2) + "\n")
    lines, md = report(run, args.seed)
    (out / "results.md").write_text(md)
    print("\n".join(lines))
    print(f"results: {out}/results.md")
    return 0


_SANDBOX = re.compile(r"verify-jstack\.[A-Za-z0-9]{6,}")
_TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)")
_SHA = re.compile(r"\b[0-9a-f]{40}\b")


def normal(text: str) -> str:
    """What differs between two replays of one checkout, and nothing else, made the same: the
    sandbox's directory, the time of day, and the commits the sandbox makes at launch, which take
    the clock into their ids. The heads the replay seeds (`bbbb...`) are one character repeated
    and are kept."""
    text = _SANDBOX.sub("verify-jstack.<sandbox>", text)
    text = _TIME.sub("<time>", text)
    return _SHA.sub(lambda m: m[0] if len(set(m[0])) == 1 else "<commit>", text)


def decisions(where: Path, event: str) -> dict[str, str]:
    """Every file the replay keeps of an event's today side, made normal."""
    return {
        p.name.split(".", 2)[2]: normal(p.read_text())
        for p in sorted(where.glob(f"{event}.1.today*"))
    }


def replay_arm(sha: str, arm: str, out: Path, events: list[str]) -> None:
    """One arm: its revision in a worktree of its own, replay.sh over it, the worktree removed."""
    done = (
        {json.loads(line)["event"] for line in (out / "today.jsonl").read_text().splitlines()}
        if (out / "today.jsonl").is_file()
        else set()
    )
    if set(events) <= done:
        print(f"replay: {arm} is kept already in {out}")
        return
    tree = Path(tempfile.mkdtemp(prefix=f"ab-{sha[:12]}-{arm}-"))
    tree.rmdir()
    git("worktree", "add", "--detach", str(tree), sha)
    try:
        env = {k: v for k, v in os.environ.items() if k != "VERIFY_JSTACK_SANDBOX"}
        ran = subprocess.run(
            [str(REPLAY), str(tree), str(out), "--runs", "1", "--events", " ".join(events)],
            env=env,
            capture_output=True,
            text=True,
        )
        (out.parent / f"{arm}.log").write_text(ran.stdout + ran.stderr)
        if ran.returncode:
            raise Refused(
                f"replay of {arm} at {sha[:12]} exited {ran.returncode}: see {out.parent}/{arm}.log"
            )
    finally:
        git("worktree", "remove", "--force", str(tree))


def say(decided: dict[str, str]) -> str:
    """An event's decision on one line: what poll, failover and `jmerge --check` printed."""
    parts = ("today-poll.txt", "today-failover.txt", "today.txt")
    lines = [ln.strip() for part in parts for ln in decided.get(part, "").splitlines()]
    return " / ".join(ln for ln in lines if ln) or "nothing"


def run_replay(args, out: Path, a: str, b: str) -> int:
    tasks = Path(args.tasks)
    try:
        events = json.loads(tasks.read_text())["events"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise Refused(f"--tasks {tasks}: a replay task file holds `events`: {error}") from None
    unknown = [e for e in events if e not in REPLAY_EVENTS]
    if not events or unknown:
        raise Refused(
            f"--tasks {tasks}: the events are {', '.join(REPLAY_EVENTS)}, "
            f"not {', '.join(unknown) or 'none'}"
        )
    start(out, identity(args, "replay", a, b, tasks))
    for arm, sha in (("A", a), ("B", b)):
        replay_arm(sha, arm, out / arm, events)
    tokens = {
        arm: sum(
            json.loads(line)["tokens"]
            for line in (out / arm / "today.jsonl").read_text().splitlines()
        )
        for arm in ("A", "B")
    }
    lines, changed = [], 0
    md = [
        "# A/B: replay",
        "",
        "Written by `features/evals/ab/ab.py`, never by hand.",
        "No model ran: the replay's today side is jbus and jmerge, so one run per arm is the whole "
        "answer, and the result is a diff of decisions, not a statistic.",
        "",
        f"A: `{a}` (`{args.a}`).",
        f"B: `{b}` (`{args.b}`).",
        f"Tokens: A {tokens['A']}, B {tokens['B']}.",
        "",
        "| Event | A decides | B decides | Same |",
        "|---|---|---|---|",
    ]
    for event in events:
        da, db = decisions(out / "A", event), decisions(out / "B", event)
        same = da == db
        changed += not same
        lines.append(f"{event}: {'same' if same else 'CHANGED'}: A {say(da)} | B {say(db)}")
        md.append(f"| `{event}` | {say(da)} | {say(db)} | {'yes' if same else '**no**'} |")
    lines.append(
        f"replay: {changed} of {len(events)} events decided differently; "
        f"tokens A {tokens['A']}, B {tokens['B']}"
    )
    md += [
        "",
        lines[-1] + ".",
        "",
        "A changed event's files are in `A/` and `B/` as replay.sh wrote them.",
    ]
    (out / "results.md").write_text("\n".join(md) + "\n")
    print("\n".join(lines))
    print(f"results: {out}/results.md")
    return 0


def rescore(args) -> int:
    path = Path(args.dir)
    ran_file = path / "run.json"
    if not ran_file.is_file():
        raise Refused(f"rescore: {path} has no run.json: it names a run directory")
    ran = json.loads(ran_file.read_text())
    if "kind" in ran:
        run = read_ab(path, Path(args.tasks) if args.tasks else None)
        seed = ran["seed"] if args.seed is None else args.seed
    elif "variant" in ran:
        run = read_skill_cut(path)
        seed = 0 if args.seed is None else args.seed
    else:
        raise Refused(f"rescore: {path} is neither a run of this harness nor a skill-cut run")
    lines, md = report(run, seed)
    print("\n".join(lines))
    if args.out:
        Path(args.out).write_text(md)
        print(f"results: {args.out}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ab.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run A, A-again and B over a task file")
    run.add_argument("--a", required=True, help="the revision A, the one compared against")
    run.add_argument("--b", required=True, help="the revision B")
    run.add_argument("--tasks", required=True, help="the task file")
    run.add_argument("--kind", choices=("prompt", "replay"), default="prompt")
    run.add_argument(
        "--out", help="the run directory, by default $TMPDIR/ab-<kind>-<a>-<b>-seed<seed>"
    )
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--trials", type=int, default=TRIALS)
    run.add_argument("--model", default=MODEL)
    run.add_argument("--effort", default=EFFORT)
    run.add_argument("--workers", type=int, default=WORKERS)
    again = sub.add_parser("rescore", help="report a kept run again, with no model")
    again.add_argument("dir")
    again.add_argument("--seed", type=int, help="the bootstrap's seed, by default the run's, or 0")
    again.add_argument("--tasks", help="the task file, when it moved since the run")
    again.add_argument("--out", help="write results.md here")
    args = parser.parse_args(argv)
    if args.command == "rescore":
        return rescore(args)
    if args.trials < 1 or args.workers < 1:
        raise Refused("run: --trials and --workers are 1 or more")
    a, b = resolve(args.a), resolve(args.b)
    out = Path(
        args.out
        or Path(tempfile.gettempdir()) / f"ab-{args.kind}-{a[:12]}-{b[:12]}-seed{args.seed}"
    )
    return (run_prompt if args.kind == "prompt" else run_replay)(args, out, a, b)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
