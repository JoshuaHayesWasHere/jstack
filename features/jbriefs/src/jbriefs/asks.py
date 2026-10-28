"""The lines a playbook asks a brief to have, and the fault of a brief that lacks one.

A playbook's `Run by:` line names them in code spans after its words `in a brief with`. An
investigation's playbook (runtime-forensics, prototype, eval) asks for `Pull request: ask
first`, so `parse.faults`, which `jbus queue add` runs, refuses a brief that would open a pull
request for one, and its findings never reach main. `jbus playbook` prints the same lines to the
crewmate as `has` or `lacks`.
"""

from __future__ import annotations

import re

from jbriefs import skills

_ASKED = re.compile(r"`([^`]*)`")


def asked(playbook: str) -> list[str]:
    """The lines a playbook's `Run by:` asks a brief to have."""
    by = next((line for line in playbook.splitlines() if line.startswith("Run by: ")), "")
    return _ASKED.findall(by.partition(" in a brief with ")[2])


def lacks(text: str, playbook: str) -> list[str]:
    """The lines `asked` names that no line of `text` starts with."""
    lines = text.splitlines()
    return [one for one in asked(playbook) if not any(line.startswith(one) for line in lines)]


def fault(text: str, name: str) -> str:
    """Why a brief lacks a line its playbook `name` asks for, as one line, or an empty string."""
    missing = lacks(text, skills.where("playbook", name).read_text())
    if not missing:
        return ""
    named = ", ".join(f"`{line}`" for line in missing)
    return (
        f"brief's Playbook: line names {name}, whose Run by: asks a brief for lines it "
        f"lacks: {named} (an investigation opens no pull request until the user says so)"
    )
