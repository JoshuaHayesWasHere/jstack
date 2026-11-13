# Where the evals' runs are kept

The evals feature holds its code, its tests and their fixtures in git. What an eval records, its runs and the cases taken from real threads, is data: it grows with every run, so it is kept out of git, in the home's state folder beside the lab's reports.

| What | Where |
|---|---|
| The skill-cut eval's runs, `run-<name>/` and the `.run-<name>.answers.jsonl` of a write still going | `~/.local/state/home/<repo>/reports/evals/skill-cut/` |
| The skill-cut eval's lead cases, `cases/lead/` | the same folder, `cases/lead/` |
| The cases the kept skill-cut runs were answered against | the same folder, `fixture/steps-of-run-1.json` |
| The retired eval of the depth questions, its cases, its two runs and its README | `~/.local/state/home/<repo>/reports/evals/deeper/` |
| The lab's result directories | `~/.local/state/home/<repo>/reports/lab/` (`lab/lab.py`) |

`<repo>` is the repo's own folder name, `jstack` here, from any of its worktrees.
`SKILL_CUT_DIR` names another folder for the skill-cut eval, for a test or a second machine.
The skill-cut eval's `steps.json` is written by hand and stays in git, at `evals/skill-cut/cases/steps.json`.

`eval.py --base <rev> --variant <rev>` writes a new run into that folder and `eval.py --run <run-name>` rescores one there; `ab.py rescore <run dir>` takes the folder's path, `ab.py rescore ~/.local/state/home/jstack/reports/evals/skill-cut/run-interrogate-986`.

## Before they left git

Every run and case up to commit `bc9eede9d` was in git under `features/evals/evals/`, and that commit keeps them.
On a machine whose state folder has none, they come back from it:

```sh
data=~/.local/state/home/jstack/reports/evals
mkdir -p "$data"
git archive bc9eede9d features/evals/evals | tar -x -C "$data" --strip-components=3 --exclude='*.py' --exclude='steps.json' --exclude='skill-cut/README.md' --exclude='.gitignore'
```

A write with no lead cases in the folder refuses, and names this section.

## What the tests read

The tests read no state folder.
`tests/fixtures/skill-cut.tar.xz` packs the few kept runs they rescore: `run-1` whole, with the lead cases and the `steps.json` it was answered against, and the `run.json`, `key.json` and `scores.json` of the five runs `test_ab.py` rescores.
`tests/conftest.py` unpacks it into each test's own temporary folder.
