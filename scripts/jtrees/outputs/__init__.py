"""One module per output, each `render(tree) -> {path: bytes or File}`, and its own folders,
`DIRS`, where it has them."""

from jtrees.outputs import catalog, docs, harness, pyproject

OUTPUTS = (catalog, docs, pyproject, harness)
