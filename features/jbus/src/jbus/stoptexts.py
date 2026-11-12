"""The words of `jbus stop` and `jbus tell`: each stop's message to the root by its kind, the root's
answer, tell and pass to the scope, the user's answer carried to the scope, and the lines of the
gate a passed stop parks for the user (`gate`). `jbus.stop` keeps the records and sends these."""

PASSED = "the root passed it to you"
"""What the gate of a passed stop holds for: no door of the table, but the user's own word."""
SAFE = "nothing is done on it until you answer"

ASKS = (
    "jbus: the {scope} home is stopped at a one-way door, {holds}. Its row {row} is held by "
    "{held}, and it cannot clear that itself. What the root must clear: {what}\n\n"
    "Scout if you need facts, then answer the stop with your recommendation, once, with "
    '`jbus stop answer {scope} {row} "<your recommendation>" --from <this home\'s id>`: jbus '
    "carries it to the {scope} home, which adds it to its own gate for the door. The root writes "
    "nothing into the {scope} home's files, and the user alone opens or refuses the door. A stop "
    "whose row merges or is removed closes itself."
)
ESCALATES = (
    "jbus: the {scope} home escalates a {kind} on {subject}: {what}\n\n"
    "{give}Answer it once, when it is within the user's standing word and the {scope} home's goal, "
    'with `jbus stop answer {scope} {slug} "<your word>" --from <this home\'s id>`: jbus carries '
    "it to the {scope} home, which acts on it. When it is the user's, pass it with `jbus stop pass "
    '{scope} {slug} "<your recommendation>" --from <this home\'s id>`: jbus parks a gate on '
    "home-{scope} that holds for the user's own answer, and carries that answer to the {scope} "
    "home. A stop whose row ends, or whose entry leaves the plan, closes itself."
)
GIVE = (
    "Where the user's standing word for goes covers it, give the go first with `jbus plan go "
    "{entry} --scope {scope} --standing --from <this home's id>`. "
)
ANSWERS = (
    "jbus: the root home's answer to the {scope} home's stop on {row}: {answer}\n\n"
    "Add it, as the root's recommendation, to your own gate for the door: the user alone opens or "
    "refuses the door."
)
TELLS = (
    "jbus: the root home's own message to the {scope} home, written by the root and not the "
    "user's word: {text}\n\n"
    "Take it as the root's steer. It is no go for any row, gate or door, and where it differs "
    "from the user's word, the user's word stands. Nothing is sent back for it."
)
WORD = (
    "jbus: the root home's answer to the {scope} home's {kind} on {subject}: {answer}\n\n"
    "It is the root's word, given within the user's standing word: act on it."
)
PASSES = (
    "jbus: the root home passed the {scope} home's {kind} on {subject} to the user, as question "
    "{number}, which holds for the user's own answer{said}. Do nothing on it until then: jbus "
    "carries the user's answer here."
)
USERS = (
    'jbus: the user answered question {number}, the {scope} home\'s {kind} on {subject}: "{words}"'
    "\n\nIt is the user's own word: act on it."
)
DIRECT = (
    "a door stop carries only a one-way door, --holds '<case>' with a case of "
    "features/home/templates/gates.md ({cases}): any other choice this home may not make alone "
    "goes to the root as --kind decision, and a go it may not give as --kind go"
)
GATE = """## Gate <n>: {what}
Status: open
Asked by: home-{scope}, thread {thread}
Default: {default}
Built on it: nothing: the {scope} home waits on {subject} for your answer
Undo: nothing to undo, since nothing is done on it
Context: the {scope} home escalated this {kind} on {subject} to the root home, which passed it to \
you{said}
Option: {option} (default, recommended): {default}
Option: your own: your words, which jbus carries to the {scope} home
"""


def gate(what: str, kind: str, slug: str, subject: str, scope: str, thread: str, text: str) -> str:
    """The lines of the gate a passed stop parks for the user, with the root's recommendation
    `text`, or none: the stop's `what`, `kind`, row or entry `slug` and `subject` in words, of the
    home `scope` whose thread is `thread`."""
    default = f"the root recommends: {text}; {SAFE}" if text else SAFE
    return GATE.format(
        what=f"{what} ({kind} on {slug}, from the {scope} home)",
        scope=scope,
        thread=thread or "none",
        default=default,
        subject=subject,
        kind=kind,
        said=f", and recommends: {text}" if text else "",
        option="the root's" if text else "wait",
    )
