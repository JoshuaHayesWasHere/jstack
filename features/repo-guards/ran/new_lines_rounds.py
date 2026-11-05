"""Which test files the second round of `test_new_lines_run.faults` runs.

The first round ran each module's own test files, measuring only the modules they are own tests
of. The second runs, for each module whose added lines are still unrun, every test file that names
it but its own: a test that is one module's own test and names another measures the other here.
"""


def second(
    left: dict[str, set[int]], tests: dict[str, list[str]], own: dict[str, list[str]]
) -> list[str]:
    """The test files of the second round, those of the module the fewest name first."""
    return sorted(
        {one for path in left for one in tests[path] if one not in own[path]},
        key=lambda one: (min(len(tests[path]) for path in left if one in tests[path]), one),
    )
