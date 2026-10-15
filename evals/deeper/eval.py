"""The /deeper eval: does a brief written through /deeper name more raw material, more of an
expert's instruments, and more proof outside the agent than one written without it?

One command runs it all, from the root of the repo:

    uv run python evals/deeper/eval.py

It runs four steps, and each can be run alone (`eval.py score` rescores the committed briefs):

- `cases`: reads each brief of `CASES` from the home's `tasks/` and writes its request, the
  `Task:` line with the private patterns of `jleak` taken out, to `cases/<slug>.md`. With no
  `tasks/` on the machine it keeps the committed cases. It also writes `outcomes.json`: how
  the shipped brief's pull request turned out, from the brief's Result and Review and GitHub.
- `write`: for each case, `TRIALS` times, writes two briefs with the same writer and the same
  template: one from the request as it is, one from the prompt /deeper rewrote it to. Each
  brief goes to `runs/<random id>.md`, and which is which only to `key.json`. What a model
  wrote has the private patterns of `jleak` taken out, as the cases have.
- `score`: runs `score.py` over `runs/*.md`, which sees each brief's text and nothing else,
  and writes `scores.json`, keyed by the random ids.
- `report`: joins the scores with the key and writes `results.md`, with the rule in
  `README.md` for whether /deeper won.

`eval.py --run run-1 score report` rescores and reports a run that is kept in its own
directory, with no model call.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
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
REPO = HERE.parents[1]
sys.path[:0] = [str(HERE), str(REPO / "src")]

from score import score  # noqa: E402

import jleak  # noqa: E402

TASKS = Path.home() / ".local/state/home/jstack/tasks"
SKILL = REPO / "skills/deeper/SKILL.md"
TEMPLATE = REPO / "templates/brief.md"
MODEL = "claude-opus-5-5"
EFFORT = "medium"
TRIALS = 2
WORKERS = 4
MEASURES = ("raw", "instruments", "outside")
# Shown beside the measures as a reading of them, and not counted by the rule.
READINGS = ("raw_beyond", "beyond", "outside_no_code")

# The briefs of the eval: research, perf, analysis and outcome work, each with a pull request.
CASES = {
    "tests-parallel": "perf",
    "cs-stubs-in-process": "perf",
    "check-workers-share": "perf",
    "cs-runner-workers": "analysis",
    "rs-parallel-reviews": "research",
    "rs-load-limit": "perf",
    "hj-home-gauge": "outcome",
    "jv-usage": "outcome",
    "jstack-leak-zero": "outcome",
    "ci-hosted-green": "analysis",
}

WRITER = """You are the home of a software repo: jstack, a set of Claude Code skills, playbooks and
Python commands that run a home thread, scouts, crewmates and reviewers on one machine. Write
the brief a crewmate will work from, for the task below. Use the template: fill each line it
asks for, and leave out the lines it says are there only in other cases. Print the brief and
nothing else.

Template:
{template}

Task:
{task}
"""

DEEPER = """{skill}

You have no tools in this run: answer from the task's text alone, and name the paths, commands
and data as you would expect them in this repo and on this machine.

/deeper {task}
"""


def claude(prompt: str) -> str:
    ran = subprocess.run(
        [
            "claude",
            "-p",
            "--model",
            MODEL,
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
    if ran.returncode or not ran.stdout.strip():
        raise RuntimeError(f"claude exited {ran.returncode}: {ran.stderr.strip()[-400:]}")
    return ran.stdout.strip()


def _private() -> tuple[jleak.Pattern, ...]:
    """The private patterns of `jleak`, found as `jleak` finds them. With none, nothing that
    could hold them is written into the repo."""
    config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    try:
        return jleak.load(jleak.path(Path(config)))
    except jleak.Invalid as error:
        raise SystemExit(f"eval.py: {error}: the eval writes nothing it cannot redact") from None


def _redact(text: str, patterns: tuple[jleak.Pattern, ...]) -> str:
    for pattern in patterns:
        text = pattern.regex.sub("the user", text)
    return text


def shipped(text: str) -> str:
    """The brief as the home wrote it: the text above its first Result or Review."""
    return re.split(r"^## (?:Result|Review)", text, maxsplit=1, flags=re.M)[0].strip()


def results(text: str) -> str:
    """The Result sections of a brief, follow-ups included, and none of its Review."""
    parts = re.split(r"^(?=## )", text, flags=re.M)
    return "".join(part for part in parts if part.startswith("## Result"))


def turned_out(slug: str, text: str) -> dict[str, object]:
    """How the pull request of a shipped brief turned out, from the brief and from GitHub."""
    url = re.search(r"https://github\.com/[^\s)]+/pull/\d+", text)
    found = {"pull_request": url[0] if url else "", "merged": None}
    if url and shutil.which("gh"):
        ran = subprocess.run(
            ["gh", "pr", "view", url[0], "--json", "state,mergedAt"],
            capture_output=True,
            text=True,
        )
        if ran.returncode == 0:
            said = json.loads(ran.stdout)
            found["merged"] = said["state"] == "MERGED"
    findings = re.findall(r"^- (error|warning|info)\b", text, re.M)
    found.update(
        status=(re.findall(r"^Status: (\S+)", text, re.M) or [""])[0].rstrip(",.;:"),
        findings_error_or_warning=sum(1 for one in findings if one != "info"),
        findings_info=findings.count("info"),
        follow_up_results=len(re.findall(r"^## Result, follow-up", text, re.M)),
        reruns=len(re.findall(r"^Rerun: ", text, re.M)),
        not_held=len(re.findall(r"\b(?:does|did) not hold\b", results(text))),
        shipped=score(_redact(shipped(text), _private())).as_dict(),
    )
    return found


def cases() -> None:
    if not TASKS.is_dir():
        print(f"cases: no {TASKS} here, the committed cases are kept")
        return
    patterns, outcomes = _private(), {}
    (HERE / "cases").mkdir(exist_ok=True)
    for slug, kind in CASES.items():
        text = (TASKS / f"{slug}.md").read_text()
        task = re.search(r"^Task: (.+)$", text, re.M)
        if not task:
            raise SystemExit(f"cases: {slug} has no Task: line")
        request = _redact(task[1], patterns)
        (HERE / "cases" / f"{slug}.md").write_text(f"Kind: {kind}\n\n{request}\n")
        outcomes[slug] = turned_out(slug, text)
    (HERE / "outcomes.json").write_text(json.dumps(outcomes, indent=2) + "\n")
    print(f"cases: {len(CASES)} written, with outcomes.json")


def request(slug: str) -> str:
    return (HERE / "cases" / f"{slug}.md").read_text().split("\n\n", 1)[1].strip()


def rewritten(said: str) -> str:
    """The block quote under `## Rewritten prompt` of /deeper's output, without its `> `."""
    found = re.search(r"^## Rewritten prompt[ \t]*\n+((?:>.*(?:\n|$))+)", said, re.M)
    if not found:
        raise RuntimeError("/deeper printed no Rewritten prompt as a block quote")
    return "\n".join(re.sub(r"^> ?", "", line) for line in found[1].splitlines()).strip()


def _one(slug: str, arm: str, trial: int) -> tuple[str, str, int, str, str]:
    template, task, deeper = TEMPLATE.read_text(), request(slug), ""
    if arm == "deeper":
        body = SKILL.read_text().split("\n---\n", 1)[1].strip()
        deeper = claude(DEEPER.format(skill=body, task=task))
        task = rewritten(deeper)
    return slug, arm, trial, claude(WRITER.format(template=template, task=task)), deeper


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def write() -> None:
    """Write every brief into a new directory, and put it in place of the committed one only
    once the last brief and the key are written: a call that fails leaves the run as it was."""
    if not shutil.which("claude"):
        raise SystemExit("eval.py: write: no claude on PATH, the committed run is kept")
    fresh = Path(tempfile.mkdtemp(prefix=".write-", dir=HERE))
    for name in ("runs", "deeper"):
        (fresh / name).mkdir()
    jobs = [
        (slug, arm, trial)
        for slug in CASES
        for arm in ("plain", "deeper")
        for trial in range(1, TRIALS + 1)
    ]
    key, patterns = {}, _private()
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for slug, arm, trial, brief, deeper in pool.map(lambda job: _one(*job), jobs):
            brief, deeper = _redact(brief, patterns), _redact(deeper, patterns)
            name = secrets.token_hex(6)
            (fresh / "runs" / f"{name}.md").write_text(brief + "\n")
            key[name] = {"slug": slug, "arm": arm, "trial": trial}
            if deeper:
                (fresh / "deeper" / f"{slug}-{trial}.md").write_text(deeper + "\n")
            print(f"write: {len(key)} of {len(jobs)}", flush=True)
    shuffled = dict(random.sample(sorted(key.items()), len(key)))
    (fresh / "key.json").write_text(json.dumps(shuffled, indent=2) + "\n")
    ran = {"template": _sha(TEMPLATE), "skill": _sha(SKILL)}
    (fresh / "run.json").write_text(json.dumps(ran, indent=2) + "\n")
    for name in ("runs", "deeper", "key.json", "run.json"):
        old = HERE / name
        if old.is_dir():
            shutil.rmtree(old)
        elif old.exists():
            old.unlink()
        (fresh / name).rename(old)
    fresh.rmdir()
    print(f"write: {len(key)} briefs in runs/, the key in key.json")


def score_all() -> None:
    """The blind step: the text of each file in runs/, and no key."""
    scores = {
        path.stem: score(path.read_text()).as_dict() for path in sorted((RUN / "runs").glob("*.md"))
    }
    (RUN / "scores.json").write_text(json.dumps(scores, indent=2) + "\n")
    print(f"score: {len(scores)} briefs scored")


def sign_test(wins: int, losses: int) -> float:
    """The two-sided p of `wins` against `losses` under a fair coin, ties left out."""
    n = wins + losses
    if not n:
        return 1.0
    tail = sum(comb(n, k) for k in range(max(wins, losses), n + 1)) / 2**n
    return min(1.0, 2 * tail)


def report() -> None:
    key = json.loads((RUN / "key.json").read_text())
    scores = json.loads((RUN / "scores.json").read_text())
    ran = json.loads((RUN / "run.json").read_text())
    outcomes = json.loads((HERE / "outcomes.json").read_text())
    if set(key) != set(scores):
        raise SystemExit("report: key.json and scores.json name different briefs: run score")
    by = {}
    for name, said in key.items():
        by.setdefault((said["slug"], said["arm"]), []).append(scores[name])

    def mean(slug: str, arm: str, measure: str) -> float:
        return statistics.mean(one[measure] for one in by[(slug, arm)])

    lines = [
        "# /deeper eval: results",
        "",
        "Written by `uv run python evals/deeper/eval.py`. Do not edit by hand.",
        "",
        f"Writer: `{MODEL}` at `{EFFORT}` effort, no tools. Trials: {TRIALS} a case and arm. "
        f"Template: `templates/brief.md` at sha256 `{ran['template']}`. Skill: "
        f"`skills/deeper/SKILL.md` at sha256 `{ran['skill']}`, the text this run read.",
        "",
        "## Each case, the mean of its trials (plain / deeper)",
        "",
        "| Case | Kind | Raw sources | Raw beyond the skill's examples | Instruments "
        "| Instruments beyond the skill's examples | Proof outside | Proof outside, no inline "
        "code | Words |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for slug, kind in CASES.items():
        cells = [
            f"{mean(slug, 'plain', m):g} / {mean(slug, 'deeper', m):g}"
            for m in (
                "raw",
                "raw_beyond",
                "instruments",
                "beyond",
                "outside",
                "outside_no_code",
                "words",
            )
        ]
        lines.append(f"| `{slug}` | {kind} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Each measure over the cases",
        "",
        "| Measure | Plain, mean | Deeper, mean | Deeper wins | Ties | Deeper loses "
        "| Sign test p | Spread of trials, plain / deeper |",
        "|---|---|---|---|---|---|---|---|",
    ]
    verdicts = {}
    for measure in (*MEASURES, *READINGS):
        plain = [mean(slug, "plain", measure) for slug in CASES]
        deeper = [mean(slug, "deeper", measure) for slug in CASES]
        wins = sum(d > p for p, d in zip(plain, deeper, strict=True))
        losses = sum(d < p for p, d in zip(plain, deeper, strict=True))
        ties = len(CASES) - wins - losses
        p = sign_test(wins, losses)
        verdicts[measure] = (wins, losses, p)
        spread = [
            statistics.mean(
                max(one[measure] for one in by[(slug, arm)])
                - min(one[measure] for one in by[(slug, arm)])
                for slug in CASES
            )
            for arm in ("plain", "deeper")
        ]
        lines.append(
            f"| {measure} | {statistics.mean(plain):.2f} | {statistics.mean(deeper):.2f} "
            f"| {wins} | {ties} | {losses} | {p:.3f} | {spread[0]:.2f} / {spread[1]:.2f} |"
        )
    won = [m for m in MEASURES if verdicts[m][0] > verdicts[m][1] and verdicts[m][2] < 0.05]
    lost = [m for m in MEASURES if verdicts[m][1] > verdicts[m][0]]
    verdict = "won" if len(won) >= 2 and not lost else "lost" if len(lost) >= 2 else "did not win"
    lines += [
        "",
        f"**Verdict of this run: /deeper {verdict}**, by the rule in `README.md`, which one "
        "run decides alone and the README's Result reads across every run: it wins a measure "
        "when it "
        "scores higher on more cases than it scores lower, with a sign test under 0.05, and it "
        f"wins the eval with two of the three measures and a loss on none. Won: "
        f"{', '.join(won) or 'none'}. Lost: {', '.join(lost) or 'none'}.",
        "",
        "## How the shipped briefs turned out",
        "",
        "The brief the home actually wrote, scored the same way, and what became of its pull "
        "request: findings of its review (errors and warnings, then info), follow-up Results, "
        "reruns of a check, and how many times its Results say a line does or did not hold.",
        "",
        "| Case | Merged | Shipped: raw / instruments / outside | Findings | Follow-ups "
        "| Reruns | Not held, in the Results |",
        "|---|---|---|---|---|---|---|",
    ]
    for slug in CASES:
        out = outcomes[slug]
        s = out["shipped"]
        merged = {True: "yes", False: "no", None: "not known"}[out["merged"]]
        lines.append(
            f"| `{slug}` | {merged} | {s['raw']} / {s['instruments']} / {s['outside']:g} "
            f"| {out['findings_error_or_warning']}, {out['findings_info']} "
            f"| {out['follow_up_results']} | {out['reruns']} | {out['not_held']} |"
        )
    (RUN / "results.md").write_text("\n".join(lines) + "\n")
    print(f"report: /deeper {verdict}, results.md written")


STEPS = {"cases": cases, "write": write, "score": score_all, "report": report}
RUN = HERE


def main(argv: list[str]) -> int:
    """`[--run <directory>] [step...]`: `--run run-1` scores and reports a kept run."""
    global RUN
    if argv[:1] == ["--run"]:
        if len(argv) < 2 or not (HERE / argv[1] / "runs").is_dir():
            print("eval.py: --run names a directory of evals/deeper with runs/", file=sys.stderr)
            return 2
        RUN, argv = HERE / argv[1], argv[2:]
    asked = argv or list(STEPS)
    unknown = [step for step in asked if step not in STEPS]
    if unknown:
        print(f"eval.py: no step {unknown[0]}, the steps are {', '.join(STEPS)}", file=sys.stderr)
        return 2
    for step in asked:
        STEPS[step]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
