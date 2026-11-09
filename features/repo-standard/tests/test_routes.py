"""`repo-standard routes`, the reference contract of a mock API, run in this process.

`test_mock_contract.py` runs the contract on a Go router and a TypeScript mock, where go and node
run. These cases call `repo_standard.cli.main` with `echo` commands for each side, so the verb's
own lines run anywhere: a mock route the producer serves, one it lacks, a literal segment against
a producer parameter, and each printout the contract refuses with exit 2.
"""

import json
import shlex

import pytest

from repo_standard import cli


def prints(*routes):
    return f"echo {shlex.quote(json.dumps([{'method': m, 'path': p} for m, p in routes]))}"


PRODUCER = prints(("GET", "/pets/{id}"), ("POST", "/pets"), ("GET", "/pets/{id}/toys"))


def contract(capsys, producer, mock):
    code = cli.main(["routes", "--producer", producer, "--mock", mock])
    said = capsys.readouterr()
    return code, said.out + said.err


def test_a_mock_whose_every_route_the_producer_serves_passes(capsys):
    mock = prints(("get", "/pets/{petId}"), ("GET", "/pets/7"), ("POST", "/pets"))
    assert contract(capsys, PRODUCER, mock) == (
        0,
        "routes: the producer serves each of the mock's 3 routes\n",
    )


def test_each_mock_route_the_producer_lacks_is_named(capsys):
    mock = prints(("GET", "/pets"), ("DELETE", "/pets/{id}"), ("GET", "/pets/{id}"))
    assert contract(capsys, PRODUCER, mock) == (
        1,
        "DELETE /pets/{id}: the mock answers it, and the producer has no such route\n"
        "GET /pets: the mock answers it, and the producer has no such route\n",
    )


def test_a_mock_parameter_is_not_served_by_a_producer_literal(capsys):
    producer = prints(("GET", "/pets/mine"))
    assert contract(capsys, producer, prints(("GET", "/pets/{id}")))[0] == 1


@pytest.mark.parametrize(
    ("producer", "said"),
    [
        ("exit 3", "the producer command `exit 3` exited 3"),
        ("echo not json", "the producer command `echo not json` printed no JSON"),
        ("echo '{}'", "printed no list of routes"),
        ('echo \'[["GET", "/pets"]]\'', 'printed ["GET", "/pets"], not a {method, path}'),
        (prints(("", "/pets")), 'printed the method "", not one like GET'),
        (prints(("GET", "pets")), 'printed the path "pets", not one from /'),
        (prints(("GET", "/files/{p...}")), "whose {p...} is no {name} parameter"),
    ],
)
def test_a_printout_the_contract_cannot_read_exits_2(capsys, producer, said):
    code, out = contract(capsys, producer, prints(("GET", "/pets")))
    assert code == 2
    assert out.startswith("repo_standard routes: ") and said in out, out
