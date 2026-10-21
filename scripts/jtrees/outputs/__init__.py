"""One module per output, each `render(tree) -> {path: bytes}`."""

from jtrees.outputs import catalog, docs, pyproject

OUTPUTS = (catalog, docs, pyproject)
