"""The two writes of `jbus view`, `POST /answer` and `POST /steer`, and the type of every
answer the server gives (`Answer`). The package's docstring says what each write takes and
gives.

A steer's `action` may also be `APPROVE`, the user's go for the item named by its id.
`jbus.steer.approve` decides it, as `jbus item approve` does. An approval has no words, and
the page approves a proposed item with this write.

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
from jbus import Refused, item, passes, questions, queue, steer, t3, wake
from jbus.view import state
from jbus.view.clean import clean
from jbus.view.state import Sources

WRITE = "/answer"
STEER = "/steer"
WRITES = (WRITE, STEER)
WHERE = "jbus view"
BATCH = 200
SEND = 15.0
HTML, JSON = "text/html; charset=utf-8", "application/json"
APPROVE = "approve"
ACTIONS = {str(one) for one in item.Steer} | {APPROVE}


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
    directory names, and no server, no webhook and no config directory."""
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
    """Close questions with the user's answer, and steer or approve an item."""

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
            closed = questions.answer(
                state_dir,
                number,
                given,
                by=user.user,
                at=user.stamp(now),
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

    def _steer(self, name: str, body: bytes) -> Answer:
        """Steer one item through `steer.steer`, or approve it through `steer.approve`. Either
        call names the user of the settings as the one who acts, and the view as the place."""
        try:
            asked = json.loads(body)
            id, action, seen = asked["item"], asked["action"], asked["seen_event"]
            words, confirm = asked.get("words", ""), asked.get("confirm", False)
            shaped = (
                isinstance(id, str)
                and 0 < len(id) <= 64
                and action in ACTIONS
                and isinstance(seen, str)
                and bool(seen)
                and isinstance(words, str)
                and (bool(words.strip()) or action in (item.Steer.HOLD, APPROVE))
                and isinstance(confirm, bool)
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            shaped = False
        if not shaped:
            return said(400, {"error": "a steer is an item, an action, words, seen_event, confirm"})
        user, state_dir, now = self.sources.user, self.sources.state(name), self.clock()
        if id not in item.items(state_dir):
            return NOT_FOUND
        box = wake.Box(state_dir, reader(self.sources).project(name))
        heard = queue.Said(words or f"{action} {id}", state.iso(now), WHERE, False)
        basis = steer.Basis("view", WHERE, heard)
        try:
            if action == APPROVE:
                made = steer.approve(
                    state_dir,
                    box,
                    id,
                    by=user.user,
                    where=item.Where.VIEW,
                    words=words,
                    seen=seen,
                    user=user,
                    project=name,
                    basis=basis,
                )
            else:
                made = steer.steer(
                    state_dir,
                    box,
                    id,
                    action,
                    words,
                    seen,
                    user.user,
                    item.Where.VIEW,
                    confirm,
                    user=user,
                    basis=basis,
                )
        except Refused as error:
            status = 400 if str(error) == steer.CONFIRM else 409
            say = str(error).removeprefix("refused: ").replace("--confirm", "confirm")
            return self._steered(name, status, id, say, now)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            say = "The server failed during the steer: the state below is what the record says."
            return self._steered(name, 500, id, say, now)
        did = "approved" if action == APPROVE else action
        say = f"{id} {did} at {user.clock(now)}: {made['line']}"
        if action == item.Steer.MESSAGE:
            joint = " " if say.endswith((".", "?", "!")) else ". "
            say = f"{say}{joint}{self._message(name, made['id'], now)}"
        return self._steered(name, 200, id, say, now)

    def _message(self, name: str, line: str, now: datetime) -> str:
        """Send the line of a message steer to the item's home, as the command does. It
        returns whether the line went, and the reason where it did not, with no secret in it."""
        hidden: tuple[str, ...] = ()
        state_dir = self.sources.state(name)
        try:
            config = replace(
                self.config(), state_dir=self.sources.state_dir, home_dir=self.sources.home_dir
            )
            hidden = config.secrets()
            mine = replace(config, user=self.sources.user)
            run = passes.Pass(mine, config.project(name), now, say=lambda line: None)
            client = t3.Client(config.server, config.token_path, timeout=SEND)
            went = steer.deliver(run, client)
            one = went.get(line) or steer.sends(state_dir).get(line, {})
            why = one.get("waits", "")
        except (Refused, OSError) as error:
            one, why = {}, str(error).removeprefix("refused: ")
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            one, why = {}, f"the send failed ({type(error).__name__})"
        if one.get("sent_at"):
            return f"It went to the home's thread, {one['thread']}."
        why = jbus.redact(why, hidden) or "it was not sent"
        return f"The line is recorded and not yet sent, since {why}: the next pass sends it."

    def _steered(self, name: str, status: int, id: str, say: str, now: datetime) -> Answer:
        """What a steer's answer says: the sentence, and the item as the record has it now."""
        now_is = item.items(self.sources.state(name)).get(id)
        answer = {
            "at": state.iso(now),
            "item": id,
            "say": say,
            "state": str(now_is.state) if now_is else None,
            "last_event": now_is.last_event if now_is else None,
        }
        return said(status, clean(answer, (state.repo(self.sources, name),)))
