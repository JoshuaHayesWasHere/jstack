"""The first line of the statement each line coverage recorded belongs to.

Coverage records the line a statement's bytecode sits on, which for a statement whose first line
holds none, as an `elif (` whose condition ruff format puts on the next line, is a later line of
the statement. Coverage's own report folds each recorded line to the first line of its statement;
`test_new_lines_run` counts a statement by its first line, so it and `lines_ran` fold what they
read from coverage's data the same way.
"""

from collections.abc import Iterable
from functools import cache

from coverage.python import PythonParser


@cache
def parsed(path: str) -> PythonParser:
    parser = PythonParser(filename=path)
    parser.parse_source()
    return parser


def folded(path: str, numbers: Iterable[int]) -> set[int]:
    return parsed(path).first_lines(numbers)
