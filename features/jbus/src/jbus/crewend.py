"""Whether a crew's turn may end, read by `features/jbus/hooks/turn-end.sh`, a `Stop` hook of
Claude Code and Codex.

A crew's turn ends where its task's end is on record: its Result, a wait that jbus owns, or its
pull request. Two ends are not, and the hook sends the crew back to finish in the same turn, in
place of `jbus poll` finding the thread over a pass later (`watch._stale`, `threads.resume`):

- the brief has no `## Result`, and the thread waits on nothing jbus wakes it from
  (`watch.owned_waits`);
- the last Result says its pull request opens after its review (`review.before_pull`), every
  reviewer jbus launched has written a review that ran (`review.awaited`), and no Result names a
  pull request: the crew is to open it and write the follow-up Result that names it.

The hook acts only for the thread a brief names: the session's thread, from T3 Code's store
(`sends.thread_of_session`, as `jbus.door` reads it), is the `Thread:` of the brief of the
checkout's branch, `tasks/<branch>.md` in the repo's homes' state, since a crew's branch is its
slug. It reads that one brief and no other. Any other thread, a session the store does not know,
and a call whose `stop_hook_active` says the hook sent this turn back once already, end their
turn. So does every call the hook cannot judge: the hook fails open, since a hook that fails
closed would trap a turn, and `threads.resume` stays the fallback.

The answer is the one JSON object both harnesses read from a `Stop` hook's stdout,
`{"decision": "block", "reason": <what to do>}`, or nothing, and the module always ends 0.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsettings
from jbriefs import findings, home, parse, sends
from jbus import review, watch
from jbus.mirror import last_result, sections
from jgauge import slot

NO_RESULT = (
    "jbus: your brief, {brief}, has no `## Result` yet, so this turn does not end here. Carry on "
    'with the task from where you are, and end the turn with the Result the crew skill\'s "End" '
    "has you write, or on a wait that jbus wakes you from: a test slot, your run that holds one, "
    "or a GitHub run you registered with `jbus run-wait`."
)
OWES_PULL = (
    "jbus: every review of {brief} is written, and its last Result says the pull request opens "
    "after the review, so this turn does not end here. Handle the review as the crew skill's "
    '"The review" says, open the pull request, and write the follow-up Result that names it.'
)


def why(brief: Path, text: str, thread: str, waits: set[str]) -> str:
    """Why the crew of the brief at `brief`, whose text is `text`, may not end its turn, or
    nothing where it may. `waits` holds the threads that wait on jbus (`watch.owned_waits`)."""
    result = last_result(text)
    if thread in waits:
        return ""
    if not result:
        return NO_RESULT.format(brief=brief)
    if not review.before_pull(result) or watch.unfinished(result):
        return ""
    if findings.mode_of(text) == findings.NONE or review.awaited(text, result):
        return ""
    if any(watch.named(one)[0] for one in _results(text)):
        return ""
    return OWES_PULL.format(brief=brief)


def _results(text: str) -> list[str]:
    return [f"{h}\n{b}" for h, b in sections(text) if h.startswith("## Result")]


def answer(call: Any) -> str:
    """The reason to send the turn back, or nothing, for a `Stop` hook's input."""
    if not isinstance(call, dict) or call.get("stop_hook_active"):
        return ""
    cwd = str(call.get("cwd") or "")
    repo = sends.repo_of(cwd)
    session = str(call.get("session_id") or "")
    thread = jsettings.thread_id(sends.thread_of_session(session, Path.home() / sends.STORE))
    if not repo or not thread:
        return ""
    branch = subprocess.run(
        ["git", "-C", cwd, "branch", "--show-current"], capture_output=True, text=True, timeout=3
    ).stdout.strip()
    brief = home.homes_dir() / repo / "tasks" / f"{branch}.md"
    if not branch or "/" in branch or not brief.is_file():
        return ""
    text = brief.read_text(errors="replace")
    if jsettings.thread_id(parse.thread_of(text)) != thread:
        return ""
    return why(brief, text, thread, watch.owned_waits(slot.locks_dir()))


def main() -> int:
    """Read the hook's input on stdin. Print the decision that sends the turn back, or nothing,
    and end 0 either way."""
    try:
        reason = answer(json.load(sys.stdin))
    except Exception:
        return 0
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
