"""One module per output, each `render(tree) -> {path: bytes or File}`."""

from jtrees.outputs import catalog, docs, jstack, pyproject

OUTPUTS = (catalog, docs, jstack, pyproject)
