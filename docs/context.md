# Context packs

A context pack is what a home needs to know about one repo that the code does not say at a glance: its background, its history, how it works. It is a folder that a home reads at its start, never a thread that answers. The skeleton is `templates/context/`.

## Where a pack lives

A pack has one copy, in the repo it is about, at `<repo>/docs/context/`, and it changes only by a pull request there. No pack text is copied into jstack, into a home's `notes.md`, or into `standing.md`. That keeps a citation to the repo's commits checked beside that repo, and lets the repo's home change its own pack by its own pull requests.

| File | Holds |
|---|---|
| `<repo>/docs/context/sources.md` | Each source, a repo or a doc, pinned to a commit or a date. |
| `<repo>/docs/context/INDEX.md` | The light layer: one line per note, `` `<note>.md`: <what it answers> (checked at <rev>) ``, at most 40 lines that are not blank. |
| `<repo>/docs/context/notes/<note>.md` | One question, as its title, answered in the four parts of `features/expert/templates/expert-answer.md`: Answer, Sources, Confidence, Not checked. |

A source in a note cites its line: `` `path:line` at <sha> ``, or `` `path:first-last` at <sha> ``, with the words the note rests on in double quotes after it. A source that is no file of the repo names the date it was read.

## Who writes it

The subject repo's home, through a scout or a crewmate on a brief that starts from `templates/context/`. jstack writes no repo's pack, and jbus edits none.

## How a home reads it

The home skill's start ("See where things stand") prints `read whole: <checkout>/docs/context/INDEX.md` after `standing.md` and the handoff, when the file is there. The home reads the index whole and opens a note only when a step needs it. When what it knows disagrees, the first in this order wins:

1. The user's word and `standing.md`.
2. The home's `notes.md`.
3. The source at its current revision.
4. The pack.
5. The model's memory, always labelled "from memory, not checked".

A pack line that a layer above it contradicts is reported, not acted on, and its fix is a pull request to the pack.

## How it is verified

`jpack` checks a pack with no model. Run it from the subject repo's checkout, or name the checkout with `--repo`. Each verb prints one line per fault and exits 1, prints nothing and exits 0 for a pack in order, and exits 2 for a folder or a repo it cannot read.

- `jpack lint <repo>/docs/context`: every note has a line in `INDEX.md`, lists at least one source, and each source names a revision. The index is at most 40 lines that are not blank. It is the same lint an expert's folder uses, one shell copy at `src/jpack/lint-notes.sh`.
- `jpack verify <repo>/docs/context`: for each citation, the commit is in the repo, the path is in the commit, the file has the cited lines, and the quoted words are on them, with white space read as one space. A citation that quotes no words is a fault. A source that names a commit and cites no `path:line` at it is a fault too, since nothing could check it. It is the outside check on whatever scout or crewmate wrote the notes. A shallow checkout says so where a cited commit is not in it.

## How it is pruned

`jpack stale <repo>/docs/context` lists `stale <note>: <path> changed since <sha>` for each cited path that differs between the citation's commit and `HEAD` (`--rev` names another revision). A note stale for more than 14 days (`--days`) is also listed `prune <note>`. A note is stale since the first commit after its pin that changed a path it cites, by that commit's committer date, which on a squash merge is when the change landed. Nothing is kept between runs: rechecking a note moves its pin, and its days start again from the next change.

jbus runs the stale check once a day for each project whose main checkout has `<repo>/docs/context/notes/`, against the checkout's `origin/HEAD` (its `HEAD` where that is not known), and logs what it found as one quiet event, `pack`: `jbus events` prints it, and nobody is posted. A pack with nothing stale logs nothing. The home rechecks a stale note, or removes a note to prune, by a pull request to the pack.
