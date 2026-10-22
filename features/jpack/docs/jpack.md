# jpack

`jpack` checks a repo's context pack, the notes a home reads about that repo at its start, so that a note never cites a line that is not there or quotes words the line does not hold.
It calls no model and writes nothing.
[Context packs](context.md) says what a pack is, where it lives and who writes it.

## Check a pack

1. Go to the checkout of the repo the pack is about.
2. Run `jpack lint docs/context`, then `jpack verify docs/context`.
3. Fix each line they print in the note it names, by a pull request to the pack.
4. To find the notes that cite a file changed since their pin, run `jpack stale docs/context`.

## The verbs

| Verb | What it does |
|---|---|
| `jpack lint <pack>` | Every note in `notes/` has a line in the index, lists a source, and each source names a revision. A pack's `INDEX.md` is at most 40 lines that are not blank. |
| `jpack verify <pack>` | Each citation `` `path:line` at <sha> `` is there: the commit, the path at it, the line, and the quoted words on the line. A citation that quotes no words is named, and so is a source that names a commit and cites no line. |
| `jpack stale <pack>` | Each note citing a path changed since its commit, as `stale <note>: <path> changed since <sha>`, and `prune <note>` for one stale more than 14 days. |

| Flag | What it does |
|---|---|
| `jpack verify --repo <checkout>`, `jpack stale --repo <checkout>` | Reads that checkout in place of the one the pack is in. |
| `jpack stale --rev <rev>` | Reads `<rev>` as now, in place of `HEAD`. |
| `jpack stale --days <n>` | Days a note is stale before it is listed `prune` (14). |

Each verb prints one line for each fault it finds and exits 1.
For a pack in order it prints nothing and exits 0.
It exits 2 for a folder with no `notes/` or a pack in no git checkout.
