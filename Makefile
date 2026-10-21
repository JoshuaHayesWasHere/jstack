# The one check command: the lint commands the README lists, and its test command on
# several workers. CI runs it on main after each merge, and `check-fast` on a pull request.
# Neither runs the tests marked `browser`, which open a real browser: `check-browser` runs
# those, on a nightly and on a release (.github/workflows/browser.yml).

# The tests run on this many workers (pytest-xdist), counted from the processors the run may
# use. One core bounds the suite, so workers are what make a run short. A run's processors are
# its cgroup's CPU quota where one is set (`cpu.max`, quota over period, rounded down, at least
# one): a container sees every processor of the machine, and `--cpus` sets only the quota. With
# no quota they are what `getconf` counts.
#
# A desk takes a quarter of them. Not `auto`, which takes them all: other work shares the
# machine, and several checks run at once. A runner (GitHub Actions sets GITHUB_ACTIONS to
# true) of this machine takes one and a half workers for each processor of its quota: a worker
# waits on subprocesses and files about half the time, so a quota of 4 runs 6 workers. One of
# GitHub's own (RUNNER_ENVIRONMENT is github-hosted) takes one for each. None takes fewer
# than two. `make check TEST_WORKERS=4` sets the count by hand, and `CORES=4` the processors
# it is counted from.
#
# The two shares and the number of test slots (`DEFAULT` in src/jgauge/slot.py) are one budget,
# counted in workers: the slots times a desk's workers, plus the runners times a runner's, at
# most one and a half for each of the machine's processors. On 24 processors with 3 slots and
# 3 runners of quota 4 that is 3 x 6 + 3 x 6 = 36 workers. A worker averages 0.51 of a core
# (measured 2026-10-19: 440 to 473 s of CPU for every run of the suite at 6 and 8 workers), so
# every slot and every runner at once ask for about 18 of the 24. Change one of the numbers and
# the sum changes: tests/test_check_command.py holds it to 36.
CGROUP ?= /sys/fs/cgroup$(shell sed -n 's/^0:://p' /proc/self/cgroup 2>/dev/null)
QUOTA = $(shell read -r q p 2>/dev/null < '$(CGROUP)/cpu.max' && [ "$$q" != max ] && n=$$((q / p)) && echo $$((n > 0 ? n : 1)))
CORES ?= $(or $(QUOTA),$(shell getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2))
PER_CORE = $(if $(filter true,$(GITHUB_ACTIONS)),$(if $(filter github-hosted,$(RUNNER_ENVIRONMENT)),1 / 1,3 / 2),1 / 4)
TEST_WORKERS ?= $(shell n=$$(($(or $(strip $(CORES)),2) * $(PER_CORE))); [ "$$n" -ge 2 ] || n=2; echo "$$n")
# Workers take the next test as each finishes (`worksteal`), so a slow file does not hold up
# the tests queued behind it. The 25 slowest tests are printed at the end, and `JUNIT=<file>`
# writes every test's time there, which CI's summary line reads.
PYTEST = uv run pytest -n $(TEST_WORKERS) --dist worksteal --durations=25 -m "not browser"$(if $(JUNIT), --junitxml=$(JUNIT))

.PHONY: check
check:
	python3 scripts/generate-jstack-trees.py --check
	uv run ruff check .
	uv run ruff format --check .
	$(PYTEST)

# The check of a change: the same lint, and only the test files its diff from BASE to HEAD
# reaches, as scripts/select_tests.py names them. Where the script says `all`, it is
# `make check`. A pull request's CI runs it with BASE=HEAD^1, which on GitHub's merge of the
# pull request is the tip of main; a desk takes origin/main. The full suite runs on main
# after the merge. Before the tests, scripts/prose_lint.py holds each prose line the diff adds
# to one sentence, and scripts/generate-jstack-trees.py fails a generated file that is stale
# against features/ (`make check` runs that itself where the selection is `all`).
BASE ?= origin/main

.PHONY: check-fast
check-fast:
	@tests=$$(python3 scripts/select_tests.py '$(BASE)' HEAD) || exit; \
	python3 scripts/prose_lint.py '$(BASE)' || exit; \
	if [ "$$tests" = all ]; then exec $(MAKE) --no-print-directory check; fi; \
	python3 scripts/generate-jstack-trees.py --check || exit; \
	set -x; \
	uv run ruff check . && uv run ruff format --check . && $(PYTEST) $$tests

# Only the tests marked `browser`, which open a real browser and hold the machine's browser
# lock. They run one at a time, so there are no workers, and no lint: `check` has that.
.PHONY: check-browser
check-browser:
	uv run pytest -m browser

# skills.json, the generated regions of pyproject.toml and the docs indexes, written from
# features/ and the files they own. Run it after any change to those, and commit what it
# writes: the check fails on a stale one.
.PHONY: trees
trees:
	python3 scripts/generate-jstack-trees.py

# What changed upstream in pstack since the pin in THIRD_PARTY.md, for the files taken
# from it. Not part of the check: it reads the network. `make pstack-drift ARGS=--diff`.
.PHONY: pstack-drift
pstack-drift:
	uv run jdrift $(ARGS)
