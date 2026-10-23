"""The mapping: a Python file that gives the chart the reader's words for model states and
steps. It is loaded from its path, whatever its name, such as Pay.map.py."""

import importlib.machinery
import importlib.util
import sys
from pathlib import Path


def load_mapping(path):
    path = Path(path).resolve()
    spec = importlib.util.spec_from_loader(
        f"statechart_mapping_{abs(hash(str(path)))}",
        importlib.machinery.SourceFileLoader(
            f"statechart_mapping_{abs(hash(str(path)))}", str(path)
        ),
    )
    module = importlib.util.module_from_spec(spec)
    written, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = written
    return module
