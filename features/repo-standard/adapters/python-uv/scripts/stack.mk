# The python-uv adapter's commands for the Makefile's targets. uv runs the lint and the tests from
# uv.lock, and the selection runs in python3 alone, so CI's plan selects before any setup. The
# tests run through scripts/select.py, which runs `uv run --locked pytest` and writes the files that
# failed to $REPO_STANDARD_FAILED where that is set.
STACK_LINT = uv run --locked ruff check . && uv run --locked ruff format --check .
STACK_TEST = python3 scripts/select.py --test
STACK_SELECT = python3 scripts/select.py
STACK_LIST = python3 scripts/select.py --list
