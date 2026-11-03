# Context packs

A context pack is what a home needs to know about one repo that the code does not say at a glance: its background, its history, how it works.
It is a folder that a home reads at its start, never a thread that answers.
The skeleton is `features/jpack/templates/context/`.

## Where a pack lives

A pack has one copy, in the repo it is about, at `<repo>/docs/context/`, and it changes only by a pull request there.
No pack text is copied into jstack or into a home's state.
That keeps a citation to the repo's commits checked beside that repo, and lets the repo's home change its own pack by its own pull requests.

| File | Holds |
|---|---|
| `<repo>/docs/context/sources.md` | Each source, a repo or a doc, pinned to a commit or a date. |
| `<repo>/docs/context/INDEX.md` | The light layer: one line per note, `` `<note>.md`: <what it answers> (checked at <rev>) ``, at most 40 lines that are not blank. |
| `<repo>/docs/context/notes/<note>.md` | One question, as its title, answered in the four parts of `features/expert/templates/expert-answer.md`: Answer, Sources, Confidence, Not checked. |

A source in a note cites its line: `` `path:line` at <sha> ``, or `` `path:first-last` at <sha> ``, with the words the note rests on in double quotes after it. A source that is no file of the repo names the date it was read.

## Who writes it

The subject repo's home, through a scout or a crewmate on a brief that starts from `features/jpack/templates/context/`.
jstack writes no repo's pack, and jbus edits none.

## How a home reads it

The home skill's start ("See where things stand") prints `read whole: <checkout>/docs/context/INDEX.md` after the files it reads whole, when the file is there.
The home reads the index whole and opens a note only when a step needs it.
When what it knows disagrees, the first in this order wins:

1. The user's word, and a standing rule of the user's, which is code, a skill step's text or a queued row.
2. The source at its current revision.
3. The pack.
4. The model's memory, always labelled "from memory, not checked".

A pack line that a layer above it contradicts is reported, not acted on, and its fix is a pull request to the pack.

## How it is checked and pruned

`jpack` checks a pack with no model, and [jpack](jpack.md) has its verbs: `jpack lint`, `jpack verify` and `jpack stale`.
`jpack verify` is the outside check on whatever scout or crewmate wrote the notes.

jbus runs `jpack stale` once a day for each project whose main checkout has `<repo>/docs/context/notes/`.
It runs it against the checkout's `origin/HEAD`, or its `HEAD` where that is not known.
It logs what it found as one quiet event, `pack`, which `jbus events` prints, and it posts to nobody.
A pack with nothing stale logs nothing.
The home rechecks a stale note, or removes a note to prune, by a pull request to the pack.
