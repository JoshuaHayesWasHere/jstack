"""Whether an agent's own `t3_thread_send` may go, read by `features/home/hooks/agent-sends.sh`.

jbus carries every message between a repo's homes, and every review notice, through its
outbox: `jbus stop` from a scope to the root, `jbus word --scope` and `jbus stop answer` from the
root to a scope, `jbus noticed add --for` for a finding one home has for another, and the notice
jbus sends a crew once its review is written. A send of the agent's own skips the outbox's rules,
so it is refused when the sender is a home or a reviewer of the repo and the thread is one of the
repo's homes, now or before a handoff, or the crew on a brief's `Thread:` line. A home's send to
a crew of its own briefs is a steer, and it goes. So does any send to a scout, to another repo's
thread, and any send by a thread that is no home and no reviewer.

The sender's thread is the one T3 Code's store runs this Claude session in. A session the store
does not know, a store that cannot be read, or a repo with no homes' state is let through: what
is not known to be a home's or a reviewer's send is not refused. Which thread is a home is
`jbriefs.home`'s rule, and which thread is a crew is the brief's `Thread:` line
(`jbriefs.parse.thread_of`).
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from jbriefs import below, home, parse

TABLE = "orchestration_v2_projection_provider_threads"
STORE = Path(".t3") / "userdata" / "statev2.sqlite"


@dataclass(frozen=True)
class Home:
    """A home of the repo: its directory, its name (`root` or the scope's), and the ids its
    `home-id` and its handoff's `Was home:` line hold."""

    directory: Path
    name: str
    now: str
    was: str

    def holds(self, thread: str) -> bool:
        return thread in (self.now, self.was)

    def live(self) -> str:
        """The thread that is this home now, or an empty string between a handoff and a start."""
        return "" if self.now == self.was else self.now


@dataclass(frozen=True)
class Crew:
    """A brief's crew: its slug, its thread, the home the brief is of, and the reviewers its
    `Reviewer:` lines name."""

    slug: str
    thread: str
    home: Path
    reviewers: frozenset[str]


def thread_of_session(session: str, store: Path) -> str:
    """The T3 thread whose Claude session this is, or an empty string when the store has none."""
    if not session or not store.is_file():
        return ""
    query = (
        f"select thread_id from {TABLE}"
        " where json_extract(payload_json, '$.nativeThreadRef.nativeId') = ? limit 1"
    )
    try:
        with sqlite3.connect(f"file:{store}?mode=ro", uri=True) as db:
            found = db.execute(query, (session,)).fetchone()
    except sqlite3.Error:
        return ""
    return str(found[0]) if found else ""


def repo_of(cwd: str) -> str:
    """The name of the repo the session runs in, its main checkout's, from a worktree too."""
    try:
        said = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""
    return Path(said).parent.name if said else ""


def homes(state: Path) -> list[Home]:
    root = Home(state, "root", *home.ids(state))
    return [root, *(Home(one, one.name, now, was) for one, now, was in home.scopes(state))]


def crews(state: Path) -> list[Crew]:
    found = []
    for path in sorted((state / "tasks").glob("*.md")):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        seats = {
            "".join(said.split()[:1]).rstrip(",")
            for kind in below.REVIEWERS
            for said in below.reviewers(text, kind)
        }
        thread = parse.thread_of(text)
        found.append(Crew(path.stem, thread, home.home_of(state, text), frozenset(seats - {""})))
    return found


def _channel(sender: Home, to: Home) -> str:
    """What carries a message from one home to another, or that nothing is to be sent."""
    if sender.directory == to.directory:
        return "it is this home's own thread: send nothing"
    if to.name == "root":
        return (
            "a scoped home reaches the root only by"
            " `jbus stop <its open row> --on <row>` or `--outside <what>`"
        )
    if sender.name == "root":
        return (
            f"the user's word goes to {to.name} by `jbus word --to <project> --message"
            f" <thread>/<message> --scope {to.name}`, and the answer to its stop by"
            f" `jbus stop answer {to.name} <row> <answer>`"
        )
    return f"a finding for it goes by `jbus noticed add --for {to.name}`"


def _handed_off(to: Home) -> str:
    if to.live():
        return f"it is the {to.name} home that handed off, the {to.name} home is {to.live()} now"
    return f"it is the {to.name} home that handed off, and no thread is the {to.name} home now"


def refusal(state: Path, sender: str, to: str) -> str:
    """Why the send from `sender` to `to` is refused, and what carries it instead, or an empty
    string when it goes."""
    every = homes(state)
    from_home = next((one for one in every if one.holds(sender)), None)
    to_home = next((one for one in every if one.holds(to)), None)
    briefs = crews(state) if from_home is None or to_home is None else []
    reviewing = [one for one in briefs if sender in one.reviewers]
    if from_home is None and not reviewing:
        return ""
    if to_home is not None:
        stale = to != to_home.live()
        if from_home is None:
            what = f"a finding for it goes by `jbus noticed add --for {to_home.name}`"
        else:
            what = _channel(from_home, to_home)
        if stale and to != sender:
            return f"{_handed_off(to_home)}, and {what}"
        return what
    crew = next((one for one in briefs if one.thread == to), None)
    if crew is None:
        return ""
    owner = next((one for one in every if one.directory == crew.home), every[0])
    if from_home is not None and from_home.directory == crew.home:
        return ""
    if from_home is None and sender in crew.reviewers:
        return (
            f"it is the crew of {crew.slug}, whose review this is: send nothing, jbus sends it the"
            " review notice once the `## Review` is written"
        )
    return (
        f"it is the crew of {crew.slug}, a brief of the {owner.name} home's: a finding for it goes"
        f" by `jbus noticed add --for {owner.name}`"
    )


def main() -> int:
    """Read the hook's input on stdin. Print the refusal on stderr and end 2, or end 0."""
    try:
        call = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(call, dict) or not str(call.get("tool_name", "")).endswith(
        "__t3_thread_send"
    ):
        return 0
    given = call.get("tool_input")
    to = given.get("threadId") if isinstance(given, dict) else None
    if not isinstance(to, str) or not to:
        return 0
    repo = repo_of(str(call.get("cwd") or ""))
    state = home.homes_dir() / repo
    if not repo or not state.is_dir():
        return 0
    sender = thread_of_session(str(call.get("session_id") or ""), Path.home() / STORE)
    if not sender:
        return 0
    why = refusal(state, sender, to)
    if not why:
        return 0
    print(f"agent-sends: refused, a send to {to}: {why}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
