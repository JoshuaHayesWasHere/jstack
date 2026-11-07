# ci2m-select-graph-cache: scripts/select_tests.py picks a selection in about a second, not 13 to 24
Green main: 8b982fb25367d0e77f4c0f5ede827cead33059bb
Task: "PR CI should take 2 minutes" (JoshuaHayesWasHere, 2026-11-06), from the scout vision-ci-two-minutes: the selector itself is a CPU-bound 13 s on a desk and 24 s on a runner, and each of about 25 tests that run it on the real repo takes 27 to 65 s in CI.
Done when:
- `python3 scripts/select_tests.py HEAD~3 HEAD` takes a median under 2 s over 5 runs on a desk (today 12.8 to 13.1 s, 3 runs, user time equal to real)
- its output is byte-identical to today's for every merge commit of main since 2026-11-01 (a script compares old and new over them)
- the check's `select` step takes under 10 s in CI (today 38 s: 24 s selecting, 13 s collecting) (in `.github/workflows/check.yml`)
- the slowest of testing/tests/test_select_tests.py and testing/tests/test_check_command.py's tests in a PR part's `--durations` drops under 15 s (in `testing/tests/test_check_command.py`)
Proves it: the before and after timings from `benchmark-checklist`'s runs.sh, and the select step and `--durations=25` lines of a PR check on the pull request
Size: M
Where: scripts/select_tests.py (the import graph: `sources`/`read`/`by_name`/`edges`, `spelled_by`, `unowned`)
Do not touch: what the selection selects; the rules and their docs stay as they are
Skills: benchmark-checklist, principle-explain-the-number
Pull request: open one when done
Review: review
Playbook: perf-issue
Home: cicd
Read: a cProfile of one run, `python3 -m cProfile -s cumulative scripts/select_tests.py HEAD~3 HEAD`: of 49 s (profiled) `sources`/`read` take 28.4 s, almost all in 16 M `ast.walk` calls (870 modules walked several times each, by `read` and `by_name`); `spelled_by` 10.7 s; `unowned` 9.9 s (1,847 `ruled` calls, one per tracked path); `ast.parse` only 1.3 s
Instruments: `python3 -m cProfile`, `sh ~/.claude/skills/benchmark-checklist/scripts/runs.sh 5 "<old>" "<new>"`, `gh run view --job <id> --log` for CI step times
Change: scripts/select_tests.py: one visitor pass per module in place of repeated `ast.walk`s, and/or a cache of the per-module facts keyed on each file's blob sha (`git ls-files -s`), and `unowned` computed only where its answer is used
Rests on: CI select step 38 s, file list printed 24 s after the step starts (job 127934001247); slow tests in part logs of runs 42230220553, 42172483453, 42174328750
Sources: the Python `ast` docs (NodeVisitor), none outside needed
Ruled out: parsing cost (1.3 s), git diff and file stats (about 2.5 s together)

