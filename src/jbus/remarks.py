"""Relaying what the repo's owner wrote on a pull request, and nobody else's words.

A comment or a review on a pull request is text from GitHub, and on a public repo anybody
may write one. `tell` reads the three lists GitHub keeps of them for each open pull request
of a slug jbus launched, and sends its crew the ones whose author is the repo's owner, one
message each. The owner is asked of GitHub every pass, `gh api repos/{owner}/{repo}`, and
is written nowhere in the tree. With no answer to that, nothing is relayed.

A remark by anybody else is counted and never read further: its body is not kept, logged,
sent to a thread or sent to the Chef. The pass says how many there are when that changes,
and `remarks.json` keeps the one count for a pull request.

A crew is the thread on a brief's `Thread:` line, whoever launched it.

A remark's key, `remark|<slug>|#<number>|<kind> <id> <when>`, is its retry key at T3 Code
and its mark in `sent.json`, so one is relayed once. A comment its author edits is relayed
again, since `<when>` is when it last changed. A review is relayed as it was submitted: one
not yet submitted is left out, and a later edit of its words is not seen. Each list is read
to its last page.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from jbus import dispatch, read_json, verbs, write_json
from jbus.t3 import Client, T3Error, T3Refused
from jbus.wake import Pass
from jbus.watch import World, _api

REPO = "repos/{owner}/{repo}"
LISTS = (
    ("comment", "issues/{number}/comments"),
    ("line", "pulls/{number}/comments"),
    ("review", "pulls/{number}/reviews"),
)
REFUSED = "T3 Code refused the owner's comment"
BODY = 4000
MESSAGE = (
    "jbus: {owner}, who owns the repo, wrote this on your pull request #{number}{where}. It "
    'is the user\'s word on it: handle it as "Stay on the pull request" says for a comment by '
    "the owner.\n\n{said}\n\n{url}"
)


@dataclass(frozen=True)
class Remark:
    """One comment, line comment or review, as GitHub lists it."""

    kind: str
    id: str
    author: str
    body: str
    state: str = ""
    path: str = ""
    url: str = ""
    at: str = ""

    @property
    def key(self) -> str:
        return f"{self.kind} {self.id} {self.at}"

    @property
    def empty(self) -> bool:
        """A review that says nothing yet: one its author has not submitted, or one with no
        words that only holds line comments, which have their own list."""
        if self.kind != "review":
            return False
        return self.state == "PENDING" or (not self.body.strip() and self.state == "COMMENTED")


def _remark(kind: str, one: dict[str, Any]) -> Remark:
    return Remark(
        kind,
        str(one.get("id", "")),
        str((one.get("user") or {}).get("login") or ""),
        str(one.get("body") or ""),
        str(one.get("state") or ""),
        str(one.get("path") or ""),
        str(one.get("html_url") or ""),
        str(one.get("updated_at") or one.get("submitted_at") or ""),
    )


def owner_of(run: Pass) -> str:
    """The login that owns the repo, as GitHub says now, or nothing where it did not say."""
    said = _api(run, REPO)
    login = (said.get("owner") or {}).get("login") if isinstance(said, dict) else ""
    return login if isinstance(login, str) else ""


def _pages(run: Pass, path: str) -> list[list[Any]] | None:
    """Every page of a list, as `gh api --paginate --slurp` gives them, or None."""
    asked = run.run("gh", "api", path, "--paginate", "--slurp")
    try:
        pages = json.loads(asked.stdout) if asked.returncode == 0 else None
    except ValueError:
        return None
    whole = isinstance(pages, list) and all(isinstance(page, list) for page in pages)
    return pages if whole else None


def read(run: Pass, number: int) -> list[Remark] | None:
    """Every remark on a pull request, or None where one of the lists was not given."""
    found: list[Remark] = []
    for kind, path in LISTS:
        pages = _pages(run, f"{REPO}/{path.format(number=number)}?per_page=100")
        if pages is None:
            return None
        found += [_remark(kind, one) for page in pages for one in page if isinstance(one, dict)]
    return [one for one in found if one.id and not one.empty]


def by_owner(remark: Remark, owner: str) -> bool:
    return bool(owner) and remark.author.lower() == owner.lower()


def message(remark: Remark, owner: str, number: int) -> str:
    whole = remark.body.strip()
    said = whole[:BODY] or f"({remark.state.lower() or 'no words'})"
    if len(whole) > BODY:
        said += f"\n\n(cut: this is the first {BODY} of its {len(whole)} characters)"
    where = f", on {remark.path}" if remark.path else ""
    return MESSAGE.format(owner=owner, number=number, where=where, said=said, url=remark.url)


def tell(run: Pass, client: Client, world: World) -> None:
    """Send each crew what the owner wrote on its open pull request, once for a remark."""
    crews = []
    for slug, pull in world.open.items():
        try:
            brief = (run.home / "tasks" / f"{slug}.md").read_text(errors="replace")
        except OSError:
            continue
        thread = dispatch.thread_of(brief)
        if thread:
            crews.append((slug, pull["number"], thread))
    if not crews:
        return
    owner = owner_of(run)
    if not owner:
        run.say(f"wait {run.project.name}: GitHub did not say who owns the repo, no comment read")
        return
    counted: dict[str, int] = read_json(run.state / "remarks.json", {})
    for slug, number, thread in crews:
        found = read(run, number)
        if found is None:
            run.say(f"wait {slug}: GitHub did not give the comments on #{number}")
            continue
        sent, others = run.box.sent(), 0
        for remark in found:
            key = f"remark|{slug}|#{number}|{remark.key}"
            if key in sent:
                continue
            if not by_owner(remark, owner):
                others += 1
                continue
            text = message(remark, owner, number)
            client.recipients = client.recipients | {thread}
            asked = {"threadId": thread, "message": text, "mode": "queue", "clientRequestId": key}
            try:
                client.call("t3_thread_send", asked)
            except T3Refused as error:
                run.gate(slug, REFUSED, f"{error}\n\n{text}", key=f"{REFUSED} {remark.key}")
                run.box.mark(key)
                continue
            except T3Error as error:
                run.say(f"wait {slug}: its crew could not be given the owner's comment ({error})")
                continue
            run.box.mark(key)
            run.say(f"remark {slug}: gave the crew the owner's {remark.kind} on #{number}")
        if others != counted.get(f"{slug} #{number}", 0):
            counted[f"{slug} #{number}"] = others
            write_json(run.state / "remarks.json", counted)
            run.say(f"remark {slug}: {others} on #{number} not by the owner, not read on")


STEPS = (
    verbs.Step(
        "after-expedite",
        20,
        "remarks.tell",
        lambda half: tell(half.run, half.client, half.seen.world),
        ("client", "world"),
    ),
)
