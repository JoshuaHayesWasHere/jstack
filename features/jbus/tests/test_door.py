"""A known slug in a command's assignment walks through no door (`door.walks`).

On 2026-11-08 the crew of rt-deploy-guard was refused its own start: the crew block's
`B="$H/tasks/rt-deploy-guard.md"`, and a scratchpad path under that slug's worktree in an
assignment, read as the deploy door, while the same path as an argument passed. An assignment's
value is a word the shell stores, not a command it runs.
"""

import pytest

from jbus import door

PROD = "touches prod or real users"


@pytest.mark.parametrize(
    "command, cases",
    [
        ('B="$H/tasks/rt-deploy-guard.md"', []),
        ('B="$H/tasks/rt-deploy-guard.md"; cat "$B"', []),
        ("P=/tmp/wt/rt-deploy-guard/scratch/notes.txt; ls $P", []),
        ("B=$H/tasks/rt-deploy-guard.md S=/tmp/rt-deploy-guard", []),
        ('B="$H/tasks/rt-deploy-guard.md" ./deploy.sh', [PROD]),
        ('B="$H/tasks/rt-deploy-guard.md" uv run deploy', [PROD]),
        ("P=/tmp/wt/rt-deploy-guard scripts/deploy caveman", [PROD]),
        ('B="$(scripts/deploy caveman)"', [PROD]),
        ('B="$H/`scripts/deploy caveman`"', [PROD]),
        ('git commit -m "run $(scripts/deploy caveman) by hand"', [PROD]),
        (r'git commit -m "document \$(scripts/deploy caveman) syntax"', []),
        (r'git commit -m "document \`scripts/deploy caveman\` syntax"', []),
    ],
)
def test_a_known_slug_in_an_assignment_names_no_door(command, cases):
    """The assignment alone walks through nothing, and a door's own command after it, or in a
    command substitution it stores, still walks through its door."""
    assert [case for case, _ in door.walks(command)] == cases
