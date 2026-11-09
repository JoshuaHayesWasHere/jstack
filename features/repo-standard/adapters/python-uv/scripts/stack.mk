# The python-uv adapter's commands for the Makefile's targets. uv runs the lint and the tests from
# uv.lock, and the selection runs in python3 alone, so CI's plan selects before any setup.
STACK_LINT = uv run --locked ruff check . && uv run --locked ruff format --check .
STACK_TEST = uv run --locked pytest
STACK_SELECT = python3 scripts/select.py
STACK_LIST = python3 scripts/select.py --list
