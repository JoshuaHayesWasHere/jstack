"""The plugins every test of the checkout loads, from `tests/` and from each feature's own
`tests/`: the fixtures of `testing/jstack_fixtures.py`, whose autouse ones isolate every test
from the machine, and the test modules the tests of other features import. Each test folder is
on pytest's `pythonpath` (`pyproject.toml`), so a module named here is found by its bare name
wherever it lives."""

pytest_plugins = [
    "testing.jstack_fixtures",
    "test_jbus_kitchen",
    "test_home_merge",
    "test_home_thread",
    "crew.helpers",
    "test_sweep",
    "test_jmerge_guarded",
]
