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
TEST_WORKERS ?= $(shell n=$$(($(or $(strip $(CORES)),2) * $(PER_CORE))); [ "$$n" -ge 2 ] || n=2; echo "$$n")
# Workers take the next test as each finishes (`worksteal`), so a slow file does not hold up
# the tests queued behind it. The 25 slowest tests are printed at the end, and `JUNIT=<file>`
# writes every test's time there, which CI's summary line reads. `SHARD=K/N` runs only the K-th
# of N parts of the tests the run selected (testing/shard.py): CI's check and full each run as
# four jobs side by side, one for each part.
PYTEST = uv run pytest -n $(TEST_WORKERS) --dist worksteal --durations=25 -m "not browser"$(if $(JUNIT), --junitxml=$(JUNIT))$(if $(SHARD), --shard=$(SHARD))

.PHONY: check
check:
	git diff -z --name-only --diff-filter=d '$(BASE)...HEAD' -- 2> /dev/null | xargs -0 -r python3 features/writing/scripts/comment_lint.py || true
	python3 scripts/generate-jstack-trees.py --check
	python3 scripts/check-jstack-docs.py
	uv run ruff check .
	uv run ruff format --check .
	$(PYTEST)

# The check of a change: the same lint, and only the test files its diff from BASE to HEAD
# reaches, as scripts/select_tests.py names them. Where the script says `all`, it is
# `make check`. A pull request's CI runs it with BASE=HEAD^1, which on GitHub's merge of the
# pull request is the tip of main; a desk takes origin/main. The full suite runs on main
# after the merge. Before the tests, features/writing/scripts/prose_lint.py holds each prose
# line the diff adds to one sentence, features/writing/scripts/comment_lint.py warns on the
# mechanical unslop rules in the comments and docstrings of the files the diff changes and
# fails nothing, scripts/generate-jstack-trees.py fails a generated file that is stale against
# features/, and scripts/check-jstack-docs.py fails a page of the README or the docs that says
# what the tree does not have (`make check` runs the last three itself where the selection is
# `all`).
BASE ?= origin/main

.PHONY: check-fast
check-fast:
	@tests=$$(python3 scripts/select_tests.py '$(BASE)' HEAD) || exit; \
	python3 features/writing/scripts/prose_lint.py '$(BASE)' || exit; \
	if [ "$$tests" = all ]; then exec $(MAKE) --no-print-directory check; fi; \
	git diff -z --name-only --diff-filter=d '$(BASE)...HEAD' -- | xargs -0 -r python3 features/writing/scripts/comment_lint.py; \
	python3 scripts/generate-jstack-trees.py --check || exit; \
	python3 scripts/check-jstack-docs.py || exit; \
	set -x; \
	uv run ruff check . && uv run ruff format --check . && $(PYTEST) $$tests

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
# tags `v<version>` and pushes the tag, dropping it again where the push fails, and
# .github/workflows/release.yml does the rest: `make release-tag`, the check, `make dist`, an
# install of the wheel in a HOME of its own, and the GitHub release.
VERSION = $(shell uv version --short)

# Fails unless TAG is `v<version>` of both pyproject.toml and plugin.json.
.PHONY: release-tag
release-tag:
	@plugin=$$(python3 -c 'import json; print(json.load(open("plugin.json"))["version"])') && \
	if [ "$$TAG" != "v$(VERSION)" ] || [ "$$TAG" != "v$$plugin" ]; then \
		echo "release-tag: the tag '$$TAG' is not v$(VERSION), pyproject.toml's, and v$$plugin, plugin.json's"; \
		exit 1; \
	fi

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
	git tag -a 'v$(VERSION)' -m 'jstack $(VERSION)'
	git push origin 'v$(VERSION)' || { git tag -d 'v$(VERSION)'; exit 1; }
