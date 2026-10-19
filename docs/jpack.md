# jpack

`jpack` checks a context pack with no model: what a pack is, where it lives and who writes it is in [context.md](context.md). Run it from the checkout of the repo the pack is about. It writes nothing.

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

Each prints one line per thing it found and exits 1, prints nothing and exits 0 for a pack in order, and exits 2 for a folder with no `notes/` or a pack in no git checkout.
