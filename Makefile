# The one check command: the lint commands the README lists, and its test command on
# several workers. CI runs it on main after each merge. On a pull request CI runs `make lint`,
# and `make test` on the files scripts/select_tests.py picks, in eight parts side by side
# (.github/workflows/check.yml). Neither runs the tests marked `browser`, which open a real
# browser: `check-browser` runs those, on a nightly and on a release
# (.github/workflows/browser.yml).

# The tests run on this many workers (pytest-xdist), counted from the processors the run may
# use. One core bounds the suite, so workers are what make a run short. A run's processors are
# its cgroup's CPU quota where one is set (`cpu.max`, quota over period, rounded down, at least
# one): a container sees every processor of the machine, and `--cpus` sets only the quota. With
# no quota they are what `getconf` counts.
#
# A desk takes a quarter of them. Not `auto`, which takes them all: other work shares the
# machine, and several checks run at once. A runner (GitHub Actions sets GITHUB_ACTIONS to
# true) of GitHub's own, where RUNNER_ENVIRONMENT is github-hosted and every jstack CI job runs,
# runs nothing else, so it takes one for each processor. A self-hosted runner takes one and a
# half for each processor of its quota, as measured on the owner's own runners before CI moved
# to GitHub: a worker waits on subprocesses and files about half the time, so a quota of 4 runs
# 6 workers. None takes fewer than two. `make check TEST_WORKERS=4`
# sets the count by hand, and `CORES=4` the processors it is counted from.
#
# The desk share is also the full test slots' count (`test_slots` in
# features/jgauge/src/jgauge/sizes.py, whose DESK_SHARE is this quarter): every slot at once
# runs at most one desk worker for each of the machine's processors: 4 slots on most machines
# of 8 cores or more, 5 on 10, 11 or 15. A worker keeps 0.86 of a core busy (measured on
# yelena, 24 processors, 2026-10-20: 456 to 483 s of CPU for each 89 to 94 s run at 6 workers),
# so every slot at once asks for about 21 of the 24. testing/tests/test_check_command.py holds the
# share and the count to each other. CI is not in that count: it runs on GitHub's machines.
# A system with no /proc/self/cgroup, such as macOS, has no cgroup, so no quota.
CGROUP ?= $(if $(wildcard /proc/self/cgroup),/sys/fs/cgroup$(shell sed -n 's/^0:://p' /proc/self/cgroup))
QUOTA = $(shell read -r q p 2>/dev/null < '$(CGROUP)/cpu.max' && [ "$$q" != max ] && n=$$((q / p)) && echo $$((n > 0 ? n : 1)))
CORES ?= $(or $(QUOTA),$(shell getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2))
PER_CORE = $(if $(filter true,$(GITHUB_ACTIONS)),$(if $(filter github-hosted,$(RUNNER_ENVIRONMENT)),1 / 1,3 / 2),1 / 4)
# A runner of GitHub's own runs the suite alone, so the TLC runs the suite starts take no jgauge
# test slot: `JGAUGE_TEST_SLOT` says one is held (features/jgauge/src/jgauge/slot.py). Were they
# to take one, a macos-15 runner's 3 cores, which jgauge gives a single slot, would queue each on
# the one before it, and its wait counts against the bound of the test that started it.
ifeq ($(GITHUB_ACTIONS) $(RUNNER_ENVIRONMENT),true github-hosted)
JGAUGE_TEST_SLOT ?= runner
export JGAUGE_TEST_SLOT
endif
TEST_WORKERS ?= $(shell n=$$(($(or $(strip $(CORES)),2) * $(PER_CORE))); [ "$$n" -ge 2 ] || n=2; echo "$$n")
# Workers take the next test as each finishes (`worksteal`), so a slow file does not hold up
# the tests queued behind it. The 25 slowest tests are printed at the end, and `JUNIT=<file>`
# writes every test's time there, which CI's summary line reads. `SHARD=K/N` runs only the K-th
# of N parts of the tests the run selected, split by time (testing/shard.py): CI's check runs as
# eight jobs side by side and its full run as four, one for each part. `NEW_LINES_PART=<folder>`
# records there the lines of the feature code the branch changes that each test file runs
# (features/repo-guards/ran/part_lines.py), which CI's job `check` reads for the guard of
# test_new_lines_run.py once the parts end, so no part runs those tests a second time for it.
# It stays out of the environment, as TESTS does, so a make that a test runs records nothing.
unexport NEW_LINES_PART
PYTEST = $(if $(NEW_LINES_PART),NEW_LINES_PART='$(NEW_LINES_PART)' PYTHONPATH='$(CURDIR)/features/repo-guards/ran'$${PYTHONPATH:+:$$PYTHONPATH} )uv run pytest$(if $(NEW_LINES_PART), -p part_lines) -n $(TEST_WORKERS) --dist worksteal --durations=25 -m "not browser"$(if $(JUNIT), --junitxml=$(JUNIT))$(if $(SHARD), --shard=$(SHARD))

# The lint of `check` and `check-fast`. comment_lint.py only warns; the repo standard's `stale`
# guard runs each generator of .repo-standard.yml with --check and fails a stale generated file, and
# check-jstack-docs.py fails a doc that says what the tree does not have.
# pyrefly type-checks each feature's src at the settings of [tool.pyrefly] in pyproject.toml, and
# fails on an error. The paths are given here, not in that table: pyrefly's default excludes
# drop every path under a dot directory, which a worktree such as ~/.t3/worktrees/... sits in.
# `repo-standard conform` runs last, and CI's lint job runs it only here, so a desk check fails on
# a rule of the standard (a file over its size cap, say) where CI does.
BASE ?= origin/main

.PHONY: lint
lint:
	git diff -z --name-only --diff-filter=d '$(BASE)...HEAD' -- 2> /dev/null | xargs -0 -r python3 features/writing/scripts/comment_lint.py || true
	PYTHONPATH=features/repo-standard/src python3 -m repo_standard stale
	python3 scripts/check-jstack-docs.py
	uv run ruff check .
	uv run ruff format --check .
	uv run pyrefly check --summary=none features/*/src
	uv run repo-standard conform

# `make test TESTS=<files>` runs only those files. TESTS stays out of the environment, where a
# make that a test runs would take it for its own.
unexport TESTS
.PHONY: test
test:
	$(PYTEST)$(if $(TESTS), $(TESTS))

.PHONY: check
check: lint test

# The test files the change from BASE to HEAD reaches, one a line, or `all` where it reaches every
# test: the repo standard's `make select BASE=<ref>`, which wraps scripts/select_tests.py.
.PHONY: select
select:
	@python3 scripts/select_tests.py '$(BASE)' HEAD

# The check of a change: prose_lint.py on the prose lines the diff from BASE adds, the lint, and the
# files select_tests.py names for the diff, one a line, which the unquoted `echo` puts on one; or
# `make check` where it says `all`. CI runs it with BASE=HEAD^1, the tip of main on GitHub's merge.
# A desk's check is `PART=touched` (features/crew/do-the-task.md): the lint and the test files the
# change adds or edits, and never the whole suite, even where the selection is `all`: CI's check
# runs the rest of it. The crew's check block runs it in steps, the lint and then each file alone,
# so each fits the short lane. `PART=guards`, the lint and the guard tests, is what jmerge runs on
# a pull request's tree merged over its base, and it too never runs the whole suite: where the
# selection is `all` its guards are the cross-cutting tests, the catch-all and the changed test
# files, since the whole suite outran jmerge's 10 minutes on 2026-11-05. `PART=rest`, the other
# tests the selection names and no lint, stays for a run by hand.
# PART stays out of the environment, as TESTS does, so a make that a guard test runs is whole.
unexport PART
.PHONY: check-fast
check-fast:
	@tests=$$(python3 scripts/select_tests.py $(if $(PART),--part '$(PART)') '$(BASE)' HEAD) || exit; \
	if [ '$(PART)' = touched ]; then \
		python3 features/writing/scripts/prose_lint.py '$(BASE)' || exit; \
		$(MAKE) --no-print-directory lint || exit; \
		[ -z "$$tests" ] || exec $(MAKE) --no-print-directory test TESTS="$$(echo $$tests)"; \
		exit 0; \
	fi; \
	if [ '$(PART)' = rest ]; then \
		[ "$$tests" != all ] || exec $(MAKE) --no-print-directory test; \
		[ -z "$$tests" ] || exec $(MAKE) --no-print-directory test TESTS="$$(echo $$tests)"; \
		exit 0; \
	fi; \
	python3 features/writing/scripts/prose_lint.py '$(BASE)' || exit; \
	if [ "$$tests" = all ] && [ -z '$(PART)' ]; then exec $(MAKE) --no-print-directory check; fi; \
	$(MAKE) --no-print-directory lint && exec $(MAKE) --no-print-directory test TESTS="$$(echo $$tests)"

# This checkout's `jbus view`, to show a branch's page before it merges: on VIEW_PORT, beside the
# live view on 4388, with the JBUS_VIEW_* variables of the live jbus-view.service (the drop-in
# that install.sh writes from the [view] table of jbus's config). It runs until Ctrl-C.
VIEW_PORT ?= 4389

.PHONY: view-preview
view-preview:
	env $$(systemctl --user show jbus-view.service --property Environment --value 2> /dev/null | tr ' ' '\n' | grep '^JBUS_VIEW_') uv run jbus view --port $(VIEW_PORT)

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

# A release. Its version is pyproject.toml's, and plugin.json's, which the generator holds to
# it. A bump is an ordinary pull request: `uv version --bump <major|minor|patch>`, then
# `make trees`. `make release`, on a clean main that is origin/main, runs `make release-tag`,
# runs `make release-green`, tags `v<version>` and pushes the tag, dropping it again where the
# push fails, and .github/workflows/release.yml does the rest: `make release-tag`, `make
# release-green` again on the tag's own checkout, `make dist`, an install of the wheel in a HOME
# of its own, and the GitHub release. The tag runs no check of its own: main's already passed on
# the same tree.
VERSION = $(shell uv version --short)

# Fails unless TAG is `v<version>` of both pyproject.toml and plugin.json.
.PHONY: release-tag
release-tag:
	@plugin=$$(python3 -c 'import json; print(json.load(open("plugin.json"))["version"])') && \
	if [ "$$TAG" != "v$(VERSION)" ] || [ "$$TAG" != "v$$plugin" ]; then \
		echo "release-tag: the tag '$$TAG' is not v$(VERSION), pyproject.toml's, and v$$plugin, plugin.json's"; \
		exit 1; \
	fi

# Fails unless a green run of check.yml in this repo left the marker `green-tree-<tree>` for the
# tree of HEAD (jmerge.green.green_run), so a release ships only files the whole suite passed.
# The tree is the key, not the commit: a tag on main has main's tree. Main's full run leaves the
# marker, kept 7 days, once its suite passed. Anything else fails closed, naming the fix: no
# marker yet, a red or a fork's run, or no answer from GitHub. It asks through `gh`, which fills
# in the repo from GH_REPO or the checkout's origin, and runs on a bare python3.
define RELEASE_GREEN
import json, subprocess, sys
from jmerge import green

tree = sys.argv[1]
name = green.ARTIFACT + tree
fix = (
    "wait for main's full run of check.yml to pass and leave it, or, where the marker expired"
    " after its 7 days, run `gh workflow run check.yml --ref main`, then run this again"
)


def ask(path):
    done = subprocess.run(
        ["gh", "api", "repos/{owner}/{repo}/" + path], capture_output=True, text=True, timeout=30
    )
    if done.returncode:
        said = done.stderr.strip() or "gh exited " + str(done.returncode)
        raise RuntimeError(said.splitlines()[0])
    return json.loads(done.stdout)


try:
    run, fork = green.green_run(ask, name)
except Exception as error:
    print(f"release-green: could not ask GitHub for {name} ({error}), so no release: {fix}")
    sys.exit(1)
if not run:
    whose = "only a fork's run left" if fork else "no green run of check.yml left"
    print(f"release-green: {whose} {name}, so tree {tree} has not passed the check: {fix}")
    sys.exit(1)
print(f"release-green: tree {tree} passed the check in {run}")
endef
export RELEASE_GREEN

.PHONY: release-green
release-green:
	@tree=$$(git rev-parse 'HEAD^{tree}') && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=features/jmerge/src python3 -c "$$RELEASE_GREEN" "$$tree"

# DIST, dist/ by default: the wheel, the sdist, and install.sh with the version written in, so
# that piped to `sh` it installs that release's wheel.
DIST ?= dist

.PHONY: dist
dist:
	rm -rf '$(DIST)'
	uv build --out-dir '$(DIST)'
	sed 's/^version=$$/version=$(VERSION)/' install.sh > '$(DIST)/install.sh'
	grep -qx 'version=$(VERSION)' '$(DIST)/install.sh'

.PHONY: release
release:
	@[ "$$(git symbolic-ref -q --short HEAD)" = main ] || { echo "release: not on main"; exit 1; }
	@[ -z "$$(git status --porcelain)" ] || { echo "release: the checkout is not clean"; exit 1; }
	@git fetch -q origin main
	@[ "$$(git rev-parse HEAD)" = "$$(git rev-parse origin/main)" ] || { echo "release: main is not origin/main"; exit 1; }
	@$(MAKE) -s release-tag TAG='v$(VERSION)'
	@$(MAKE) -s release-green
	git tag -a 'v$(VERSION)' -m 'jstack $(VERSION)'
	git push origin 'v$(VERSION)' || { git tag -d 'v$(VERSION)'; exit 1; }
