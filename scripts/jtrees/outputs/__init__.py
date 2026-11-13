"""One module per output, each `render(tree) -> {path: bytes or File}`."""

from jtrees.outputs import catalog, docs, pyproject

OUTPUTS = (catalog, docs, pyproject)
