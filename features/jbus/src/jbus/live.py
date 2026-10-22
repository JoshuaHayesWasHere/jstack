"""Say whether a thread that is out is alive, in one word worked out from what T3 Code says
of it.

`judge` does all of the work. It reads no clock and no file: the pass gives it the thread's
status, the minutes since the thread last wrote an item, how many runs are queued behind
the one that is active, how many requests wait for an answer, and
whether the thread holds a page that still waits on the user.

The word is one of `LIVENESS`:

- `moving`: a turn is under way and wrote something within `QUIET_MINUTES`;
- `quiet`: a turn is under way and has written nothing for `QUIET_MINUTES`;
- `hung`: it has written nothing for `HUNG_MINUTES`, or for `QUIET_MINUTES` while a run is
  queued behind it. A long run that is still working has no wake waiting behind it;
- `waiting`: the thread waits on a request, or is silent while a request or a page waits on
  the user. That is never a hang;
- `ended`: no turn is under way;
- `unknown`: no rule above matches the facts given. It is never `moving`. `judge` returns
  the facts with the word, so a case nobody foresaw is reported as it is.
"""

from __future__ import annotations

from dataclasses import dataclass

QUIET_MINUTES = 10
HUNG_MINUTES = 20
LIVENESS = ("moving", "quiet", "hung", "waiting", "ended", "unknown")
OUT = ("moving", "quiet", "hung", "waiting", "unknown")
TURNING = ("preparing", "queued", "starting", "running")
OVER = ("completed", "failed", "interrupted", "cancelled", "rolled_back", "idle")


@dataclass(frozen=True)
class Facts:
    """A `Facts` holds what a pass knows of one thread. `silent` is None where the pass does not
    know the thread's last write."""

    status: str
    silent: float | None
    queued: int = 0
    pending: int = 0
    page: bool = False


@dataclass(frozen=True)
class Liveness:
    word: str
    facts: Facts


def judge(facts: Facts) -> Liveness:
    return Liveness(_word(facts), facts)


def _word(facts: Facts) -> str:
    if facts.status in OVER:
        return "ended"
    if facts.status == "waiting":
        return "waiting"
    if facts.status not in TURNING or facts.silent is None:
        return "unknown"
    if facts.silent < QUIET_MINUTES:
        return "moving"
    if facts.page or facts.pending:
        return "waiting"
    if facts.queued or facts.silent >= HUNG_MINUTES:
        return "hung"
    return "quiet"
