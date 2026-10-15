"""The blind scorer of the /deeper eval: a brief's text in, three numbers out.

It reads the text of one brief and nothing else: not its file name, not which arm wrote it.
No model reads anything. The lexicons below were written and committed before any brief of
the eval was generated, and a rerun scores with them as they are.

- `raw`: how many kinds of raw material the brief names (`RAW`), each counted once.
- `instruments`: how many instruments it names (`INSTRUMENTS`), each counted once.
  `beyond` is the same count without the ones `skills/deeper/SKILL.md` gives as examples, so
  an arm that only copies the skill's examples is seen doing it.
- `outside`: of the brief's proof lines (its `Done when:` items and a `Proves it:` line), the
  share that name a judge outside the agent (`OUTSIDE`) and do not rest on a review or a
  self-report (`SELF`).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

CASE = re.IGNORECASE


def _each(**shapes: str) -> dict[str, re.Pattern[str]]:
    return {name.replace("_", "-"): re.compile(shape, CASE) for name, shape in shapes.items()}


RAW = _each(
    logs=r"\blogs?\b|journalctl|\bjournal\b",
    transcripts=r"\btranscripts?\b|\.jsonl\b",
    traces=r"\btraces?\b|\bstrace\b",
    profiles=r"\bprofil(?:e|es|ing|er)\b|flame ?graphs?",
    database=r"\bsqlite3?\b|\bdatabase\b|\.db\b|\bSQL\b",
    machine_counters=r"/proc/|/sys/fs/cgroup|\bcounters?\b|pressure stall|\bloadavg\b|\bPSI\b",
    timings=r"--durations|\btimings?\b|wall[- ]clock|per-test time",
    event_log=r"events?\.jsonl|event log",
    ci_runs=r"gh run (?:view|list)|workflow runs?|job logs?|run logs?|actions/runs",
    git_history=r"git log\b|git bisect|git blame|commit history",
    raw_data=r"\braw (?:data|logs?|output|numbers?|samples?|measurements?|readings?)\b",
    samples=r"\bsamples?\b|\bruns? (?:count|counts)\b|\bspread\b",
)

INSTRUMENTS = _each(
    py_spy=r"\bpy-spy\b",
    perf=r"\bperf (?:stat|record|report|top)\b",
    hyperfine=r"\bhyperfine\b",
    cprofile=r"\bcProfile\b|\bpstats\b",
    pyinstrument=r"\bpyinstrument\b",
    pytest_durations=r"--durations\b",
    pytest_xdist=r"\bxdist\b|pytest -n\b",
    strace=r"\bstrace\b|\bltrace\b",
    time=r"/usr/bin/time|`time [a-z]|\btime -v\b",
    vmstat=r"\bvmstat\b",
    pidstat=r"\bpidstat\b",
    iostat=r"\biostat\b|\bmpstat\b|\bsar\b",
    top=r"\bhtop\b|\btop -b\b|\bbtop\b|\bsystemd-cgtop\b",
    ps=r"`ps |\bps aux\b|\bpgrep\b",
    free=r"\bfree -[mhg]\b|/proc/meminfo",
    pressure=r"/proc/pressure",
    journalctl=r"\bjournalctl\b",
    gh_api=r"\bgh api\b",
    gh_run=r"\bgh run\b",
    jq=r"\bjq\b",
    sqlite3=r"\bsqlite3\b",
    git_bisect=r"\bgit bisect\b",
    git_log=r"\bgit log\b|\bgit blame\b",
    lighthouse=r"\blighthouse\b|\baxe\b|\bplaywright\b",
    benchmark=r"\bpytest-benchmark\b|\bbenchmark harness\b|\btimeit\b",
)

# The instruments `skills/deeper/SKILL.md` names as its examples.
SKILL_EXAMPLES = frozenset(
    {"py-spy", "pytest-durations", "hyperfine", "perf", "pidstat", "git-bisect", "sqlite3"}
)

OUTSIDE = re.compile(
    r"`[^`]+`"
    r"|\btests?\b|\bexits? (?:0|1|2|with)\b|\bexit code\b"
    r"|\bmeasured\b|\bmeasure\b|\bbenchmark|\bmedian\b|\bp\d\d\b|\bspread\b"
    r"|\b\d+(?:\.\d+)?\s?(?:ms|s|seconds?|minutes?|%|GB|MB|x)\b"
    r"|\bCI\b|\bcheck(?:s)? (?:pass|passes|passed|green)\b|\bgreen\b"
    r"|\bdataset\b|\bmetric\b|\bthe user (?:checks|confirms|says|sees|answers)\b",
    CASE,
)
SELF = re.compile(
    r"\breview(?:ed|er|ers)?\b|\bcrewmate (?:confirms|checks|says|judges)\b"
    r"|\blooks? (?:right|good|fine)\b|\bself-(?:report|assess)|\bagent (?:confirms|judges)\b",
    CASE,
)


@dataclass(frozen=True)
class Score:
    raw: int
    instruments: int
    beyond: int
    outside: float
    proof_lines: int
    words: int

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


def proof_lines(text: str) -> list[str]:
    """The `Done when:` items of a brief, and its `Proves it:` line where it has one."""
    lines, found, inside = text.splitlines(), [], False
    for line in lines:
        stripped = line.strip()
        if re.match(r"\**Done when\**:", stripped):
            inside = True
            rest = stripped.split(":", 1)[1].strip()
            if rest:
                found.append(rest)
            continue
        if inside and stripped.startswith(("- ", "* ")):
            found.append(stripped[2:])
            continue
        if inside and stripped:
            inside = False
        if re.match(r"\**Proves it\**:", stripped):
            found.append(stripped.split(":", 1)[1].strip())
    return [line for line in found if line]


def outside(line: str) -> bool:
    return bool(OUTSIDE.search(line)) and not SELF.search(line)


def score(text: str) -> Score:
    raw = [name for name, shape in RAW.items() if shape.search(text)]
    tools = [name for name, shape in INSTRUMENTS.items() if shape.search(text)]
    proofs = proof_lines(text)
    share = sum(map(outside, proofs)) / len(proofs) if proofs else 0.0
    return Score(
        raw=len(raw),
        instruments=len(tools),
        beyond=len([name for name in tools if name not in SKILL_EXAMPLES]),
        outside=round(share, 3),
        proof_lines=len(proofs),
        words=len(text.split()),
    )
