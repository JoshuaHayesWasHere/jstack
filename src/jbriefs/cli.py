from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from jbriefs import page, parse

DEFAULT_STATE = Path.home() / ".local" / "state" / "home"


def default_out() -> Path:
    """Under the cache, never the state directory: the homes own that."""
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache) / "jbriefs" / "briefs.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jbriefs",
        description="Write one page of every home's handoff, open plan entries, briefs and "
        "results, and print its path.",
    )
    parser.add_argument(
        "state",
        nargs="?",
        type=Path,
        default=DEFAULT_STATE,
        help="the directory that holds one home per repo (default: %(default)s)",
    )
    parser.add_argument("--out", type=Path, help="where to write the page (default: the cache)")
    args = parser.parse_args(argv)

    state = args.state.expanduser()
    out = (args.out or default_out()).expanduser()
    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    html = page.render(parse.repos(state), state=state, generated=generated)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(out)
    return 0
