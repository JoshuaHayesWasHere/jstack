"""`jbriefs.proved` reads each kind of `Proved:` line the crew skill's proof block prints: a run at
the base and at the head, a `none, <kind>` exemption, and a run at the head alone for a pull
request that changes only tests, whose code at the base is the head's own."""

from jbriefs import proved

HEAD = "d" * 40
TESTS = "features/x/tests/test_x.py features/x/tests/test_y.py"


def result(line):
    return f"# alpha: a task\n\n## Result\nStatus: done\n{line}\n"


def test_a_tests_only_line_names_its_tests_and_its_head_run():
    said = proved.proved(result(f"Proved: {TESTS} head exit 0 at {HEAD}, tests only"))
    assert said == proved.Proved(
        tests=("features/x/tests/test_x.py", "features/x/tests/test_y.py"),
        head_exit=0,
        head=HEAD,
        tests_only=True,
    )


def test_a_tests_only_line_keeps_a_head_exit_that_is_not_0():
    said = proved.proved(result(f"Proved: {TESTS} head exit 1 at {HEAD}, tests only"))
    assert (said.head_exit, said.tests_only, said.fault) == (1, True, "")


def test_a_base_and_head_line_is_not_tests_only():
    base = "c" * 40
    said = proved.proved(result(f"Proved: {TESTS} base exit 1 at {base}, head exit 0 at {HEAD}"))
    assert (said.base_exit, said.head_exit, said.tests_only) == (1, 0, False)
