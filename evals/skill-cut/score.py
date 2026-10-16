"""The blind scorer of the skill-cut eval: an answer's text and its case's key in, a score out.

It reads the text of one answer and the key of the case it answers, and nothing else: not the
file name, not the arm or the revision that wrote it. No model reads anything. The keys were
committed in `cases/` before the first run.

- `lead`: the answer buckets each of the readers' findings in a `BUCKETS` block, one line per
  id (`A1: Act on`). A finding scores 1 when the answer sends it (Act on, Consider) and the
  shipped review sent it, or holds it back (Noted, Dismissed) and the shipped review held it
  back. A finding the shipped review dropped as outside the diff is not scored. The score is
  the mean over the scored findings. A scored finding the answer gives no bucket the scorer
  can read is unsettled, and only then does the eval ask a judge.
- `steps`: 1 when every `must` expression of the case matches the answer, else 0. When one
  fails while the case's `near` expression matches, the answer is unsettled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BUCKETS = ("act on", "consider", "noted", "dismissed")
SENT = frozenset({"act on", "consider"})

# One line of the BUCKETS block: an id, a separator, a bucket. Markdown around either is allowed.
_LINE = re.compile(
    r"^[\s>*_`-]*([AB]\d+)[*_`]*\s*(?::|=|-|\u2013|\u2014)\s*[*_`]*"
    r"(act on|consider|noted|dismissed)\b",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class Score:
    """A score in [0, 1], or None while `unsettled` names what the key cannot settle."""

    value: float | None
    unsettled: list[str] = field(default_factory=list)
    detail: dict[str, object] = field(default_factory=dict)


def buckets(text: str) -> dict[str, str]:
    """The bucket the answer gives each id, from its last `BUCKETS` block, or from the whole
    answer when it has none. A later line for the same id wins."""
    marks = [m.end() for m in re.finditer(r"^\W*BUCKETS\W*$", text, re.MULTILINE)]
    tail = text[marks[-1] :] if marks else text
    return {m[1].upper(): m[2].lower() for m in _LINE.finditer(tail)}


def held(fate: str) -> bool | None:
    """Whether the shipped review held the finding back, or None when it is not scored."""
    return {"sent": False, "noted": True, "dismissed": True}.get(fate)


def score_lead(text: str, key: dict[str, dict], given: dict[str, str] | None = None) -> Score:
    """Score a lead answer against the case's key. `given` holds buckets the judge read out of
    this answer for ids the scorer could not read: they fill gaps and never override a line."""
    said = {**{k: v for k, v in (given or {}).items() if v in BUCKETS}, **buckets(text)}
    scored = {fid: entry for fid, entry in key.items() if held(entry["fate"]) is not None}
    missing = sorted(fid for fid in scored if fid not in said)
    if missing and not (given is not None and all(fid in given for fid in missing)):
        return Score(None, missing)
    hits, agree3, fixed_sent, fixed = 0, 0, 0, 0
    for fid, entry in scored.items():
        bucket = said.get(fid)
        sent = bucket in SENT
        hits += sent != held(entry["fate"])
        three = "sent" if sent else bucket
        agree3 += three == entry["fate"]
        if entry.get("fixed"):
            fixed += 1
            fixed_sent += sent
    n = len(scored)
    return Score(
        hits / n,
        detail={
            "findings": n,
            "three_way": agree3 / n,
            "fixed": fixed,
            "fixed_sent": fixed_sent,
            "sent": sum(said.get(fid) in SENT for fid in scored),
        },
    )


def score_steps(text: str, case: dict, judged: bool | None = None) -> Score:
    """Score a steps answer against the case's expressions. `judged` is the judge's word on an
    answer the expressions could not settle."""
    if all(re.search(must, text) for must in case["must"]):
        return Score(1.0)
    if case.get("near") and re.search(case["near"], text):
        if judged is None:
            return Score(None, [case["id"]])
        return Score(float(judged), detail={"judged": True})
    return Score(0.0)
