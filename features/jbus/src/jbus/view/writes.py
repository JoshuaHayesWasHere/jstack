"""The two writes of `jbus view`, `POST /answer` and `POST /approve`, and the type of every
answer the server gives (`Answer`). The package's docstring says what each write takes and
gives.

`POST /approve` is the user's go for the item named by its id. `jbus.item.approve` decides it,
as `jbus item approve` does. An approval has no words, and the page approves a proposed item
with this write.

`Writes` is the part of `jbus.view.App` that writes. What it reads, `sources`, `clock` and
`config`, belongs to the app.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import jbus
from jbus import Refused, acts, asks, item, party, passes, questions, queue, t3, wake
from jbus.view import state
from jbus.view.clean import clean
from jbus.view.state import Sources

WRITE = "/answer"
APPROVE = "/approve"
ACT = "/act"
WRITES = (WRITE, APPROVE)
WHERE = "jbus view"
BATCH = 200
SEND = 15.0
HTML, JSON = "text/html; charset=utf-8", "application/json"


@dataclass(frozen=True)
class Answer:
    status: int
    body: bytes
    kind: str = JSON


def said(status: int, value: Any) -> Answer:
    return Answer(status, (json.dumps(value, sort_keys=True) + "\n").encode())


NOT_FOUND = said(404, {"error": "not found"})


def reader(sources: Sources) -> jbus.Config:
    """A `Config` for code that only reads the state. It has the projects the state
    directory names, and no server and no config directory."""
    nowhere = Path(os.devnull)
    return jbus.Config(
        server="",
        runtime_mode=None,
        dispatch=False,
        max_running=0,
        warn_days=0,
        wake_alert=0,
        room_passes=0,
        projects=tuple(
            jbus.Project(name, nowhere, name, "", "", "") for name in state.projects(sources)
        ),
        config_dir=nowhere,
        state_dir=sources.state_dir,
        home_dir=sources.home_dir,
        user=sources.user,
    )


class Writes:
    """Close questions with the user's answer, and approve an item."""

    sources: Sources
    clock: Callable[[], datetime]
    config: Callable[[], jbus.Config]

    def _carry(self, name: str, closed: questions.Question, now: datetime) -> tuple[bool, str, str]:
        """Send one answer that differs from the default to the thread that asked the
        question, as a pass would. It returns whether the answer went, and the reason where it
        did not, with no secret in it. It also returns what will send the answer later. For a
        slug that was removed from the queue, nothing sends it later."""
        pass_ = "the next pass sends it"
        hidden: tuple[str, ...] = ()
        try:
            config = replace(
                self.config(), state_dir=self.sources.state_dir, home_dir=self.sources.home_dir
            )
            hidden = config.secrets()
            run = passes.Pass(config, config.project(name), now, say=lambda line: None)
            client = t3.Client(config.server, config.token_path, timeout=SEND)
            went = questions.carry(run, client, closed)
        except (Refused, OSError) as error:
            return False, jbus.redact(str(error).removeprefix("refused: "), hidden), pass_
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            return False, f"the send failed ({type(error).__name__})", pass_
        if went.told:
            return True, "", ""
        if not went.message:
            return False, f"{closed.slug} was removed from the queue", ""
        if not went.thread:
            why = f"{closed.slug} has no Thread: line in a brief or request"
            return False, why, "a pass sends it once one names its thread"
        if went.held:
            why = f"its thread {went.thread} is capped"
            return False, why, "the first pass after the reset sends it"
        how = "T3 Code refused it" if went.refused else "T3 Code did not answer"
        return False, jbus.redact(f"{how} ({went.error})", hidden), pass_

    def _close(
        self, name: str, number: int, option: str, words: str, now: datetime
    ) -> tuple[bool, dict[str, Any]]:
        """Close one question. It returns whether the question closed, and what to tell the page."""
        user, state_dir = self.sources.user, self.sources.state(name)
        held = {one.number: one for one in questions.load(state_dir)}
        one = held.get(number)
        options = one.options if one else ()
        picked = [each for each in options if state.text(each.name) == option]
        if one and option and not picked:
            say = f"Question {number} has no option of that name, and nothing changed."
            return False, {"number": number, "say": say, "first": None}
        keeps = not words and (not picked or picked[0].default)
        taken = [each.name for each in options if each.default] + ([one.default] if one else [])
        if keeps:
            given = next((word for word in taken if word.strip()), "the default")
        else:
            named = [] if not picked or (picked[0].default and words) else [picked[0].name]
            given = ". ".join([*named, *([words] if words else [])])
        try:
            closed, _ = questions.answer(
                state_dir,
                number,
                party=party.Party("user", "view"),
                evidence=party.Evidence("view", "", given, user.stamp(now), WHERE),
                where=WHERE,
                keeps=keeps,
                user=user,
            )
        except Refused as error:
            first = one.answer if one else None
            first = first or next(
                (q.answer for q in questions.load(state_dir) if q.number == number), None
            )
            say = (
                f"Question {number} was answered already, and nothing changed: {first.line()}."
                if first
                else f"Question {number} did not close: {str(error).removeprefix('refused: ')}."
            )
            kept = {**asdict(first), "line": first.line()} if first else None
            return False, {"number": number, "say": say, "first": kept}
        home = self.sources.home(name)
        thread, role = state.asker(home, closed.slug, state.threads_seen(self.sources, name))
        whose = f"the {role} thread of {closed.slug}" if role else f"the thread of {closed.slug}"
        at = user.clock(now)
        sent, why, later = (False, "", "") if keeps else self._carry(name, closed, now)
        if keeps:
            say = f"Question {number} closed at {at} with its default, and nothing was sent."
        elif sent:
            say = f"Question {number} closed at {at}, and its answer went to {whose}."
        elif later:
            say = (
                f"Question {number} closed at {at} with its answer recorded and not yet sent, "
                f"since {why}: {later}."
            )
        else:
            say = (
                f"Question {number} closed at {at} with its answer recorded, and it goes to "
                f"no thread, since {why}."
            )
        return True, {
            "number": number,
            "slug": closed.slug,
            "keeps": keeps,
            "words": closed.answer.words,
            "sent": sent,
            "why": why,
            "thread": thread if sent else "",
            "role": role,
            "say": say,
        }

    def _answer(self, name: str, body: bytes) -> Answer:
        """Close each question whose number the body gives, with the user's answer."""
        try:
            asked = json.loads(body)
            numbers, option, words = asked["numbers"], asked.get("option"), asked.get("words")
            shaped = (
                isinstance(numbers, list)
                and 0 < len(numbers) <= BATCH
                and all(isinstance(n, int) and not isinstance(n, bool) for n in numbers)
                and len(set(numbers)) == len(numbers)
                and (option is None or isinstance(option, str))
                and (words is None or isinstance(words, str))
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            shaped = False
        if not shaped:
            return said(400, {"error": "a write is the numbers to close, an option and words"})
        option, words = option or "", " ".join((words or "").split())
        if len(numbers) > 1 and (option or words):
            return said(400, {"error": "a batch only takes defaults: answer that one by itself"})
        now = self.clock()
        closed, refused = [], []
        for number in numbers:
            went, told = self._close(name, number, option, words, now)
            (closed if went else refused).append(told)
        answer = {"at": state.iso(now), "closed": closed, "refused": refused}
        return said(200 if closed else 409, clean(answer, (state.repo(self.sources, name),)))

    def _approve(self, name: str, body: bytes) -> Answer:
        """Approve one item through `item.approve`, as the user of the settings, in the view."""
        try:
            asked = json.loads(body)
            id, seen = asked["item"], asked["seen_event"]
            shaped = isinstance(id, str) and 0 < len(id) <= 64 and isinstance(seen, str) and seen
        except (ValueError, TypeError, KeyError, AttributeError):
            shaped = False
        if not shaped:
            return said(400, {"error": "a go is an item and seen_event"})
        user, state_dir, now = self.sources.user, self.sources.state(name), self.clock()
        if id not in item.items(state_dir):
            return NOT_FOUND
        box = wake.Box(state_dir, reader(self.sources).project(name))
        heard = queue.Said(f"approve {id}", state.iso(now), WHERE, False)
        try:
            made = item.approve(
                state_dir,
                box,
                id,
                by=user.user,
                where=item.Where.VIEW,
                words="",
                seen=seen,
                user=user,
                project=name,
                basis=item.Basis("view", WHERE, heard),
            )
        except Refused as error:
            say = str(error).removeprefix("refused: ")
            return self._approved(name, 409, id, say, now)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            say = "The server failed during the go: the state below is what the record says."
            return self._approved(name, 500, id, say, now)
        say = f"{id} approved at {user.clock(now)}: {made['line']}"
        return self._approved(name, 200, id, say, now)

    def _approved(self, name: str, status: int, id: str, say: str, now: datetime) -> Answer:
        """What a go's answer says: the sentence, and the item as the record has it now."""
        now_is = item.items(self.sources.state(name)).get(id)
        answer = {
            "at": state.iso(now),
            "item": id,
            "say": say,
            "state": str(now_is.state) if now_is else None,
            "last_event": now_is.last_event if now_is else None,
        }
        return said(status, clean(answer, (state.repo(self.sources, name),)))

    def act(self, name: str, body: bytes, authorization: str) -> Answer:
        """`POST /act`, the bot's own route: a go or an answer, taken by `jbus.acts.act` as the
        bot, on the bot's word from its chat. Only a request with the bot's key is the bot's
        (`acts.is_bot`), wherever it comes from."""
        if not acts.is_bot(self.sources.state_dir, authorization):
            return said(401, {"error": "this route is the bot's, and takes the bot's key"})
        try:
            asked = json.loads(body)
            verb, given, seen = asked["action"], asked["evidence"], asked.get("seen") or ""
            words = " ".join(str(asked.get("words") or "").split())
            if verb == "go":
                subject, pre = asked["slug"], asked["sha12"]
                shaped = isinstance(subject, str) and isinstance(pre, str) and len(pre) == 12
            else:
                number, pre = asked["number"], ""
                shaped = verb == "answer" and isinstance(number, int) and bool(words)
                subject = str(number)
                shaped = shaped and isinstance(asked.get("keeps", False), bool)
            shaped = shaped and isinstance(seen, str) and isinstance(given, str)
            evidence = party.evidence(given) if shaped else None
        except (ValueError, TypeError, KeyError, AttributeError):
            shaped, evidence = False, None
        if not shaped or evidence is None or evidence.source != "bot-chat":
            return said(
                400,
                {
                    "error": "an act is {action: go, slug, sha12} or {action: answer, number, "
                    "words, keeps}, with evidence bot-chat:<address>/<device> and an optional seen"
                },
            )
        now = self.clock()
        heard = replace(
            evidence,
            words=words or f"go {subject}",
            said_at=self.sources.user.stamp(now),
            said_in=f"bot-chat {evidence.ref}",
        )
        config = replace(
            self.config(), state_dir=self.sources.state_dir, home_dir=self.sources.home_dir
        )
        project = config.project(name)
        run = passes.Pass(config, project, now, say=lambda line: None)
        action = party.Action(verb, subject, pre, seen)
        try:
            made = acts.act(
                run,
                party.BOT,
                action,
                heard,
                asks=asks._asks(config, project) if verb == "go" else None,
                keeps=bool(asked.get("keeps", False)),
                where=f"{WHERE} {ACT}",
                ran_by=queue.BOT,
            )
        except Refused as error:
            kept = acts.read(self.sources.state(name))
            last = kept[-1] if kept else None
            return said(409, {"error": str(error), "act": last})
        return said(200, {"act": asdict(made)})
