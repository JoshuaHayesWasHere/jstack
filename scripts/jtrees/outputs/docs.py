"""The docs indexes: the regions of README.md and of the pages under docs/ that the tree writes.

A region is the text between `<!-- generated: <part> ... -->` and the next
`<!-- generated: end -->`; the rest of each page is hand-written and is left as it is. The
parts are:

- `commands`, in README.md: one row a command, its page and what its feature does.
- `catalog`, in docs/playbooks.md: one row a feature, with its skills, principles and
  playbooks.
- `hooks`, in docs/hooks.md: one row a hook, status line or git hook the install adds.
- `pages`, in any page `<x>.md`: one line a page of the folder `<x>/` beside it, its first
  line `# <heading>`.

A page that must hold a part and has lost its region is refused, and so is a part with no
maker.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path

from jtrees.crawl import Invalid
from jtrees.model import FEATURES, Item, Tree

REGION = re.compile(
    r"(?P<begin><!-- generated: (?P<part>[a-z-]+)[^\n]*-->\n)(?P<body>.*?)"
    r"(?P<end><!-- generated: end -->)",
    re.S,
)
HEADING = re.compile(r"\A# (.+)\n")
REQUIRED = {"README.md": "commands", "docs/playbooks.md": "catalog", "docs/hooks.md": "hooks"}


def _link(page: str, target: str) -> str:
    return os.path.relpath(target, os.path.dirname(page) or ".")


def commands(tree: Tree, page: str) -> str:
    rows = ["| Command | Page | What it does |\n", "|---|---|---|\n"]
    listed = sorted(
        (command, feature) for feature in tree.features for command, _ in feature.commands
    )
    for command, feature in listed:
        doc = feature.docs[0] if feature.docs else ""
        shown = f"[{doc}]({_link(page, doc)})" if doc else ""
        rows.append(f"| `{command}` | {shown} | {feature.description} |\n")
    return "".join(rows)


def catalog(tree: Tree, page: str) -> str:
    def links(items: list[Item]) -> str:
        return ", ".join(f"[{one.name}]({_link(page, one.path)})" for one in items)

    rows = [
        "| Feature | What it does | Skills and principles | Playbooks |\n",
        "|---|---|---|---|\n",
    ]
    for feature in tree.features:
        held = [one for one in tree.items if one.feature == feature.name]
        skills = [one for one in held if one.kind in ("skill", "principle")]
        playbooks = [one for one in held if one.kind == "playbook"]
        if skills or playbooks:
            rows.append(
                f"| `{feature.name}` | {feature.description} | {links(skills)} | "
                f"{links(playbooks)} |\n"
            )
    return "".join(rows)


def hooks(tree: Tree, page: str) -> str:
    rows = ["| Hook | Script | Harnesses | Feature |\n", "|---|---|---|---|\n"]

    def row(when: str, script: str, harnesses: str, feature: str) -> None:
        rows.append(f"| {when} | [{script}]({_link(page, script)}) | {harnesses} | `{feature}` |\n")

    for feature in tree.features:
        for hook in feature.hooks:
            when = f"`{hook.event}`" + (f", matcher `{hook.matcher}`" if hook.matcher else "")
            when += ", refuses" if hook.refuses else ""
            row(when, hook.script, ", ".join(hook.harnesses), feature.name)
        if feature.status_line:
            row("the status line", feature.status_line, "claude-code", feature.name)
        for name, script in feature.git_hooks:
            row(f"git `{name}`", script, "git", feature.name)
    return "".join(rows)


def pages(tree: Tree, page: str) -> str:
    folder = Path(page).with_suffix("")
    lines = []
    for path in sorted((tree.root / folder).glob("*.md")):
        found = HEADING.match(path.read_text(encoding="utf-8"))
        if not found:
            raise Invalid([f"{folder}/{path.name}: its first line is not `# <heading>`"])
        lines.append(f"- [{found[1]}]({folder.name}/{path.name})\n")
    return "".join(lines)


MAKERS: dict[str, Callable[[Tree, str], str]] = {
    "commands": commands,
    "catalog": catalog,
    "hooks": hooks,
    "pages": pages,
}


def _scanned(tree: Tree) -> list[str]:
    found = {"README.md", *REQUIRED}
    for glob in ("docs/**/*.md", f"{FEATURES}/*/docs/**/*.md"):
        found |= {path.relative_to(tree.root).as_posix() for path in tree.root.glob(glob)}
    return sorted(one for one in found if (tree.root / one).is_file())


def render(tree: Tree) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    faults: list[str] = []
    for page in _scanned(tree):
        text = (tree.root / page).read_text(encoding="utf-8")
        parts = [found["part"] for found in REGION.finditer(text)]
        if page in REQUIRED and REQUIRED[page] not in parts:
            faults.append(f"{page}: has no `<!-- generated: {REQUIRED[page]} -->` region")
        if not parts:
            continue
        unknown = [part for part in parts if part not in MAKERS]
        if unknown:
            faults.append(f"{page}: has a region of no part the generator makes: {unknown}")
            continue

        def fill(found: re.Match[str], page: str = page) -> str:
            return found["begin"] + MAKERS[found["part"]](tree, page) + found["end"]

        out[page] = REGION.sub(fill, text).encode()
    if faults:
        raise Invalid(faults)
    return out
