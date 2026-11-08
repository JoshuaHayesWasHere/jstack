# The targets of the repo standard, the same in every stack:
# https://github.com/JoshuaHayesWasHere/jstack/blob/main/features/repo-standard/docs/skeleton.md
# scripts/stack.mk, from the stack's adapter, fills in the commands: STACK_LINT, STACK_TEST and
# STACK_SELECT. The standard's guards run from jstack at the tag .repo-standard.yml pins, cloned
# once into .cache/, with no tool but git and python3.
STANDARD := $(shell sed -n 's/^standard:[[:space:]]*\([0-9][0-9]*\).*/\1/p' .repo-standard.yml)
REPO_STANDARD_UPSTREAM ?= https://github.com/JoshuaHayesWasHere/jstack
REPO_STANDARD_HOME := .cache/repo-standard-v$(STANDARD)
REPO_STANDARD := PYTHONPATH=$(REPO_STANDARD_HOME)/features/repo-standard/src python3 -m repo_standard

include scripts/stack.mk

# `make test TESTS=<ids>` runs only those tests. TESTS stays out of the environment, where a make
# that a test runs would take it for its own.
unexport TESTS

.PHONY: lint test check select check-fast borders generate

$(REPO_STANDARD_HOME):
	git -c advice.detachedHead=false clone -q --depth 1 --branch 'repo-standard-v$(STANDARD)' '$(REPO_STANDARD_UPSTREAM)' '$@'

lint: | $(REPO_STANDARD_HOME)
	$(STACK_LINT)
	$(REPO_STANDARD) conform --upstream '$(REPO_STANDARD_UPSTREAM)'

test:
	$(STACK_TEST)$(if $(TESTS), $(TESTS))

check: lint test

# The test ids the change from BASE reaches, one a line, or `all`. It prints nothing else, since
# the shared check reads what it prints.
select:
	@test -n '$(BASE)' || { echo 'make select needs BASE=<ref>' >&2; exit 2; }
	@$(STACK_SELECT) '$(BASE)'

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
