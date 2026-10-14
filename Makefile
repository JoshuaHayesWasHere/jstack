# The one check command: the lint commands the README lists, and its test command on
# several workers. CI runs it on every pull request.

# The tests run on this many workers (pytest-xdist), counted from the machine the run is on.
# One core bounds the suite, so workers are what make a run short. A desk takes a third of the
# machine's processors. Not `auto`, which takes them all: other work shares the machine, and
# several checks run at once.
#
# A runner (GitHub Actions sets GITHUB_ACTIONS to true) of this machine takes a sixth of them,
# since a machine that hosts runners has several going at once beside its other work. One of
# GitHub's own (RUNNER_ENVIRONMENT is github-hosted) runs nothing else, and takes them all.
# None takes fewer than two. `make check TEST_WORKERS=4` sets the count by hand, and `CORES=4`
# the processors it is counted from.
#
# The two shares and the number of test slots (`DEFAULT` in src/jgauge/slot.py) are one budget:
# the slots times a desk's workers, plus the runners times a runner's. On 12 processors with
# 2 slots and 3 runners that is 2 x 4 + 3 x 2 = 14 workers. A worker uses about 0.8 of a
# processor, so every slot and every runner at once ask for about 11 of the 12. Change one of
# the three numbers and the sum changes: tests/test_check_command.py holds it to 14.
CORES ?= $(shell getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)
SHARE = $(if $(filter true,$(GITHUB_ACTIONS)),$(if $(filter github-hosted,$(RUNNER_ENVIRONMENT)),1,6),3)
TEST_WORKERS ?= $(shell n=$$(($(or $(strip $(CORES)),2) / $(SHARE))); [ "$$n" -ge 2 ] || n=2; echo "$$n")

.PHONY: check
check:
	PYTHONPATH=tests uv run pytest -p no:xdist -p diag_plugin -o timeout=100 -q tests/test_jbus_view_page.py --maxfail=3 2>&1 | grep -v dbus | head -250 || true
	echo ===== on 4 workers
	PYTHONPATH=tests uv run pytest -n 4 -p diag_plugin -o timeout=100 -q tests/test_jbus_view_page.py 2>&1 | grep -v dbus | tail -80 || true
	false

# What changed upstream in pstack since the pin in THIRD_PARTY.md, for the files taken
# from it. Not part of the check: it reads the network. `make pstack-drift ARGS=--diff`.
.PHONY: pstack-drift
pstack-drift:
	uv run jdrift $(ARGS)
