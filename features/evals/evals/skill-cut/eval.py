"""The skill-cut eval: does a variant of skill text change what an agent does under it?

One command runs it, from the root of the repo:

    uv run python features/evals/evals/skill-cut/eval.py --base main --variant HEAD

It reads every file under test from the two revisions with `git show <rev>:<path>`, never
from the working tree, and runs each case of `cases/` three times in each of three arms: base,
base again (the noise floor) and variant. Then:

- `write`: each answer goes to `run-<name>/answers.json` under a random id, which case it answers to
  `run-<name>/which.json`, and which arm and trial wrote it only to `run-<name>/key.json`. What a
  model wrote has the private patterns of `jleak` taken out, as the cases have.
- `score`: runs `score.py` over each answer with its case's key and no arm, and writes
  `run-<name>/scores.json`, keyed by the random ids.
- `judge`: asks the judge model about each answer the key could not settle, and keeps what it
  said in `run-<name>/judge.json`; `score` then runs again.
- `report`: joins the scores with the key and writes `run-<name>/results.md`, with the rule in
  `README.md` for whether the variant regresses.

`eval.py --run run-1` rescores and reports a kept run with no model call, against the cases it
was answered against: `run.json` holds their hash, and a run whose cases changed is refused.
`eval.py cases <dir>` rebuilds `cases/lead/` from the extraction's JSON files.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import importlib.util
import json
import os
import random
import re
import secrets
import shutil
import statistics
import subprocess
import sys
import tempfile
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path[:0] = [str(REPO / "features" / "jleak" / "src")]


def _scorer():
    """`score.py` beside this file, loaded under a name of its own, so that it never takes the
    place of another `score` module in one process."""
    name = "skill_cut_score"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, HERE / "score.py")
        sys.modules[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules[name])
    return sys.modules[name]


buckets, score_lead, score_steps = _scorer().buckets, _scorer().score_lead, _scorer().score_steps


import jleak  # noqa: E402

MODEL = "claude-opus-5-5"
JUDGE = "claude-sonnet-5-5"
EFFORT = "medium"
TRIALS = 3
WORKERS = 6
ARMS = ("base", "base-again", "variant")
FAMILIES = ("lead", "steps")
STEP5 = "skills/interrogate/SKILL.md"
REFERENCE = "skills/interrogate/references/lead-judgment.md"
LEAD_FILES = (STEP5, REFERENCE)

LEAD = """You are the lead reviewer of a pull request's review. The readers below read the diff \
against the intent and listed what they found; you have the intent and their findings, not the \
code. Do the lead judgment as the step and its reference below say.

<step path="{step_path}">
{step}
</step>

<reference path="{reference_path}">
{reference}
</reference>

{case}

Write your judgment as the step says. Then end your answer with a block that starts with a line \
`BUCKETS` and has one line for every finding id above, in the order they are listed, each as \
`<id>: <bucket>`, where the bucket is one of Act on, Consider, Noted, Dismissed. Findings you \
merged get the same bucket.
"""

STEPS = """You are a thread working under the file below, which is loaded in full.

<file path="{path}">
{text}
</file>

{state}

What do you do next? Answer in at most six lines: what you do first, the step or section of the \
file you follow, and the exact command, tool call or line you run or write. You cannot run \
anything here: say it.
"""

JUDGE_LEAD = """Below is a lead reviewer's answer, which judged a list of findings with ids \
such as A1 and B2. For each of these ids: {ids}, say which bucket the answer put that finding \
in: Act on, Consider, Noted or Dismissed, or none if the answer does not say. Reply with one \
line per id, `<id>: <bucket or none>`, and nothing else.

<answer>
{answer}
</answer>
"""

JUDGE_STEPS = """Below is the next step a thread was expected to take, and the answer it gave. \
Does the answer take that step (the same action, in any words)? Reply with YES or NO on the \
first line, then one line saying why.

<expected>
{expect}
</expected>

<answer>
{answer}
</answer>
"""


def claude(prompt: str, model: str = MODEL) -> str:
    """One call, no tools, at medium effort, with the model named and two more tries for a call
    that fails."""
    said = ""
    for _ in range(3):
        ran = subprocess.run(
            [
                "claude",
                "-p",
                "--model",
                model,
                "--effort",
                EFFORT,
                "--tools",
                "",
                "--strict-mcp-config",
                "--setting-sources",
                "",
                "--no-session-persistence",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            cwd="/tmp",
            timeout=900,
        )
        if ran.returncode == 0 and ran.stdout.strip():
            return ran.stdout.strip()
        said = ran.stderr.strip()[-400:] or ran.stdout.strip()[-400:]
    raise RuntimeError(f"claude exited {ran.returncode}: {said}")


def _private() -> tuple[jleak.Pattern, ...]:
    """The private patterns of `jleak`, found as `jleak` finds them. With none, nothing that
    could hold them is written into the repo."""
    config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    try:
        return jleak.load(jleak.path(Path(config)))
    except jleak.Invalid as error:
        raise SystemExit(f"eval.py: {error}: the eval writes nothing it cannot redact") from None


def _redact(text: str, patterns: tuple[jleak.Pattern, ...]) -> str:
    """Take the private patterns out, line by line, as `jleak` matches them. A pattern anchored
    at the start of a line (`^.*\\bname\\b`) matches from there, so only the last word of its
    match is taken out, not the line before it."""
    lines = text.split("\n")
    for at, line in enumerate(lines):
        for pattern in patterns:
            anchored = re.match(r"(?:\(\?[a-zA-Z]+\))?\^", pattern.regex.pattern)
            for _ in range(100):
                found = pattern.regex.search(line)
                if not found:
                    break
                start, end = found.span()
                if anchored:
                    word = re.search(r"\w+\W*$", found[0])
                    start = start + word.start() if word else start
                line = line[:start] + "the user" + line[end:]
            else:
                raise SystemExit(f"eval.py: {pattern.name} still matches after 100 redactions")
        lines[at] = line
    return "\n".join(lines)


def git(*args: str) -> str:
    ran = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if ran.returncode:
        raise SystemExit(f"eval.py: git {' '.join(args)}: {ran.stderr.strip()}")
    return ran.stdout


def resolve(rev: str) -> str:
    return git("rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def spellings(path: str) -> tuple[str, ...]:
    """The paths a file a case names has had: a principle as `principles/<name>.md` before it
    took pstack's prefix, `principles/principle-<name>.md` after, and
    `features/principles/skills/principle-<name>/SKILL.md` once it is a skill, and a skill's file
    as `skills/<name>/<file>` before its move and `features/<name>/<file>` or
    `features/<feature>/skills/<name>/<file>` after, so a case names it either way."""
    if path.startswith("principles/"):
        name = path.removeprefix("principles/").removeprefix("principle-")
        skill = f"features/principles/skills/principle-{name.removesuffix('.md')}/SKILL.md"
        return (skill, f"principles/principle-{name}", f"principles/{name}")
    if path.startswith("skills/"):
        rest = path.removeprefix("skills/")
        held = sorted(
            one.relative_to(REPO).parts[1] for one in REPO.glob(f"features/*/skills/{rest}")
        )
        return (path, *(f"features/{one}/skills/{rest}" for one in held), "features/" + rest)
    return (path,)


def show(rev: str, path: str) -> str:
    """A file as it is at a revision, never from the working tree, read under the path it has
    there (`spellings`)."""
    *before, last = spellings(path)
    for each in before:
        try:
            return git("show", f"{rev}:{each}")
        except SystemExit:
            continue
    return git("show", f"{rev}:{last}")


def step5(skill: str) -> str:
    """Step 5 of the interrogate skill and the output format under it, to the end of the file."""
    found = re.search(r"^## Step 5\b.*", skill, re.M | re.S)
    if not found:
        raise SystemExit(f"eval.py: {STEP5} has no '## Step 5' at this revision")
    return found[0].strip()


# The cases.


def steps_cases() -> list[dict]:
    return json.loads((HERE / "cases" / "steps.json").read_text())


def lead_cases() -> list[str]:
    return sorted(path.stem for path in (HERE / "cases" / "lead").glob("*.md"))


def lead_key(slug: str) -> dict[str, dict]:
    return json.loads((HERE / "cases" / "lead" / f"{slug}.key.json").read_text())["key"]


def case_ids() -> dict[str, str]:
    """Every case, by id, with its family."""
    found = {f"lead/{slug}": "lead" for slug in lead_cases()}
    found.update({f"steps/{case['id']}": "steps" for case in steps_cases()})
    return found


def files_under_test() -> list[str]:
    return sorted({*LEAD_FILES, *(case["file"] for case in steps_cases())})


def cases(staging: str) -> None:
    """Rebuild `cases/lead/` from the extraction's JSON files: the readers' findings and the
    shipped Review, with the intent from `/tmp/pr-review-<slug>.*/intent`, the oldest
    directory of the slug, which the first review built."""
    patterns, out = _private(), HERE / "cases" / "lead"
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in sorted(Path(staging).glob("*.json")):
        said = json.loads(path.read_text())
        slug = said["slug"]
        if not said.get("key"):
            print(f"cases: {slug} has no key, left out")
            continue
        dirs = sorted(Path("/tmp").glob(f"pr-review-{slug}.*"), key=lambda d: d.stat().st_mtime)
        intents = [d / "intent" for d in dirs if (d / "intent").is_file()]
        if not intents:
            print(f"cases: {slug} has no intent under /tmp, left out")
            continue
        body = [f"# {slug}", "", "## Intent", "", intents[0].read_text().strip(), "", "## Findings"]
        for reader in sorted(said["readers"]):
            for finding in said["readers"][reader]:
                body += ["", f"### {finding['id']}", "", finding["text"].strip()]
        (out / f"{slug}.md").write_text(_redact("\n".join(body), patterns) + "\n")
        key = {k: said[k] for k in ("slug", "reviewer", "head", "review", "key", "notes")}
        text = _redact(json.dumps(key, indent=2, ensure_ascii=False), patterns)
        (out / f"{slug}.key.json").write_text(text + "\n")
        written += 1
    print(f"cases: {written} lead cases written to {out}")


# A run.


def prompt(case: str, files: dict[str, str]) -> str:
    family, name = case.split("/", 1)
    if family == "lead":
        body = (HERE / "cases" / "lead" / f"{name}.md").read_text()
        body = body.split("\n", 1)[1].strip()
        return LEAD.format(
            step_path=STEP5,
            step=step5(files[STEP5]),
            reference_path=REFERENCE,
            reference=files[REFERENCE].strip(),
            case=body,
        )
    found = next(one for one in steps_cases() if one["id"] == name)
    return STEPS.format(path=found["file"], text=files[found["file"]].strip(), state=found["state"])


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def runs() -> list[Path]:
    """The kept runs, `run-<name>/`."""
    return sorted(path for path in HERE.glob("run-*") if path.is_dir())


def cases_sha() -> str:
    """One hash of every file under `cases/`, its path and its bytes: what a run was answered
    and scored against."""
    digest = hashlib.sha256()
    for path in sorted(p for p in (HERE / "cases").rglob("*") if p.is_file()):
        digest.update(path.relative_to(HERE).as_posix().encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()[:12]


def _same_cases() -> None:
    """A kept run is scored only against the cases it was answered against: a change to a case
    is a new case set, and a new run from base."""
    was = json.loads((RUN / "run.json").read_text()).get("cases")
    if was != cases_sha():
        raise SystemExit(
            f"eval.py: {RUN.name} was answered against cases {was}, and cases/ is {cases_sha()} "
            "now: write a new run, the kept one is not rescored against other cases"
        )


def write(base: str, variant: str, name: str | None = None) -> None:
    """Write a new run next to the kept ones, `run-<the variant's first 12>/` or the `name`
    given, so two branches that each add a run never pick the same directory. It is built in a
    directory of its own and put in place by one rename once its last answer and its key are
    written, so a call that fails leaves no part of it and no kept run is touched."""
    global RUN
    if not shutil.which("claude"):
        raise SystemExit("eval.py: write: no claude on PATH, no run is written")
    revs = {"base": resolve(base), "variant": resolve(variant)}
    made = HERE / (name or f"run-{revs['variant'][:12]}")
    if not re.fullmatch(r"run-[A-Za-z0-9._-]+", made.name):
        raise SystemExit(f"eval.py: write: {made.name} is not run-<letters, digits, . _ ->")
    if made.exists():
        raise SystemExit(f"eval.py: write: {made.name} is kept already: give --name")
    patterns = _private()
    cases = cases_sha()
    paths = files_under_test()
    text = {arm: {p: show(rev, p) for p in paths} for arm, rev in revs.items()}
    text["base-again"] = text["base"]
    jobs = [
        (case, arm, trial) for case in case_ids() for arm in ARMS for trial in range(1, 1 + TRIALS)
    ]
    random.shuffle(jobs)
    fresh = Path(tempfile.mkdtemp(prefix=".write-", dir=HERE))
    try:
        key, which, answers = {}, {}, {}
        with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
            done = pool.map(lambda job: (job, claude(prompt(job[0], text[job[1]]))), jobs)
            for (case, arm, trial), answer in done:
                name = secrets.token_hex(6)
                answers[name] = _redact(answer, patterns) + "\n"
                key[name] = {"case": case, "arm": arm, "trial": trial}
                which[name] = case
                print(f"write: {len(key)} of {len(jobs)}", flush=True)
        shuffled = sorted(key)
        (fresh / "answers.json").write_text(
            json.dumps({n: answers[n] for n in shuffled}, indent=2, ensure_ascii=False) + "\n"
        )
        (fresh / "key.json").write_text(json.dumps({n: key[n] for n in shuffled}, indent=2) + "\n")
        (fresh / "which.json").write_text(
            json.dumps({n: which[n] for n in shuffled}, indent=2) + "\n"
        )
        ran = {
            "base": revs["base"],
            "variant": revs["variant"],
            "model": MODEL,
            "judge": JUDGE,
            "effort": EFFORT,
            "trials": TRIALS,
            "cases": cases,
            "files": {
                p: {"base": _sha(text["base"][p]), "variant": _sha(text["variant"][p])}
                for p in paths
            },
        }
        (fresh / "run.json").write_text(json.dumps(ran, indent=2) + "\n")
        (fresh / "variant.patch").write_text(
            git("diff", revs["base"], revs["variant"], "--", *paths)
        )
        if cases != cases_sha():
            raise SystemExit("eval.py: write: cases/ changed while the run was written")
        fresh.rename(made)
    finally:
        shutil.rmtree(fresh, ignore_errors=True)
    RUN = made
    print(f"write: {len(key)} answers in {made.name}/answers.json, the key in {made.name}/key.json")


def _answers() -> dict[str, str]:
    """Every answer of the run, by its random id: one file, so a run adds four files to a pull
    request and not one per answer."""
    return json.loads((RUN / "answers.json").read_text())


def _judged() -> dict:
    path = RUN / "judge.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def score_one(text: str, case: str, judged: object) -> dict:
    """The blind step for one answer: its text, its case's key, and what the judge said of it."""
    family, slug = case.split("/", 1)
    if family == "lead":
        said = score_lead(text, lead_key(slug), judged)
    else:
        found = next(one for one in steps_cases() if one["id"] == slug)
        said = score_steps(text, found, judged)
    return {"value": said.value, "unsettled": said.unsettled, **said.detail}


def score_all() -> None:
    """Score each answer from its text and its case, never its arm: `which.json` holds no arm."""
    _same_cases()
    which, judged = json.loads((RUN / "which.json").read_text()), _judged()
    answers = _answers()
    scores = {
        name: score_one(answers[name], which[name], judged.get(name)) for name in sorted(which)
    }
    (RUN / "scores.json").write_text(json.dumps(scores, indent=2) + "\n")
    left = sum(1 for one in scores.values() if one["value"] is None)
    print(f"score: {len(scores)} answers scored, {left} the key cannot settle")


def judge() -> None:
    """Ask the judge about each answer the key could not settle, and keep what it said."""
    which, scores, judged = (
        json.loads((RUN / "which.json").read_text()),
        json.loads((RUN / "scores.json").read_text()),
        _judged(),
    )
    asks = [name for name, one in scores.items() if one["value"] is None and name not in judged]
    if not asks:
        print("judge: nothing to settle")
        return
    if not shutil.which("claude"):
        raise SystemExit("eval.py: judge: no claude on PATH, the unsettled answers stay so")

    answers = _answers()

    def ask(name: str) -> tuple[str, object]:
        text = answers[name]
        family, slug = which[name].split("/", 1)
        if family == "lead":
            ids = scores[name]["unsettled"]
            said = claude(JUDGE_LEAD.format(ids=", ".join(ids), answer=text), JUDGE)
            got = buckets(said)
            return name, {fid: got.get(fid, "none") for fid in ids}
        found = next(one for one in steps_cases() if one["id"] == slug)
        said = claude(JUDGE_STEPS.format(expect=found["expect"], answer=text), JUDGE)
        return name, said.strip().upper().startswith("YES")

    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for name, verdict in pool.map(ask, asks):
            judged[name] = verdict
    (RUN / "judge.json").write_text(json.dumps(dict(sorted(judged.items())), indent=2) + "\n")
    print(f"judge: {len(asks)} answers settled")


def sign_test(wins: int, losses: int) -> float:
    """The two-sided p of `wins` against `losses` under a fair coin, ties left out."""
    n = wins + losses
    if not n:
        return 1.0
    tail = sum(comb(n, k) for k in range(max(wins, losses), n + 1)) / 2**n
    return min(1.0, 2 * tail)


def verdict(base: list[float], again: list[float], variant: list[float]) -> dict:
    """The rule of the README for one family, from the case means of each arm."""
    means = [statistics.mean(arm) for arm in (base, again, variant)]
    floor = abs(means[0] - means[1])
    wins = sum(v > b for b, v in zip(base, variant, strict=True))
    losses = sum(v < b for b, v in zip(base, variant, strict=True))
    p = sign_test(wins, losses)
    within = means[2] >= means[0] - floor - 1e-12
    lost = losses > wins and p < 0.05
    return {
        "means": means,
        "floor": floor,
        "wins": wins,
        "ties": len(base) - wins - losses,
        "losses": losses,
        "p": p,
        "within": within,
        "lost": lost,
        "holds": within and not lost,
    }


def report() -> None:
    _same_cases()
    key = json.loads((RUN / "key.json").read_text())
    scores = json.loads((RUN / "scores.json").read_text())
    ran = json.loads((RUN / "run.json").read_text())
    judged = _judged()
    if set(key) != set(scores):
        raise SystemExit("report: key.json and scores.json name different answers: run score")
    left = [name for name, one in scores.items() if one["value"] is None]
    if left:
        raise SystemExit(f"report: {len(left)} answers are unsettled: run judge")
    by: dict[tuple[str, str], list[dict]] = {}
    for name, said in key.items():
        by.setdefault((said["case"], said["arm"]), []).append(scores[name])
    families = {}
    for case, family in sorted(
        {said["case"]: said["case"].split("/")[0] for said in key.values()}.items()
    ):
        families.setdefault(family, []).append(case)

    def mean(case: str, arm: str, measure: str = "value") -> float:
        return statistics.mean(one[measure] for one in by[(case, arm)])

    def spread(case: str, arm: str) -> float:
        values = [one["value"] for one in by[(case, arm)]]
        return max(values) - min(values)

    changed = [p for p, sha in ran["files"].items() if sha["base"] != sha["variant"]]
    lines = [
        "# skill-cut eval: results",
        "",
        "Written by `uv run python features/evals/evals/skill-cut/eval.py`, never by hand.",
        "",
        f"Base: `{ran['base']}`.",
        f"Variant: `{ran['variant']}`.",
        f"Candidate: `{ran['model']}` at `{ran['effort']}` effort, no tools.",
        f"Judge: `{ran['judge']}` at `{ran['effort']}`, only for an answer the key cannot settle.",
        f"Trials: {ran['trials']} a case and arm.",
        "",
        "Files that differ between the two revisions: "
        + (", ".join(f"`{p}`" for p in changed) or "none")
        + ".",
        "The diff is `variant.patch`.",
    ]
    verdicts = {}
    for family in FAMILIES:
        if family not in families:
            continue
        cases_of = families[family]
        lines += [
            "",
            f"## Family `{family}`: each case, the mean of its trials, and the spread of trials",
            "",
            "| Case | Base | Base again | Variant | Spread of trials, base / again / variant |",
            "|---|---|---|---|---|",
        ]
        for case in cases_of:
            cells = " | ".join(f"{mean(case, arm):.3f}" for arm in ARMS)
            spreads = " / ".join(f"{spread(case, arm):.2f}" for arm in ARMS)
            lines.append(f"| `{case.split('/', 1)[1]}` | {cells} | {spreads} |")
        said = verdict(*([mean(case, arm) for case in cases_of] for arm in ARMS))
        verdicts[family] = said
        b, a, v = said["means"]
        lines += [
            "",
            f"Mean over {len(cases_of)} cases: base {b:.3f}, base again {a:.3f}, variant {v:.3f}.",
            f"Noise floor (base against base again): {said['floor']:.3f}, so the variant is held "
            f"to {b - said['floor']:.3f} or above: {'it is' if said['within'] else 'it is not'}.",
            f"Variant against base over the cases: {said['wins']} higher, {said['ties']} tied, "
            f"{said['losses']} lower, sign test p {said['p']:.3f}: "
            f"{'a loss under 0.05' if said['lost'] else 'no loss under 0.05'}.",
            f"**{'Does not regress' if said['holds'] else 'Regresses'}.**",
        ]
        if family == "lead":
            lines += [
                "",
                "Readings, not counted by the rule (mean over the cases): agreement on sent, "
                "noted and dismissed, three ways; the share of the findings the crewmate fixed "
                "that the answer sent; findings sent per answer.",
                "",
                "| Arm | Three ways | Fixed ones sent | Sent per answer |",
                "|---|---|---|---|",
            ]
            for arm in ARMS:
                three = statistics.mean(mean(case, arm, "three_way") for case in cases_of)
                fixed = sum(one["fixed"] for case in cases_of for one in by[(case, arm)])
                fixed_sent = sum(one["fixed_sent"] for case in cases_of for one in by[(case, arm)])
                sent = statistics.mean(one["sent"] for case in cases_of for one in by[(case, arm)])
                share = fixed_sent / fixed if fixed else 0.0
                lines.append(f"| {arm} | {three:.3f} | {share:.3f} | {sent:.2f} |")
    lines += ["", "## The judge", ""]
    for family in FAMILIES:
        names = [n for n in judged if key[n]["case"].startswith(f"{family}/")]
        per = ", ".join(f"{arm} {sum(key[n]['arm'] == arm for n in names)}" for arm in ARMS)
        lines.append(
            f"- `{family}`: {len(names)} of "
            f"{sum(1 for s in key.values() if s['case'].startswith(f'{family}/'))} answers settled "
            f"by the judge ({per})."
        )
    holds = all(said["holds"] for said in verdicts.values())
    lines += [
        "",
        f"**Verdict of this run: the variant {'does not regress' if holds else 'regresses'}**, by "
        "the rule in `README.md`: in each family its mean is no lower than base minus the noise "
        "floor, and the sign test against base shows no loss under 0.05.",
    ]
    (RUN / "results.md").write_text("\n".join(lines) + "\n")
    print(f"report: the variant {'does not regress' if holds else 'regresses'}, results.md written")


KEPT = ("score", "report")
RUN = HERE


def main(argv: list[str]) -> int:
    """`--base <rev> --variant <rev> [--name run-<name>]` writes, scores, judges and reports a
    new run. `--run <run-name> [score] [report]` scores and reports a kept run and writes none.
    `cases <dir>` rebuilds the lead cases."""
    global RUN
    kept = runs()
    if argv[:1] == ["cases"]:
        if len(argv) != 2:
            print("eval.py: cases <the extraction's directory>", file=sys.stderr)
            return 2
        cases(argv[1])
        return 0
    if argv[:1] == ["--run"]:
        if len(argv) < 2 or HERE / argv[1] not in kept:
            print(
                f"eval.py: --run names a kept run: {', '.join(p.name for p in kept) or 'none'}",
                file=sys.stderr,
            )
            return 2
        RUN, steps = HERE / argv[1], argv[2:] or list(KEPT)
        if set(steps) - set(KEPT):
            print("eval.py: --run scores and reports a kept run: score, report", file=sys.stderr)
            return 2
        for step in steps:
            {"score": score_all, "report": report}[step]()
        return 0
    if len(argv) in (4, 6) and argv[0] == "--base" and argv[2] == "--variant":
        if len(argv) == 6 and argv[4] != "--name":
            print("eval.py: --base <rev> --variant <rev> [--name run-<name>]", file=sys.stderr)
            return 2
        write(argv[1], argv[3], argv[5] if len(argv) == 6 else None)
        score_all()
        judge()
        score_all()
        report()
        return 0
    print(
        "eval.py: --base <rev> --variant <rev> [--name run-<name>], --run <run-name> "
        "[score] [report], or cases <dir>",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
