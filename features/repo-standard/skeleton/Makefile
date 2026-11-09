# The targets of the repo standard, the same in every stack:
# https://github.com/JoshuaHayesWasHere/jstack/blob/main/features/repo-standard/docs/skeleton.md
# scripts/stack.mk, from the stack's adapter, fills in the commands: STACK_LINT, STACK_TEST,
# STACK_SELECT and STACK_LIST. A repo of several stacks sets `stacks:` in .repo-standard.yml
# instead, and the standard's driver runs each stack over its own roots and joins them. The
# standard's guards run from jstack at the ref REPO_STANDARD_REF names, or else at the ref
# .github/workflows/check.yml calls the shared check at, such as a branch of a version not yet
# tagged, or else at the tag .repo-standard.yml pins, cloned once into .cache/<ref>, with no tool
# but git and a python3 at or past the standard's floor, which `make lint` checks first and names.
# The standard's version owns this file, so the repo's own targets, such as a deploy entry, go in
# local.mk, included at the end when it is there.
STANDARD := $(shell sed -n 's/^standard:[[:space:]]*\([0-9][0-9]*\).*/\1/p' .repo-standard.yml)
REPO_STANDARD_UPSTREAM ?= https://github.com/JoshuaHayesWasHere/jstack
REPO_STANDARD_CALLED := $(shell sed -n 's/^[[:space:]]*uses:.*\/repo-standard-check\.yml@\([A-Za-z0-9._\/-]*\).*/\1/p' .github/workflows/check.yml 2> /dev/null | head -n 1)
REPO_STANDARD_REF := $(or $(REPO_STANDARD_REF),$(REPO_STANDARD_CALLED),repo-standard-v$(STANDARD))
REPO_STANDARD_HOME := .cache/$(REPO_STANDARD_REF)
REPO_STANDARD := PYTHONPATH=$(REPO_STANDARD_HOME)/features/repo-standard/src python3 -m repo_standard

ifneq ($(shell sed -n '/^stacks:/p' .repo-standard.yml),)
STACK_LINT = $(REPO_STANDARD) stacks lint
STACK_TEST = $(REPO_STANDARD) stacks test
STACK_SHARD = $(REPO_STANDARD) stacks test --shard '$(SHARD)'
STACK_SELECT = $(REPO_STANDARD) stacks select
test select e2e: | $(REPO_STANDARD_HOME)
else
include scripts/stack.mk
STACK_SHARD = $(if $(STACK_LIST),,$(error scripts/stack.mk sets no STACK_LIST, which SHARD needs)) \
	ids=$$($(STACK_LIST)) || exit 1; \
	part=$$(printf '%s\n' "$$ids" | $(DEAL)) || exit 2; \
	if [ -z "$$part" ]; then echo 'part $(SHARD) of the suite is dealt no test'; exit 0; fi; \
	echo $(STACK_TEST) $$part; $(STACK_TEST) $$part
endif

# `make test TESTS=<ids>` runs only those tests, and `make test SHARD=<part>/<parts>` with no TESTS
# runs that part of the whole suite: the ids the stack lists, dealt to the parts in turn, as the
# shared check deals a selection. Neither reaches a test, through its environment or through the
# MAKEFLAGS a make it runs reads, where that make would take them for its own.
unexport TESTS SHARD
MAKEOVERRIDES :=
DEAL = awk -v shard='$(SHARD)' 'BEGIN { split(shard, s, "/"); k = s[1] + 0; n = s[2] + 0; \
	if (shard !~ /^[0-9]+\/[0-9]+$$/ || k < 1 || k > n) { \
	print "SHARD " shard " is not <part>/<parts>, with 1 <= part <= parts" > "/dev/stderr"; exit 2 } } \
	NF && (++i - k) % n == 0'

.PHONY: lint test check select check-fast e2e borders generate

$(REPO_STANDARD_HOME):
	git -c advice.detachedHead=false clone -q --depth 1 --branch '$(REPO_STANDARD_REF)' '$(REPO_STANDARD_UPSTREAM)' '$@'

lint: | $(REPO_STANDARD_HOME)
	@$(REPO_STANDARD) floor
	$(STACK_LINT)
	$(REPO_STANDARD) conform --upstream '$(REPO_STANDARD_UPSTREAM)'

test:
ifeq ($(if $(TESTS),,$(SHARD)),)
	$(STACK_TEST)$(if $(TESTS), $(TESTS))
else
	@$(STACK_SHARD)
endif

check: lint test

# The test ids the change from BASE reaches, one a line, or `all`. It prints nothing else, since
# the shared check reads what it prints.
select:
	@test -n '$(BASE)' || { echo 'make select needs BASE=<ref>' >&2; exit 2; }
	@$(STACK_SELECT) '$(BASE)'

# The browser tests of each stack whose config sets `e2e:`: its npm script runs Playwright on the
# app it builds and serves with a mocked API, never on a live stage, and a test that passes only on
# a retry fails. `make e2e E2E_LIST=<file>` runs only the ids in the file, one a line, as `make
# select` prints them.
e2e:
	$(REPO_STANDARD) stacks e2e$(if $(E2E_LIST), '$(E2E_LIST)')

check-fast: lint
	@test -n '$(BASE)' || { echo 'make check-fast needs BASE=<ref>' >&2; exit 2; }
	@selection=$$($(MAKE) -s --no-print-directory select BASE='$(BASE)') || exit 1; \
	case $$selection in \
	all) $(MAKE) --no-print-directory test ;; \
	'') echo 'the change from $(BASE) selects no test' ;; \
	*) $(MAKE) --no-print-directory test TESTS="$$(echo $$selection)" ;; \
	esac

# A change across two features needs the label `cross-cutting`, so the borders of a change are
# checked here, with the pull request's labels in LABELS, and not in `lint`, which the shared check
# runs with no labels. borders.yml runs this on each push of a pull request and each change of its
# labels.
borders: | $(REPO_STANDARD_HOME)
	$(REPO_STANDARD) borders --hard --base '$(BASE)' --labels "$$LABELS"

# Writes each generated file again from the manifests, after a feature is added or changed. The
# lint runs the same generators with --check, which fails on a stale file.
generate:
	python3 scripts/generate-index.py

-include local.mk
