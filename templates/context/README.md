# Context pack

A context pack is what a home needs to know about one repo that the code does not say at a glance: its background, its history, how it works. It is a folder that a home reads, not a thread that answers. Copy this folder to `docs/context/` in the repo it is about and fill it in.

- **One copy.** The pack lives in the repo it describes, at `docs/context/`, and changes only by a pull request there. No pack text is copied into jstack, into a home's `notes.md` or into `standing.md`.
- **Who writes it.** The subject repo's home, through a scout or a crewmate on a brief. Whoever writes a note, `jpack verify` checks it, with no model.
- **What it holds.** `sources.md`, each source pinned to a commit or a date.
  `INDEX.md`, the light layer: one line per note, at most 40.
  `notes/`, one note a question, in the four parts of `features/expert/templates/expert-answer.md`, its question as its title.
- **A claim cites its line.** Each source of a note is written `` `path:line` at <sha> ``, with the words the note rests on in double quotes after it, as `` `src/app.py:12` at `3f9c2ab`: "retries three times" ``. A source that is no file of the repo (a doc, a link, a command run) names the date it was read.

## Checks

Run them from the subject repo's checkout. Each prints one line per fault and exits 1, or prints nothing and exits 0.

```sh
jpack lint docs/context
jpack verify docs/context
jpack stale docs/context
```

`lint`: every note has a line in `INDEX.md`, lists a source, and each source names a revision. `verify`: each cited commit has the path, the path has the line, and the line says the quoted words. `stale`: each note citing a path that changed since its pin is listed `stale`, and one stale for more than 14 days `prune`. jbus runs `stale` once a day and logs what it finds. A stale note is rechecked, and its pin moved, or it is removed, by a pull request here.

## When layers disagree

A home reads the layers in this order, and the one that comes first wins:

1. The user's word and the home's `standing.md`.
2. The home's `notes.md`.
3. The source at its current revision.
4. This pack.
5. The model's memory, always labelled "from memory, not checked".

A pack line that a layer above it contradicts is reported to the subject repo's home, not acted on.
